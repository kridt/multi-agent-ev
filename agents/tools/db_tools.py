"""Database query tools exposed to Claude agents.

Each function is a self-contained async coroutine that opens its own session.
All queries are read-only (no writes). Return types are plain dicts so they
can be serialised directly into Claude tool_result content.

Assumptions:
- OddsMovement stores opening/closing/movement_pct per bookmaker/market/selection.
- ModelRun (system.py) is the source of model performance metrics.
- BankrollSnapshot.snapshot_at is used to find the latest bankroll state.
- Bet.placed_at is used to filter recent bets by days.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

from sqlalchemy import and_, select

from db.models.betting import Bet, BankrollSnapshot
from db.models.matches import Match
from db.models.odds import OddsMovement
from db.models.predictions import EVSignal
from db.models.system import ModelRun
from db.session import get_session

logger = logging.getLogger(__name__)


async def get_upcoming_matches(hours_ahead: int = 24) -> list[dict]:
    """Return scheduled matches kicking off within the next hours_ahead hours.

    Queries: matches table, status='scheduled', kickoff_at in [now, now+hours_ahead].
    Returns a list of dicts with fixture metadata (no ORM objects).
    """
    now = datetime.now(timezone.utc)
    cutoff = now + timedelta(hours=hours_ahead)

    async with get_session() as session:
        stmt = (
            select(Match)
            .where(
                and_(
                    Match.kickoff_at >= now,
                    Match.kickoff_at <= cutoff,
                    Match.status == "scheduled",
                )
            )
            .order_by(Match.kickoff_at.asc())
        )
        result = await session.execute(stmt)
        matches = result.scalars().all()

    return [
        {
            "match_id": m.id,
            "home_team_id": m.home_team_id,
            "away_team_id": m.away_team_id,
            "league_id": m.league_id,
            "kickoff_at": m.kickoff_at.isoformat(),
            "status": m.status,
            "season": m.season,
            "matchday": m.matchday,
            "sportmonks_fixture_id": m.sportmonks_fixture_id,
        }
        for m in matches
    ]


async def get_signals_for_match(match_id: str) -> list[dict]:
    """Return all EV signals for a given match_id.

    Queries: ev_signals table filtered by match_id.
    Returns signals in descending ev_pct order.
    """
    async with get_session() as session:
        stmt = (
            select(EVSignal)
            .where(EVSignal.match_id == match_id)
            .order_by(EVSignal.ev_pct.desc())
        )
        result = await session.execute(stmt)
        signals = result.scalars().all()

    return [
        {
            "signal_id": s.id,
            "match_id": s.match_id,
            "market": s.market,
            "selection": s.selection,
            "bookmaker": s.bookmaker,
            "odds_at_signal": s.odds_at_signal,
            "model_prob": s.model_prob,
            "ev_pct": s.ev_pct,
            "confidence": s.confidence,
            "suggested_stake_pct": s.suggested_stake_pct,
            "suggested_stake_dkk": s.suggested_stake_dkk,
            "status": s.status,
            "anomaly_flag": s.anomaly_flag,
            "anomaly_reasoning": s.anomaly_reasoning,
            "generated_at": s.generated_at.isoformat(),
            "expires_at": s.expires_at.isoformat(),
        }
        for s in signals
    ]


async def get_odds_movement(
    match_id: str,
    market: str,
    selection: str,
) -> list[dict]:
    """Return odds movement records for a given match/market/selection combination.

    Queries: odds_movements table.
    The OddsMovement model stores movement across all bookmakers for the same
    market/selection tuple. Multiple rows may exist (one per bookmaker).

    NOTE: market and selection are matched exactly (no fuzzy matching).
    If no movement records exist, returns an empty list — caller must handle
    the absence of data explicitly.
    """
    async with get_session() as session:
        stmt = select(OddsMovement).where(
            and_(
                OddsMovement.match_id == match_id,
                OddsMovement.market == market,
                OddsMovement.selection == selection,
            )
        )
        result = await session.execute(stmt)
        rows = result.scalars().all()

    return [
        {
            "match_id": r.match_id,
            "bookmaker": r.bookmaker,
            "market": r.market,
            "selection": r.selection,
            "opening_odds": r.opening_odds,
            "closing_odds": r.closing_odds,
            "movement_pct": r.movement_pct,
        }
        for r in rows
    ]


async def get_bankroll_status() -> dict:
    """Return the most recent bankroll snapshot.

    Queries: bankroll_snapshots table, latest row by snapshot_at.
    Returns a single dict. If no snapshot exists, returns a dict with
    null values and a reason code.
    """
    async with get_session() as session:
        stmt = (
            select(BankrollSnapshot)
            .order_by(BankrollSnapshot.snapshot_at.desc())
            .limit(1)
        )
        result = await session.execute(stmt)
        snap = result.scalar_one_or_none()

    if snap is None:
        return {
            "available": False,
            "reason": "NO_SNAPSHOT",
            "balance_dkk": None,
            "peak_dkk": None,
            "drawdown_pct": None,
            "daily_exposure_pct": None,
            "total_bets": None,
            "total_wins": None,
            "total_losses": None,
            "roi_pct": None,
            "brier_score": None,
            "snapshot_at": None,
        }

    return {
        "available": True,
        "reason": None,
        "balance_dkk": snap.balance_dkk,
        "peak_dkk": snap.peak_dkk,
        "drawdown_pct": snap.drawdown_pct,
        "daily_exposure_pct": snap.daily_exposure_pct,
        "total_bets": snap.total_bets,
        "total_wins": snap.total_wins,
        "total_losses": snap.total_losses,
        "roi_pct": snap.roi_pct,
        "brier_score": snap.brier_score,
        "snapshot_at": snap.snapshot_at.isoformat(),
    }


async def get_recent_bets(days: int = 7) -> list[dict]:
    """Return bets placed within the last days days.

    Queries: bets table filtered by placed_at >= now - days.
    Returns bets ordered by placed_at descending.
    """
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)

    async with get_session() as session:
        stmt = (
            select(Bet)
            .where(Bet.placed_at >= cutoff)
            .order_by(Bet.placed_at.desc())
        )
        result = await session.execute(stmt)
        bets = result.scalars().all()

    return [
        {
            "bet_id": b.id,
            "signal_id": b.signal_id,
            "match_id": b.match_id,
            "market": b.market,
            "selection": b.selection,
            "bookmaker": b.bookmaker,
            "odds": b.odds,
            "stake_dkk": b.stake_dkk,
            "potential_return_dkk": b.potential_return_dkk,
            "outcome": b.outcome,
            "pnl_dkk": b.pnl_dkk,
            "closing_odds": b.closing_odds,
            "clv_pct": b.clv_pct,
            "placed_at": b.placed_at.isoformat(),
            "settled_at": b.settled_at.isoformat() if b.settled_at else None,
        }
        for b in bets
    ]


async def get_model_performance(model_type: str) -> dict:
    """Return the most recent active ModelRun metrics for a given model_type.

    Queries: model_runs table, filtered by model_type and active=True,
    ordered by trained_at descending. Falls back to any run (active or not)
    if no active run exists. Returns a single dict.

    If no run exists for model_type, returns a dict with available=False
    and reason code NO_MODEL_RUN.
    """
    async with get_session() as session:
        # Prefer active=True, fall back to most recent regardless of active flag.
        stmt = (
            select(ModelRun)
            .where(
                and_(
                    ModelRun.model_type == model_type,
                    ModelRun.active.is_(True),
                )
            )
            .order_by(ModelRun.trained_at.desc())
            .limit(1)
        )
        result = await session.execute(stmt)
        run = result.scalar_one_or_none()

        if run is None:
            # Fallback: most recent regardless of active status.
            fallback_stmt = (
                select(ModelRun)
                .where(ModelRun.model_type == model_type)
                .order_by(ModelRun.trained_at.desc())
                .limit(1)
            )
            fallback_result = await session.execute(fallback_stmt)
            run = fallback_result.scalar_one_or_none()

    if run is None:
        return {
            "available": False,
            "reason": "NO_MODEL_RUN",
            "model_type": model_type,
            "model_version": None,
            "brier_score": None,
            "log_loss": None,
            "auc_roc": None,
            "calibration_error": None,
            "training_samples": None,
            "training_data_cutoff": None,
            "active": None,
            "trained_at": None,
        }

    return {
        "available": True,
        "reason": None,
        "model_type": run.model_type,
        "model_version": run.model_version,
        "brier_score": run.brier_score,
        "log_loss": run.log_loss,
        "auc_roc": run.auc_roc,
        "calibration_error": run.calibration_error,
        "training_samples": run.training_samples,
        "training_data_cutoff": run.training_data_cutoff.isoformat(),
        "active": run.active,
        "trained_at": run.trained_at.isoformat(),
    }
