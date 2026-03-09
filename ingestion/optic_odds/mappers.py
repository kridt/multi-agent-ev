"""Map Optic Odds Pydantic schemas to raw DB models."""

from datetime import datetime

from db.models.base import new_uuid
from db.models.raw import RawFixture, RawOdds, RawPlayerStats

from .schemas import OpticFixture, OpticOddsData, OpticPlayerResult


def map_fixture_to_raw(fixture: OpticFixture, fetched_at: datetime) -> RawFixture:
    """Map an OpticFixture schema to a RawFixture DB row."""
    return RawFixture(
        id=new_uuid(),
        source="optic_odds",
        source_fixture_id=fixture.id,
        raw_json=fixture.model_dump_json(),
        fetched_at=fetched_at,
        processed=False,
    )


def map_odds_to_raw(odds: OpticOddsData, fetched_at: datetime) -> RawOdds:
    """Map an OpticOddsData schema to a RawOdds DB row."""
    return RawOdds(
        id=new_uuid(),
        source="optic_odds",
        source_fixture_id=odds.fixture_id,
        source_market=odds.market,
        raw_json=odds.model_dump_json(),
        fetched_at=fetched_at,
        processed=False,
    )


def map_player_result_to_raw(result: OpticPlayerResult, fetched_at: datetime) -> RawPlayerStats:
    """Map an OpticPlayerResult schema to a RawPlayerStats DB row."""
    return RawPlayerStats(
        id=new_uuid(),
        source="optic_odds",
        source_fixture_id=result.fixture_id,
        source_player_id=result.player.id,
        raw_json=result.model_dump_json(),
        fetched_at=fetched_at,
        processed=False,
    )
