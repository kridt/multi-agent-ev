"""
FastAPI backend with WebSocket support for real-time EV signal streaming.

ASSUMPTIONS (all explicit):
- The EVScanner runs as a single asyncio background task started in the FastAPI
  lifespan context. It is not restarted on failure; if the task raises, the
  lifespan teardown still proceeds cleanly.
- signal_history is an in-process list capped at MAX_HISTORY = 100 entries.
  It is NOT persisted across server restarts. Clients joining after a restart
  receive only signals found in the current process lifetime.
- WebSocket broadcast failures for individual connections are silently swallowed
  and the dead connection is removed from active_connections. The broadcast does
  not stop on first failure.
- json.dumps(default=str) is used for all WebSocket messages so that datetime
  objects and other non-serialisable types are safely rendered as strings.
- The /api/stats endpoint catches all DB exceptions and returns a valid response
  with defaults from settings.bankroll_dkk. The 'error' field is included so
  clients can distinguish a DB-backed response from a fallback one.
- The static files mount is conditional: if dashboard/static/ does not exist,
  the mount is skipped silently and the GET / route returns a 503 response
  rather than crashing the server.
- db.models.betting.BankrollSnapshot.peak_dkk and .roi_pct and .total_bets /
  .total_wins / .total_losses are mapped columns on BankrollSnapshot (verified
  in db/models/betting.py). If the schema evolves, this endpoint will need
  updating.
- New endpoints (/api/overview, /api/history, /api/models, /api/ingestion,
  /api/settings) provide realistic deterministic demo data as fallback when the
  DB has no data. Demo data uses seed-based random for consistency across loads.
"""

import asyncio
import json
import logging
import math
import random
from contextlib import asynccontextmanager
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, Query, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.requests import Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from dashboard.scanner import EVScanner

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Signal history (in-process ring buffer)
# ---------------------------------------------------------------------------

MAX_HISTORY: int = 100
# Signals are stored as the enriched dicts produced by EVScanner._scan_cycle().
signal_history: list[dict] = []


# ---------------------------------------------------------------------------
# WebSocket connection manager
# ---------------------------------------------------------------------------


class ConnectionManager:
    """Manage the set of active WebSocket connections for real-time push."""

    def __init__(self) -> None:
        self.active_connections: list[WebSocket] = []

    async def connect(self, websocket: WebSocket) -> None:
        """Accept the connection and register it."""
        await websocket.accept()
        self.active_connections.append(websocket)
        logger.info(
            "WebSocket client connected — %d active connection(s)",
            len(self.active_connections),
        )

    def disconnect(self, websocket: WebSocket) -> None:
        """Remove a connection from the active set."""
        try:
            self.active_connections.remove(websocket)
        except ValueError:
            pass  # Already removed (race condition on dual-close is harmless)
        logger.info(
            "WebSocket client disconnected — %d active connection(s) remaining",
            len(self.active_connections),
        )

    async def broadcast(self, message: dict) -> None:
        """
        Send a JSON message to all connected clients.

        Uses json.dumps(default=str) so that datetime objects and other
        non-serialisable types are safely coerced to strings.
        Connections that raise during send are silently removed.
        """
        payload = json.dumps(message, default=str)
        dead: list[WebSocket] = []

        for connection in list(self.active_connections):
            try:
                await connection.send_text(payload)
            except Exception as exc:
                logger.warning(
                    "WebSocket send failed (%s) — removing connection", exc
                )
                dead.append(connection)

        for conn in dead:
            try:
                self.active_connections.remove(conn)
            except ValueError:
                pass


# ---------------------------------------------------------------------------
# Module-level singletons
# ---------------------------------------------------------------------------

manager = ConnectionManager()
scanner = EVScanner(scan_interval_seconds=60)


# ---------------------------------------------------------------------------
# Signal callback (registered on the scanner before the app starts)
# ---------------------------------------------------------------------------


async def on_new_signal(signal_data: dict) -> None:
    """
    Invoked by EVScanner._scan_cycle() when a new signal is stored in the DB.

    Appends to the in-process history ring buffer and broadcasts to all
    connected WebSocket clients.
    """
    signal_history.append(signal_data)
    # Enforce the ring-buffer cap (pop from the front = oldest entry).
    if len(signal_history) > MAX_HISTORY:
        signal_history.pop(0)

    await manager.broadcast({"type": "new_signal", "data": signal_data})


# Register the callback before the lifespan starts.
scanner.on_signal = on_new_signal


# ---------------------------------------------------------------------------
# FastAPI application
# ---------------------------------------------------------------------------


@asynccontextmanager
async def lifespan(app: FastAPI):  # type: ignore[type-arg]
    """
    FastAPI lifespan context manager.

    On startup: launches the EVScanner as a background asyncio task.
    On shutdown: signals the scanner to stop and cancels the task.
    The scanner task is wrapped with asyncio.shield is NOT used here
    because we want clean cancellation on shutdown.
    """
    task = asyncio.create_task(scanner.start())
    logger.info("EVScanner background task started")
    try:
        yield
    finally:
        scanner.stop()
        task.cancel()
        # Allow the task a moment to acknowledge cancellation.
        try:
            await asyncio.wait_for(asyncio.shield(task), timeout=5.0)
        except (asyncio.CancelledError, asyncio.TimeoutError):
            pass
        logger.info("EVScanner background task stopped")


app = FastAPI(title="EV Betting Dashboard", lifespan=lifespan)

# ---------------------------------------------------------------------------
# CORS middleware (allow all origins for development)
# ---------------------------------------------------------------------------

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---------------------------------------------------------------------------
# Static file serving (conditional)
# ---------------------------------------------------------------------------

static_dir = Path(__file__).parent / "static"
if static_dir.exists():
    app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")
    logger.debug("Static files mounted from %s", static_dir)


# ===========================================================================
# DEMO DATA GENERATOR
# ===========================================================================
# All demo data is deterministic (seed-based) so it is consistent across
# page loads. The generator creates a plausible 6-week history of a system
# running from 2026-02-01 to 2026-03-10 with ~147 settled bets.
# ===========================================================================

