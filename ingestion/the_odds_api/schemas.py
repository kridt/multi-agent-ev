from datetime import datetime

from pydantic import BaseModel


class OddsAPISport(BaseModel):
    key: str
    group: str
    title: str
    description: str
    active: bool
    has_outrights: bool


class OddsAPIEvent(BaseModel):
    id: str
    sport_key: str
    sport_title: str
    commence_time: datetime
    home_team: str
    away_team: str


class OddsAPIScoreEntry(BaseModel):
    name: str
    score: str


class OddsAPIScore(BaseModel):
    id: str
    sport_key: str
    commence_time: datetime
    home_team: str
    away_team: str
    scores: list[OddsAPIScoreEntry] | None = None
    completed: bool


class OddsAPIOutcome(BaseModel):
    name: str
    price: float
    point: float | None = None


class OddsAPIMarket(BaseModel):
    key: str
    last_update: datetime
    outcomes: list[OddsAPIOutcome]


class OddsAPIBookmaker(BaseModel):
    key: str
    title: str
    last_update: datetime
    markets: list[OddsAPIMarket]


class OddsAPIEventOdds(BaseModel):
    id: str
    sport_key: str
    commence_time: datetime
    home_team: str
    away_team: str
    bookmakers: list[OddsAPIBookmaker]
