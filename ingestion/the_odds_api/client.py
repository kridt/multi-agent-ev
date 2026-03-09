import logging
from typing import Any

import httpx

from config.settings import settings
from ingestion.base_client import BaseAPIClient
from ingestion.the_odds_api.schemas import (
    OddsAPIEvent,
    OddsAPIEventOdds,
    OddsAPIScore,
    OddsAPISport,
)

logger = logging.getLogger(__name__)

SPORT_KEYS: dict[str, str] = {
    "epl": "soccer_epl",
    "la_liga": "soccer_spain_la_liga",
    "serie_a": "soccer_italy_serie_a",
    "bundesliga": "soccer_germany_bundesliga",
    "ligue_1": "soccer_france_ligue_one",
    "danish_superliga": "soccer_denmark_superliga",
    "allsvenskan": "soccer_sweden_allsvenskan",
    "eliteserien": "soccer_norway_eliteserien",
}

TARGET_MARKETS = "h2h,h2h_3_way,totals,btts,team_totals,alternate_totals_corners,alternate_totals_cards"


class TheOddsAPIClient(BaseAPIClient):
    """Client for The Odds API with automatic apiKey injection and credit tracking."""

    def __init__(
        self,
        api_key: str | None = None,
        rate_limit_per_second: float = 1.0,
        max_retries: int = 3,
        timeout: float = 30.0,
    ):
        super().__init__(
            base_url="https://api.the-odds-api.com",
            rate_limit_per_second=rate_limit_per_second,
            max_retries=max_retries,
            timeout=timeout,
        )
        self._api_key = api_key or settings.the_odds_api_key
        self.credits_remaining: int | None = None
        self.credits_used: int | None = None

    def _build_client(self) -> httpx.AsyncClient:
        return httpx.AsyncClient(
            base_url=self.base_url,
            timeout=self.timeout,
            http2=True,
        )

    def _on_response(self, response: httpx.Response) -> None:
        remaining = response.headers.get("x-requests-remaining")
        used = response.headers.get("x-requests-used")
        if remaining is not None:
            self.credits_remaining = int(remaining)
        if used is not None:
            self.credits_used = int(used)
        logger.debug(
            "Odds API credits — remaining: %s, used: %s",
            self.credits_remaining,
            self.credits_used,
        )

    async def get(self, path: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        params = dict(params) if params else {}
        params["apiKey"] = self._api_key
        return await self._request("GET", path, params=params)

    async def get_sports(self) -> list[OddsAPISport]:
        data = await self.get("/v4/sports/")
        return [OddsAPISport.model_validate(item) for item in data]

    async def get_events(self, sport_key: str) -> list[OddsAPIEvent]:
        data = await self.get(f"/v4/sports/{sport_key}/events")
        return [OddsAPIEvent.model_validate(item) for item in data]

    async def get_odds(
        self,
        sport_key: str,
        regions: str = "eu",
        markets: str = "h2h,totals",
        odds_format: str = "decimal",
    ) -> list[OddsAPIEventOdds]:
        params: dict[str, Any] = {
            "regions": regions,
            "markets": markets,
            "oddsFormat": odds_format,
        }
        data = await self.get(f"/v4/sports/{sport_key}/odds/", params=params)
        return [OddsAPIEventOdds.model_validate(item) for item in data]

    async def get_event_odds(
        self,
        sport_key: str,
        event_id: str,
        regions: str = "eu",
        markets: str | None = None,
    ) -> OddsAPIEventOdds:
        params: dict[str, Any] = {"regions": regions}
        if markets is not None:
            params["markets"] = markets
        data = await self.get(
            f"/v4/sports/{sport_key}/events/{event_id}/odds",
            params=params,
        )
        return OddsAPIEventOdds.model_validate(data)

    async def get_scores(
        self,
        sport_key: str,
        days_from: int = 3,
    ) -> list[OddsAPIScore]:
        params: dict[str, Any] = {"daysFrom": days_from}
        data = await self.get(f"/v4/sports/{sport_key}/scores/", params=params)
        return [OddsAPIScore.model_validate(item) for item in data]

    async def get_historical_odds(
        self,
        sport_key: str,
        date: str,
        regions: str = "eu",
        markets: str | None = None,
    ) -> list[OddsAPIEventOdds]:
        params: dict[str, Any] = {
            "date": date,
            "regions": regions,
        }
        if markets is not None:
            params["markets"] = markets
        data = await self.get(
            f"/v4/historical/sports/{sport_key}/odds",
            params=params,
        )
        return [OddsAPIEventOdds.model_validate(item) for item in data]
