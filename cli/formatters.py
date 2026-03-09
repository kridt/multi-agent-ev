"""Rich formatters for CLI output."""

from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.text import Text


def format_ev(ev_pct: float) -> str:
    """Color-coded EV display. Green >= 5%, Yellow 3-5%, Red < 3%."""
    if ev_pct >= 0.05:
        return f"[green]{ev_pct:.1%}[/green]"
    elif ev_pct >= 0.03:
        return f"[yellow]{ev_pct:.1%}[/yellow]"
    else:
        return f"[red]{ev_pct:.1%}[/red]"


def format_odds(odds: float) -> str:
    """Format decimal odds."""
    return f"{odds:.2f}"


def format_pnl(pnl: float) -> str:
    """Color-coded P&L."""
    if pnl > 0:
        return f"[green]{pnl:+,.0f} DKK[/green]"
    elif pnl < 0:
        return f"[red]{pnl:+,.0f} DKK[/red]"
    else:
        return f"[white]{pnl:+,.0f} DKK[/white]"


def format_bankroll_panel(
    balance: float, peak: float, drawdown: float, daily_exposure: float
) -> Panel:
    """Rich panel showing bankroll status."""
    text = Text()
    text.append(f"Balance: {balance:,.0f} DKK\n", style="bold green" if balance > 0 else "bold red")
    text.append(f"Peak: {peak:,.0f} DKK\n", style="bold")
    text.append(
        f"Drawdown: {drawdown:.1%}\n",
        style="red" if drawdown > 0.10 else "yellow" if drawdown > 0.05 else "green",
    )
    text.append(
        f"Daily Exposure: {daily_exposure:.1%}",
        style="red" if daily_exposure > 0.10 else "yellow" if daily_exposure > 0.05 else "green",
    )
    return Panel(text, title="Bankroll Status", border_style="blue")
