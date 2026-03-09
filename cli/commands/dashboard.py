"""Dashboard launch CLI command."""

import typer

app = typer.Typer()


@app.command()
def launch(port: int = typer.Option(8080, help="Dashboard port")):
    """Launch the web dashboard."""
    from dashboard.app import run_dashboard

    run_dashboard(port=port)