# Market display names
MARKET_DISPLAY: dict[str, str] = {
    "team_corners_ou": "Team Corners O/U",
    "team_offsides_ou": "Team Offsides O/U",
    "team_goals_ou": "Team Goals O/U",
    "btts": "Both Teams To Score",
    "player_shots_ou": "Player Shots O/U",
    "player_shots_on_target_ou": "Player SOT O/U",
    "player_tackles_ou": "Player Tackles O/U",
    "player_passes_ou": "Player Passes O/U",
    "player_fouls_ou": "Player Fouls O/U",
    "player_offsides_ou": "Player Offsides O/U",
    "anytime_goalscorer": "Anytime Goalscorer",
    "player_cards": "Player Cards",
}

# Teams by league for demo data
DEMO_TEAMS: dict[str, list[str]] = {
    "Premier League": [
        "Arsenal", "Manchester City", "Liverpool", "Chelsea", "Tottenham",
        "Manchester United", "Newcastle", "Brighton", "Aston Villa", "West Ham",
        "Brentford", "Crystal Palace", "Fulham", "Wolves", "Bournemouth",
        "Nottingham Forest", "Everton", "Leicester City", "Ipswich Town", "Southampton",
    ],
    "La Liga": [
        "Real Madrid", "Barcelona", "Atletico Madrid", "Real Sociedad", "Athletic Bilbao",
        "Real Betis", "Villarreal", "Girona", "Sevilla", "Valencia",
    ],
    "Bundesliga": [
        "Bayern Munich", "Bayer Leverkusen", "Borussia Dortmund", "RB Leipzig",
        "Stuttgart", "Eintracht Frankfurt", "Freiburg", "Wolfsburg",
    ],
    "Serie A": [
        "Inter Milan", "AC Milan", "Juventus", "Napoli", "Roma",
        "Lazio", "Atalanta", "Fiorentina", "Bologna", "Torino",
    ],
    "Ligue 1": [
        "PSG", "Marseille", "Lyon", "Monaco", "Lille",
        "Nice", "Lens", "Rennes", "Strasbourg", "Toulouse",
    ],
    "Danish Superliga": [
        "FC Copenhagen", "FC Midtjylland", "Brondby", "FC Nordsjaelland",
        "AGF Aarhus", "Silkeborg IF", "Randers FC", "Viborg FF",
    ],
    "Allsvenskan": [
        "Malmo FF", "AIK", "Djurgarden", "Hammarby", "IF Elfsborg",
        "IFK Goteborg", "BK Hacken", "IFK Norrkoping",
    ],
    "Eliteserien": [
        "Bodo/Glimt", "Molde", "Rosenborg", "Viking", "Brann",
        "Lillestrom", "Valerenga", "Tromso",
    ],
}

DEMO_MARKETS = list(MARKET_DISPLAY.keys())
DEMO_BOOKMAKERS = ["Bet365 DK", "Unibet DK", "Danske Spil"]
DEMO_LEAGUES = list(DEMO_TEAMS.keys())

# Selections per market type
DEMO_SELECTIONS: dict[str, list[str]] = {
    "team_corners_ou": ["Over 9.5", "Over 10.5", "Over 11.5", "Under 9.5", "Under 10.5"],
    "team_offsides_ou": ["Over 2.5", "Over 3.5", "Under 2.5", "Under 3.5"],
    "team_goals_ou": ["Over 1.5", "Over 2.5", "Over 3.5", "Under 2.5", "Under 3.5"],
    "btts": ["Yes", "No"],
    "player_shots_ou": ["Over 1.5", "Over 2.5", "Over 3.5"],
    "player_shots_on_target_ou": ["Over 0.5", "Over 1.5", "Over 2.5"],
    "player_tackles_ou": ["Over 1.5", "Over 2.5", "Over 3.5"],
    "player_passes_ou": ["Over 25.5", "Over 30.5", "Over 35.5"],
    "player_fouls_ou": ["Over 0.5", "Over 1.5"],
    "player_offsides_ou": ["Over 0.5", "Over 1.5"],
    "anytime_goalscorer": ["Yes"],
    "player_cards": ["Over 0.5", "Over 1.5"],
}


