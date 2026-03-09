"""Optic Odds ingestion pipelines — fetch, map, store, log."""

from __future__ import annotations

import logging
import time
from datetime import datetime, timezone

from db.models.raw import RawFixture, RawOdds, RawPlayerStats
from db.models.system import IngestionLog
from db.session import get_session

from .client import OpticOddsClient
from .mappers import map_fixture_to_raw, map_odds_to_raw, map_player_result_to_raw

logger = logging.getLogger(__name__)


async def ingest_fixtures(league: str | None = None) -> int:
    """Fetch fixtures from Optic Odds and store as raw data.

    Returns the count of records stored.
    """
    start = time.monotonic()
    fetched_at = datetime.now(timezone.utc)
    count = 0
    status_code = 200
    error_message: str | None = None

    try:
        async with OpticOddsClient() as client:
            fixtures = await client.get_active_fixtures(league=league)

        rows = [map_fixture_to_raw(f, fetched_at) for f in fixtures]

        async with get_session() as session:
            session.add_all(rows)
            count = len(rows)

    except Exception as exc:
        status_code = getattr(exc, "status_code", 500)
        error_message = str(exc)
        logger.error("ingest_fixtures failed: %s", exc, exc_info=True)

    duration_ms = int((time.monotonic() - start) * 1000)

    try:
        async with get_session() as session:
            session.add(
                IngestionLog(
                    source="optic_odds",
                    endpoint="fixtures/active",
                    status_code=status_code,
                    records_fetched=count,
                    duration_ms=duration_ms,
                    error_message=error_message,
                    fetched_at=fetched_at,
                )
            )
    except Exception as log_exc:
        logger.error("Failed to write ingestion log: %s", log_exc)

    logger.info("optic_odds ingest_fixtures: %d records in %dms", count, duration_ms)
    return count


async def ingest_odds(fixture_id: str, sportsbook: str | None = None) -> int:
    """Fetch odds for a fixture from Optic Odds and store as raw data.

    Returns the count of records stored.
    """
    start = time.monotonic()
    fetched_at = datetime.now(timezone.utc)
    count = 0
    status_code = 200
    error_message: str | None = None

    try:
        async with OpticOddsClient() as client:
            odds_list = await client.get_odds(fixture_id=fixture_id, sportsbook=sportsbook)

        rows = [map_odds_to_raw(o, fetched_at) for o in odds_list]

        async with get_session() as session:
            session.add_all(rows)
            count = len(rows)

    except Exception as exc:
        status_code = getattr(exc, "status_code", 500)
        error_message = str(exc)
        logger.error("ingest_odds failed for fixture %s: %s", fixture_id, exc, exc_info=True)

    duration_ms = int((time.monotonic() - start) * 1000)

    try:
        async with get_session() as session:
            session.add(
                IngestionLog(
                    source="optic_odds",
                    endpoint=f"fixtures/odds?fixture_id={fixture_id}",
                    status_code=status_code,
                    records_fetched=count,
                    duration_ms=duration_ms,
                    error_message=error_message,
                    fetched_at=fetched_at,
                )
            )
    except Exception as log_exc:
        logger.error("Failed to write ingestion log: %s", log_exc)

    logger.info("optic_odds ingest_odds(%s): %d records in %dms", fixture_id, count, duration_ms)
    return count


async def ingest_player_results(fixture_id: str) -> int:
    """Fetch player results for a fixture from Optic Odds and store as raw data.

    Returns the count of records stored.
    """
    start = time.monotonic()
    fetched_at = datetime.now(timezone.utc)
    count = 0
    status_code = 200
    error_message: str | None = None

    try:
        async with OpticOddsClient() as client:
            results = await client.get_player_results(fixture_id=fixture_id)

        rows = [map_player_result_to_raw(r, fetched_at) for r in results]

        async with get_session() as session:
            session.add_all(rows)
            count = len(rows)

    except Exception as exc:
        status_code = getattr(exc, "status_code", 500)
        error_message = str(exc)
        logger.error(
            "ingest_player_results failed for fixture %s: %s",
            fixture_id,
            exc,
            exc_info=True,
        )

    duration_ms = int((time.monotonic() - start) * 1000)

    try:
        async with get_session() as session:
            session.add(
                IngestionLog(
                    source="optic_odds",
                    endpoint=f"fixtures/player-results?fixture_id={fixture_id}",
                    status_code=status_code,
                    records_fetched=count,
                    duration_ms=duration_ms,
                    error_message=error_message,
                    fetched_at=fetched_at,
                )
            )
    except Exception as log_exc:
        logger.error("Failed to write ingestion log: %s", log_exc)

    logger.info(
        "optic_odds ingest_player_results(%s): %d records in %dms",
        fixture_id,
        count,
        duration_ms,
    )
    return count


async def ingest_results() -> int:
    """Fetch completed results from Optic Odds and store as raw data.

    Returns the count of records stored.
    """
    start = time.monotonic()
    fetched_at = datetime.now(timezone.utc)
    count = 0
    status_code = 200
    error_message: str | None = None

    try:
        async with OpticOddsClient() as client:
            results = await client.get_results()

        rows = [map_fixture_to_raw(r, fetched_at) for r in results]

        async with get_session() as session:
            session.add_all(rows)
            count = len(rows)

    except Exception as exc:
        status_code = getattr(exc, "status_code", 500)
        error_message = str(exc)
        logger.error("ingest_results failed: %s", exc, exc_info=True)

    duration_ms = int((time.monotonic() - start) * 1000)

    try:
        async with get_session() as session:
            session.add(
                IngestionLog(
                    source="optic_odds",
                    endpoint="fixtures/results",
                    status_code=status_code,
                    records_fetched=count,
                    duration_ms=duration_ms,
                    error_message=error_message,
                    fetched_at=fetched_at,
                )
            )
    except Exception as log_exc:
        logger.error("Failed to write ingestion log: %s", log_exc)

    logger.info("optic_odds ingest_results: %d records in %dms", count, duration_ms)
    return count
