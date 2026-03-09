"""Pydantic v2 models for SportMonks Football API v3 responses."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Generic, TypeVar

from pydantic import BaseModel, ConfigDict

T = TypeVar("T")


class SMPagination(BaseModel):
    model_config = ConfigDict(extra="allow")

    count: int = 0
    per_page: int = 25
    current_page: int = 1
    next_page: str | None = None
    has_more: bool = False


class SMFixture(BaseModel):
    model_config = ConfigDict(extra="allow")

    id: int
    sport_id: int | None = None
    league_id: int | None = None
    season_id: int | None = None
    stage_id: int | None = None
    round_id: int | None = None
    name: str | None = None
    starting_at: datetime | None = None
    result_info: str | None = None
    leg: str | None = None
    length: int | None = None
    has_odds: bool | None = None

    statistics: list[dict[str, Any]] | None = None
    lineups: list[dict[str, Any]] | None = None
    events: list[dict[str, Any]] | None = None
    scores: list[dict[str, Any]] | None = None


class SMScore(BaseModel):
    model_config = ConfigDict(extra="allow")

    id: int
    fixture_id: int | None = None
    type_id: int | None = None
    description: str = ""
    score: dict[str, Any] = {}
    participant_id: int | None = None


class SMStatistic(BaseModel):
    model_config = ConfigDict(extra="allow")

    id: int
    fixture_id: int | None = None
    type_id: int | None = None
    type: dict[str, Any] | None = None
    participant_id: int | None = None
    value: dict[str, Any] | int | float | str | None = None


class SMLineup(BaseModel):
    model_config = ConfigDict(extra="allow")

    id: int
    fixture_id: int | None = None
    player_id: int | None = None
    team_id: int | None = None
    position: str | None = None
    formation_position: int | None = None
    type_id: int | None = None


class SMEvent(BaseModel):
    model_config = ConfigDict(extra="allow")

    id: int
    fixture_id: int | None = None
    type_id: int | None = None
    participant_id: int | None = None
    player_id: int | None = None
    minute: int | None = None
    extra_minute: int | None = None
    result: str | None = None
    info: str | None = None


class SMTeam(BaseModel):
    model_config = ConfigDict(extra="allow")

    id: int
    name: str | None = None
    short_code: str | None = None
    country_id: int | None = None


class SMPlayer(BaseModel):
    model_config = ConfigDict(extra="allow")

    id: int
    sport_id: int | None = None
    country_id: int | None = None
    name: str = ""
    display_name: str | None = None
    position_id: int | None = None
    detailed_position_id: int | None = None


class SMLeague(BaseModel):
    model_config = ConfigDict(extra="allow")

    id: int
    sport_id: int | None = None
    country_id: int | None = None
    name: str | None = None
    active: bool | None = None
    type: str | None = None


class SMSeason(BaseModel):
    model_config = ConfigDict(extra="allow")

    id: int
    sport_id: int | None = None
    league_id: int | None = None
    name: str | None = None
    is_current: bool = False
    starting_at: str | None = None
    ending_at: str | None = None


class SMStanding(BaseModel):
    model_config = ConfigDict(extra="allow")

    id: int
    participant_id: int | None = None
    sport_id: int | None = None
    league_id: int | None = None
    season_id: int | None = None
    position: int | None = None
    points: int | None = None
    result: str | None = None


class SMResponse(BaseModel, Generic[T]):
    model_config = ConfigDict(extra="allow")

    data: list[T] | T = []  # type: ignore[assignment]
    pagination: SMPagination | None = None