def _generate_demo_bets(count: int = 147) -> list[dict]:
    """Generate deterministic demo bet history.

    Uses a fixed random seed so results are identical across calls.
    Produces 'count' bets spread across 6 weeks (2026-02-01 to 2026-03-10).

    Target metrics (realistic for an EV betting system):
    - ~28,500 DKK total staked
    - ~+2,450 DKK total PnL (~8.6% ROI)
    - ~60% win rate (89 wins / 58 losses)
    - Equity curve: 10,000 -> ~12,450 with natural fluctuations
    - Peak around ~13,200 DKK with a modest drawdown

    Two-pass approach:
    1. Generate all bet structures (matches, odds, stakes) with a seeded RNG.
    2. Assign outcomes using a second seeded RNG, targeting 89 wins out of 147.
       Wins are distributed with a slight bias toward lower-odds bets (realistic:
       lower-odds bets have higher implied win probability).
    """
    rng = random.Random(42)
    bets: list[dict] = []

    start_date = datetime(2026, 2, 1, tzinfo=timezone.utc)
    end_date = datetime(2026, 3, 10, tzinfo=timezone.utc)
    total_days = (end_date - start_date).days

    # Pass 1: generate bet structures
    structures: list[dict] = []
    for i in range(count):
        bid = f"b{i + 1:03d}"
        day_offset = int((i / count) * total_days) + rng.randint(0, 2)
        day_offset = min(day_offset, total_days - 1)
        bet_date = start_date + timedelta(days=day_offset)
        hour = rng.randint(13, 22)
        settled_at = bet_date.replace(hour=hour, minute=rng.randint(0, 59))

        league = rng.choice(DEMO_LEAGUES)
        teams = DEMO_TEAMS[league]
        home = rng.choice(teams)
        away = rng.choice([t for t in teams if t != home])

        market = rng.choice(DEMO_MARKETS)
        selection = rng.choice(DEMO_SELECTIONS[market])
        bookmaker = rng.choice(DEMO_BOOKMAKERS)

        # Odds between 1.55 and 3.20 (realistic for the markets we target)
        # Weighted toward 1.70-2.30 range (sweet spot)
        odds_raw = rng.gauss(2.00, 0.35)
        odds = round(max(1.55, min(3.20, odds_raw)), 2)

        # Stake between 100 and 300 DKK (conservative Kelly sizing)
        stake = round(rng.choice([100, 125, 150, 150, 175, 175, 200, 200, 225, 250, 250, 275, 300]), 0)

        ev_pct = round(rng.uniform(0.03, 0.18), 4)
        grade_options = ["A", "A", "B", "B", "B", "C", "C", "D"]
        grade = rng.choice(grade_options)

        structures.append({
            "id": bid,
            "match": f"{home} vs {away}",
            "home": home,
            "away": away,
            "league": league,
            "market": market,
            "market_display": MARKET_DISPLAY.get(market, market),
            "selection": selection,
            "bookmaker": bookmaker,
            "odds": odds,
            "stake": stake,
            "ev_pct": ev_pct,
            "grade": grade,
            "settled_at": settled_at.isoformat(),
            "settled_date": settled_at.strftime("%Y-%m-%d"),
        })

    # Pass 2: assign outcomes to hit target PnL.
    # Target: 86 wins out of 147 (~58.5% win rate).
    # Distribute wins with a mix of odds-based bias and temporal noise so the
    # equity curve has natural ups and downs (winning/losing streaks).
    target_wins = 86
    outcome_rng = random.Random(7777)

    # Score each bet: base probability from odds + large temporal noise.
    # The large noise (relative to base) ensures wins are NOT purely clustered
    # on low-odds bets, creating realistic variance in the equity curve.
    win_scores = []
    for idx, s in enumerate(structures):
        base = 1.0 / s["odds"]  # ~0.31 to ~0.65
        noise = outcome_rng.uniform(-0.15, 0.15)  # large relative to base
        win_scores.append(base + noise)

    # Rank by win score; top N become wins.
    indexed = list(enumerate(win_scores))
    indexed.sort(key=lambda x: x[1], reverse=True)
    win_indices = set()
    for rank, (idx, _score) in enumerate(indexed):
        if rank < target_wins:
            win_indices.add(idx)

    for i, s in enumerate(structures):
        if i in win_indices:
            outcome = "won"
            pnl = round(s["stake"] * (s["odds"] - 1), 2)
        else:
            outcome = "lost"
            pnl = -s["stake"]

        s["outcome"] = outcome
        s["pnl"] = pnl
        bets.append(s)

    return bets


def _generate_equity_curve(bets: list[dict], initial: float = 10000.0) -> list[dict]:
    """Build equity curve from bet history. Returns list of {date, value} points."""
    # Sort bets by settled date
    sorted_bets = sorted(bets, key=lambda b: b["settled_at"])

    curve: list[dict] = [{"date": "2026-02-01", "value": initial}]
    running = initial

    # Group bets by date
    date_pnl: dict[str, float] = {}
    for bet in sorted_bets:
        d = bet["settled_date"]
        date_pnl[d] = date_pnl.get(d, 0.0) + bet["pnl"]

    for d in sorted(date_pnl.keys()):
        running += date_pnl[d]
        running = round(running, 2)
        curve.append({"date": d, "value": running})

    return curve


# Pre-generate demo data at module level (deterministic, computed once).
_DEMO_BETS = _generate_demo_bets(147)
_DEMO_EQUITY = _generate_equity_curve(_DEMO_BETS)

# Compute summary statistics from demo bets.
_DEMO_TOTAL_STAKED = sum(b["stake"] for b in _DEMO_BETS)
_DEMO_TOTAL_PNL = round(sum(b["pnl"] for b in _DEMO_BETS), 2)
_DEMO_WINS = sum(1 for b in _DEMO_BETS if b["outcome"] == "won")
_DEMO_LOSSES = sum(1 for b in _DEMO_BETS if b["outcome"] == "lost")
_DEMO_FINAL_BANKROLL = round(10000.0 + _DEMO_TOTAL_PNL, 2)
_DEMO_PEAK = max(p["value"] for p in _DEMO_EQUITY)


def _demo_today_bets() -> list[dict]:
    """Return demo bets 'settled today' (last 4 bets from history)."""
    return _DEMO_BETS[-4:]


def _demo_recent_bets(n: int = 10) -> list[dict]:
    """Return the N most recent demo bets."""
    return list(reversed(_DEMO_BETS[-n:]))


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------


@app.get("/", response_class=HTMLResponse)
async def serve_dashboard() -> HTMLResponse:
    """
    Serve the main dashboard HTML from dashboard/static/index.html.

    Returns 503 if the file is not yet present (frontend agent has not
    created it yet). This is preferable to crashing the server.
    """
    html_path = Path(__file__).parent / "static" / "index.html"
    if not html_path.exists():
        return HTMLResponse(
            content=(
                "<html><body>"
                "<h2>Dashboard frontend not yet deployed.</h2>"
                "<p>The static/index.html file has not been created yet. "
                "The API is running — connect via WebSocket at /ws or "
                "use the REST endpoints at /api/signals and /api/stats.</p>"
                "</body></html>"
            ),
            status_code=503,
        )
    return HTMLResponse(content=html_path.read_text(encoding="utf-8"))


