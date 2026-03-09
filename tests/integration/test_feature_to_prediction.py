"""Feature pipeline to model prediction integration tests.

Tests the full chain:
  1. Create match stats in DB (historical finished matches + a target upcoming match).
  2. Run FeaturePipeline.build_team_features / build_match_features.
  3. Verify per-90 and rolling computations on stats loaded from DB.
  4. Feed features into OpponentAdjuster.
  5. Store features via FeatureStore.
  6. Create and store a ModelPrediction in DB.
  7. Verify prediction output format and DB persistence.

Key facts:
  - FeaturePipeline._load_team_match_stats only loads matches with status="finished"
    and with kickoff_at < target match's kickoff_at.
  - FeatureStore.save_features serialises the feature dict to JSON in the DB.
  - ModelPrediction.predicted_prob must be a float in [0, 1].
  - FeatureVector.entity_type must be one of "team" or "player" (DB Enum).
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from db.models.base import new_uuid
from db.models.entities import League, Player, Team
from db.models.matches import Match, MatchStats, PlayerMatchStats
from db.models.predictions import FeatureVector, ModelPrediction
from features.feature_store import FeatureStore
from features.opponent_adjustment import OpponentAdjuster
from features.per90 import normalize_per90, normalize_player_stats_per90
from features.pipeline import FeaturePipeline
from features.rolling import RollingCalculator


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


async def _create_league(session: AsyncSession, name: str = "Test League") -> str:
    league = League(id=new_uuid(), name=name, country="Test", active=True)
    session.add(league)
    await session.flush()
    return league.id


async def _create_team(
    session: AsyncSession, name: str, league_id: str
) -> str:
    team = Team(id=new_uuid(), name=name, league_id=league_id, active=True)
    session.add(team)
    await session.flush()
    return team.id


async def _create_player(
    session: AsyncSession, name: str, team_id: str
) -> str:
    player = Player(id=new_uuid(), name=name, team_id=team_id, active=True)
    session.add(player)
    await session.flush()
    return player.id


async def _create_finished_match(
    session: AsyncSession,
    league_id: str,
    home_id: str,
    away_id: str,
    kickoff_offset_days: int,
    home_goals: int = 1,
    away_goals: int = 1,
) -> str:
    """Create a finished match ``kickoff_offset_days`` days in the past."""
    match = Match(
        id=new_uuid(),
        league_id=league_id,
        home_team_id=home_id,
        away_team_id=away_id,
        kickoff_at=_utcnow() - timedelta(days=kickoff_offset_days),
        status="finished",
        home_goals=home_goals,
        away_goals=away_goals,
    )
    session.add(match)
    await session.flush()
    return match.id


async def _create_target_match(
    session: AsyncSession,
    league_id: str,
    home_id: str,
    away_id: str,
) -> str:
    """Create an upcoming scheduled match (target for feature computation)."""
    match = Match(
        id=new_uuid(),
        league_id=league_id,
        home_team_id=home_id,
        away_team_id=away_id,
        kickoff_at=_utcnow() + timedelta(hours=24),
        status="scheduled",
    )
    session.add(match)
    await session.flush()
    return match.id


async def _add_match_stats(
    session: AsyncSession,
    match_id: str,
    team_id: str,
    is_home: bool,
    goals: int = 1,
    shots: int = 10,
    corners: int = 4,
    possession_pct: float = 50.0,
    passes: int = 400,
    xg: float = 1.2,
) -> str:
    stats = MatchStats(
        id=new_uuid(),
        match_id=match_id,
        team_id=team_id,
        is_home=is_home,
        goals=goals,
        shots=shots,
        shots_on_target=max(1, shots // 3),
        corners=corners,
        fouls=10,
        possession_pct=possession_pct,
        passes=passes,
        xg=xg,
    )
    session.add(stats)
    await session.flush()
    return stats.id


async def _add_player_match_stats(
    session: AsyncSession,
    match_id: str,
    player_id: str,
    team_id: str,
    minutes_played: int = 90,
    goals: int = 0,
    shots: int = 2,
    passes: int = 40,
    tackles: int = 2,
    key_passes: int = 1,
) -> str:
    stats = PlayerMatchStats(
        id=new_uuid(),
        match_id=match_id,
        player_id=player_id,
        team_id=team_id,
        minutes_played=minutes_played,
        goals=goals,
        assists=0,
        shots=shots,
        shots_on_target=max(0, shots // 2),
        key_passes=key_passes,
        passes=passes,
        tackles=tackles,
        interceptions=1,
    )
    session.add(stats)
    await session.flush()
    return stats.id


# ---------------------------------------------------------------------------
# Feature pipeline unit-style sanity tests (with DB)
# ---------------------------------------------------------------------------

class TestPer90WithDBStats:
    """Verify per-90 normalisation produces correct values for stats from DB rows."""

    async def test_per90_normalization_90_minutes(
        self, db_session: AsyncSession
    ) -> None:
        """Stats for a 90-minute player normalize correctly."""
        # 2 shots in 90 minutes = 2.0 per 90
        result = normalize_per90(2, 90)
        assert result == pytest.approx(2.0)

    async def test_per90_normalization_partial_minutes(
        self, db_session: AsyncSession
    ) -> None:
        """Stats for 45 minutes: 1 goal => 2.0 per 90."""
        result = normalize_per90(1, 45)
        assert result == pytest.approx(2.0)

    async def test_per90_excludes_below_minimum(
        self, db_session: AsyncSession
    ) -> None:
        """Less than 15 minutes played returns None."""
        result = normalize_per90(3, 10)
        assert result is None

    async def test_normalize_player_stats_dict(
        self, db_session: AsyncSession
    ) -> None:
        """normalize_player_stats_per90 normalizes applicable stats and
        passes through rate-based stats unchanged."""
        stats = {"goals": 2, "shots": 4, "pass_accuracy_pct": 85.0, "xg": 0.8}
        result = normalize_player_stats_per90(stats, 90)

        assert result["goals"] == pytest.approx(2.0)  # 2 * 90 / 90 = 2.0
        assert result["shots"] == pytest.approx(4.0)   # 4 * 90 / 90 = 4.0
        # Rate-based: unchanged
        assert result["pass_accuracy_pct"] == pytest.approx(85.0)
        assert result["xg"] == pytest.approx(0.8)


class TestRollingCalculatorWithHistoricalData:
    """RollingCalculator tests using realistic historical value sequences."""

    def test_rolling_mean_window_3(self) -> None:
        """Mean of last 3 values of [1.0, 1.5, 2.0, 2.5, 3.0] = 2.5."""
        values = [1.0, 1.5, 2.0, 2.5, 3.0]
        result = RollingCalculator.rolling_mean(values, 3)
        assert result == pytest.approx((2.0 + 2.5 + 3.0) / 3)

    def test_rolling_std_returns_none_insufficient_data(self) -> None:
        """Window > len(values) returns None."""
        result = RollingCalculator.rolling_std([1.0, 2.0], 5)
        assert result is None

    def test_compute_all_windows_structure(self) -> None:
        """compute_all_windows returns correct key structure."""
        values = list(range(1, 11))
        result = RollingCalculator.compute_all_windows(values, [3, 5, 10])
        assert set(result.keys()) == {"w3", "w5", "w10"}
        for key in result:
            assert set(result[key].keys()) == {"mean", "median", "std", "trend"}

    def test_compute_all_windows_insufficient_data_returns_none(self) -> None:
        """Values shorter than window produce None for all stats in that window."""
        result = RollingCalculator.compute_all_windows([1.0, 2.0], [3, 5])
        # w3 and w5 both need more data than available
        assert result["w3"]["mean"] is None
        assert result["w5"]["mean"] is None


# ---------------------------------------------------------------------------
# FeaturePipeline with real DB
# ---------------------------------------------------------------------------

class TestFeaturePipelineWithDB:
    """FeaturePipeline reads from DB and computes features correctly."""

    async def test_build_team_features_returns_correct_structure(
        self, db_session: AsyncSession
    ) -> None:
        """build_team_features returns dict with team_id, rolling,
        opponent_adjusted, and consistency keys."""
        league_id = await _create_league(db_session)
        home_id = await _create_team(db_session, "Team Alpha", league_id)
        away_id = await _create_team(db_session, "Team Beta", league_id)

        # Create 5 finished matches for home_id and away_id (before target)
        for i in range(1, 6):
            m_id = await _create_finished_match(
                db_session, league_id, home_id, away_id,
                kickoff_offset_days=i * 7
            )
            await _add_match_stats(
                db_session, m_id, home_id, is_home=True,
                goals=i % 3, shots=8 + i, corners=3 + (i % 3),
                possession_pct=48.0 + i, passes=380 + i * 5,
            )
            await _add_match_stats(
                db_session, m_id, away_id, is_home=False,
                goals=(i + 1) % 3, shots=7 + i, corners=2 + (i % 4),
                possession_pct=52.0 - i, passes=400 - i * 5,
            )

        target_match_id = await _create_target_match(
            db_session, league_id, home_id, away_id
        )

        pipeline = FeaturePipeline()
        features = await pipeline.build_team_features(
            db_session, home_id, target_match_id, away_id
        )

        assert features["team_id"] == home_id
        assert "rolling" in features
        assert "opponent_adjusted" in features
        assert "consistency" in features

        # Rolling structure should include all TEAM_ROLLING_STATS
        for stat_name in ["goals", "shots", "corners", "possession_pct", "passes"]:
            assert stat_name in features["rolling"]
            for window_key in ["w3", "w5", "w10"]:
                assert window_key in features["rolling"][stat_name]

    async def test_build_team_features_rolling_mean_matches_data(
        self, db_session: AsyncSession
    ) -> None:
        """Rolling mean values are consistent with the data inserted.

        Insert 5 matches with known goals (1, 2, 3, 4, 5).
        w3 mean should be mean of last 3 = (3+4+5)/3 = 4.0.
        """
        league_id = await _create_league(db_session)
        home_id = await _create_team(db_session, "Known Team", league_id)
        away_id = await _create_team(db_session, "Opponent", league_id)

        # Insert 5 finished matches, goals increasing from 1 to 5 (oldest first)
        for i in range(1, 6):
            m_id = await _create_finished_match(
                db_session, league_id, home_id, away_id,
                kickoff_offset_days=(6 - i) * 7  # day-35, day-28, ..., day-7
            )
            await _add_match_stats(
                db_session, m_id, home_id, is_home=True,
                goals=i, shots=10, corners=4, possession_pct=50.0, passes=400,
            )
            await _add_match_stats(
                db_session, m_id, away_id, is_home=False,
                goals=1, shots=8, corners=3, possession_pct=50.0, passes=380,
            )

        target_match_id = await _create_target_match(
            db_session, league_id, home_id, away_id
        )

        pipeline = FeaturePipeline()
        features = await pipeline.build_team_features(
            db_session, home_id, target_match_id, away_id
        )

        # Goals series (chronological): [1, 2, 3, 4, 5]
        # w3 mean = (3 + 4 + 5) / 3 = 4.0
        goals_w3_mean = features["rolling"]["goals"]["w3"]["mean"]
        assert goals_w3_mean is not None
        assert goals_w3_mean == pytest.approx(4.0, rel=1e-3)

    async def test_build_match_features_returns_both_teams(
        self, db_session: AsyncSession
    ) -> None:
        """build_match_features returns home_team and away_team sub-dicts."""
        league_id = await _create_league(db_session)
        home_id = await _create_team(db_session, "Home Club", league_id)
        away_id = await _create_team(db_session, "Away Club", league_id)

        # Need at least some historical matches for pipeline to process
        for i in range(1, 4):
            m_id = await _create_finished_match(
                db_session, league_id, home_id, away_id,
                kickoff_offset_days=i * 7
            )
            await _add_match_stats(
                db_session, m_id, home_id, is_home=True,
                goals=1, shots=9, corners=3, possession_pct=50.0, passes=390,
            )
            await _add_match_stats(
                db_session, m_id, away_id, is_home=False,
                goals=1, shots=8, corners=3, possession_pct=50.0, passes=380,
            )

        target_match_id = await _create_target_match(
            db_session, league_id, home_id, away_id
        )

        pipeline = FeaturePipeline()
        match_features = await pipeline.build_match_features(
            db_session, target_match_id
        )

        assert "home_team" in match_features
        assert "away_team" in match_features
        assert "players" in match_features

        assert match_features["home_team"]["team_id"] == home_id
        assert match_features["away_team"]["team_id"] == away_id

    async def test_build_and_store_writes_feature_vectors(
        self, db_session: AsyncSession
    ) -> None:
        """build_and_store persists FeatureVector rows to DB (at least 2 for teams)."""
        league_id = await _create_league(db_session)
        home_id = await _create_team(db_session, "Home FC", league_id)
        away_id = await _create_team(db_session, "Away FC", league_id)

        for i in range(1, 4):
            m_id = await _create_finished_match(
                db_session, league_id, home_id, away_id,
                kickoff_offset_days=i * 7
            )
            await _add_match_stats(
                db_session, m_id, home_id, is_home=True,
                goals=1, shots=9, corners=3, possession_pct=50.0, passes=390,
            )
            await _add_match_stats(
                db_session, m_id, away_id, is_home=False,
                goals=0, shots=7, corners=2, possession_pct=50.0, passes=370,
            )

        target_match_id = await _create_target_match(
            db_session, league_id, home_id, away_id
        )

        pipeline = FeaturePipeline()
        count = await pipeline.build_and_store(db_session, target_match_id)

        # At minimum 2 feature vectors (home + away teams)
        assert count >= 2

        # Verify DB rows exist
        stmt = select(FeatureVector).where(FeatureVector.match_id == target_match_id)
        result = await db_session.execute(stmt)
        rows = result.scalars().all()
        assert len(rows) >= 2

        # All rows should have parseable JSON features
        for row in rows:
            parsed = json.loads(row.features)
            assert isinstance(parsed, dict)
            assert "rolling" in parsed

    async def test_feature_pipeline_empty_history_returns_none_for_rolling(
        self, db_session: AsyncSession
    ) -> None:
        """With no historical data, rolling stats are all None (insufficient data)."""
        league_id = await _create_league(db_session)
        home_id = await _create_team(db_session, "No History FC", league_id)
        away_id = await _create_team(db_session, "No History United", league_id)

        target_match_id = await _create_target_match(
            db_session, league_id, home_id, away_id
        )

        pipeline = FeaturePipeline()
        features = await pipeline.build_team_features(
            db_session, home_id, target_match_id, away_id
        )

        # With no historical matches, all rolling means should be None
        for stat_name in ["goals", "shots", "corners"]:
            for window_key in ["w3", "w5", "w10"]:
                assert features["rolling"][stat_name][window_key]["mean"] is None


# ---------------------------------------------------------------------------
# FeatureStore tests
# ---------------------------------------------------------------------------

class TestFeatureStore:
    """FeatureStore persistence layer tests."""

    async def test_save_and_retrieve_features(
        self, db_session: AsyncSession
    ) -> None:
        """save_features stores JSON; get_features retrieves the original dict."""
        league_id = await _create_league(db_session)
        home_id = await _create_team(db_session, "Store Team A", league_id)
        away_id = await _create_team(db_session, "Store Team B", league_id)

        target_match_id = await _create_target_match(
            db_session, league_id, home_id, away_id
        )

        features_dict = {
            "team_id": home_id,
            "rolling": {"goals": {"w3": {"mean": 1.5}}},
            "opponent_adjusted": {"goals": 1.2},
        }

        store = FeatureStore()
        fv_id = await store.save_features(
            db_session,
            match_id=target_match_id,
            entity_type="team",
            entity_id=home_id,
            features=features_dict,
            version="v1",
        )
        assert fv_id is not None

        retrieved = await store.get_features(
            db_session, match_id=target_match_id, entity_id=home_id, version="v1"
        )
        assert retrieved is not None
        assert retrieved["team_id"] == home_id
        assert retrieved["rolling"]["goals"]["w3"]["mean"] == pytest.approx(1.5)

    async def test_save_features_returns_uuid(
        self, db_session: AsyncSession
    ) -> None:
        """save_features returns a non-empty string (UUID)."""
        league_id = await _create_league(db_session)
        home_id = await _create_team(db_session, "UUID Team", league_id)
        away_id = await _create_team(db_session, "UUID Opp", league_id)

        target_match_id = await _create_target_match(
            db_session, league_id, home_id, away_id
        )

        store = FeatureStore()
        fv_id = await store.save_features(
            db_session,
            match_id=target_match_id,
            entity_type="team",
            entity_id=home_id,
            features={"x": 1},
        )
        assert isinstance(fv_id, str)
        assert len(fv_id) == 36  # UUID format

    async def test_get_features_returns_none_for_missing(
        self, db_session: AsyncSession
    ) -> None:
        """get_features returns None when no feature vector exists."""
        store = FeatureStore()
        result = await store.get_features(
            db_session,
            match_id=new_uuid(),
            entity_id=new_uuid(),
            version="v1",
        )
        assert result is None

    async def test_get_features_for_match_returns_all_entities(
        self, db_session: AsyncSession
    ) -> None:
        """get_features_for_match returns one entry per entity stored."""
        league_id = await _create_league(db_session)
        home_id = await _create_team(db_session, "Both Team A", league_id)
        away_id = await _create_team(db_session, "Both Team B", league_id)

        target_match_id = await _create_target_match(
            db_session, league_id, home_id, away_id
        )

        store = FeatureStore()
        await store.save_features(
            db_session,
            match_id=target_match_id,
            entity_type="team",
            entity_id=home_id,
            features={"team_id": home_id, "rolling": {}},
        )
        await store.save_features(
            db_session,
            match_id=target_match_id,
            entity_type="team",
            entity_id=away_id,
            features={"team_id": away_id, "rolling": {}},
        )

        all_fvs = await store.get_features_for_match(
            db_session, match_id=target_match_id
        )
        assert len(all_fvs) == 2
        entity_ids = {fv["entity_id"] for fv in all_fvs}
        assert entity_ids == {home_id, away_id}


# ---------------------------------------------------------------------------
# ModelPrediction storage tests
# ---------------------------------------------------------------------------

class TestModelPredictionStorage:
    """Store and retrieve ModelPrediction rows from DB."""

    async def test_store_model_prediction_and_query(
        self, db_session: AsyncSession
    ) -> None:
        """A ModelPrediction row is stored and all fields are correctly set."""
        league_id = await _create_league(db_session)
        home_id = await _create_team(db_session, "Pred Team A", league_id)
        away_id = await _create_team(db_session, "Pred Team B", league_id)

        target_match_id = await _create_target_match(
            db_session, league_id, home_id, away_id
        )

        pred = ModelPrediction(
            id=new_uuid(),
            match_id=target_match_id,
            model_type="poisson",
            model_version="v1",
            market="team_goals_ou",
            selection="over_2.5",
            predicted_prob=0.55,
            predicted_at=_utcnow(),
        )
        db_session.add(pred)
        await db_session.flush()

        row = await db_session.get(ModelPrediction, pred.id)
        assert row is not None
        assert row.match_id == target_match_id
        assert row.model_type == "poisson"
        assert row.model_version == "v1"
        assert row.market == "team_goals_ou"
        assert row.selection == "over_2.5"
        assert row.predicted_prob == pytest.approx(0.55)
        assert row.actual_outcome is None  # Not yet known

    async def test_store_multiple_predictions_for_same_match(
        self, db_session: AsyncSession
    ) -> None:
        """Multiple predictions for different markets can coexist for the same match."""
        league_id = await _create_league(db_session)
        home_id = await _create_team(db_session, "Multi Pred A", league_id)
        away_id = await _create_team(db_session, "Multi Pred B", league_id)

        target_match_id = await _create_target_match(
            db_session, league_id, home_id, away_id
        )

        predictions_data = [
            ("team_goals_ou", "over_2.5", 0.55),
            ("btts", "yes", 0.48),
            ("team_goals_ou", "under_2.5", 0.45),
        ]

        pred_ids = []
        for market, selection, prob in predictions_data:
            pred = ModelPrediction(
                id=new_uuid(),
                match_id=target_match_id,
                model_type="poisson",
                model_version="v1",
                market=market,
                selection=selection,
                predicted_prob=prob,
                predicted_at=_utcnow(),
            )
            db_session.add(pred)
            pred_ids.append(pred.id)
        await db_session.flush()

        stmt = select(ModelPrediction).where(
            ModelPrediction.match_id == target_match_id
        )
        result = await db_session.execute(stmt)
        rows = result.scalars().all()

        assert len(rows) == 3
        stored_markets = {(r.market, r.selection) for r in rows}
        assert ("team_goals_ou", "over_2.5") in stored_markets
        assert ("btts", "yes") in stored_markets
        assert ("team_goals_ou", "under_2.5") in stored_markets

    async def test_prediction_actual_outcome_can_be_set(
        self, db_session: AsyncSession
    ) -> None:
        """actual_outcome can be set after the match result is known."""
        league_id = await _create_league(db_session)
        home_id = await _create_team(db_session, "Outcome Team A", league_id)
        away_id = await _create_team(db_session, "Outcome Team B", league_id)

        target_match_id = await _create_target_match(
            db_session, league_id, home_id, away_id
        )

        pred = ModelPrediction(
            id=new_uuid(),
            match_id=target_match_id,
            model_type="poisson",
            model_version="v1",
            market="team_goals_ou",
            selection="over_2.5",
            predicted_prob=0.55,
            predicted_at=_utcnow(),
        )
        db_session.add(pred)
        await db_session.flush()

        # Simulate result: over 2.5 goals happened = True
        pred.actual_outcome = True
        await db_session.flush()

        row = await db_session.get(ModelPrediction, pred.id)
        assert row is not None
        assert row.actual_outcome is True


# ---------------------------------------------------------------------------
# OpponentAdjuster integration test (logic layer, no DB needed)
# ---------------------------------------------------------------------------

class TestOpponentAdjusterLogic:
    """OpponentAdjuster produces correct adjustments for realistic football data."""

    def test_adjusted_value_when_facing_weak_defence(self) -> None:
        """Team with raw xg=1.5 facing weak defence (avg_allowed=2.0 vs league avg=1.3)
        should have xg adjusted DOWNWARD.

        Formula: adjusted = raw_stat * league_avg / opponent_avg
        adjusted = 1.5 * 1.3 / 2.0 = 0.975
        """
        adjuster = OpponentAdjuster({"xg": 1.3})
        result = adjuster.adjust(
            raw_stat=1.5,
            opponent_stat_avg=2.0,
            stat_name="xg",
        )
        assert result == pytest.approx(1.5 * 1.3 / 2.0, rel=1e-6)

    def test_adjusted_value_when_facing_strong_defence(self) -> None:
        """Team with raw xg=1.5 facing strong defence (avg_allowed=0.8 vs league avg=1.3)
        should have xg adjusted UPWARD.

        adjusted = 1.5 * 1.3 / 0.8 = 2.4375
        """
        adjuster = OpponentAdjuster({"xg": 1.3})
        result = adjuster.adjust(
            raw_stat=1.5,
            opponent_stat_avg=0.8,
            stat_name="xg",
        )
        assert result == pytest.approx(1.5 * 1.3 / 0.8, rel=1e-6)

    def test_adjust_batch_all_stats(self) -> None:
        """adjust_batch applies correct adjustments to all stats simultaneously."""
        league_averages = {"goals": 1.3, "shots": 11.5, "corners": 5.0}
        adjuster = OpponentAdjuster(league_averages)

        raw_stats = {"goals": 1.5, "shots": 13.0, "corners": 6.0}
        opp_avgs = {"goals": 1.0, "shots": 10.0, "corners": 4.5}

        result = adjuster.adjust_batch(raw_stats, opp_avgs)

        assert result["goals"] == pytest.approx(1.5 * 1.3 / 1.0, rel=1e-6)
        assert result["shots"] == pytest.approx(13.0 * 11.5 / 10.0, rel=1e-6)
        assert result["corners"] == pytest.approx(6.0 * 5.0 / 4.5, rel=1e-6)

    def test_compute_league_averages_from_team_stats(self) -> None:
        """compute_league_averages computes the mean across all teams correctly."""
        team_stats = [
            {"goals": 2.0, "shots": 12.0},
            {"goals": 1.0, "shots": 10.0},
            {"goals": 1.5, "shots": 11.0},
        ]
        averages = OpponentAdjuster.compute_league_averages(team_stats)
        assert averages["goals"] == pytest.approx(1.5, rel=1e-6)
        assert averages["shots"] == pytest.approx(11.0, rel=1e-6)
