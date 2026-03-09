"""Tests for raw-data mapper functions across all three data sources."""

import json
from datetime import datetime, timezone

import pytest

from db.models.raw import RawFixture, RawOdds, RawPlayerStats


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

NOW = datetime(2026, 3, 9, 14, 30, 0, tzinfo=timezone.utc)


# ---------------------------------------------------------------------------
# Optic Odds mappers
# ---------------------------------------------------------------------------


class TestOpticOddsMappers:
    def test_map_fixture_to_raw(self):
        from ingestion.optic_odds.mappers import map_fixture_to_raw
        from ingestion.optic_odds.schemas import OpticFixture

        fixture = OpticFixture(
            id="fix-abc-123",
            sport="soccer",
            league="english-premier-league",
            home_team="Arsenal",
            away_team="Chelsea",
            start_date=datetime(2026, 3, 10, 15, 0, tzinfo=timezone.utc),
            status="pre-match",
            is_live=False,
        )

        raw = map_fixture_to_raw(fixture, NOW)

        assert isinstance(raw, RawFixture)
        assert raw.source == "optic_odds"
        assert raw.source_fixture_id == "fix-abc-123"
        assert raw.fetched_at == NOW
        assert raw.processed is False
        assert raw.id is not None

        # raw_json should be valid JSON matching the fixture
        parsed = json.loads(raw.raw_json)
        assert parsed["id"] == "fix-abc-123"
        assert parsed["home_team"] == "Arsenal"
        assert parsed["away_team"] == "Chelsea"
        assert parsed["league"] == "english-premier-league"

    def test_map_odds_to_raw(self):
        from ingestion.optic_odds.mappers import map_odds_to_raw
        from ingestion.optic_odds.schemas import OpticOddsData, OpticSelection

        odds = OpticOddsData(
            fixture_id="fix-abc-123",
            sportsbook="bet365",
            market="player_shots_ou",
            selection=OpticSelection(name="Over 2.5", odds=1.85),
            is_live=False,
        )

        raw = map_odds_to_raw(odds, NOW)

        assert isinstance(raw, RawOdds)
        assert raw.source == "optic_odds"
        assert raw.source_fixture_id == "fix-abc-123"
        assert raw.source_market == "player_shots_ou"
        assert raw.fetched_at == NOW
        assert raw.processed is False

        parsed = json.loads(raw.raw_json)
        assert parsed["sportsbook"] == "bet365"
        assert parsed["selection"]["odds"] == 1.85

    def test_map_player_result_to_raw(self):
        from ingestion.optic_odds.mappers import map_player_result_to_raw
        from ingestion.optic_odds.schemas import OpticPlayerInfo, OpticPlayerResult

        result = OpticPlayerResult(
            fixture_id="fix-abc-123",
            player=OpticPlayerInfo(id="player-001", name="Bukayo Saka", team="Arsenal"),
            stats={"shots": 4.0, "tackles": 2.0, "passes": 45.0},
        )

        raw = map_player_result_to_raw(result, NOW)

        assert isinstance(raw, RawPlayerStats)
        assert raw.source == "optic_odds"
        assert raw.source_fixture_id == "fix-abc-123"
        assert raw.source_player_id == "player-001"
        assert raw.fetched_at == NOW
        assert raw.processed is False

        parsed = json.loads(raw.raw_json)
        assert parsed["player"]["name"] == "Bukayo Saka"
        assert parsed["stats"]["shots"] == 4.0


# ---------------------------------------------------------------------------
# The Odds API mappers
# ---------------------------------------------------------------------------


