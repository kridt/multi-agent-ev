"""SportMonks Football API v3 client."""

from __future__ import annotations

import logging
from typing import Any

import httpx

from config.settings import settings
from ingestion.base_client import BaseAPIClient
from ingestion.sportmonks.schemas import (
    SMFixture,
    SMLeague,
    SMPlayer,
    SMSeason,
    SMStanding,
    SMStatistic,
    SMTeam,
)

logger = logging.getLogger(__name__)


class SportMonksClient(BaseAPIClient):
    """Async client for the SportMonks Football API v3."""

    def __init__(
        self,
        api_key: str | None = None,
        rate_limit_per_second: float = 2.0,
        max_retries: int = 3,
        timeout: float = 30.0,
    ):
        super().__init__(
            base_url="https://api.sportmonks.com/v3/football",
            rate_limit_per_second=rate_limit_per_second,
            max_retries=max_retries,
            timeout=timeout,
        )
        self._api_key = api_key or settings.sportmonks_api_key

    def _build_client(self) -> httpx.AsyncClient:
        return httpx.AsyncClient(
            base_url=self.base_url,
            timeout=self.timeout,
            http2=True,
            headers={"Authorization": self._api_key},
        )

    async def _paginate(self, path: str, params: dict[str, Any] | None = None) -> list[dict[str, Any]]:
        all_data: list[dict[str, Any]] = []
        params = dict(params or {})
        page = 1
        while True:
            params["page"] = page
            response = await self.get(path, params=params)
            data = response.get("data", [])
            if isinstance(data, list):
                all_data.extend(data)
            else:
                all_data.append(data)
            pagination = response.get("pagination", {})
            if not pagination.get("has_more", False):
                break
            page += 1
        return all_data

    # -- Fixtures --

    async def get_fixtures_by_date_range(
        self,
        start: str,
        end: str,
        includes: str = "statistics;lineups;events;scores",
    ) -> list[SMFixture]:
        raw = await self._paginate(
            f"/fixtures/between/{start}/{end}",
            params={"include": includes},
        )
        return [SMFixture.model_validate(r) for r in raw]

    async def get_fixture(
        self,
        fixture_id: int,
        includes: str = "statistics;lineups;events;scores",
    ) -> SMFixture:
        response = await self.get(
            f"/fixtures/{fixture_id}",
            params={"include": includes},
        )
        return SMFixture.model_validate(response.get("data", response))

    # -- Statistics --

    async def get_season_statistics(self, season_id: int) -> list[SMStatistic]:
        raw = await self._paginate(f"/statistics/seasons/{season_id}")
        return [SMStatistic.model_validate(r) for r in raw]

    # -- Players --

    async def get_player(self, player_id: int) -> SMPlayer:
        response = await self.get(f"/players/{player_id}")
        return SMPlayer.model_validate(response.get("data", response))

    # -- Teams --

    async def get_team(self, team_id: int) -> SMTeam:
        response = await self.get(f"/teams/{team_id}")
        return SMTeam.model_validate(response.get("data", response))

    async def get_teams_by_season(self, season_id: int) -> list[SMTeam]:
        raw = await self._paginate(f"/teams/seasons/{season_id}")
        return [SMTeam.model_validate(r) for r in raw]

    # -- Standings --

    async def get_standings(self, season_id: int) -> list[SMStanding]:
        response = await self.get(f"/standings/seasons/{season_id}")
        data = response.get("data", [])
        if isinstance(data, list):
            return [SMStanding.model_validate(r) for r in data]
        return [SMStanding.model_validate(data)]

    # -- Top Scorers --

    async def get_topscorers(self, season_id: int) -> list[dict[str, Any]]:
        return await self._paginate(f"/topscorers/seasons/{season_id}")

    # -- Leagues --

    async def get_leagues(self) -> list[SMLeague]:
        raw = await self._paginate("/leagues")
        return [SMLeague.model_validate(r) for r in raw]

    # -- Seasons --

    async def get_seasons(self, league_id: int | None = None) -> list[SMSeason]:
        if league_id:
            path = f"/seasons/teams/{league_id}"
        else:
            path = "/seasons"
        raw = await self._paginate(path)
        return [SMSeason.model_validate(r) for r in raw]

    # -- Squads --

    async def get_squads(self, team_id: int, season_id: int) -> list[dict[str, Any]]:
        response = await self.get(f"/squads/seasons/{season_id}/teams/{team_id}")
        data = response.get("data", [])
        if isinstance(data, list):
            return data
        return [data]
