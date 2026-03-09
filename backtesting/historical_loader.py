"""Load historical data from the database for backtesting."""

from sqlalchemy import select, and_
from sqlalchemy.ext.asyncio import AsyncSession


class HistoricalLoader:
    """Load historical data from SportMonks for backtesting.

    Queries the database for settled match and player data,
    producing feature dicts suitable for walk-forward backtesting.
    """

    async def load_team_goals_data(
        self, session: AsyncSession, league_id: str | None = None
    ) -> list[dict]:
        """Load historical match data for goals O/U backtesting.

        Returns list of dicts with features and outcomes, sorted chronologically.
        Each dict contains:
        - match_id, date, market, selection
        - Feature columns (rolling averages, form, etc.)
        - outcome (bool): whether the goals line was hit
        - odds, closing_odds
        """
        from db.models.betting import Bet
        from db.models.predictions import ModelPrediction

        stmt = (
            select(ModelPrediction)
            .where(ModelPrediction.market == "team_goals_ou")
            .where(ModelPrediction.actual_outcome.isnot(None))
            .order_by(ModelPrediction.predicted_at)
        )
        result = await session.execute(stmt)
        predictions = result.scalars().all()

        data = []
        for pred in predictions:
            data.append(
                {
                    "match_id": pred.match_id,
                    "date": pred.predicted_at.strftime("%Y-%m-%d"),
                    "market": pred.market,
                    "selection": pred.selection,
                    "model_prob": pred.predicted_prob,
                    "outcome": pred.actual_outcome,
                }
            )

        return data

    async def load_team_corners_data(
        self, session: AsyncSession, league_id: str | None = None
    ) -> list[dict]:
        """Load historical match data for corners O/U backtesting.

        Returns list of dicts with features and outcomes, sorted chronologically.
        """
        from db.models.predictions import ModelPrediction

        stmt = (
            select(ModelPrediction)
            .where(ModelPrediction.market == "team_corners_ou")
            .where(ModelPrediction.actual_outcome.isnot(None))
            .order_by(ModelPrediction.predicted_at)
        )
        result = await session.execute(stmt)
        predictions = result.scalars().all()

        data = []
        for pred in predictions:
            data.append(
                {
                    "match_id": pred.match_id,
                    "date": pred.predicted_at.strftime("%Y-%m-%d"),
                    "market": pred.market,
                    "selection": pred.selection,
                    "model_prob": pred.predicted_prob,
                    "outcome": pred.actual_outcome,
                }
            )

        return data

    async def load_btts_data(
        self, session: AsyncSession, league_id: str | None = None
    ) -> list[dict]:
        """Load historical match data for BTTS backtesting.

        Returns list of dicts with features and outcomes, sorted chronologically.
        """
        from db.models.predictions import ModelPrediction

        stmt = (
            select(ModelPrediction)
            .where(ModelPrediction.market == "btts")
            .where(ModelPrediction.actual_outcome.isnot(None))
            .order_by(ModelPrediction.predicted_at)
        )
        result = await session.execute(stmt)
        predictions = result.scalars().all()

        data = []
        for pred in predictions:
            data.append(
                {
                    "match_id": pred.match_id,
                    "date": pred.predicted_at.strftime("%Y-%m-%d"),
                    "market": pred.market,
                    "selection": pred.selection,
                    "model_prob": pred.predicted_prob,
                    "outcome": pred.actual_outcome,
                }
            )

        return data

    async def load_player_props_data(
        self,
        session: AsyncSession,
        stat: str,
        league_id: str | None = None,
    ) -> list[dict]:
        """Load historical player data for player prop backtesting.

        Args:
            session: Database session.
            stat: The player stat market (e.g. "player_shots_ou", "player_tackles_ou").
            league_id: Optional league filter.

        Returns list of dicts with features and outcomes, sorted chronologically.
        """
        from db.models.predictions import ModelPrediction

        stmt = (
            select(ModelPrediction)
            .where(ModelPrediction.market == stat)
            .where(ModelPrediction.actual_outcome.isnot(None))
            .order_by(ModelPrediction.predicted_at)
        )
        result = await session.execute(stmt)
        predictions = result.scalars().all()

        data = []
        for pred in predictions:
            data.append(
                {
                    "match_id": pred.match_id,
                    "date": pred.predicted_at.strftime("%Y-%m-%d"),
                    "market": pred.market,
                    "selection": pred.selection,
                    "model_prob": pred.predicted_prob,
                    "outcome": pred.actual_outcome,
                }
            )

        return data
