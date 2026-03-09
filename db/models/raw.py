"""Raw data tables — store unprocessed API responses."""

from datetime import datetime

from sqlalchemy import Boolean, DateTime, Enum, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from db.models.base import Base, TimestampMixin, new_uuid

SourceEnum = Enum("optic_odds", "the_odds_api", "sportmonks", name="data_source")


class RawFixture(Base, TimestampMixin):
    __tablename__ = "raw_fixtures"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    source: Mapped[str] = mapped_column(SourceEnum, nullable=False)
    source_fixture_id: Mapped[str] = mapped_column(String(100), nullable=False)
    raw_json: Mapped[str] = mapped_column(Text, nullable=False)
    fetched_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    processed: Mapped[bool] = mapped_column(Boolean, default=False)


class RawOdds(Base, TimestampMixin):
    __tablename__ = "raw_odds"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    source: Mapped[str] = mapped_column(SourceEnum, nullable=False)
    source_fixture_id: Mapped[str] = mapped_column(String(100), nullable=False)
    source_market: Mapped[str] = mapped_column(String(100), nullable=False)
    raw_json: Mapped[str] = mapped_column(Text, nullable=False)
    fetched_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    processed: Mapped[bool] = mapped_column(Boolean, default=False)


class RawPlayerStats(Base, TimestampMixin):
    __tablename__ = "raw_player_stats"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    source: Mapped[str] = mapped_column(SourceEnum, nullable=False)
    source_fixture_id: Mapped[str] = mapped_column(String(100), nullable=False)
    source_player_id: Mapped[str] = mapped_column(String(100), nullable=False)
    raw_json: Mapped[str] = mapped_column(Text, nullable=False)
    fetched_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    processed: Mapped[bool] = mapped_column(Boolean, default=False)
