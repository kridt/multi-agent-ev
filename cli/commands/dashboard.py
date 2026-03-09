"""Dashboard launch CLI command."""

import typer

app = typer.Typer()


@app.command()
def launch(
    port: int = typer.Option(8080, help="Dashboard port"),
    host: str = typer.Option("0.0.0.0", help="Host interface to bind to"),
) -> None:
    """Launch the real-time EV betting dashboard (FastAPI + WebSocket)."""
    from dashboard.app import run_dashboard

    run_dashboard(host=host, port=port)
