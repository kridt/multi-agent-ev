"""Core entity resolver — cascaded matching with logging."""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from config.constants import FUZZY_MATCH_THRESHOLD
from db.models.base import new_uuid
from db.models.entities import Player, Team
from db.models.system import EntityResolutionLog
from entity_resolution.alias_store import AliasStore
from entity_resolution.matchers import (
    ContextualMatcher,
    ExactMatcher,
    FuzzyMatcher,
    NormalizedMatcher,
)


class EntityResolver:
    """Resolve raw entity names to canonical IDs using a cascade of matchers.

    Resolution order:
    1. Exact match against canonical names in DB
    2. Exact match against the alias table
    3. Normalized match against canonical names
    4. Fuzzy match against canonical names (optionally filtered by league)
    5. If nothing found → (None, 0.0, "unresolved")
    """

    def __init__(self) -> None:
        self.alias_store = AliasStore()
        self.exact = ExactMatcher()
        self.normalized = NormalizedMatcher()
        self.fuzzy = FuzzyMatcher(threshold=FUZZY_MATCH_THRESHOLD)
        self.contextual = ContextualMatcher(threshold=FUZZY_MATCH_THRESHOLD)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    async def _get_team_candidates(
        self, session: AsyncSession, league_id: str | None = None
    ) -> dict[str, str]:
        """Return {team_name: team_id} for active teams, optionally filtered by league."""
        stmt = select(Team).where(Team.active.is_(True))
        if league_id is not None:
            stmt = stmt.where(Team.league_id == league_id)
        result = await session.execute(stmt)
        teams = result.scalars().all()
        return {t.name: t.id for t in teams}

    async def _get_all_team_candidates(self, session: AsyncSession) -> dict[str, str]:
        """Return {team_name: team_id} for all active teams."""
        return await self._get_team_candidates(session, league_id=None)

    async def _get_player_candidates(
        self, session: AsyncSession, team_id: str | None = None
    ) -> dict[str, str]:
        """Return {player_name: player_id} for active players, optionally filtered by team."""
        stmt = select(Player).where(Player.active.is_(True))
        if team_id is not None:
            stmt = stmt.where(Player.team_id == team_id)
        result = await session.execute(stmt)
        players = result.scalars().all()
        return {p.name: p.id for p in players}

    async def _log_resolution(
        self,
        session: AsyncSession,
        entity_type: str,
        input_name: str,
        source: str,
        resolved_to_id: str | None,
        resolved_to_name: str | None,
        method: str,
        confidence: float,
    ) -> None:
        """Write a row to ``entity_resolution_logs``."""
        log = EntityResolutionLog(
            id=new_uuid(),
            entity_type=entity_type,
            input_name=input_name,
            source=source,
            resolved_to_id=resolved_to_id,
            resolved_to_name=resolved_to_name,
            method=method,
            confidence=confidence,
        )
        session.add(log)

    # ------------------------------------------------------------------
    # Core resolution
    # ------------------------------------------------------------------

    async def resolve(
        self,
        session: AsyncSession,
        name: str,
        entity_type: str,
        source: str,
        league_id: str | None = None,
        team_id: str | None = None,
    ) -> tuple[str | None, float, str]:
        """Resolve an entity name to a canonical ID.

        Returns:
            (canonical_id, confidence, method)
        """
        # Build candidate map based on entity type
        if entity_type == "team":
            all_candidates = await self._get_all_team_candidates(session)
            league_candidates = (
                await self._get_team_candidates(session, league_id)
                if league_id
                else None
            )
        elif entity_type == "player":
            all_candidates = await self._get_player_candidates(session, team_id=None)
            league_candidates = (
                await self._get_player_candidates(session, team_id)
                if team_id
                else None
            )
        else:
            all_candidates = {}
            league_candidates = None

        candidate_names = list(all_candidates.keys())

        # ---- Step 1: Exact match against canonical names ----
        result = self.exact.match(name, candidate_names)
        if result is not None:
            matched_name, confidence = result
            canonical_id = all_candidates[matched_name]
            await self._log_resolution(
                session, entity_type, name, source, canonical_id, matched_name, "exact", confidence
            )
            return (canonical_id, confidence, "exact")

        # ---- Step 2: Exact match against alias table ----
        alias_result = await self.alias_store.find_canonical(session, name, entity_type)
        if alias_result is not None:
            canonical_id, confidence = alias_result
            # Look up the canonical name for logging
            resolved_name = None
            for cname, cid in all_candidates.items():
                if cid == canonical_id:
                    resolved_name = cname
                    break
            await self._log_resolution(
                session, entity_type, name, source, canonical_id, resolved_name, "alias", confidence
            )
            return (canonical_id, confidence, "alias")

        # ---- Step 3: Normalized match against canonical names ----
        result = self.normalized.match(name, candidate_names)
        if result is not None:
            matched_name, confidence = result
            canonical_id = all_candidates[matched_name]
            await self._log_resolution(
                session, entity_type, name, source, canonical_id, matched_name, "normalized", confidence
            )
            return (canonical_id, confidence, "normalized")

        # ---- Step 4: Fuzzy / contextual match ----
        if league_candidates is not None:
            league_names = list(league_candidates.keys())
            result = self.contextual.match(name, candidate_names, league_teams=league_names)
            if result is not None:
                matched_name, confidence = result
                canonical_id = (
                    league_candidates.get(matched_name) or all_candidates[matched_name]
                )
                await self._log_resolution(
                    session, entity_type, name, source, canonical_id, matched_name, "contextual", confidence
                )
                return (canonical_id, confidence, "contextual")

        # Plain fuzzy (no league filter)
        result = self.fuzzy.match(name, candidate_names)
        if result is not None:
            matched_name, confidence = result
            canonical_id = all_candidates[matched_name]
            await self._log_resolution(
                session, entity_type, name, source, canonical_id, matched_name, "fuzzy", confidence
            )
            return (canonical_id, confidence, "fuzzy")

        # ---- Step 5: Unresolved ----
        await self._log_resolution(
            session, entity_type, name, source, None, None, "unresolved", 0.0
        )
        return (None, 0.0, "unresolved")

    # ------------------------------------------------------------------
    # Convenience wrappers
    # ------------------------------------------------------------------

    async def resolve_team(
        self,
        session: AsyncSession,
        name: str,
        source: str,
        league_id: str | None = None,
    ) -> tuple[str | None, float, str]:
        """Convenience wrapper for team resolution."""
        return await self.resolve(session, name, "team", source, league_id=league_id)

    async def resolve_player(
        self,
        session: AsyncSession,
        name: str,
        source: str,
        team_id: str | None = None,
    ) -> tuple[str | None, float, str]:
        """Convenience wrapper for player resolution."""
        return await self.resolve(session, name, "player", source, team_id=team_id)
