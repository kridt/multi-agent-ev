"""Optic Odds API client."""

from __future__ import annotations

from typing import Any

import httpx

from config.settings import settings
from ingestion.base_client import BaseAPIClient

from .schemas import (
    OpticFixture,
    OpticLeague,
    OpticMarket,
    OpticOddsData,
    OpticPlayer,
    OpticPlayerResult,
    OpticResponse,
    OpticSportsbook,
    OpticTeam,
)


class OpticOddsClient(BaseAPIClient):
    """Async client for the Optic Odds v3 API."""

    def __init__(self, rate_limit_per_second: float = 5.0) -> None:
        super().__init__(
            base_url="https://api.opticodds.com/api/v3",
            rate_limit_per_second=rate_limit_per_second,
        )

    def _build_client(self) -> httpx.AsyncClient:
        return httpx.AsyncClient(
            base_url=self.base_url,
            timeout=self.timeout,
            http2=True,
            headers={"X-Api-Key": settings.optic_odds_api_key},
        )

    # ── Fixtures ─────────────────────────────────────────────────────

    async def get_fixtures(
        self,
        league: str | None = None,
        status: str | None = None,
    ) -> list[OpticFixture]:
        params: dict[str, Any] = {"sport": "soccer"}
        if league:
            params["league"] = league
        if status:
            params["status"] = status
        data = await self.get("/fixtures", params=params)
        return OpticResponse[OpticFixture].model_validate(data).data

    async def get_active_fixtures(
        self,
        league: str | None = None,
    ) -> list[OpticFixture]:
        params: dict[str, Any] = {"sport": "soccer"}
        if league:
            params["league"] = league
        data = await self.get("/fixtures/active", params=params)
        return OpticResponse[OpticFixture].model_validate(data).data

    async def get_results(
        self,
        fixture_id: str | None = None,
    ) -> list[OpticFixture]:
        params: dict[str, Any] = {}
        if fixture_id:
            params["fixture_id"] = fixture_id
        data = await self.get("/fixtures/results", params=params)
        return OpticResponse[OpticFixture].model_validate(data).data

    # ── Odds ─────────────────────────────────────────────────────────

    async def get_odds(
        self,
        fixture_id: str,
        sportsbook: str | None = None,
        market: str | None = None,
    ) -> list[OpticOddsData]:
        params: dict[str, Any] = {"fixture_id": fixture_id}
        if sportsbook:
            params["sportsbook"] = sportsbook
        if market:
            params["market"] = market
        data = await self.get("/fixtures/odds", params=params)
        return OpticResponse[OpticOddsData].model_validate(data).data

    async def get_historical_odds(
        self,
        fixture_id: str,
        sportsbook: str | None = None,
    ) -> list[OpticOddsData]:
        params: dict[str, Any] = {"fixture_id": fixture_id}
        if sportsbook:
            params["sportsbook"] = sportsbook
        data = await self.get("/fixtures/odds/historical", params=params)
        return OpticResponse[OpticOddsData].model_validate(data).data

    # ── Player results ───────────────────────────────────────────────

    async def get_player_results(
        self,
        fixture_id: str,
    ) -> list[OpticPlayerResult]:
        params: dict[str, Any] = {"fixture_id": fixture_id}
        data = await self.get("/fixtures/player-results", params=params)
        return OpticResponse[OpticPlayerResult].model_validate(data).data

    async def get_player_results_last_x(
        self,
        player_id: str,
        count: int = 10,
    ) -> list[OpticPlayerResult]:
        params: dict[str, Any] = {"player_id": player_id, "count": count}
        data = await self.get("/fixtures/player-results/last-x", params=params)
        return OpticResponse[OpticPlayerResult].model_validate(data).data

    # ── Reference data ───────────────────────────────────────────────

    async def get_leagues(self) -> list[OpticLeague]:
        data = await self.get("/leagues/active", params={"sport": "soccer"})
        return OpticResponse[OpticLeague].model_validate(data).data

    async def get_sportsbooks(self) -> list[OpticSportsbook]:
        data = await self.get("/sportsbooks/active")
        return OpticResponse[OpticSportsbook].model_validate(data).data

    async def get_markets(self) -> list[OpticMarket]:
        data = await self.get("/markets/active")
        return OpticResponse[OpticMarket].model_validate(data).data

    async def get_teams(self) -> list[OpticTeam]:
        data = await self.get("/teams", params={"sport": "soccer"})
        return OpticResponse[OpticTeam].model_validate(data).data

    async def get_players(self) -> list[OpticPlayer]:
        data = await self.get("/players", params={"sport": "soccer"})
        return OpticResponse[OpticPlayer].model_validate(data).data
