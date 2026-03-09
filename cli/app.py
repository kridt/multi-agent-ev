"""CLI entry point for the EV betting system."""

import typer

from cli.commands import backtest, bankroll, bet, dashboard, entity, ingest, model, scan

app = typer.Typer(name="ev", help="AI Soccer EV Betting Platform", no_args_is_help=True)
app.add_typer(ingest.app, name="ingest", help="Data ingestion commands")
app.add_typer(scan.app, name="scan", help="EV scanning commands")
app.add_typer(bet.app, name="bet", help="Bet management commands")
app.add_typer(backtest.app, name="backtest", help="Backtesting commands")
app.add_typer(model.app, name="model", help="Model management commands")
app.add_typer(bankroll.app, name="bankroll", help="Bankroll commands")
app.add_typer(entity.app, name="entity", help="Entity resolution commands")
app.add_typer(dashboard.app, name="dashboard", help="Web dashboard commands")


@app.command()
def status():
    """Show system status."""
    from rich.console import Console
    from rich.table import Table

    from config.bookmakers import TARGET_BOOKMAKERS
    from config.leagues import get_active_leagues
    from config.settings import settings

    console = Console()

    table = Table(title="EV System Status")
    table.add_column("Setting", style="cyan")
    table.add_column("Value", style="green")

    table.add_row("Database", settings.database_url)
    table.add_row("Bankroll", f"{settings.bankroll_dkk:,.0f} DKK")
    table.add_row("Min EV Threshold", f"{settings.min_ev_threshold:.0%}")
    table.add_row("Kelly Fraction", f"{settings.kelly_fraction}")
    table.add_row("Odds Range", f"{settings.min_odds} - {settings.max_odds}")
    table.add_row("Active Leagues", str(len(get_active_leagues())))
    table.add_row("Target Bookmakers", ", ".join(b.display_name for b in TARGET_BOOKMAKERS.values()))
    table.add_row("Optic Odds API", "configured" if settings.optic_odds_api_key else "missing")
    table.add_row("The Odds API", "configured" if settings.the_odds_api_key else "missing")
    table.add_row("SportMonks API", "configured" if settings.sportmonks_api_key else "missing")

    console.print(table)


if __name__ == "__main__":
    app()