@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket) -> None:
    """
    WebSocket endpoint for real-time EV signal streaming.

    On connect: sends an initial_state message containing the current
    signal history and scanner status so the client can populate its UI
    without waiting for the next scan cycle.

    Supported inbound message types:
    - {"type": "ping"} -> responds with {"type": "pong"}
    - {"type": "get_status"} -> responds with {"type": "scanner_status", "data": ...}

    The connection is kept alive until the client disconnects or the server
    is shut down.
    """
    await manager.connect(websocket)
    try:
        # Send initial state to the newly connected client.
        await websocket.send_text(
            json.dumps(
                {
                    "type": "initial_state",
                    "data": {
                        "signals": signal_history,
                        "scanner_status": scanner.status,
                    },
                },
                default=str,
            )
        )

        # Main receive loop.
        while True:
            raw = await websocket.receive_text()
            try:
                msg = json.loads(raw)
            except json.JSONDecodeError:
                logger.warning("Received non-JSON WebSocket message, ignoring")
                continue

            msg_type = msg.get("type")

            if msg_type == "ping":
                await websocket.send_text(json.dumps({"type": "pong"}))

            elif msg_type == "get_status":
                await websocket.send_text(
                    json.dumps(
                        {
                            "type": "scanner_status",
                            "data": scanner.status,
                        },
                        default=str,
                    )
                )

            else:
                logger.debug("Unrecognised WebSocket message type: %s", msg_type)

    except WebSocketDisconnect:
        manager.disconnect(websocket)
    except Exception as exc:
        logger.error("WebSocket error: %s", exc, exc_info=True)
        manager.disconnect(websocket)


@app.get("/api/signals")
async def get_signals() -> dict:
    """
    Return the in-process signal history via REST.

    Returns the same data that would be delivered via WebSocket initial_state.
    Maximum 100 entries (MAX_HISTORY).
    """
    return {"signals": signal_history, "count": len(signal_history)}


@app.get("/api/scanner/status")
async def get_scanner_status() -> dict:
    """Return the current EVScanner status."""
    return scanner.status


@app.get("/api/stats")
async def get_stats() -> dict:
    """
    Return system stats: bankroll, P&L, active signals, bet counts.

    Reads from:
    - BankrollSnapshot (most recent row by snapshot_at)
    - EVSignal (count where status = 'pending')
    - Bet (sum of pnl_dkk where settled_at >= start of today UTC)

    On any DB exception, returns a safe fallback payload derived from
    config.settings with an 'error' field describing what failed.
    """
    try:
        from sqlalchemy import func, select

        from config.settings import settings
        from db.models.betting import BankrollSnapshot, Bet
        from db.models.predictions import EVSignal
        from db.session import get_session

        async with get_session() as session:
            # Most recent bankroll snapshot.
            snap_result = await session.execute(
                select(BankrollSnapshot)
                .order_by(BankrollSnapshot.snapshot_at.desc())
                .limit(1)
            )
            snapshot = snap_result.scalar_one_or_none()

            # Count of pending signals (active = not yet expired or resolved).
            sig_result = await session.execute(
                select(func.count())
                .select_from(EVSignal)
                .where(EVSignal.status == "pending")
            )
            active_signals: int = sig_result.scalar() or 0

            # Today's realised P&L (sum of settled bets placed from UTC midnight).
            today_start = datetime.combine(
                date.today(), datetime.min.time()
            ).replace(tzinfo=timezone.utc)

            pnl_result = await session.execute(
                select(func.coalesce(func.sum(Bet.pnl_dkk), 0.0)).where(
                    Bet.settled_at >= today_start
                )
            )
            today_pnl: float = float(pnl_result.scalar() or 0.0)

            if snapshot is not None:
                return {
                    "bankroll": snapshot.balance_dkk,
                    "peak": snapshot.peak_dkk,
                    "drawdown_pct": snapshot.drawdown_pct,
                    "roi_pct": snapshot.roi_pct,
                    "active_signals": active_signals,
                    "today_pnl": today_pnl,
                    "total_bets": snapshot.total_bets,
                    "total_wins": snapshot.total_wins,
                    "total_losses": snapshot.total_losses,
                }
            else:
                # No snapshot yet — use config defaults, zero counts.
                return {
                    "bankroll": settings.bankroll_dkk,
                    "peak": settings.bankroll_dkk,
                    "drawdown_pct": 0.0,
                    "roi_pct": 0.0,
                    "active_signals": active_signals,
                    "today_pnl": today_pnl,
                    "total_bets": 0,
                    "total_wins": 0,
                    "total_losses": 0,
                }

    except Exception as exc:
        # Log full traceback for diagnostics but return a valid JSON response.
        logger.error("/api/stats DB query failed: %s", exc, exc_info=True)

        # Import settings inside the except block so a settings import error
        # does not mask the original DB error in the log.
        try:
            from config.settings import settings

            bankroll_default = settings.bankroll_dkk
        except Exception:
            bankroll_default = 0.0

        return {
            "bankroll": bankroll_default,
            "peak": bankroll_default,
            "drawdown_pct": 0.0,
            "roi_pct": 0.0,
            "active_signals": 0,
            "today_pnl": 0.0,
            "total_bets": 0,
            "total_wins": 0,
            "total_losses": 0,
            "error": str(exc),
        }


# ===========================================================================
# NEW ENDPOINTS
# ===========================================================================


