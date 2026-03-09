"""The Odds API ingestion pipelines — fetch, map, store, log."""

from __future__ import annotations

import logging
import time
from datetime import datetime, timezone

from db.models.system import IngestionLog
from db.session import get_session

from .client import TARGET_MARKETS, TheOddsAPIClient
from .mappers import map_event_to_raw, map_odds_to_raw

logger = logging.getLogger(__name__)


async def ingest_events(sport_key: str) -> int:
    """Fetch upcoming events for a sport and store as raw fixtures.

    Returns the count of records stored.
    """
    start = time.monotonic()
    fetched_at = datetime.now(timezone.utc)
    count = 0
    status_code = 200
    error_message: str | None = None
    credits_remaining: int | None = None

    try:
        async with TheOddsAPIClient() as client:
            events = await client.get_events(sport_key)
            credits_remaining = client.credits_remaining

        rows = [map_event_to_raw(e, fetched_at) for e in events]

        async with get_session() as session:
            session.add_all(rows)
            count = len(rows)

    except Exception as exc:
        status_code = getattr(exc, "status_code", 500)
        error_message = str(exc)
        logger.error("ingest_events(%s) failed: %s", sport_key, exc, exc_info=True)

    duration_ms = int((time.monotonic() - start) * 1000)

    try:
        async with get_session() as session:
            session.add(
                IngestionLog(
                    source="the_odds_api",
                    endpoint=f"/v4/sports/{sport_key}/events",
                    status_code=status_code,
                    records_fetched=count,
                    duration_ms=duration_ms,
                    error_message=error_message,
                    credits_remaining=credits_remaining,
                    fetched_at=fetched_at,
                )
            )
    except Exception as log_exc:
        logger.error("Failed to write ingestion log: %s", log_exc)

    logger.info(
        "the_odds_api ingest_events(%s): %d records in %dms (credits_remaining=%s)",
        sport_key,
        count,
        duration_ms,
        credits_remaining,
    )
    return count


async def ingest_odds(sport_key: str, markets: str = TARGET_MARKETS) -> int:
    """Fetch odds for a sport and store as raw odds (one row per market per bookmaker).

    Returns the count of records stored.
    """
    start = time.monotonic()
    fetched_at = datetime.now(timezone.utc)
    count = 0
    status_code = 200
    error_message: str | None = None
    credits_remaining: int | None = None

    try:
        async with TheOddsAPIClient() as client:
            events_odds = await client.get_odds(sport_key, markets=markets)
            credits_remaining = client.credits_remaining

        all_rows = []
        for event_odds in events_odds:
            all_rows.extend(map_odds_to_raw(event_odds, fetched_at))

        async with get_session() as session:
            session.add_all(all_rows)
            count = len(all_rows)

    except Exception as exc:
        status_code = getattr(exc, "status_code", 500)
        error_message = str(exc)
        logger.error("ingest_odds(%s) failed: %s", sport_key, exc, exc_info=True)

    duration_ms = int((time.monotonic() - start) * 1000)

    try:
        async with get_session() as session:
            session.add(
                IngestionLog(
                    source="the_odds_api",
                    endpoint=f"/v4/sports/{sport_key}/odds",
                    status_code=status_code,
                    records_fetched=count,
                    duration_ms=duration_ms,
                    error_message=error_message,
                    credits_remaining=credits_remaining,
                    fetched_at=fetched_at,
                )
            )
    except Exception as log_exc:
        logger.error("Failed to write ingestion log: %s", log_exc)

    logger.info(
        "the_odds_api ingest_odds(%s): %d records in %dms (credits_remaining=%s)",
        sport_key,
        count,
        duration_ms,
        credits_remaining,
    )
    return count


async def ingest_scores(sport_key: str) -> int:
    """Fetch recent scores for a sport and store as raw fixtures.

    Returns the count of records stored.
    """
    start = time.monotonic()
    fetched_at = datetime.now(timezone.utc)
    count = 0
    status_code = 200
    error_message: str | None = None
    credits_remaining: int | None = None

    try:
        async with TheOddsAPIClient() as client:
            scores = await client.get_scores(sport_key)
            credits_remaining = client.credits_remaining

        # Store scores as raw fixtures (they contain result data)
        rows = []
        for score in scores:
            from db.models.base import new_uuid
            from db.models.raw import RawFixture

            rows.append(
                RawFixture(
                    id=new_uuid(),
                    source="the_odds_api",
                    source_fixture_id=score.id,
                    raw_json=score.model_dump_json(),
                    fetched_at=fetched_at,
                    processed=False,
                )
            )

        async with get_session() as session:
            session.add_all(rows)
            count = len(rows)

    except Exception as exc:
        status_code = getattr(exc, "status_code", 500)
        error_message = str(exc)
        logger.error("ingest_scores(%s) failed: %s", sport_key, exc, exc_info=True)

    duration_ms = int((time.monotonic() - start) * 1000)

    try:
        async with get_session() as session:
            session.add(
                IngestionLog(
                    source="the_odds_api",
                    endpoint=f"/v4/sports/{sport_key}/scores",
                    status_code=status_code,
                    records_fetched=count,
                    duration_ms=duration_ms,
                    error_message=error_message,
                    credits_remaining=credits_remaining,
                    fetched_at=fetched_at,
                )
            )
    except Exception as log_exc:
        logger.error("Failed to write ingestion log: %s", log_exc)

    logger.info(
        "the_odds_api ingest_scores(%s): %d records in %dms (credits_remaining=%s)",
        sport_key,
        count,
        duration_ms,
        credits_remaining,
    )
    return count
