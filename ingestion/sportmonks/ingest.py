"""SportMonks ingestion pipelines — historical data backfill."""

from __future__ import annotations

import logging
import time
from datetime import datetime, timezone

from db.models.system import IngestionLog
from db.session import get_session

from .client import SportMonksClient
from .mappers import map_fixture_to_raw, map_statistics_to_raw

logger = logging.getLogger(__name__)


async def backfill_fixtures(league_sportmonks_id: int, start_date: str, end_date: str) -> int:
    """Backfill historical fixtures from SportMonks for a date range.

    Args:
        league_sportmonks_id: The SportMonks league ID to filter by.
        start_date: Start date in YYYY-MM-DD format.
        end_date: End date in YYYY-MM-DD format.

    Returns the count of records stored.
    """
    start = time.monotonic()
    fetched_at = datetime.now(timezone.utc)
    count = 0
    status_code = 200
    error_message: str | None = None

    try:
        async with SportMonksClient() as client:
            fixtures = await client.get_fixtures_by_date_range(start_date, end_date)

        # Filter to the requested league
        league_fixtures = [
            f for f in fixtures if f.league_id == league_sportmonks_id
        ]

        rows = [map_fixture_to_raw(f, fetched_at) for f in league_fixtures]

        async with get_session() as session:
            session.add_all(rows)
            count = len(rows)

    except Exception as exc:
        status_code = getattr(exc, "status_code", 500)
        error_message = str(exc)
        logger.error(
            "backfill_fixtures(league=%d, %s to %s) failed: %s",
            league_sportmonks_id,
            start_date,
            end_date,
            exc,
            exc_info=True,
        )

    duration_ms = int((time.monotonic() - start) * 1000)

    try:
        async with get_session() as session:
            session.add(
                IngestionLog(
                    source="sportmonks",
                    endpoint=f"fixtures/between/{start_date}/{end_date}",
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
        "sportmonks backfill_fixtures(league=%d): %d records in %dms",
        league_sportmonks_id,
        count,
        duration_ms,
    )
    return count


async def backfill_statistics(season_id: int) -> int:
    """Backfill player statistics for a SportMonks season.

    Args:
        season_id: The SportMonks season ID.

    Returns the count of records stored.
    """
    start = time.monotonic()
    fetched_at = datetime.now(timezone.utc)
    count = 0
    status_code = 200
    error_message: str | None = None

    try:
        async with SportMonksClient() as client:
            statistics = await client.get_season_statistics(season_id)

        # Group statistics by fixture_id for mapping
        by_fixture: dict[int, list] = {}
        for stat in statistics:
            fid = stat.fixture_id
            if fid is None:
                continue
            by_fixture.setdefault(fid, []).append(stat)

        all_rows = []
        for fixture_id, fixture_stats in by_fixture.items():
            all_rows.extend(map_statistics_to_raw(fixture_id, fixture_stats, fetched_at))

        async with get_session() as session:
            session.add_all(all_rows)
            count = len(all_rows)

    except Exception as exc:
        status_code = getattr(exc, "status_code", 500)
        error_message = str(exc)
        logger.error(
            "backfill_statistics(season=%d) failed: %s",
            season_id,
            exc,
            exc_info=True,
        )

    duration_ms = int((time.monotonic() - start) * 1000)

    try:
        async with get_session() as session:
            session.add(
                IngestionLog(
                    source="sportmonks",
                    endpoint=f"statistics/seasons/{season_id}",
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
        "sportmonks backfill_statistics(season=%d): %d records in %dms",
        season_id,
        count,
        duration_ms,
    )
    return count
