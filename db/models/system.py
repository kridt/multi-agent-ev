"""System tables — model runs, ingestion logs, entity resolution logs."""

from datetime import date, datetime

from sqlalchemy import Boolean, DateTime, Float, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from db.models.base import Base, TimestampMixin, new_uuid


class ModelRun(Base, TimestampMixin):
    __tablename__ = "model_runs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    model_type: Mapped[str] = mapped_column(String(50), nullable=False)
    model_version: Mapped[str] = mapped_column(String(20), nullable=False)
    training_data_cutoff: Mapped[date] = mapped_column(nullable=False)
    training_samples: Mapped[int] = mapped_column(Integer, nullable=False)
    brier_score: Mapped[float] = mapped_column(Float, nullable=False)
    log_loss: Mapped[float] = mapped_column(Float, nullable=False)
    auc_roc: Mapped[float | None] = mapped_column(Float)
    calibration_error: Mapped[float] = mapped_column(Float, nullable=False)
    file_path: Mapped[str] = mapped_column(String(500), nullable=False)
    active: Mapped[bool] = mapped_column(Boolean, default=False)
    trained_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class IngestionLog(Base, TimestampMixin):
    __tablename__ = "ingestion_logs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    source: Mapped[str] = mapped_column(String(50), nullable=False)
    endpoint: Mapped[str] = mapped_column(String(200), nullable=False)
    status_code: Mapped[int] = mapped_column(Integer, nullable=False)
    records_fetched: Mapped[int] = mapped_column(Integer, default=0)
    duration_ms: Mapped[int] = mapped_column(Integer, nullable=False)
    error_message: Mapped[str | None] = mapped_column(Text)
    credits_used: Mapped[int | None] = mapped_column(Integer)
    credits_remaining: Mapped[int | None] = mapped_column(Integer)
    fetched_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class EntityResolutionLog(Base, TimestampMixin):
    __tablename__ = "entity_resolution_logs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    entity_type: Mapped[str] = mapped_column(String(20), nullable=False)
    input_name: Mapped[str] = mapped_column(String(300), nullable=False)
    source: Mapped[str] = mapped_column(String(50), nullable=False)
    resolved_to_id: Mapped[str | None] = mapped_column(String(36))
    resolved_to_name: Mapped[str | None] = mapped_column(String(200))
    method: Mapped[str] = mapped_column(String(50), nullable=False)  # exact, alias, normalized, fuzzy
    confidence: Mapped[float] = mapped_column(Float, nullable=False)
    manual_override: Mapped[bool] = mapped_column(Boolean, default=False)
