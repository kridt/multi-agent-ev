"""Map The Odds API Pydantic schemas to raw DB models."""

from __future__ import annotations

from datetime import datetime

from db.models.base import new_uuid
from db.models.raw import RawFixture, RawOdds

from .schemas import OddsAPIEvent, OddsAPIEventOdds


def map_event_to_raw(event: OddsAPIEvent | OddsAPIEventOdds, fetched_at: datetime) -> RawFixture:
    """Map an OddsAPIEvent (or OddsAPIEventOdds) to a RawFixture DB row."""
    return RawFixture(
        id=new_uuid(),
        source="the_odds_api",
        source_fixture_id=event.id,
        raw_json=event.model_dump_json(),
        fetched_at=fetched_at,
        processed=False,
    )


def map_odds_to_raw(event_odds: OddsAPIEventOdds, fetched_at: datetime) -> list[RawOdds]:
    """Map an OddsAPIEventOdds to a list of RawOdds — one per market per bookmaker."""
    rows: list[RawOdds] = []
    for bookmaker in event_odds.bookmakers:
        for market in bookmaker.markets:
            # Serialize just this bookmaker+market slice for the raw record
            market_data = {
                "event_id": event_odds.id,
                "sport_key": event_odds.sport_key,
                "commence_time": event_odds.commence_time.isoformat(),
                "home_team": event_odds.home_team,
                "away_team": event_odds.away_team,
                "bookmaker_key": bookmaker.key,
                "bookmaker_title": bookmaker.title,
                "bookmaker_last_update": bookmaker.last_update.isoformat(),
                "market_key": market.key,
                "market_last_update": market.last_update.isoformat(),
                "outcomes": [
                    {
                        "name": o.name,
                        "price": o.price,
                        "point": o.point,
                    }
                    for o in market.outcomes
                ],
            }
            import json

            rows.append(
                RawOdds(
                    id=new_uuid(),
                    source="the_odds_api",
                    source_fixture_id=event_odds.id,
                    source_market=market.key,
                    raw_json=json.dumps(market_data),
                    fetched_at=fetched_at,
                    processed=False,
                )
            )
    return rows