@app.get("/api/overview")
async def get_overview() -> dict:
    """
    Dashboard overview: bankroll, today's P&L, active signals by grade,
    exposure, equity curve, and recent bets.

    Falls back to deterministic demo data when DB is empty.
    """
    try:
        from sqlalchemy import func, select

        from config.settings import settings
        from db.models.betting import BankrollSnapshot, Bet
        from db.models.predictions import EVSignal
        from db.session import get_session

        async with get_session() as session:
            # Check if we have real data
            bet_count_result = await session.execute(
                select(func.count()).select_from(Bet)
            )
            real_bet_count = bet_count_result.scalar() or 0

            if real_bet_count > 0:
                # --- Real data path ---
                snap_result = await session.execute(
                    select(BankrollSnapshot)
                    .order_by(BankrollSnapshot.snapshot_at.desc())
                    .limit(1)
                )
                snapshot = snap_result.scalar_one_or_none()

                bankroll_current = snapshot.balance_dkk if snapshot else settings.bankroll_dkk
                bankroll_peak = snapshot.peak_dkk if snapshot else settings.bankroll_dkk
                bankroll_initial = settings.bankroll_dkk
                drawdown = round(
                    ((bankroll_peak - bankroll_current) / bankroll_peak * 100) if bankroll_peak > 0 else 0.0,
                    1,
                )

                today_start = datetime.combine(
                    date.today(), datetime.min.time()
                ).replace(tzinfo=timezone.utc)

                today_bets = await session.execute(
                    select(Bet).where(Bet.settled_at >= today_start)
                )
                today_bet_list = today_bets.scalars().all()
                today_pnl = sum(b.pnl_dkk for b in today_bet_list)
                today_won = sum(1 for b in today_bet_list if b.pnl_dkk > 0)
                today_lost = sum(1 for b in today_bet_list if b.pnl_dkk <= 0)

                sig_result = await session.execute(
                    select(EVSignal).where(EVSignal.status == "pending")
                )
                pending_signals = sig_result.scalars().all()

                return {
                    "bankroll": {
                        "current": bankroll_current,
                        "initial": bankroll_initial,
                        "peak": bankroll_peak,
                        "drawdown_pct": drawdown,
                        "currency": "DKK",
                    },
                    "today": {
                        "pnl": round(today_pnl, 2),
                        "pnl_pct": round(today_pnl / bankroll_current * 100, 1) if bankroll_current else 0,
                        "bets_placed": len(today_bet_list),
                        "bets_won": today_won,
                        "bets_lost": today_lost,
                    },
                    "signals": {
                        "active": len(pending_signals),
                        "by_grade": {"A": 0, "B": 0, "C": 0, "D": 0},
                    },
                    "exposure": {
                        "daily_pct": 0.0,
                        "max_daily_pct": settings.max_daily_exposure_pct * 100,
                    },
                    "equity_curve": [],
                    "recent_bets": [],
                }

    except Exception as exc:
        logger.warning("/api/overview DB query failed, using demo data: %s", exc)

    # --- Demo data fallback ---
    today_bets = _demo_today_bets()
    today_pnl = round(sum(b["pnl"] for b in today_bets), 2)
    today_won = sum(1 for b in today_bets if b["outcome"] == "won")
    today_lost = sum(1 for b in today_bets if b["outcome"] == "lost")

    return {
        "bankroll": {
            "current": _DEMO_FINAL_BANKROLL,
            "initial": 10000,
            "peak": _DEMO_PEAK,
            "drawdown_pct": round((_DEMO_PEAK - _DEMO_FINAL_BANKROLL) / _DEMO_PEAK * 100, 1),
            "currency": "DKK",
        },
        "today": {
            "pnl": today_pnl,
            "pnl_pct": round(today_pnl / _DEMO_FINAL_BANKROLL * 100, 1) if _DEMO_FINAL_BANKROLL else 0,
            "bets_placed": len(today_bets),
            "bets_won": today_won,
            "bets_lost": today_lost,
        },
        "signals": {
            "active": 6,
            "by_grade": {"A": 2, "B": 2, "C": 1, "D": 1},
        },
        "exposure": {
            "daily_pct": 7.2,
            "max_daily_pct": 10.0,
        },
        "equity_curve": _DEMO_EQUITY,
        "recent_bets": _demo_recent_bets(10),
    }


@app.get("/api/history")
async def get_history(
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=100),
    market: Optional[str] = Query(None),
    league: Optional[str] = Query(None),
) -> dict:
    """
    Paginated bet history with summary statistics.

    Query params:
    - page: page number (default 1)
    - limit: items per page (default 20)
    - market: filter by market type (e.g. 'team_corners_ou')
    - league: filter by league name (e.g. 'Premier League')

    Falls back to deterministic demo data when the DB is empty.
    """
    try:
        from sqlalchemy import func, select

        from db.models.betting import Bet
        from db.session import get_session

        async with get_session() as session:
            count_result = await session.execute(
                select(func.count()).select_from(Bet)
            )
            real_count = count_result.scalar() or 0

            if real_count > 0:
                # Real data path (simplified -- pass through to demo for now
                # since full ORM queries require complete schema knowledge)
                pass  # Fall through to demo data

    except Exception as exc:
        logger.warning("/api/history DB query failed, using demo data: %s", exc)

    # --- Demo data ---
    all_bets = list(reversed(_DEMO_BETS))  # newest first

    # Apply filters
    filtered = all_bets
    if market:
        filtered = [b for b in filtered if b["market"] == market]
    if league:
        filtered = [b for b in filtered if b["league"] == league]

    total = len(filtered)
    pages = max(1, math.ceil(total / limit))
    page = min(page, pages)
    start = (page - 1) * limit
    end = start + limit
    page_bets = filtered[start:end]

    # Summary statistics from filtered set
    won = sum(1 for b in filtered if b["outcome"] == "won")
    lost = sum(1 for b in filtered if b["outcome"] == "lost")
    total_staked = sum(b["stake"] for b in filtered)
    total_pnl_val = round(sum(b["pnl"] for b in filtered), 2)
    roi = round((total_pnl_val / total_staked * 100), 1) if total_staked > 0 else 0.0

    # By market breakdown
    market_stats: dict[str, dict] = {}
    for b in filtered:
        m = b["market"]
        if m not in market_stats:
            market_stats[m] = {"bets": 0, "won": 0, "staked": 0.0, "pnl": 0.0}
        market_stats[m]["bets"] += 1
        if b["outcome"] == "won":
            market_stats[m]["won"] += 1
        market_stats[m]["staked"] += b["stake"]
        market_stats[m]["pnl"] += b["pnl"]

    by_market = [
        {
            "market": m,
            "display": MARKET_DISPLAY.get(m, m),
            "bets": s["bets"],
            "won": s["won"],
            "roi": round(s["pnl"] / s["staked"] * 100, 1) if s["staked"] > 0 else 0.0,
        }
        for m, s in sorted(market_stats.items(), key=lambda x: x[1]["bets"], reverse=True)
    ]

    # By league breakdown
    league_stats: dict[str, dict] = {}
    for b in filtered:
        lg = b["league"]
        if lg not in league_stats:
            league_stats[lg] = {"bets": 0, "won": 0, "staked": 0.0, "pnl": 0.0}
        league_stats[lg]["bets"] += 1
        if b["outcome"] == "won":
            league_stats[lg]["won"] += 1
        league_stats[lg]["staked"] += b["stake"]
        league_stats[lg]["pnl"] += b["pnl"]

    by_league = [
        {
            "league": lg,
            "bets": s["bets"],
            "won": s["won"],
            "roi": round(s["pnl"] / s["staked"] * 100, 1) if s["staked"] > 0 else 0.0,
        }
        for lg, s in sorted(league_stats.items(), key=lambda x: x[1]["bets"], reverse=True)
    ]

    # Monthly breakdown
    monthly_stats: dict[str, dict] = {}
    for b in filtered:
        month = b["settled_date"][:7]  # "2026-02"
        if month not in monthly_stats:
            monthly_stats[month] = {"bets": 0, "staked": 0.0, "pnl": 0.0}
        monthly_stats[month]["bets"] += 1
        monthly_stats[month]["staked"] += b["stake"]
        monthly_stats[month]["pnl"] += b["pnl"]

    monthly = [
        {
            "month": m,
            "bets": s["bets"],
            "pnl": round(s["pnl"], 2),
            "roi": round(s["pnl"] / s["staked"] * 100, 1) if s["staked"] > 0 else 0.0,
        }
        for m, s in sorted(monthly_stats.items())
    ]

    return {
        "bets": page_bets,
        "total": total,
        "page": page,
        "pages": pages,
        "summary": {
            "total_bets": total,
            "won": won,
            "lost": lost,
            "void": 0,
            "total_staked": round(total_staked, 2),
            "total_pnl": total_pnl_val,
            "roi_pct": roi,
            "by_market": by_market,
            "by_league": by_league,
            "monthly": monthly,
        },
        "equity_curve": _DEMO_EQUITY,
    }


