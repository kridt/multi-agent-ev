"""Prediction, signal, and feature vector tables."""

from datetime import datetime

from sqlalchemy import Boolean, DateTime, Enum, Float, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from db.models.base import Base, TimestampMixin, new_uuid

SignalStatusEnum = Enum("pending", "approved", "rejected", "expired", name="signal_status")


class FeatureVector(Base, TimestampMixin):
    __tablename__ = "feature_vectors"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    match_id: Mapped[str] = mapped_column(ForeignKey("matches.id"), nullable=False)
    entity_type: Mapped[str] = mapped_column(
        Enum("team", "player", name="feature_entity_type"), nullable=False
    )
    entity_id: Mapped[str] = mapped_column(String(36), nullable=False)
    feature_version: Mapped[str] = mapped_column(String(20), nullable=False)
    features: Mapped[str] = mapped_column(Text, nullable=False)  # JSON string
    computed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class ModelPrediction(Base, TimestampMixin):
    __tablename__ = "model_predictions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    match_id: Mapped[str] = mapped_column(ForeignKey("matches.id"), nullable=False)
    model_type: Mapped[str] = mapped_column(String(50), nullable=False)
    model_version: Mapped[str] = mapped_column(String(20), nullable=False)
    market: Mapped[str] = mapped_column(String(100), nullable=False)
    selection: Mapped[str] = mapped_column(String(200), nullable=False)
    predicted_prob: Mapped[float] = mapped_column(Float, nullable=False)
    predicted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    actual_outcome: Mapped[bool | None] = mapped_column(Boolean)


class EVSignal(Base, TimestampMixin):
    __tablename__ = "ev_signals"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    match_id: Mapped[str] = mapped_column(ForeignKey("matches.id"), nullable=False)
    market: Mapped[str] = mapped_column(String(100), nullable=False)
    selection: Mapped[str] = mapped_column(String(200), nullable=False)
    bookmaker: Mapped[str] = mapped_column(String(100), nullable=False)
    odds_at_signal: Mapped[float] = mapped_column(Float, nullable=False)
    model_prob: Mapped[float] = mapped_column(Float, nullable=False)
    ev_pct: Mapped[float] = mapped_column(Float, nullable=False)
    confidence: Mapped[float] = mapped_column(Float, nullable=False)
    suggested_stake_pct: Mapped[float] = mapped_column(Float, nullable=False)
    suggested_stake_dkk: Mapped[float] = mapped_column(Float, nullable=False)
    status: Mapped[str] = mapped_column(SignalStatusEnum, default="pending")
    anomaly_flag: Mapped[bool] = mapped_column(Boolean, default=False)
    anomaly_reasoning: Mapped[str | None] = mapped_column(Text)
    generated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
