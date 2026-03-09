"""APScheduler-based ingestion scheduler for the EV betting system."""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

from apscheduler.jobstores.sqlalchemy import SQLAlchemyJobStore
from apscheduler.schedulers.asyncio import AsyncIOScheduler

from config.constants import (
    BETTING_HOURS_END,
    BETTING_HOURS_START,
    FIXTURE_POLL_INTERVAL_HOURS,
    ODDS_POLL_INTERVAL_MIN,
    RESULTS_POLL_INTERVAL_HOURS,
)
from config.leagues import get_active_leagues
from config.settings import settings

logger = logging.getLogger(__name__)

# CET timezone
try:
    from zoneinfo import ZoneInfo
except ImportError:
    from backports.zoneinfo import ZoneInfo  # type: ignore[no-redef]

CET = ZoneInfo("Europe/Copenhagen")


# ---------------------------------------------------------------------------
# Scheduled job functions
# ---------------------------------------------------------------------------


async def _ingest_upcoming_fixtures() -> None:
    """Iterate all active leagues and ingest fixtures from Optic Odds."""
    from ingestion.optic_odds.ingest import ingest_fixtures

    leagues = get_active_leagues()
    total = 0
    for key, league in leagues.items():
        try:
            count = await ingest_fixtures(league=league.optic_odds_id)
            total += count
        except Exception as exc:
            logger.error("Fixture ingestion failed for %s: %s", key, exc)
    logger.info("_ingest_upcoming_fixtures completed: %d total records", total)


async def _ingest_prematch_odds() -> None:
    """Ingest odds for fixtures starting within 24 hours via The Odds API."""
    from ingestion.the_odds_api.ingest import ingest_odds as ingest_odds_api

    leagues = get_active_leagues()
    total = 0
    for key, league in leagues.items():
        try:
            count = await ingest_odds_api(sport_key=league.the_odds_api_key)
            total += count
        except Exception as exc:
            logger.error("Odds ingestion failed for %s: %s", key, exc)
    logger.info("_ingest_prematch_odds completed: %d total records", total)


async def _ingest_results() -> None:
    """Fetch completed results from Optic Odds."""
    from ingestion.optic_odds.ingest import ingest_results

    try:
        count = await ingest_results()
        logger.info("_ingest_results completed: %d records", count)
    except Exception as exc:
        logger.error("Results ingestion failed: %s", exc)


async def _ingest_player_stats() -> None:
    """Fetch player stats for recently completed matches.

    Queries the database for recently completed fixtures that have raw fixture data
    but not yet player stats, then fetches player results for each.
    """
    from sqlalchemy import select

    from db.models.raw import RawFixture, RawPlayerStats
    from db.session import get_session
    from ingestion.optic_odds.ingest import ingest_player_results

    cutoff = datetime.now(timezone.utc) - timedelta(hours=24)

    try:
        async with get_session() as session:
            # Find fixture IDs from recently fetched results that are not yet in player stats
            result = await session.execute(
                select(RawFixture.source_fixture_id)
                .where(RawFixture.source == "optic_odds")
                .where(RawFixture.fetched_at >= cutoff)
                .distinct()
            )
            fixture_ids = [row[0] for row in result.all()]

            # Check which ones already have player stats
            existing = await session.execute(
                select(RawPlayerStats.source_fixture_id)
                .where(RawPlayerStats.source == "optic_odds")
                .where(RawPlayerStats.source_fixture_id.in_(fixture_ids))
                .distinct()
            )
            already_fetched = {row[0] for row in existing.all()}

        missing = [fid for fid in fixture_ids if fid not in already_fetched]

        total = 0
        for fixture_id in missing:
            try:
                count = await ingest_player_results(fixture_id)
                total += count
            except Exception as exc:
                logger.error("Player stats ingestion failed for %s: %s", fixture_id, exc)

        logger.info("_ingest_player_stats completed: %d records for %d fixtures", total, len(missing))

    except Exception as exc:
        logger.error("_ingest_player_stats failed: %s", exc)