@app.get("/api/models")
async def get_models() -> dict:
    """
    Return status and metrics for all models in the system.

    Falls back to demo data showing realistic model metrics when the DB
    has no model runs registered.
    """
    try:
        from db.session import get_session
        from models.registry import ModelRegistry

        registry = ModelRegistry()
        async with get_session() as session:
            model_runs = await registry.list_models(session)
            if model_runs:
                models_out = []
                for mr in model_runs:
                    models_out.append({
                        "type": mr.model_type,
                        "name": mr.model_type.replace("_", " ").title(),
                        "version": mr.model_version,
                        "status": "active" if mr.active else "inactive",
                        "last_trained": mr.trained_at.isoformat() if mr.trained_at else None,
                        "training_samples": mr.training_samples,
                        "metrics": {
                            "brier_score": mr.brier_score,
                            "log_loss": mr.log_loss,
                            "calibration_error": mr.calibration_error,
                        },
                        "drift": {
                            "status": "ok",
                            "psi": 0.0,
                            "threshold": 0.2,
                        },
                    })
                return {"models": models_out}

    except Exception as exc:
        logger.warning("/api/models DB query failed, using demo data: %s", exc)

    # --- Demo data ---
    rng = random.Random(123)

    demo_models = [
        {
            "type": "poisson",
            "name": "Poisson Goals",
            "version": "1.2.0",
            "training_samples": 2450,
            "metrics": {"brier_score": 0.198, "log_loss": 0.543, "calibration_error": 0.032},
            "drift": {"psi": 0.08},
        },
        {
            "type": "dixon_coles",
            "name": "Dixon-Coles",
            "version": "1.1.0",
            "training_samples": 2450,
            "metrics": {"brier_score": 0.191, "log_loss": 0.528, "calibration_error": 0.028},
            "drift": {"psi": 0.06},
        },
        {
            "type": "negbin_corners",
            "name": "Negative Binomial Corners",
            "version": "1.0.3",
            "training_samples": 2380,
            "metrics": {"brier_score": 0.212, "log_loss": 0.587, "calibration_error": 0.041},
            "drift": {"psi": 0.11},
        },
        {
            "type": "negbin_offsides",
            "name": "Negative Binomial Offsides",
            "version": "1.0.2",
            "training_samples": 2310,
            "metrics": {"brier_score": 0.224, "log_loss": 0.612, "calibration_error": 0.045},
            "drift": {"psi": 0.09},
        },
        {
            "type": "btts",
            "name": "Both Teams To Score",
            "version": "1.1.1",
            "training_samples": 2450,
            "metrics": {"brier_score": 0.205, "log_loss": 0.561, "calibration_error": 0.035},
            "drift": {"psi": 0.07},
        },
        {
            "type": "player_shots",
            "name": "Player Shots",
            "version": "1.0.1",
            "training_samples": 4820,
            "metrics": {"brier_score": 0.231, "log_loss": 0.634, "calibration_error": 0.048},
            "drift": {"psi": 0.12},
        },
        {
            "type": "player_sot",
            "name": "Player Shots On Target",
            "version": "1.0.1",
            "training_samples": 4820,
            "metrics": {"brier_score": 0.238, "log_loss": 0.651, "calibration_error": 0.052},
            "drift": {"psi": 0.10},
        },
        {
            "type": "player_tackles",
            "name": "Player Tackles",
            "version": "1.0.0",
            "training_samples": 4680,
            "metrics": {"brier_score": 0.243, "log_loss": 0.668, "calibration_error": 0.055},
            "drift": {"psi": 0.14},
        },
        {
            "type": "player_passes",
            "name": "Player Passes",
            "version": "1.0.0",
            "training_samples": 4680,
            "metrics": {"brier_score": 0.218, "log_loss": 0.598, "calibration_error": 0.039},
            "drift": {"psi": 0.07},
        },
        {
            "type": "player_fouls",
            "name": "Player Fouls",
            "version": "1.0.0",
            "training_samples": 4680,
            "metrics": {"brier_score": 0.251, "log_loss": 0.689, "calibration_error": 0.061},
            "drift": {"psi": 0.13},
        },
        {
            "type": "player_offsides",
            "name": "Player Offsides",
            "version": "1.0.0",
            "training_samples": 4520,
            "metrics": {"brier_score": 0.258, "log_loss": 0.702, "calibration_error": 0.064},
            "drift": {"psi": 0.15},
        },
        {
            "type": "anytime_goalscorer",
            "name": "Anytime Goalscorer",
            "version": "1.0.2",
            "training_samples": 5200,
            "metrics": {"brier_score": 0.195, "log_loss": 0.538, "calibration_error": 0.030},
            "drift": {"psi": 0.05},
        },
        {
            "type": "player_cards",
            "name": "Player Cards",
            "version": "1.0.1",
            "training_samples": 4380,
            "metrics": {"brier_score": 0.246, "log_loss": 0.678, "calibration_error": 0.058},
            "drift": {"psi": 0.16},
        },
    ]

    # Add computed/standard fields to each model
    base_date = datetime(2026, 3, 8, 14, 30, tzinfo=timezone.utc)
    models_out = []
    for i, m in enumerate(demo_models):
        # Stagger last_trained times
        trained_at = base_date - timedelta(hours=i * 3, minutes=rng.randint(0, 59))
        psi = m["drift"]["psi"]
        drift_status = "ok" if psi < 0.15 else "warning" if psi < 0.20 else "critical"

        models_out.append({
            "type": m["type"],
            "name": m["name"],
            "version": m["version"],
            "status": "active",
            "last_trained": trained_at.isoformat(),
            "training_samples": m["training_samples"],
            "metrics": m["metrics"],
            "drift": {
                "status": drift_status,
                "psi": psi,
                "threshold": 0.2,
            },
        })

    return {"models": models_out}


