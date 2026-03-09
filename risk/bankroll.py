"""Bankroll management and tracking."""

from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from db.models.base import new_uuid
from db.models.betting import BankrollSnapshot


class BankrollManager:
    """Track bankroll state, drawdowns, and ROI."""

    def __init__(self, initial_bankroll: float):
        self.current = initial_bankroll
        self.peak = initial_bankroll
        self.initial = initial_bankroll

    @property
    def drawdown_pct(self) -> float:
        """Current drawdown from peak as a percentage (0.0 to 1.0)."""
        if self.peak == 0:
            return 0.0
        return (self.peak - self.current) / self.peak

    @property
    def roi_pct(self) -> float:
        """Return on investment from initial bankroll as a percentage."""
        if self.initial == 0:
            return 0.0
        return (self.current - self.initial) / self.initial

    def update(self, pnl: float) -> None:
        """Apply profit/loss to bankroll and update peak."""
        self.current += pnl
        if self.current > self.peak:
            self.peak = self.current

    async def load_from_db(self, session: AsyncSession) -> None:
        """Load latest bankroll state from bankroll_snapshots."""
        stmt = (
            select(BankrollSnapshot)
            .order_by(BankrollSnapshot.snapshot_at.desc())
            .limit(1)
        )
        result = await session.execute(stmt)
        snapshot = result.scalar_one_or_none()

        if snapshot is not None:
            self.current = snapshot.balance_dkk
            self.peak = snapshot.peak_dkk

    async def snapshot(self, session: AsyncSession) -> None:
        """Save current state to bankroll_snapshots table."""
        snap = BankrollSnapshot(
            id=new_uuid(),
            balance_dkk=self.current,
            peak_dkk=self.peak,
            drawdown_pct=self.drawdown_pct,
            roi_pct=self.roi_pct,
            snapshot_at=datetime.now(timezone.utc),
        )
        session.add(snap)
        await session.flush()
