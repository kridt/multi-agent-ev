"""Data ingestion CLI commands."""

import asyncio

import typer
from rich.console import Console

app = typer.Typer()
console = Console()


@app.command("run")
def run_ingestion(
    league: str = typer.Option(None, help="Specific league key (e.g., epl)"),
):
    """Run all ingestion jobs now."""

    async def _run():
        from ingestion.scheduler import run_all_ingestion

        console.print("[bold]Running ingestion...[/bold]")
        await run_all_ingestion(league_key=league)
        console.print("[green]Ingestion complete[/green]")

    asyncio.run(_run())


@app.command("status")
def ingestion_status():
    """Show last ingestion times and record counts."""

    async def _status():
        from sqlalchemy import func, select

        from db.models.raw import RawFixture, RawOdds, RawPlayerStats
        from db.models.system import IngestionLog
        from db.session import get_session
        from rich.table import Table

        async with get_session() as session:
            table = Table(title="Ingestion Status")
            table.add_column("Source", style="cyan")
            table.add_column("Records", style="green")

            for model, name in [
                (RawFixture, "Raw Fixtures"),
                (RawOdds, "Raw Odds"),
                (RawPlayerStats, "Raw Player Stats"),
            ]:
                result = await session.execute(select(func.count()).select_from(model))
                count = result.scalar() or 0
                table.add_row(name, str(count))

            # Show latest ingestion log entries
            log_result = await session.execute(
                select(IngestionLog).order_by(IngestionLog.fetched_at.desc()).limit(5)
            )
            logs = log_result.scalars().all()

            console.print(table)

            if logs:
                log_table = Table(title="Recent Ingestion Logs")
                log_table.add_column("Source", style="cyan")
                log_table.add_column("Endpoint")
                log_table.add_column("Status", justify="right")
                log_table.add_column("Records", justify="right")
                log_table.add_column("Duration", justify="right")
                log_table.add_column("Time")

                for log in logs:
                    status_color = "green" if log.status_code == 200 else "red"
                    log_table.add_row(
                        log.source,
                        log.endpoint,
                        f"[{status_color}]{log.status_code}[/{status_color}]",
                        str(log.records_fetched),
                        f"{log.duration_ms}ms",
                        log.fetched_at.strftime("%Y-%m-%d %H:%M"),
                    )

                console.print(log_table)

    asyncio.run(_status())
