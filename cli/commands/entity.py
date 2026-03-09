"""Entity resolution CLI commands."""

import asyncio

import typer
from rich.console import Console
from rich.table import Table

app = typer.Typer()
console = Console()


@app.command("unresolved")
def show_unresolved():
    """Show unmatched entities."""

    async def _unresolved():
        from sqlalchemy import select

        from db.models.system import EntityResolutionLog
        from db.session import get_session

        async with get_session() as session:
            result = await session.execute(
                select(EntityResolutionLog)
                .where(EntityResolutionLog.resolved_to_id.is_(None))
                .order_by(EntityResolutionLog.created_at.desc())
                .limit(50)
            )
            logs = result.scalars().all()

            if not logs:
                console.print("[green]No unresolved entities.[/green]")
                return

            table = Table(title=f"Unresolved Entities ({len(logs)})")
            table.add_column("Type", style="cyan")
            table.add_column("Input Name")
            table.add_column("Source")
            table.add_column("Method")
            table.add_column("Confidence", justify="right")

            for log in logs:
                table.add_row(
                    log.entity_type,
                    log.input_name,
                    log.source,
                    log.method,
                    f"{log.confidence:.2f}",
                )

            console.print(table)

    asyncio.run(_unresolved())


@app.command("aliases")
def show_aliases(team: str = typer.Argument(..., help="Team name to search")):
    """Show known aliases for a team."""

    async def _aliases():
        from sqlalchemy import select

        from db.models.entities import Alias, Team
        from db.session import get_session

        async with get_session() as session:
            # Find the team
            result = await session.execute(
                select(Team).where(Team.name.ilike(f"%{team}%"))
            )
            teams = result.scalars().all()

            if not teams:
                console.print(f"[red]No teams matching '{team}' found.[/red]")
                return

            for t in teams:
                alias_result = await session.execute(
                    select(Alias).where(
                        Alias.entity_type == "team",
                        Alias.canonical_id == t.id,
                    )
                )
                aliases = alias_result.scalars().all()

                table = Table(title=f"Aliases for {t.name}")
                table.add_column("Alias", style="cyan")
                table.add_column("Source")
                table.add_column("Confidence", justify="right")

                for a in aliases:
                    table.add_row(a.alias_name, a.source, f"{a.confidence:.2f}")

                console.print(table)

    asyncio.run(_aliases())
