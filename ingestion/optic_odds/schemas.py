"""Pydantic v2 schemas for Optic Odds API responses."""

from __future__ import annotations

from datetime import datetime
from typing import Generic, TypeVar

from pydantic import BaseModel, Field

T = TypeVar("T")


class OpticResponse(BaseModel, Generic[T]):
    data: list[T]


# ── Reference entities ──────────────────────────────────────────────


class OpticLeague(BaseModel):
    id: str
    name: str
    sport: str
    active: bool


class OpticTeam(BaseModel):
    id: str
    name: str
    sport: str


class OpticPlayer(BaseModel):
    id: str
    name: str
    sport: str
    team: str | None = None


class OpticMarket(BaseModel):
    id: str
    name: str


class OpticSportsbook(BaseModel):
    id: str
    name: str


# ── Fixtures ─────────────────────────────────────────────────────────


class OpticFixture(BaseModel):
    id: str
    sport: str
    league: str
    home_team: str
    away_team: str
    start_date: datetime
    status: str
    is_live: bool = False


# ── Odds ─────────────────────────────────────────────────────────────


class OpticSelection(BaseModel):
    name: str
    odds: float


class OpticOddsData(BaseModel):
    fixture_id: str
    sportsbook: str
    market: str
    selection: OpticSelection
    is_live: bool = False


# ── Player results ───────────────────────────────────────────────────


class OpticPlayerInfo(BaseModel):
    id: str
    name: str
    team: str | None = None


class OpticPlayerResult(BaseModel):
    fixture_id: str
    player: OpticPlayerInfo
    stats: dict[str, float] = Field(default_factory=dict)