class TestTheOddsAPIMappers:
    def test_map_event_to_raw(self):
        from ingestion.the_odds_api.mappers import map_event_to_raw
        from ingestion.the_odds_api.schemas import OddsAPIEvent

        event = OddsAPIEvent(
            id="evt-xyz-456",
            sport_key="soccer_epl",
            sport_title="EPL",
            commence_time=datetime(2026, 3, 10, 15, 0, tzinfo=timezone.utc),
            home_team="Liverpool",
            away_team="Man City",
        )

        raw = map_event_to_raw(event, NOW)

        assert isinstance(raw, RawFixture)
        assert raw.source == "the_odds_api"
        assert raw.source_fixture_id == "evt-xyz-456"
        assert raw.fetched_at == NOW

        parsed = json.loads(raw.raw_json)
        assert parsed["home_team"] == "Liverpool"

    def test_map_event_odds_to_raw(self):
        """OddsAPIEventOdds should also map correctly as a fixture."""
        from ingestion.the_odds_api.mappers import map_event_to_raw
        from ingestion.the_odds_api.schemas import (
            OddsAPIBookmaker,
            OddsAPIEventOdds,
            OddsAPIMarket,
            OddsAPIOutcome,
        )

        event_odds = OddsAPIEventOdds(
            id="evt-xyz-456",
            sport_key="soccer_epl",
            commence_time=datetime(2026, 3, 10, 15, 0, tzinfo=timezone.utc),
            home_team="Liverpool",
            away_team="Man City",
            bookmakers=[
                OddsAPIBookmaker(
                    key="bet365",
                    title="Bet365",
                    last_update=datetime(2026, 3, 9, 14, 0, tzinfo=timezone.utc),
                    markets=[
                        OddsAPIMarket(
                            key="h2h",
                            last_update=datetime(2026, 3, 9, 14, 0, tzinfo=timezone.utc),
                            outcomes=[
                                OddsAPIOutcome(name="Liverpool", price=2.10),
                                OddsAPIOutcome(name="Draw", price=3.40),
                                OddsAPIOutcome(name="Man City", price=3.20),
                            ],
                        ),
                    ],
                ),
            ],
        )

        raw = map_event_to_raw(event_odds, NOW)
        assert isinstance(raw, RawFixture)
        assert raw.source_fixture_id == "evt-xyz-456"

    def test_map_odds_to_raw_correct_count(self):
        """Should produce one RawOdds per market per bookmaker."""
        from ingestion.the_odds_api.mappers import map_odds_to_raw
        from ingestion.the_odds_api.schemas import (
            OddsAPIBookmaker,
            OddsAPIEventOdds,
            OddsAPIMarket,
            OddsAPIOutcome,
        )

        event_odds = OddsAPIEventOdds(
            id="evt-xyz-456",
            sport_key="soccer_epl",
            commence_time=datetime(2026, 3, 10, 15, 0, tzinfo=timezone.utc),
            home_team="Liverpool",
            away_team="Man City",
            bookmakers=[
                OddsAPIBookmaker(
                    key="bet365",
                    title="Bet365",
                    last_update=datetime(2026, 3, 9, 14, 0, tzinfo=timezone.utc),
                    markets=[
                        OddsAPIMarket(
                            key="h2h",
                            last_update=datetime(2026, 3, 9, 14, 0, tzinfo=timezone.utc),
                            outcomes=[
                                OddsAPIOutcome(name="Liverpool", price=2.10),
                                OddsAPIOutcome(name="Draw", price=3.40),
                                OddsAPIOutcome(name="Man City", price=3.20),
                            ],
                        ),
                        OddsAPIMarket(
                            key="totals",
                            last_update=datetime(2026, 3, 9, 14, 0, tzinfo=timezone.utc),
                            outcomes=[
                                OddsAPIOutcome(name="Over", price=1.90, point=2.5),
                                OddsAPIOutcome(name="Under", price=1.90, point=2.5),
                            ],
                        ),
                    ],
                ),
                OddsAPIBookmaker(
                    key="pinnacle",
                    title="Pinnacle",
                    last_update=datetime(2026, 3, 9, 13, 50, tzinfo=timezone.utc),
                    markets=[
                        OddsAPIMarket(
                            key="h2h",
                            last_update=datetime(2026, 3, 9, 13, 50, tzinfo=timezone.utc),
                            outcomes=[
                                OddsAPIOutcome(name="Liverpool", price=2.15),
                                OddsAPIOutcome(name="Draw", price=3.35),
                                OddsAPIOutcome(name="Man City", price=3.25),
                            ],
                        ),
                    ],
                ),
            ],
        )

        rows = map_odds_to_raw(event_odds, NOW)

        # bet365 has 2 markets, pinnacle has 1 = 3 total
        assert len(rows) == 3
        assert all(isinstance(r, RawOdds) for r in rows)
        assert all(r.source == "the_odds_api" for r in rows)
        assert all(r.source_fixture_id == "evt-xyz-456" for r in rows)

        # Verify markets are correct
        market_keys = [r.source_market for r in rows]
        assert market_keys.count("h2h") == 2
        assert market_keys.count("totals") == 1

        # Verify JSON is parseable and contains correct data
        for row in rows:
            parsed = json.loads(row.raw_json)
            assert "outcomes" in parsed
            assert "bookmaker_key" in parsed
            assert parsed["event_id"] == "evt-xyz-456"

    def test_map_odds_to_raw_empty_bookmakers(self):
        """Event with no bookmakers should produce an empty list."""
        from ingestion.the_odds_api.mappers import map_odds_to_raw
        from ingestion.the_odds_api.schemas import OddsAPIEventOdds

        event_odds = OddsAPIEventOdds(
            id="evt-empty",
            sport_key="soccer_epl",
            commence_time=datetime(2026, 3, 10, 15, 0, tzinfo=timezone.utc),
            home_team="Fulham",
            away_team="Brentford",
            bookmakers=[],
        )

        rows = map_odds_to_raw(event_odds, NOW)
        assert rows == []


