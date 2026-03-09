"""End-to-end feature engineering pipeline."""

from __future__ import annotations

import logging

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from config.constants import PLAYER_ROLLING_STATS, ROLLING_WINDOWS, TEAM_ROLLING_STATS
from db.models.matches import Match, MatchStats, PlayerMatchStats
from features.consistency import ConsistencyScorer
from features.feature_store import FeatureStore
from features.opponent_adjustment import OpponentAdjuster
from features.per90 import normalize_player_stats_per90
from features.rolling import RollingCalculator

logger = logging.getLogger(__name__)


class FeaturePipeline:
    """Orchestrates feature computation for teams and players."""

    def __init__(self) -> None:
        self.rolling = RollingCalculator()
        self.consistency = ConsistencyScorer()
        self.feature_store = FeatureStore()

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @staticmethod
    async def _load_team_match_stats(
        session: AsyncSession, team_id: str, before_match_id: str, limit: int = 10
    ) -> list[MatchStats]:
        """Load the last ``limit`` MatchStats rows for a team,
        ordered by kickoff date descending, only from matches before the given match.
        """
        # First, get the kickoff time of the target match
        match_stmt = select(Match.kickoff_at).where(Match.id == before_match_id)
        match_result = await session.execute(match_stmt)
        kickoff = match_result.scalar_one_or_none()

        stmt = (
            select(MatchStats)
            .join(Match, MatchStats.match_id == Match.id)
            .where(MatchStats.team_id == team_id)
            .where(Match.status == "finished")
        )
        if kickoff is not None:
            stmt = stmt.where(Match.kickoff_at < kickoff)
        stmt = stmt.order_by(Match.kickoff_at.desc()).limit(limit)

        result = await session.execute(stmt)
        rows = list(result.scalars().all())
        # Reverse so oldest first (chronological order for rolling calcs)
        rows.reverse()
        return rows

    @staticmethod
    async def _load_player_match_stats(
        session: AsyncSession, player_id: str, before_match_id: str, limit: int = 10
    ) -> list[PlayerMatchStats]:
        """Load the last ``limit`` PlayerMatchStats rows for a player."""
        match_stmt = select(Match.kickoff_at).where(Match.id == before_match_id)
        match_result = await session.execute(match_stmt)
        kickoff = match_result.scalar_one_or_none()

        stmt = (
            select(PlayerMatchStats)
            .join(Match, PlayerMatchStats.match_id == Match.id)
            .where(PlayerMatchStats.player_id == player_id)
            .where(Match.status == "finished")
        )
        if kickoff is not None:
            stmt = stmt.where(Match.kickoff_at < kickoff)
        stmt = stmt.order_by(Match.kickoff_at.desc()).limit(limit)

        result = await session.execute(stmt)
        rows = list(result.scalars().all())
        rows.reverse()
        return rows

    @staticmethod
    def _extract_stat_series(rows: list, stat_name: str) -> list[float]:
        """Extract a single stat as a list of floats from ORM rows."""
        values: list[float] = []
        for row in rows:
            val = getattr(row, stat_name, None)
            if val is not None:
                values.append(float(val))
        return values

    # ------------------------------------------------------------------
    # Public feature builders
    # ------------------------------------------------------------------

    async def build_team_features(
        self, session: AsyncSession, team_id: str, match_id: str, opponent_id: str
    ) -> dict:
        """Build complete feature vector for a team in a match.

        Steps:
            1. Load last 10 match stats for this team from DB.
            2. Compute rolling windows (3, 5, 10) for key stats.
            3. Load opponent's defensive stats.
            4. Apply opponent adjustments.
            5. Compute consistency scores.
            6. Return feature dict.
        """
        # 1. Load team history
        team_rows = await self._load_team_match_stats(session, team_id, match_id)

        # 2. Rolling windows for each stat
        rolling_features: dict = {}
        for stat_name in TEAM_ROLLING_STATS:
            values = self._extract_stat_series(team_rows, stat_name)
            rolling_features[stat_name] = self.rolling.compute_all_windows(
                values, ROLLING_WINDOWS
            )

        # 3. Opponent defensive stats
        opp_rows = await self._load_team_match_stats(session, opponent_id, match_id)
        opponent_averages: dict[str, float] = {}
        for stat_name in TEAM_ROLLING_STATS:
            opp_values = self._extract_stat_series(opp_rows, stat_name)
            if opp_values:
                opponent_averages[stat_name] = sum(opp_values) / len(opp_values)
            else:
                opponent_averages[stat_name] = 0.0

        # Compute league averages from both teams' data (approximation)
        all_rows = team_rows + opp_rows
        league_averages: dict[str, float] = {}
        for stat_name in TEAM_ROLLING_STATS:
            all_values = self._extract_stat_series(all_rows, stat_name)
            if all_values:
                league_averages[stat_name] = sum(all_values) / len(all_values)
            else:
                league_averages[stat_name] = 0.0

        # 4. Opponent adjustments on the rolling means (w5)
        adjuster = OpponentAdjuster(league_averages)
        raw_means: dict[str, float] = {}
        for stat_name in TEAM_ROLLING_STATS:
            w5 = rolling_features[stat_name].get("w5", {})
            mean_val = w5.get("mean")
            raw_means[stat_name] = mean_val if mean_val is not None else 0.0

        adjusted = adjuster.adjust_batch(raw_means, opponent_averages)

        # 5. Consistency scores
        consistency: dict = {}
        for stat_name in TEAM_ROLLING_STATS:
            values = self._extract_stat_series(team_rows, stat_name)
            consistency[stat_name] = self.consistency.score_player(values, window=10)

        return {
            "team_id": team_id,
            "rolling": rolling_features,
            "opponent_adjusted": adjusted,
            "consistency": consistency,
        }

    async def build_player_features(
        self, session: AsyncSession, player_id: str, match_id: str, opponent_id: str
    ) -> dict:
        """Build complete feature vector for a player in a match.

        Steps:
            1. Load last 10 player match stats.
            2. Per-90 normalize.
            3. Compute rolling windows for key stats.
            4. Opponent adjustments.
            5. Consistency scores.
            6. Return feature dict.
        """
        # 1. Load player history
        player_rows = await self._load_player_match_stats(
            session, player_id, match_id
        )

        # 2. Per-90 normalize each match's stats
        per90_series: dict[str, list[float]] = {s: [] for s in PLAYER_ROLLING_STATS}
        for row in player_rows:
            raw_stats = {s: float(getattr(row, s, 0)) for s in PLAYER_ROLLING_STATS}
            normalized = normalize_player_stats_per90(raw_stats, row.minutes_played)
            for s in PLAYER_ROLLING_STATS:
                val = normalized.get(s)
                if val is not None:
                    per90_series[s].append(val)

        # 3. Rolling windows on per-90 values
        rolling_features: dict = {}
        for stat_name in PLAYER_ROLLING_STATS:
            rolling_features[stat_name] = self.rolling.compute_all_windows(
                per90_series[stat_name], ROLLING_WINDOWS
            )

        # 4. Opponent adjustments
        opp_rows = await self._load_team_match_stats(session, opponent_id, match_id)
        opponent_averages: dict[str, float] = {}
        for stat_name in PLAYER_ROLLING_STATS:
            opp_values = self._extract_stat_series(opp_rows, stat_name)
            if opp_values:
                opponent_averages[stat_name] = sum(opp_values) / len(opp_values)
            else:
                opponent_averages[stat_name] = 0.0

        # Simple league averages from opponent data
        league_averages = dict(opponent_averages)  # fallback approximation
        adjuster = OpponentAdjuster(league_averages)

        raw_means: dict[str, float] = {}
        for stat_name in PLAYER_ROLLING_STATS:
            w5 = rolling_features[stat_name].get("w5", {})
            mean_val = w5.get("mean")
            raw_means[stat_name] = mean_val if mean_val is not None else 0.0

        adjusted = adjuster.adjust_batch(raw_means, opponent_averages)

        # 5. Consistency scores
        consistency: dict = {}
        for stat_name in PLAYER_ROLLING_STATS:
            consistency[stat_name] = self.consistency.score_player(
                per90_series[stat_name], window=10
            )

        return {
            "player_id": player_id,
            "rolling": rolling_features,
            "opponent_adjusted": adjusted,
            "consistency": consistency,
        }

    async def build_match_features(self, session: AsyncSession, match_id: str) -> dict:
        """Build features for all entities in a match.

        Returns::

            {
                "home_team": {...},
                "away_team": {...},
                "players": {"player_id": {...}, ...},
            }
        """
        # Load match to get team IDs
        stmt = select(Match).where(Match.id == match_id)
        result = await session.execute(stmt)
        match = result.scalar_one_or_none()
        if match is None:
            raise ValueError(f"Match {match_id} not found")

        home_team_id = match.home_team_id
        away_team_id = match.away_team_id

        # Build team features
        home_features = await self.build_team_features(
            session, home_team_id, match_id, away_team_id
        )
        away_features = await self.build_team_features(
            session, away_team_id, match_id, home_team_id
        )

        # Build player features for all players who have stats in recent matches
        # for both teams
        player_features: dict[str, dict] = {}

        for team_id, opponent_id in [
            (home_team_id, away_team_id),
            (away_team_id, home_team_id),
        ]:
            # Find players with stats for this team
            player_stmt = (
                select(PlayerMatchStats.player_id)
                .join(Match, PlayerMatchStats.match_id == Match.id)
                .where(PlayerMatchStats.team_id == team_id)
                .where(Match.status == "finished")
                .distinct()
            )
            player_result = await session.execute(player_stmt)
            player_ids = [row[0] for row in player_result.all()]

            for pid in player_ids:
                try:
                    pf = await self.build_player_features(
                        session, pid, match_id, opponent_id
                    )
                    player_features[pid] = pf
                except Exception:
                    logger.warning(
                        "Failed to build features for player %s in match %s",
                        pid,
                        match_id,
                        exc_info=True,
                    )

        return {
            "home_team": home_features,
            "away_team": away_features,
            "players": player_features,
        }

    async def build_and_store(self, session: AsyncSession, match_id: str) -> int:
        """Build features and store in DB. Returns count of feature vectors stored."""
        match_features = await self.build_match_features(session, match_id)
        count = 0

        # Store home team
        await self.feature_store.save_features(
            session,
            match_id=match_id,
            entity_type="team",
            entity_id=match_features["home_team"]["team_id"],
            features=match_features["home_team"],
        )
        count += 1

        # Store away team
        await self.feature_store.save_features(
            session,
            match_id=match_id,
            entity_type="team",
            entity_id=match_features["away_team"]["team_id"],
            features=match_features["away_team"],
        )
        count += 1

        # Store player features
        for player_id, pf in match_features["players"].items():
            await self.feature_store.save_features(
                session,
                match_id=match_id,
                entity_type="player",
                entity_id=player_id,
                features=pf,
            )
            count += 1

        return count