async def _snapshot_bankroll() -> None:
    """Create a daily bankroll snapshot."""
    from sqlalchemy import func, select

    from db.models.betting import BankrollSnapshot, Bet
    from db.session import get_session

    now = datetime.now(timezone.utc)

    try:
        async with get_session() as session:
            # Count bets and outcomes
            total_bets_q = await session.execute(select(func.count(Bet.id)))
            total_bets = total_bets_q.scalar() or 0

            wins_q = await session.execute(
                select(func.count(Bet.id)).where(Bet.outcome == "won")
            )
            total_wins = wins_q.scalar() or 0

            losses_q = await session.execute(
                select(func.count(Bet.id)).where(Bet.outcome == "lost")
            )
            total_losses = losses_q.scalar() or 0

            # Calculate current balance from PnL
            pnl_q = await session.execute(
                select(func.coalesce(func.sum(Bet.pnl_dkk), 0.0))
            )
            total_pnl = pnl_q.scalar() or 0.0
            balance = settings.bankroll_dkk + total_pnl

            # Get peak from previous snapshots
            peak_q = await session.execute(
                select(func.max(BankrollSnapshot.peak_dkk))
            )
            prev_peak = peak_q.scalar() or settings.bankroll_dkk
            peak = max(balance, prev_peak)

            drawdown_pct = (peak - balance) / peak if peak > 0 else 0.0
            roi_pct = (total_pnl / settings.bankroll_dkk) * 100 if settings.bankroll_dkk > 0 else 0.0

            snapshot = BankrollSnapshot(
                balance_dkk=balance,
                peak_dkk=peak,
                drawdown_pct=drawdown_pct,
                total_bets=total_bets,
                total_wins=total_wins,
                total_losses=total_losses,
                roi_pct=roi_pct,
                snapshot_at=now,
            )
            session.add(snapshot)

        logger.info(
            "Bankroll snapshot: balance=%.2f DKK, peak=%.2f, drawdown=%.4f, ROI=%.2f%%",
            balance,
            peak,
            drawdown_pct,
            roi_pct,
        )

    except Exception as exc:
        logger.error("_snapshot_bankroll failed: %s", exc)


# ---------------------------------------------------------------------------
# Scheduler factory
# ---------------------------------------------------------------------------


def create_scheduler(db_url: str | None = None) -> AsyncIOScheduler:
    """Create and configure the ingestion scheduler.

    Args:
        db_url: SQLAlchemy database URL for the jobstore. Uses synchronous URL
                (without +aiosqlite) because APScheduler 3.x jobstore needs
                a synchronous engine. Falls back to settings if not provided.
    """
    # APScheduler 3.x SQLAlchemyJobStore requires a synchronous URL
    if db_url is None:
        db_url = settings.database_url
    sync_url = db_url.replace("+aiosqlite", "").replace("+asyncpg", "")

    jobstores = {
        "default": SQLAlchemyJobStore(url=sync_url),
    }
    job_defaults = {
        "coalesce": True,
        "max_instances": 1,
        "misfire_grace_time": 300,  # 5 minutes
    }

    scheduler = AsyncIOScheduler(
        jobstores=jobstores,
        job_defaults=job_defaults,
        timezone=CET,
    )

    # ── Register jobs ─────────────────────────────────────────────────

    # Ingest upcoming fixtures: every 6 hours
    scheduler.add_job(
        _ingest_upcoming_fixtures,
        "interval",
        hours=FIXTURE_POLL_INTERVAL_HOURS,
        id="ingest_upcoming_fixtures",
        name="Ingest upcoming fixtures from Optic Odds",
        replace_existing=True,
    )

    # Ingest pre-match odds: every 30 minutes during betting hours (8:00-23:00 CET)
    scheduler.add_job(
        _ingest_prematch_odds,
        "cron",
        minute=f"*/{ODDS_POLL_INTERVAL_MIN}",
        hour=f"{BETTING_HOURS_START}-{BETTING_HOURS_END}",
        id="ingest_prematch_odds",
        name="Ingest pre-match odds from The Odds API",
        replace_existing=True,
    )

    # Ingest results: every hour
    scheduler.add_job(
        _ingest_results,
        "interval",
        hours=RESULTS_POLL_INTERVAL_HOURS,
        id="ingest_results",
        name="Ingest completed results from Optic Odds",
        replace_existing=True,
    )

    # Ingest player stats: 10 minutes after each results run
    scheduler.add_job(
        _ingest_player_stats,
        "interval",
        hours=RESULTS_POLL_INTERVAL_HOURS,
        minutes=10,
        id="ingest_player_stats",
        name="Ingest player stats for completed matches",
        replace_existing=True,
    )

    # Bankroll snapshot: daily at 23:59 CET
    scheduler.add_job(
        _snapshot_bankroll,
        "cron",
        hour=23,
        minute=59,
        id="snapshot_bankroll",
        name="Daily bankroll snapshot",
        replace_existing=True,
    )

    logger.info("Scheduler configured with %d jobs", len(scheduler.get_jobs()))
    return scheduler


# ---------------------------------------------------------------------------
# One-shot helper for CLI use
# ---------------------------------------------------------------------------


async def run_all_ingestion() -> None:
    """Run all ingestion jobs once (for CLI use)."""
    logger.info("Running all ingestion jobs once...")

    await _ingest_upcoming_fixtures()
    await _ingest_prematch_odds()
    await _ingest_results()
    await _ingest_player_stats()
    await _snapshot_bankroll()

    logger.info("All ingestion jobs completed.")
