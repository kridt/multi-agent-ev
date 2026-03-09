"""Odds comparison across bookmakers."""

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession

from config.bookmakers import TARGET_BOOKMAKERS
from db.models.odds import OddsSnapshot
from ev_engine.calculator import EVCalculator


@dataclass
class BestPrice:
    bookmaker: str
    odds: float
    implied_prob: float
    source: str


class OddsComparer:
    """Compare odds across bookmakers to find best available prices."""

    async def find_best_price(
        self, session: AsyncSession, match_id: str, market: str, selection: str
    ) -> BestPrice | None:
        """Find best odds across target bookmakers for a market/selection.

        Queries the odds_snapshots table, filters to target bookmakers,
        returns the highest odds available.
        """
        target_keys = [b.optic_odds_key for b in TARGET_BOOKMAKERS.values()]

        stmt = (
            select(OddsSnapshot)
            .where(
                and_(
                    OddsSnapshot.match_id == match_id,
                    OddsSnapshot.market == market,
                    OddsSnapshot.selection == selection,
                    OddsSnapshot.bookmaker.in_(target_keys),
                )
            )
            .order_by(OddsSnapshot.snapshot_at.desc())
        )

        result = await session.execute(stmt)
        snapshots = result.scalars().all()

        if not snapshots:
            return None

        # Get latest snapshot per bookmaker, then find best price
        latest_by_book: dict[str, OddsSnapshot] = {}
        for snap in snapshots:
            if snap.bookmaker not in latest_by_book:
                latest_by_book[snap.bookmaker] = snap

        best = max(latest_by_book.values(), key=lambda s: s.odds)
        return BestPrice(
            bookmaker=best.bookmaker,
            odds=best.odds,
            implied_prob=EVCalculator.calculate_implied_prob(best.odds),
            source=best.source,
        )

    async def get_all_prices(
        self, session: AsyncSession, match_id: str, market: str, selection: str
    ) -> list[BestPrice]:
        """Get odds from all bookmakers for comparison."""
        stmt = (
            select(OddsSnapshot)
            .where(
                and_(
                    OddsSnapshot.match_id == match_id,
                    OddsSnapshot.market == market,
                    OddsSnapshot.selection == selection,
                )
            )
            .order_by(OddsSnapshot.snapshot_at.desc())
        )

        result = await session.execute(stmt)
        snapshots = result.scalars().all()

        # Latest per bookmaker
        latest_by_book: dict[str, OddsSnapshot] = {}
        for snap in snapshots:
            if snap.bookmaker not in latest_by_book:
                latest_by_book[snap.bookmaker] = snap

        return [
            BestPrice(
                bookmaker=snap.bookmaker,
                odds=snap.odds,
                implied_prob=EVCalculator.calculate_implied_prob(snap.odds),
                source=snap.source,
            )
            for snap in latest_by_book.values()
        ]

    @staticmethod
    def calculate_market_margin(prices: list[BestPrice]) -> float:
        """Calculate bookmaker margin from a set of prices."""
        if not prices:
            return 0.0
        return sum(p.implied_prob for p in prices) - 1.0

    async def detect_odds_movement(
        self,
        session: AsyncSession,
        match_id: str,
        market: str,
        selection: str,
        hours: int = 24,
    ) -> dict | None:
        """Detect odds movement direction and magnitude.

        Returns:
            {"direction": "shortening"|"drifting"|"stable",
             "change_pct": float, "opening": float, "current": float}
        """
        cutoff = datetime.now(timezone.utc) - timedelta(hours=hours)

        stmt = (
            select(OddsSnapshot)
            .where(
                and_(
                    OddsSnapshot.match_id == match_id,
                    OddsSnapshot.market == market,
                    OddsSnapshot.selection == selection,
                    OddsSnapshot.snapshot_at >= cutoff,
                )
            )
            .order_by(OddsSnapshot.snapshot_at.asc())
        )

        result = await session.execute(stmt)
        snapshots = result.scalars().all()

        if len(snapshots) < 2:
            return None

        opening = snapshots[0].odds
        current = snapshots[-1].odds

        if opening == 0:
            return None

        change_pct = (current - opening) / opening

        if change_pct < -0.02:
            direction = "shortening"
        elif change_pct > 0.02:
            direction = "drifting"
        else:
            direction = "stable"

        return {
            "direction": direction,
            "change_pct": change_pct,
            "opening": opening,
            "current": current,
        }
