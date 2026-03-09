"""Backtesting CLI commands."""

import asyncio

import typer
from rich.console import Console
from rich.table import Table

app = typer.Typer()
console = Console()


@app.command("run")
def run_backtest(
    market: str = typer.Option("goals_ou", help="Market type"),
    start_date: str = typer.Option(None, help="Start date (YYYY-MM-DD)"),
    end_date: str = typer.Option(None, help="End date (YYYY-MM-DD)"),
    league: str = typer.Option(None, help="Filter by league key"),
    kelly_fraction: float = typer.Option(0.25, help="Kelly fraction to use"),
):
    """Run walk-forward backtest."""

    async def _run():
        from db.session import get_session

        console.print(f"[bold]Running backtest for market: {market}[/bold]")
        if start_date:
            console.print(f"  Start: {start_date}")
        if end_date:
            console.print(f"  End: {end_date}")
        if league:
            console.print(f"  League: {league}")
        console.print(f"  Kelly fraction: {kelly_fraction}")

        # TODO: Integrate with backtesting engine
        console.print("[yellow]Backtest engine integration pending[/yellow]")

    asyncio.run(_run())


@app.command("report")
def show_report():
    """Show latest backtest results."""

    async def _report():
        from db.session import get_session

        console.print("[bold]Backtest Report[/bold]")

        # TODO: Load from backtest results table
        table = Table(title="Backtest Summary")
        table.add_column("Metric", style="cyan")
        table.add_column("Value", style="green")

        table.add_row("Total Bets", "-")
        table.add_row("Win Rate", "-")
        table.add_row("ROI", "-")
        table.add_row("Profit (DKK)", "-")
        table.add_row("Max Drawdown", "-")
        table.add_row("Sharpe Ratio", "-")
        table.add_row("Avg EV at Bet", "-")

        console.print(table)
        console.print("[yellow]No backtest results available yet.[/yellow]")

    asyncio.run(_report())
