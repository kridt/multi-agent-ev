from datetime import datetime, timezone
from pathlib import Path

from db.models.system import ModelRun


class ModelRegistry:
    def __init__(self, models_dir: str = "models_store"):
        self.models_dir = Path(models_dir)
        self.models_dir.mkdir(parents=True, exist_ok=True)

    async def register(self, session, model, metrics: dict, training_samples: int, training_cutoff) -> str:
        """Save model and register in DB. Returns model_run_id."""
        from db.models.base import new_uuid

        model_run_id = new_uuid()
        file_name = f"{model.model_type}_{model.version}_{model_run_id}.joblib"
        file_path = str(self.models_dir / file_name)

        # Save model to disk
        model.save(file_path)

        # Create DB record
        model_run = ModelRun(
            id=model_run_id,
            model_type=model.model_type,
            model_version=model.version,
            training_data_cutoff=training_cutoff,
            training_samples=training_samples,
            brier_score=metrics.get("brier_score", 0.0),
            log_loss=metrics.get("log_loss", 0.0),
            auc_roc=metrics.get("auc_roc"),
            calibration_error=metrics.get("calibration_error", 0.0),
            file_path=file_path,
            active=False,
            trained_at=datetime.now(timezone.utc),
        )
        session.add(model_run)
        await session.flush()

        return model_run_id

    async def get_active_model(self, session, model_type: str):
        """Load the currently active model of given type."""
        from sqlalchemy import select

        stmt = select(ModelRun).where(
            ModelRun.model_type == model_type,
            ModelRun.active == True,
        ).order_by(ModelRun.trained_at.desc()).limit(1)

        result = await session.execute(stmt)
        return result.scalar_one_or_none()

    async def list_models(self, session, model_type: str | None = None) -> list[ModelRun]:
        """List all model runs, optionally filtered by type."""
        from sqlalchemy import select

        stmt = select(ModelRun).order_by(ModelRun.trained_at.desc())
        if model_type is not None:
            stmt = stmt.where(ModelRun.model_type == model_type)

        result = await session.execute(stmt)
        return list(result.scalars().all())
