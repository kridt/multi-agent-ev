"""Exposure tracking — daily and per-fixture limits."""

from datetime import date, datetime, timezone

from sqlalchemy import and_, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from db.models.betting import Bet


class ExposureTracker:
    """Track and limit betting exposure."""

    async def get_daily_exposure(
        self, session: AsyncSession, bankroll: float, day: date | None = None
    ) -> float:
        """Sum of pending stakes today as a fraction of bankroll.

        Returns a value between 0.0 and 1.0+ (percentage as decimal).
        """
        if bankroll <= 0:
            return 0.0

        target_day = day or datetime.now(timezone.utc).date()

        stmt = select(func.coalesce(func.sum(Bet.stake_dkk), 0.0)).where(
            and_(
                Bet.outcome == "pending",
                func.date(Bet.placed_at) == target_day,
            )
        )

        result = await session.execute(stmt)
        total_stakes = result.scalar()

        return float(total_stakes) / bankroll

    async def get_fixture_exposure(
        self, session: AsyncSession, match_id: str, bankroll: float
    ) -> float:
        """Sum of stakes on this fixture as a fraction of bankroll."""
        if bankroll <= 0:
            return 0.0

        stmt = select(func.coalesce(func.sum(Bet.stake_dkk), 0.0)).where(
            and_(
                Bet.match_id == match_id,
                Bet.outcome == "pending",
            )
        )

        result = await session.execute(stmt)
        total_stakes = result.scalar()

        return float(total_stakes) / bankroll

    def check_daily_limit(self, current_exposure: float, max_pct: float = 0.10) -> bool:
        """True if under the daily exposure limit."""
        return current_exposure < max_pct

    def check_fixture_limit(self, fixture_exposure: float, max_pct: float = 0.05) -> bool:
        """True if under the per-fixture exposure limit."""
        return fixture_exposure < max_pct