# ---------------------------------------------------------------------------
# SportMonks mappers
# ---------------------------------------------------------------------------


class TestSportMonksMappers:
    def test_map_fixture_to_raw(self):
        from ingestion.sportmonks.mappers import map_fixture_to_raw
        from ingestion.sportmonks.schemas import SMFixture

        fixture = SMFixture(
            id=12345678,
            sport_id=1,
            league_id=8,
            season_id=21638,
            name="Arsenal vs Chelsea",
            starting_at=datetime(2026, 3, 10, 15, 0, tzinfo=timezone.utc),
        )

        raw = map_fixture_to_raw(fixture, NOW)

        assert isinstance(raw, RawFixture)
        assert raw.source == "sportmonks"
        assert raw.source_fixture_id == "12345678"  # int -> str
        assert raw.fetched_at == NOW
        assert raw.processed is False

        parsed = json.loads(raw.raw_json)
        assert parsed["id"] == 12345678
        assert parsed["league_id"] == 8

    def test_map_fixture_to_raw_missing_optional_fields(self):
        """SportMonks fixtures with missing optional fields should still map correctly."""
        from ingestion.sportmonks.mappers import map_fixture_to_raw
        from ingestion.sportmonks.schemas import SMFixture

        fixture = SMFixture(
            id=99999999,
            # All optional fields left as None/default
        )

        raw = map_fixture_to_raw(fixture, NOW)

        assert isinstance(raw, RawFixture)
        assert raw.source == "sportmonks"
        assert raw.source_fixture_id == "99999999"

        parsed = json.loads(raw.raw_json)
        assert parsed["id"] == 99999999
        assert parsed["league_id"] is None
        assert parsed["name"] is None

    def test_map_statistics_to_raw(self):
        from ingestion.sportmonks.mappers import map_statistics_to_raw
        from ingestion.sportmonks.schemas import SMStatistic

        stats = [
            SMStatistic(
                id=1,
                fixture_id=12345678,
                type_id=52,
                type={"id": 52, "name": "Shots Total", "code": "shots-total"},
                participant_id=1001,
                value={"total": 3},
            ),
            SMStatistic(
                id=2,
                fixture_id=12345678,
                type_id=56,
                type={"id": 56, "name": "Tackles", "code": "tackles"},
                participant_id=1001,
                value={"total": 5},
            ),
            SMStatistic(
                id=3,
                fixture_id=12345678,
                type_id=52,
                type={"id": 52, "name": "Shots Total", "code": "shots-total"},
                participant_id=1002,
                value={"total": 1},
            ),
        ]

        rows = map_statistics_to_raw(12345678, stats, NOW)

        # 2 unique participants -> 2 rows
        assert len(rows) == 2
        assert all(isinstance(r, RawPlayerStats) for r in rows)
        assert all(r.source == "sportmonks" for r in rows)
        assert all(r.source_fixture_id == "12345678" for r in rows)

        player_ids = {r.source_player_id for r in rows}
        assert player_ids == {"1001", "1002"}

        # Check JSON for player 1001 contains both stats
        for row in rows:
            parsed = json.loads(row.raw_json)
            assert "statistics" in parsed
            assert parsed["fixture_id"] == 12345678
            if row.source_player_id == "1001":
                assert len(parsed["statistics"]) == 2
            elif row.source_player_id == "1002":
                assert len(parsed["statistics"]) == 1

    def test_map_statistics_skips_null_participant(self):
        """Statistics without a participant_id should be skipped."""
        from ingestion.sportmonks.mappers import map_statistics_to_raw
        from ingestion.sportmonks.schemas import SMStatistic

        stats = [
            SMStatistic(
                id=10,
                fixture_id=12345678,
                type_id=52,
                participant_id=None,  # Team-level stat, no player
                value={"total": 15},
            ),
            SMStatistic(
                id=11,
                fixture_id=12345678,
                type_id=52,
                participant_id=2001,
                value={"total": 2},
            ),
        ]

        rows = map_statistics_to_raw(12345678, stats, NOW)

        # Only the stat with participant_id=2001 should be included
        assert len(rows) == 1
        assert rows[0].source_player_id == "2001"

    def test_map_statistics_empty_list(self):
        """Empty stats list should return empty rows."""
        from ingestion.sportmonks.mappers import map_statistics_to_raw

        rows = map_statistics_to_raw(12345678, [], NOW)
        assert rows == []