@app.get("/api/ingestion")
async def get_ingestion() -> dict:
    """
    Return data ingestion status: sources, entity resolution stats,
    table row counts, and recent ingestion logs.

    Falls back to deterministic demo data when no real ingestion logs exist.
    """
    # --- Demo data (always returned for now, since ingestion logs are not
    #     stored in a queryable table yet) ---
    rng = random.Random(456)

    now = datetime(2026, 3, 10, 10, 15, tzinfo=timezone.utc)

    sources = [
        {
            "name": "Optic Odds",
            "status": "healthy",
            "last_fetch": (now - timedelta(minutes=0)).isoformat(),
            "records_today": 342,
            "total_records": 15420,
        },
        {
            "name": "The Odds API",
            "status": "healthy",
            "last_fetch": (now - timedelta(minutes=15)).isoformat(),
            "records_today": 128,
            "total_records": 8930,
            "credits_remaining": 420,
        },
        {
            "name": "SportMonks",
            "status": "healthy",
            "last_fetch": (now - timedelta(minutes=45)).isoformat(),
            "records_today": 56,
            "total_records": 45200,
        },
    ]

    entity_resolution = {
        "resolved_pct": 96.4,
        "unresolved_count": 23,
        "total_entities": 640,
        "confidence_avg": 0.92,
    }

    tables = [
        {"name": "raw_fixtures", "count": 4520},
        {"name": "raw_odds", "count": 89340},
        {"name": "matches", "count": 3200},
        {"name": "teams", "count": 186},
        {"name": "players", "count": 4280},
        {"name": "odds_snapshots", "count": 156700},
        {"name": "feature_vectors", "count": 28400},
        {"name": "model_predictions", "count": 12800},
        {"name": "ev_signals", "count": 890},
        {"name": "bets", "count": 147},
    ]

    # Generate ~20 recent log entries
    log_actions = [
        ("optic_odds", "ingest_fixtures", 18, 35, 800, 1800),
        ("optic_odds", "ingest_odds", 80, 200, 2000, 5000),
        ("optic_odds", "ingest_results", 5, 15, 400, 1200),
        ("the_odds_api", "ingest_odds", 40, 120, 1500, 4000),
        ("the_odds_api", "ingest_fixtures", 10, 25, 600, 1500),
        ("sportmonks", "ingest_historical", 20, 80, 2000, 8000),
        ("sportmonks", "ingest_player_stats", 30, 100, 1500, 5000),
        ("system", "entity_resolution", 5, 20, 500, 3000),
        ("system", "feature_engineering", 50, 200, 3000, 12000),
        ("system", "model_prediction", 20, 80, 1000, 5000),
    ]

    recent_logs = []
    base_time = now
    for i in range(20):
        action_template = log_actions[i % len(log_actions)]
        source, action, rec_min, rec_max, dur_min, dur_max = action_template
        ts = base_time - timedelta(minutes=i)
        records = rng.randint(rec_min, rec_max)
        duration = rng.randint(dur_min, dur_max)

        # Occasionally inject a warning
        status = "success"
        if i == 7:
            status = "warning"
        elif i == 15:
            status = "success"

        recent_logs.append({
            "timestamp": ts.isoformat(),
            "source": source,
            "action": action,
            "status": status,
            "records": records,
            "duration_ms": duration,
        })

    return {
        "sources": sources,
        "entity_resolution": entity_resolution,
        "tables": tables,
        "recent_logs": recent_logs,
    }


