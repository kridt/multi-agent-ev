"""EV scanning CLI commands."""

import asyncio

import typer
from rich.console import Console
from rich.table import Table

app = typer.Typer()
console = Console()


@app.command("run")
def run_scan(
    league: str = typer.Option(None, help="Filter by league"),
    min_ev: float = typer.Option(0.03, help="Minimum EV threshold"),
):
    """Run EV scan for upcoming fixtures."""

    async def _scan():
        from sqlalchemy import select

        from db.models.predictions import EVSignal
        from db.session import get_session

        async with get_session() as session:
            query = select(EVSignal).where(EVSignal.status == "pending")
            if min_ev:
                query = query.where(EVSignal.ev_pct >= min_ev)
            result = await session.execute(query)
            signals = result.scalars().all()

            if not signals:
                console.print("[yellow]No active signals found.[/yellow]")
                return

            table = Table(title=f"EV Signals ({len(signals)} found)")
            table.add_column("ID", style="dim", max_width=8)
            table.add_column("Match")
            table.add_column("Market")
            table.add_column("Selection")
            table.add_column("Bookmaker")
            table.add_column("Odds", justify="right")
            table.add_column("Model Prob", justify="right")
            table.add_column("EV %", justify="right")
            table.add_column("Stake DKK", justify="right")

            for s in signals:
                ev_color = "green" if s.ev_pct >= 0.05 else "yellow"
                table.add_row(
                    s.id[:8],
                    s.match_id[:8],
                    s.market,
                    s.selection,
                    s.bookmaker,
                    f"{s.odds_at_signal:.2f}",
                    f"{s.model_prob:.1%}",
                    f"[{ev_color}]{s.ev_pct:.1%}[/{ev_color}]",
                    f"{s.suggested_stake_dkk:.0f}",
                )

            console.print(table)

    asyncio.run(_scan())


@app.command("list")
def list_signals(status: str = typer.Option("pending", help="Filter by status")):
    """List EV signals by status."""

    async def _list():
        from sqlalchemy import select

        from db.models.predictions import EVSignal
        from db.session import get_session

        async with get_session() as session:
            query = select(EVSignal).where(EVSignal.status == status)
            result = await session.execute(query)
            signals = result.scalars().all()

            if not signals:
                console.print(f"[yellow]No signals with status '{status}'.[/yellow]")
                return

            table = Table(title=f"EV Signals - {status} ({len(signals)} found)")
            table.add_column("ID", style="dim", max_width=8)
            table.add_column("Match")
            table.add_column("Market")
            table.add_column("Selection")
            table.add_column("Bookmaker")
            table.add_column("Odds", justify="right")
            table.add_column("Model Prob", justify="right")
            table.add_column("EV %", justify="right")
            table.add_column("Stake DKK", justify="right")

            for s in signals:
                ev_color = "green" if s.ev_pct >= 0.05 else "yellow"
                table.add_row(
                    s.id[:8],
                    s.match_id[:8],
                    s.market,
                    s.selection,
                    s.bookmaker,
                    f"{s.odds_at_signal:.2f}",
                    f"{s.model_prob:.1%}",
                    f"[{ev_color}]{s.ev_pct:.1%}[/{ev_color}]",
                    f"{s.suggested_stake_dkk:.0f}",
                )

            console.print(table)

    asyncio.run(_list())
