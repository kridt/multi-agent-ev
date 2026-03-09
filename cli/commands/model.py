"""Model management CLI commands."""

import asyncio

import typer
from rich.console import Console
from rich.table import Table

app = typer.Typer()
console = Console()


@app.command("list")
def list_models():
    """List all model versions."""

    async def _list():
        from sqlalchemy import select

        from db.models.system import ModelRun
        from db.session import get_session

        async with get_session() as session:
            result = await session.execute(
                select(ModelRun).order_by(ModelRun.trained_at.desc())
            )
            models = result.scalars().all()

            if not models:
                console.print("[yellow]No models found.[/yellow]")
                return

            table = Table(title="Model Versions")
            table.add_column("Type", style="cyan")
            table.add_column("Version")
            table.add_column("Brier Score", justify="right")
            table.add_column("Log Loss", justify="right")
            table.add_column("AUC-ROC", justify="right")
            table.add_column("Cal. Error", justify="right")
            table.add_column("Samples", justify="right")
            table.add_column("Active")
            table.add_column("Trained At")

            for m in models:
                active_str = "[green]YES[/green]" if m.active else "[dim]no[/dim]"
                auc = f"{m.auc_roc:.4f}" if m.auc_roc else "-"
                table.add_row(
                    m.model_type,
                    m.model_version,
                    f"{m.brier_score:.4f}",
                    f"{m.log_loss:.4f}",
                    auc,
                    f"{m.calibration_error:.4f}",
                    str(m.training_samples),
                    active_str,
                    m.trained_at.strftime("%Y-%m-%d %H:%M"),
                )

            console.print(table)

    asyncio.run(_list())


@app.command("train")
def train_model(model_type: str = typer.Argument(..., help="Model type (e.g., goals_ou, match_result)")):
    """Train a specific model type."""

    async def _train():
        console.print(f"[bold]Training model: {model_type}[/bold]")
        # TODO: Integrate with model training pipeline
        console.print("[yellow]Model training pipeline integration pending[/yellow]")

    asyncio.run(_train())


@app.command("evaluate")
def evaluate_model(model_type: str = typer.Argument(..., help="Model type to evaluate")):
    """Show model evaluation metrics."""

    async def _evaluate():
        from sqlalchemy import select

        from db.models.system import ModelRun
        from db.session import get_session

        async with get_session() as session:
            result = await session.execute(
                select(ModelRun)
                .where(ModelRun.model_type == model_type, ModelRun.active.is_(True))
            )
            model_run = result.scalar_one_or_none()

            if not model_run:
                console.print(f"[red]No active model found for type: {model_type}[/red]")
                return

            table = Table(title=f"Model Evaluation: {model_type} v{model_run.model_version}")
            table.add_column("Metric", style="cyan")
            table.add_column("Value", style="green")

            table.add_row("Brier Score", f"{model_run.brier_score:.4f}")
            table.add_row("Log Loss", f"{model_run.log_loss:.4f}")
            if model_run.auc_roc:
                table.add_row("AUC-ROC", f"{model_run.auc_roc:.4f}")
            table.add_row("Calibration Error", f"{model_run.calibration_error:.4f}")
            table.add_row("Training Samples", str(model_run.training_samples))
            table.add_row("Training Cutoff", str(model_run.training_data_cutoff))
            table.add_row("Model Path", model_run.file_path)

            console.print(table)

    asyncio.run(_evaluate())
