"""Alias store — CRUD operations on the aliases table."""

from collections import defaultdict

from sqlalchemy import select
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.ext.asyncio import AsyncSession

from db.models.entities import Alias


class AliasStore:
    """Async alias store backed by the ``aliases`` table."""

    async def add_alias(
        self,
        session: AsyncSession,
        entity_type: str,
        canonical_id: str,
        alias_name: str,
        source: str,
        confidence: float = 1.0,
    ) -> None:
        """Insert or update an alias mapping.

        Uses SQLite ``INSERT OR IGNORE`` semantics via the unique constraint
        on (entity_type, alias_name, source) to avoid duplicates.
        """
        stmt = (
            sqlite_insert(Alias)
            .values(
                entity_type=entity_type,
                canonical_id=canonical_id,
                alias_name=alias_name,
                source=source,
                confidence=confidence,
            )
            .on_conflict_do_nothing(index_elements=["entity_type", "alias_name", "source"])
        )
        await session.execute(stmt)

    async def get_aliases(self, session: AsyncSession, canonical_id: str) -> list[Alias]:
        """Return all alias rows for a given canonical entity ID."""
        stmt = select(Alias).where(Alias.canonical_id == canonical_id)
        result = await session.execute(stmt)
        return list(result.scalars().all())

    async def find_canonical(
        self, session: AsyncSession, alias_name: str, entity_type: str
    ) -> tuple[str, float] | None:
        """Look up a canonical_id by alias_name and entity_type.

        Returns (canonical_id, confidence) or None if not found.
        """
        stmt = (
            select(Alias)
            .where(Alias.alias_name == alias_name, Alias.entity_type == entity_type)
            .order_by(Alias.confidence.desc())
            .limit(1)
        )
        result = await session.execute(stmt)
        alias = result.scalar_one_or_none()
        if alias is not None:
            return (alias.canonical_id, alias.confidence)
        return None

    async def get_all_aliases_by_type(
        self, session: AsyncSession, entity_type: str
    ) -> dict[str, list[str]]:
        """Return a dict mapping canonical_id to a list of alias names for the given entity type."""
        stmt = select(Alias).where(Alias.entity_type == entity_type)
        result = await session.execute(stmt)
        aliases = result.scalars().all()

        grouped: dict[str, list[str]] = defaultdict(list)
        for alias in aliases:
            grouped[alias.canonical_id].append(alias.alias_name)
        return dict(grouped)
