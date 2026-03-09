"""Closing line value (CLV) tracking and analysis."""

from datetime import datetime, timedelta, timezone

from sqlalchemy import and_, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from db.models.betting import Bet
from db.models.odds import OddsSnapshot
from ev_engine.calculator import EVCalculator


class ClosingLineTracker:
    """Track closing line value to assess betting edge quality."""

    @staticmethod
    def calculate_clv(signal_odds: float, closing_odds: float) -> float:
        """Calculate closing line value.

        CLV = (signal_odds / closing_odds) - 1
        Positive CLV = got better odds than the closing line (good).
        Negative CLV = got worse odds than the closing line (bad).
        """
        if closing_odds <= 0:
            return 0.0
        return (signal_odds / closing_odds) - 1.0

    async def capture_closing_odds(self, session: AsyncSession, match_id: str) -> int:
        """Mark the latest odds snapshot per bookmaker/market/selection as closing odds.

        Should be called shortly before kickoff.
        Returns the count of snapshots updated.
        """
        # Find the latest snapshot per bookmaker/market/selection for this match
        subq = (
            select(
                OddsSnapshot.bookmaker,
                OddsSnapshot.market,
                OddsSnapshot.selection,
                func.max(OddsSnapshot.snapshot_at).label("latest_at"),
            )
            .where(OddsSnapshot.match_id == match_id)
            .group_by(
                OddsSnapshot.bookmaker,
                OddsSnapshot.market,
                OddsSnapshot.selection,
            )
            .subquery()
        )

        # Get the IDs of those latest snapshots
        id_stmt = select(OddsSnapshot.id).join(
            subq,
            and_(
                OddsSnapshot.bookmaker == subq.c.bookmaker,
                OddsSnapshot.market == subq.c.market,
                OddsSnapshot.selection == subq.c.selection,
                OddsSnapshot.snapshot_at == subq.c.latest_at,
                OddsSnapshot.match_id == match_id,
            ),
        )

        result = await session.execute(id_stmt)
        ids = [row[0] for row in result.all()]

        if not ids:
            return 0

        # Mark them as closing
        stmt = (
            update(OddsSnapshot)
            .where(OddsSnapshot.id.in_(ids))
            .values(is_closing=True)
        )
        await session.execute(stmt)
        return len(ids)

    async def calculate_clv_for_bet(
        self, session: AsyncSession, bet_id: str
    ) -> float | None:
        """Calculate CLV for a specific bet.

        Looks up the bet's signal odds and the closing odds for the same
        market/selection/bookmaker.
        """
        # Get the bet
        bet_stmt = select(Bet).where(Bet.id == bet_id)
        result = await session.execute(bet_stmt)
        bet = result.scalar_one_or_none()

        if bet is None:
            return None

        # Find closing odds for this bet's market/selection
        closing_stmt = (
            select(OddsSnapshot)
            .where(
                and_(
                    OddsSnapshot.match_id == bet.match_id,
                    OddsSnapshot.bookmaker == bet.bookmaker,
                    OddsSnapshot.market == bet.market,
                    OddsSnapshot.selection == bet.selection,
                    OddsSnapshot.is_closing.is_(True),
                )
            )
            .order_by(OddsSnapshot.snapshot_at.desc())
            .limit(1)
        )

        closing_result = await session.execute(closing_stmt)
        closing_snap = closing_result.scalar_one_or_none()

        if closing_snap is None:
            return None

        clv = self.calculate_clv(bet.odds, closing_snap.odds)

        # Update the bet record with closing odds and CLV
        bet.closing_odds = closing_snap.odds
        bet.clv_pct = clv
        await session.flush()

        return clv

    async def get_clv_stats(
        self, session: AsyncSession, days: int = 30
    ) -> dict:
        """CLV statistics over a period.

        Returns:
            {"avg_clv": float, "pct_positive_clv": float, "total_bets": int}
        """
        cutoff = datetime.now(timezone.utc) - timedelta(days=days)

        stmt = select(Bet).where(
            and_(
                Bet.placed_at >= cutoff,
                Bet.clv_pct.isnot(None),
            )
        )

        result = await session.execute(stmt)
        bets = result.scalars().all()

        if not bets:
            return {"avg_clv": 0.0, "pct_positive_clv": 0.0, "total_bets": 0}

        clv_values = [b.clv_pct for b in bets]
        positive_count = sum(1 for v in clv_values if v > 0)

        return {
            "avg_clv": sum(clv_values) / len(clv_values),
            "pct_positive_clv": positive_count / len(clv_values),
            "total_bets": len(clv_values),
        }
