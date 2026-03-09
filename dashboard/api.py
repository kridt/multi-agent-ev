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
"""

import asyncio
import json
import logging
from contextlib import asynccontextmanager
from datetime import date, datetime, timezone
from pathlib import Path

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
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
# Static file serving (conditional)
# ---------------------------------------------------------------------------

static_dir = Path(__file__).parent / "static"
if static_dir.exists():
    app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")
    logger.debug("Static files mounted from %s", static_dir)


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
