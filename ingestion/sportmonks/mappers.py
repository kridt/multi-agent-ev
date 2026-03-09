"""Map SportMonks Pydantic schemas to raw DB models."""

from __future__ import annotations

import json
from datetime import datetime

from db.models.base import new_uuid
from db.models.raw import RawFixture, RawPlayerStats

from .schemas import SMFixture, SMStatistic


def map_fixture_to_raw(fixture: SMFixture, fetched_at: datetime) -> RawFixture:
    """Map an SMFixture schema to a RawFixture DB row."""
    return RawFixture(
        id=new_uuid(),
        source="sportmonks",
        source_fixture_id=str(fixture.id),
        raw_json=fixture.model_dump_json(),
        fetched_at=fetched_at,
        processed=False,
    )


def map_statistics_to_raw(
    fixture_id: int,
    stats: list[SMStatistic],
    fetched_at: datetime,
) -> list[RawPlayerStats]:
    """Map a list of SMStatistic to RawPlayerStats rows.

    Groups statistics by participant_id (player) and creates one row per player.
    Statistics without a participant_id are skipped.
    """
    # Group stats by participant_id
    by_participant: dict[int, list[SMStatistic]] = {}
    for stat in stats:
        pid = stat.participant_id
        if pid is None:
            continue
        by_participant.setdefault(pid, []).append(stat)

    rows: list[RawPlayerStats] = []
    for participant_id, player_stats in by_participant.items():
        raw_data = {
            "fixture_id": fixture_id,
            "participant_id": participant_id,
            "statistics": [s.model_dump(mode="json") for s in player_stats],
        }
        rows.append(
            RawPlayerStats(
                id=new_uuid(),
                source="sportmonks",
                source_fixture_id=str(fixture_id),
                source_player_id=str(participant_id),
                raw_json=json.dumps(raw_data),
                fetched_at=fetched_at,
                processed=False,
            )
        )
    return rows
