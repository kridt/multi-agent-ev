"""Odds snapshot and movement tables."""

from datetime import datetime

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Index, String
from sqlalchemy.orm import Mapped, mapped_column

from db.models.base import Base, TimestampMixin, new_uuid
from db.models.raw import SourceEnum


class OddsSnapshot(Base, TimestampMixin):
    __tablename__ = "odds_snapshots"
    __table_args__ = (
        Index("ix_odds_match_book_market", "match_id", "bookmaker", "market", "selection"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    match_id: Mapped[str] = mapped_column(ForeignKey("matches.id"), nullable=False)
    bookmaker: Mapped[str] = mapped_column(String(100), nullable=False)
    market: Mapped[str] = mapped_column(String(100), nullable=False)
    selection: Mapped[str] = mapped_column(String(200), nullable=False)
    odds: Mapped[float] = mapped_column(Float, nullable=False)
    implied_prob: Mapped[float] = mapped_column(Float, nullable=False)
    source: Mapped[str] = mapped_column(SourceEnum, nullable=False)
    snapshot_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    is_closing: Mapped[bool] = mapped_column(Boolean, default=False)


class OddsMovement(Base, TimestampMixin):
    __tablename__ = "odds_movements"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    match_id: Mapped[str] = mapped_column(ForeignKey("matches.id"), nullable=False)
    bookmaker: Mapped[str] = mapped_column(String(100), nullable=False)
    market: Mapped[str] = mapped_column(String(100), nullable=False)
    selection: Mapped[str] = mapped_column(String(200), nullable=False)
    opening_odds: Mapped[float] = mapped_column(Float, nullable=False)
    closing_odds: Mapped[float] = mapped_column(Float, nullable=False)
    movement_pct: Mapped[float] = mapped_column(Float, nullable=False)