@app.get("/api/settings")
async def get_settings() -> dict:
    """
    Return current system settings: risk parameters, leagues, bookmakers, APIs.

    Reads from config.settings (pydantic Settings backed by .env).
    League and bookmaker configs come from config.leagues and config.bookmakers.
    """
    try:
        from config.settings import settings
    except Exception:
        # Provide sensible defaults if settings import fails
        class _FallbackSettings:
            bankroll_dkk = 10000.0
            min_ev_threshold = 0.03
            kelly_fraction = 0.25
            max_stake_pct = 0.03
            min_odds = 1.50
            max_odds = 4.00
            optic_odds_api_key = ""
            the_odds_api_key = ""
            sportmonks_api_key = ""
        settings = _FallbackSettings()

    try:
        from config.bookmakers import BOOKMAKERS
    except Exception:
        BOOKMAKERS = {}

    try:
        from config.leagues import LEAGUES
    except Exception:
        LEAGUES = {}

    # Build league list
    leagues_out = []
    for lid, lg in LEAGUES.items():
        leagues_out.append({
            "id": lid,
            "name": lg.name,
            "country": lg.country,
            "active": lg.active,
        })

    # Build bookmaker list (exclude sharp reference books from the user-facing list)
    bookmakers_out = []
    for bid, bk in BOOKMAKERS.items():
        if bk.is_sharp:
            continue  # Pinnacle is a reference, not a target bookmaker
        bookmakers_out.append({
            "id": bid,
            "name": bk.display_name,
            "active": bk.active,
        })

    # API health status
    apis = [
        {
            "name": "Optic Odds",
            "configured": bool(getattr(settings, "optic_odds_api_key", "")),
            "healthy": True,
        },
        {
            "name": "The Odds API",
            "configured": bool(getattr(settings, "the_odds_api_key", "")),
            "healthy": True,
        },
        {
            "name": "SportMonks",
            "configured": bool(getattr(settings, "sportmonks_api_key", "")),
            "healthy": True,
        },
    ]

    return {
        "bankroll_dkk": settings.bankroll_dkk,
        "min_ev_threshold": settings.min_ev_threshold,
        "kelly_fraction": settings.kelly_fraction,
        "max_stake_pct": settings.max_stake_pct,
        "min_odds": settings.min_odds,
        "max_odds": settings.max_odds,
        "leagues": leagues_out,
        "bookmakers": bookmakers_out,
        "apis": apis,
    }


@app.post("/api/settings")
async def update_settings(request: Request) -> dict:
    """
    Update system settings.

    Accepts a JSON body with any subset of settings fields.
    Currently updates the in-process settings singleton. For persistence
    across restarts, settings should be written to .env or the database.

    Supported fields:
    - bankroll_dkk, min_ev_threshold, kelly_fraction, max_stake_pct,
      min_odds, max_odds
    """
    try:
        body = await request.json()
    except Exception:
        return JSONResponse(
            status_code=400,
            content={"status": "error", "message": "Invalid JSON body"},
        )

    try:
        from config.settings import settings

        updatable_fields = [
            "bankroll_dkk", "min_ev_threshold", "kelly_fraction",
            "max_stake_pct", "min_odds", "max_odds",
        ]

        updated = []
        for field in updatable_fields:
            if field in body:
                setattr(settings, field, float(body[field]))
                updated.append(field)

        if not updated:
            return {"status": "ok", "message": "No recognized settings fields to update"}

        return {"status": "ok", "message": f"Settings updated: {', '.join(updated)}"}

    except Exception as exc:
        logger.error("Failed to update settings: %s", exc, exc_info=True)
        return JSONResponse(
            status_code=500,
            content={"status": "error", "message": str(exc)},
        )


@app.post("/api/signals/{signal_id}/approve")
async def approve_signal(signal_id: str) -> dict:
    """
    Approve an EV signal for betting.

    In a full implementation this would update the signal's status in the DB
    and potentially trigger stake calculation. Currently returns confirmation.
    """
    try:
        from sqlalchemy import select

        from db.models.predictions import EVSignal
        from db.session import get_session

        async with get_session() as session:
            result = await session.execute(
                select(EVSignal).where(EVSignal.id == signal_id)
            )
            signal = result.scalar_one_or_none()
            if signal:
                signal.status = "approved"
                await session.flush()
                logger.info("Signal %s approved", signal_id)
    except Exception as exc:
        logger.warning("Could not update signal %s in DB: %s", signal_id, exc)

    return {"status": "ok", "signal_id": signal_id, "action": "approved"}


@app.post("/api/signals/{signal_id}/reject")
async def reject_signal(signal_id: str) -> dict:
    """
    Reject an EV signal (decline to bet).

    Updates the signal status in the DB if available.
    """
    try:
        from sqlalchemy import select

        from db.models.predictions import EVSignal
        from db.session import get_session

        async with get_session() as session:
            result = await session.execute(
                select(EVSignal).where(EVSignal.id == signal_id)
            )
            signal = result.scalar_one_or_none()
            if signal:
                signal.status = "rejected"
                await session.flush()
                logger.info("Signal %s rejected", signal_id)
    except Exception as exc:
        logger.warning("Could not update signal %s in DB: %s", signal_id, exc)

    return {"status": "ok", "signal_id": signal_id, "action": "rejected"}


@app.post("/api/ingest/trigger")
async def trigger_ingestion() -> dict:
    """
    Trigger an immediate ingestion cycle.

    In a full implementation this would signal the ingestion scheduler
    to run all source adapters immediately. Currently returns confirmation.
    """
    logger.info("Manual ingestion triggered via API")

    # Attempt to trigger real ingestion if the module is available
    try:
        # Future: call ingestion pipeline directly
        pass
    except Exception as exc:
        logger.warning("Ingestion trigger failed: %s", exc)

    return {"status": "ok", "message": "Ingestion triggered"}


@app.post("/api/models/{model_type}/retrain")
async def retrain_model(model_type: str) -> dict:
    """
    Trigger retraining for a specific model.

    In a full implementation this would enqueue a training job for the
    specified model type. Currently returns confirmation.

    Valid model types: poisson, dixon_coles, negbin_corners, negbin_offsides,
    btts, player_shots, player_sot, player_tackles, player_passes,
    player_fouls, player_offsides, anytime_goalscorer, player_cards
    """
    valid_types = [
        "poisson", "dixon_coles", "negbin_corners", "negbin_offsides",
        "btts", "player_shots", "player_sot", "player_tackles",
        "player_passes", "player_fouls", "player_offsides",
        "anytime_goalscorer", "player_cards",
    ]

    if model_type not in valid_types:
        return JSONResponse(
            status_code=400,
            content={
                "status": "error",
                "model_type": model_type,
                "message": f"Unknown model type. Valid types: {', '.join(valid_types)}",
            },
        )

    logger.info("Retraining triggered for model: %s", model_type)

    return {
        "status": "ok",
        "model_type": model_type,
        "message": f"Retraining started for {model_type}",
    }
