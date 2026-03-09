"""Bet management CLI commands."""

import asyncio
from datetime import datetime, timezone

import typer
from rich.console import Console
from rich.table import Table

app = typer.Typer()
console = Console()


@app.command("approve")
def approve_bet(signal_id: str = typer.Argument(..., help="Signal ID to approve")):
    """Approve a signal and record the bet."""

    async def _approve():
        from sqlalchemy import select

        from db.models.base import new_uuid
        from db.models.betting import Bet
        from db.models.predictions import EVSignal
        from db.session import get_session

        async with get_session() as session:
            result = await session.execute(
                select(EVSignal).where(EVSignal.id.like(f"{signal_id}%"))
            )
            signal = result.scalar_one_or_none()
            if not signal:
                console.print(f"[red]Signal {signal_id} not found[/red]")
                return

            signal.status = "approved"
            bet = Bet(
                id=new_uuid(),
                signal_id=signal.id,
                match_id=signal.match_id,
                market=signal.market,
                selection=signal.selection,
                bookmaker=signal.bookmaker,
                odds=signal.odds_at_signal,
                stake_dkk=signal.suggested_stake_dkk,
                potential_return_dkk=signal.suggested_stake_dkk * signal.odds_at_signal,
                placed_at=datetime.now(timezone.utc),
            )
            session.add(bet)
            console.print(
                f"[green]Bet placed: {signal.market} {signal.selection} "
                f"@ {signal.odds_at_signal:.2f} - Stake: {signal.suggested_stake_dkk:.0f} DKK[/green]"
            )

    asyncio.run(_approve())


@app.command("reject")
def reject_bet(signal_id: str = typer.Argument(..., help="Signal ID to reject")):
    """Reject a signal."""

    async def _reject():
        from sqlalchemy import select

        from db.models.predictions import EVSignal
        from db.session import get_session

        async with get_session() as session:
            result = await session.execute(
                select(EVSignal).where(EVSignal.id.like(f"{signal_id}%"))
            )
            signal = result.scalar_one_or_none()
            if not signal:
                console.print(f"[red]Signal {signal_id} not found[/red]")
                return
            signal.status = "rejected"
            console.print(f"[yellow]Signal {signal_id} rejected[/yellow]")

    asyncio.run(_reject())


@app.command("result")
def record_result(
    bet_id: str = typer.Argument(..., help="Bet ID"),
    outcome: str = typer.Argument(..., help="won, lost, or void"),
):
    """Record bet outcome."""

    async def _result():
        from sqlalchemy import select

        from db.models.betting import Bet
        from db.session import get_session

        async with get_session() as session:
            result = await session.execute(select(Bet).where(Bet.id.like(f"{bet_id}%")))
            bet = result.scalar_one_or_none()
            if not bet:
                console.print(f"[red]Bet {bet_id} not found[/red]")
                return

            bet.outcome = outcome
            bet.settled_at = datetime.now(timezone.utc)
            if outcome == "won":
                bet.pnl_dkk = bet.stake_dkk * (bet.odds - 1)
            elif outcome == "lost":
                bet.pnl_dkk = -bet.stake_dkk
            else:
                bet.pnl_dkk = 0.0

            console.print(
                f"[green]Bet {bet_id}: {outcome} (P&L: {bet.pnl_dkk:+.0f} DKK)[/green]"
            )

    asyncio.run(_result())


@app.command("list")
def list_bets(
    status: str = typer.Option(None, help="Filter: pending, won, lost"),
    days: int = typer.Option(30, help="Number of days to show"),
):
    """List bets with P&L."""

    async def _list():
        from sqlalchemy import select

        from db.models.betting import Bet
        from db.session import get_session

        async with get_session() as session:
            query = select(Bet).order_by(Bet.placed_at.desc()).limit(50)
            if status:
                query = query.where(Bet.outcome == status)
            result = await session.execute(query)
            bets = result.scalars().all()

            if not bets:
                console.print("[yellow]No bets found[/yellow]")
                return

            table = Table(title="Bet History")
            table.add_column("ID", style="dim", max_width=8)
            table.add_column("Market")
            table.add_column("Selection")
            table.add_column("Odds", justify="right")
            table.add_column("Stake", justify="right")
            table.add_column("Outcome")
            table.add_column("P&L", justify="right")

            total_pnl = 0.0
            for b in bets:
                pnl_str = f"{b.pnl_dkk:+.0f}" if b.pnl_dkk is not None else "-"
                pnl_color = (
                    "green"
                    if (b.pnl_dkk or 0) > 0
                    else "red"
                    if (b.pnl_dkk or 0) < 0
                    else "white"
                )
                outcome_color = (
                    "green"
                    if b.outcome == "won"
                    else "red"
                    if b.outcome == "lost"
                    else "yellow"
                )
                table.add_row(
                    b.id[:8],
                    b.market,
                    b.selection,
                    f"{b.odds:.2f}",
                    f"{b.stake_dkk:.0f}",
                    f"[{outcome_color}]{b.outcome or 'pending'}[/{outcome_color}]",
                    f"[{pnl_color}]{pnl_str}[/{pnl_color}]",
                )
                total_pnl += b.pnl_dkk or 0

            console.print(table)
            color = "green" if total_pnl > 0 else "red"
            console.print(f"[{color}]Total P&L: {total_pnl:+,.0f} DKK[/{color}]")

    asyncio.run(_list())
