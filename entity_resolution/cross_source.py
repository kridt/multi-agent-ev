"""Cross-source fixture linking — match fixtures across multiple APIs."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import cast, func, select, Date
from sqlalchemy.ext.asyncio import AsyncSession

from db.models.matches import Match
from entity_resolution.resolver import EntityResolver


class CrossSourceLinker:
    """Link fixtures across Optic Odds, The Odds API, and SportMonks by
    matching on date + team names + league."""

    def __init__(self) -> None:
        self.resolver = EntityResolver()

    async def link_fixture(
        self,
        session: AsyncSession,
        optic_fixture_id: str,
        odds_api_event_id: str,
    ) -> str | None:
        """Match a specific Optic fixture to an Odds API event.

        Finds both events, resolves their team names to canonical IDs,
        and if both home and away teams match, returns (or creates) a
        canonical match_id.
        """
        # Look up the match by optic_odds_fixture_id
        stmt_optic = select(Match).where(
            Match.optic_odds_fixture_id == optic_fixture_id
        )
        result = await session.execute(stmt_optic)
        optic_match = result.scalar_one_or_none()
        if optic_match is None:
            return None

        # Look up the match by the_odds_api_event_id
        stmt_odds = select(Match).where(
            Match.the_odds_api_event_id == odds_api_event_id
        )
        result = await session.execute(stmt_odds)
        odds_match = result.scalar_one_or_none()
        if odds_match is None:
            return None

        # Both must share the same canonical home/away teams
        if (
            optic_match.home_team_id == odds_match.home_team_id
            and optic_match.away_team_id == odds_match.away_team_id
        ):
            # Merge into a single canonical match row (prefer the optic row)
            if odds_match.id != optic_match.id:
                optic_match.the_odds_api_event_id = odds_api_event_id
            return optic_match.id

        # Teams don't match — try resolving via entity resolver
        home_resolved_optic, _, _ = await self.resolver.resolve_team(
            session, optic_match.home_team_id or "", "optic_odds"
        )
        home_resolved_odds, _, _ = await self.resolver.resolve_team(
            session, odds_match.home_team_id or "", "the_odds_api"
        )

        if home_resolved_optic and home_resolved_optic == home_resolved_odds:
            optic_match.the_odds_api_event_id = odds_api_event_id
            return optic_match.id

        return None

    async def link_fixtures_by_date(
        self, session: AsyncSession, date: str
    ) -> list[dict]:
        """Find and link all fixtures on a given date across all APIs.

        Args:
            date: ISO date string, e.g. ``"2026-03-09"``.

        Returns:
            List of dicts with keys: match_id, optic_id, odds_api_id,
            sportmonks_id, confidence.
        """
        target_date = datetime.strptime(date, "%Y-%m-%d").date()

        # Fetch all matches on this date (compare date portion of kickoff_at)
        stmt = select(Match).where(
            cast(Match.kickoff_at, Date) == target_date
        )
        result = await session.execute(stmt)
        matches = list(result.scalars().all())

        # Group matches by (home_team_id, away_team_id) to detect cross-source duplicates
        team_pair_map: dict[tuple[str, str], list[Match]] = {}
        for m in matches:
            key = (m.home_team_id, m.away_team_id)
            team_pair_map.setdefault(key, []).append(m)

        linked: list[dict] = []
        for (home_id, away_id), group in team_pair_map.items():
            if not home_id or not away_id:
                continue

            # Merge API IDs from all rows in the group
            canonical = group[0]
            optic_id = None
            odds_api_id = None
            sportmonks_id = None

            for m in group:
                if m.optic_odds_fixture_id:
                    optic_id = m.optic_odds_fixture_id
                if m.the_odds_api_event_id:
                    odds_api_id = m.the_odds_api_event_id
                if m.sportmonks_fixture_id:
                    sportmonks_id = m.sportmonks_fixture_id

            # Confidence is based on how many sources matched
            source_count = sum(
                1 for x in [optic_id, odds_api_id, sportmonks_id] if x
            )
            confidence = min(1.0, 0.5 + source_count * 0.2)

            # Update the canonical match row with merged IDs
            if optic_id:
                canonical.optic_odds_fixture_id = optic_id
            if odds_api_id:
                canonical.the_odds_api_event_id = odds_api_id
            if sportmonks_id:
                canonical.sportmonks_fixture_id = sportmonks_id

            linked.append(
                {
                    "match_id": canonical.id,
                    "optic_id": optic_id,
                    "odds_api_id": odds_api_id,
                    "sportmonks_id": sportmonks_id,
                    "confidence": confidence,
                }
            )

        return linked
