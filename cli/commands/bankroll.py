"""Bankroll management CLI commands."""

import asyncio
from datetime import datetime, timezone

import typer
from rich.console import Console
from rich.table import Table

app = typer.Typer()
console = Console()


@app.command("status")
def bankroll_status():
    """Show current bankroll, drawdown, exposure."""

    async def _status():
        from sqlalchemy import select

        from cli.formatters import format_bankroll_panel
        from db.models.betting import BankrollSnapshot
        from db.session import get_session

        async with get_session() as session:
            result = await session.execute(
                select(BankrollSnapshot).order_by(BankrollSnapshot.snapshot_at.desc()).limit(1)
            )
            snapshot = result.scalar_one_or_none()

            if not snapshot:
                from config.settings import settings

                console.print(
                    format_bankroll_panel(
                        balance=settings.bankroll_dkk,
                        peak=settings.bankroll_dkk,
                        drawdown=0.0,
                        daily_exposure=0.0,
                    )
                )
                console.print("[dim]No snapshots recorded yet. Using initial bankroll from settings.[/dim]")
                return

            console.print(
                format_bankroll_panel(
                    balance=snapshot.balance_dkk,
                    peak=snapshot.peak_dkk,
                    drawdown=snapshot.drawdown_pct,
                    daily_exposure=snapshot.daily_exposure_pct,
                )
            )

            table = Table(title="Bankroll Metrics")
            table.add_column("Metric", style="cyan")
            table.add_column("Value", style="green")

            table.add_row("Total Bets", str(snapshot.total_bets))
            table.add_row("Wins", str(snapshot.total_wins))
            table.add_row("Losses", str(snapshot.total_losses))
            table.add_row("ROI", f"{snapshot.roi_pct:.1%}")
            if snapshot.brier_score is not None:
                table.add_row("Brier Score", f"{snapshot.brier_score:.4f}")
            table.add_row("Snapshot At", snapshot.snapshot_at.strftime("%Y-%m-%d %H:%M"))

            console.print(table)

    asyncio.run(_status())


@app.command("set")
def set_bankroll(amount: float = typer.Argument(..., help="Initial bankroll amount in DKK")):
    """Set initial bankroll amount."""

    async def _set():
        from db.models.base import new_uuid
        from db.models.betting import BankrollSnapshot
        from db.session import get_session

        async with get_session() as session:
            snapshot = BankrollSnapshot(
                id=new_uuid(),
                balance_dkk=amount,
                peak_dkk=amount,
                drawdown_pct=0.0,
                daily_exposure_pct=0.0,
                total_bets=0,
                total_wins=0,
                total_losses=0,
                roi_pct=0.0,
                snapshot_at=datetime.now(timezone.utc),
            )
            session.add(snapshot)
            console.print(f"[green]Bankroll set to {amount:,.0f} DKK[/green]")

    asyncio.run(_set())


@app.command("history")
def bankroll_history(days: int = typer.Option(30, help="Number of days to show")):
    """Show bankroll trajectory."""

    async def _history():
        from datetime import timedelta

        from sqlalchemy import select

        from db.models.betting import BankrollSnapshot
        from db.session import get_session

        async with get_session() as session:
            cutoff = datetime.now(timezone.utc) - timedelta(days=days)
            result = await session.execute(
                select(BankrollSnapshot)
                .where(BankrollSnapshot.snapshot_at >= cutoff)
                .order_by(BankrollSnapshot.snapshot_at.asc())
            )
            snapshots = result.scalars().all()

            if not snapshots:
                console.print(f"[yellow]No bankroll snapshots in the last {days} days.[/yellow]")
                return

            table = Table(title=f"Bankroll History (last {days} days)")
            table.add_column("Date", style="cyan")
            table.add_column("Balance", justify="right")
            table.add_column("Peak", justify="right")
            table.add_column("Drawdown", justify="right")
            table.add_column("Bets", justify="right")
            table.add_column("ROI", justify="right")

            for s in snapshots:
                dd_color = "red" if s.drawdown_pct > 0.10 else "yellow" if s.drawdown_pct > 0.05 else "green"
                table.add_row(
                    s.snapshot_at.strftime("%Y-%m-%d"),
                    f"{s.balance_dkk:,.0f}",
                    f"{s.peak_dkk:,.0f}",
                    f"[{dd_color}]{s.drawdown_pct:.1%}[/{dd_color}]",
                    str(s.total_bets),
                    f"{s.roi_pct:.1%}",
                )

            console.print(table)

    asyncio.run(_history())
