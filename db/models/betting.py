"""Bet tracking and bankroll tables."""

from datetime import datetime

from sqlalchemy import DateTime, Enum, Float, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from db.models.base import Base, TimestampMixin, new_uuid

BetOutcomeEnum = Enum(
    "pending", "won", "lost", "void", "half_won", "half_lost", name="bet_outcome"
)


class Bet(Base, TimestampMixin):
    __tablename__ = "bets"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    signal_id: Mapped[str] = mapped_column(ForeignKey("ev_signals.id"), nullable=False)
    match_id: Mapped[str] = mapped_column(ForeignKey("matches.id"), nullable=False)
    market: Mapped[str] = mapped_column(String(100), nullable=False)
    selection: Mapped[str] = mapped_column(String(200), nullable=False)
    bookmaker: Mapped[str] = mapped_column(String(100), nullable=False)
    odds: Mapped[float] = mapped_column(Float, nullable=False)
    stake_dkk: Mapped[float] = mapped_column(Float, nullable=False)
    potential_return_dkk: Mapped[float] = mapped_column(Float, nullable=False)
    outcome: Mapped[str | None] = mapped_column(BetOutcomeEnum)
    pnl_dkk: Mapped[float | None] = mapped_column(Float)
    closing_odds: Mapped[float | None] = mapped_column(Float)
    clv_pct: Mapped[float | None] = mapped_column(Float)
    placed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    settled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class BankrollSnapshot(Base, TimestampMixin):
    __tablename__ = "bankroll_snapshots"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    balance_dkk: Mapped[float] = mapped_column(Float, nullable=False)
    peak_dkk: Mapped[float] = mapped_column(Float, nullable=False)
    drawdown_pct: Mapped[float] = mapped_column(Float, nullable=False)
    daily_exposure_pct: Mapped[float] = mapped_column(Float, default=0.0)
    total_bets: Mapped[int] = mapped_column(Integer, default=0)
    total_wins: Mapped[int] = mapped_column(Integer, default=0)
    total_losses: Mapped[int] = mapped_column(Integer, default=0)
    roi_pct: Mapped[float] = mapped_column(Float, default=0.0)
    brier_score: Mapped[float | None] = mapped_column(Float)
    snapshot_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
