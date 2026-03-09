"""Match and match stats tables."""

from datetime import datetime

from sqlalchemy import Boolean, DateTime, Enum, Float, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from db.models.base import Base, FullTimestampMixin, TimestampMixin, new_uuid

MatchStatusEnum = Enum(
    "scheduled", "live", "finished", "postponed", "cancelled", name="match_status"
)


class Match(Base, FullTimestampMixin):
    __tablename__ = "matches"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    league_id: Mapped[str] = mapped_column(ForeignKey("leagues.id"), nullable=False)
    home_team_id: Mapped[str] = mapped_column(ForeignKey("teams.id"), nullable=False)
    away_team_id: Mapped[str] = mapped_column(ForeignKey("teams.id"), nullable=False)
    kickoff_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    status: Mapped[str] = mapped_column(MatchStatusEnum, default="scheduled")
    home_goals: Mapped[int | None] = mapped_column(Integer)
    away_goals: Mapped[int | None] = mapped_column(Integer)
    optic_odds_fixture_id: Mapped[str | None] = mapped_column(String(100))
    the_odds_api_event_id: Mapped[str | None] = mapped_column(String(100))
    sportmonks_fixture_id: Mapped[int | None] = mapped_column(Integer)
    season: Mapped[str | None] = mapped_column(String(20))
    matchday: Mapped[int | None] = mapped_column(Integer)

    league = relationship("League")
    home_team = relationship("Team", foreign_keys=[home_team_id])
    away_team = relationship("Team", foreign_keys=[away_team_id])
    stats: Mapped[list["MatchStats"]] = relationship(back_populates="match")
    player_stats: Mapped[list["PlayerMatchStats"]] = relationship(back_populates="match")


class MatchStats(Base, TimestampMixin):
    __tablename__ = "match_stats"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    match_id: Mapped[str] = mapped_column(ForeignKey("matches.id"), nullable=False)
    team_id: Mapped[str] = mapped_column(ForeignKey("teams.id"), nullable=False)
    is_home: Mapped[bool] = mapped_column(Boolean, nullable=False)
    goals: Mapped[int] = mapped_column(Integer, default=0)
    shots: Mapped[int] = mapped_column(Integer, default=0)
    shots_on_target: Mapped[int] = mapped_column(Integer, default=0)
    corners: Mapped[int] = mapped_column(Integer, default=0)
    fouls: Mapped[int] = mapped_column(Integer, default=0)
    yellow_cards: Mapped[int] = mapped_column(Integer, default=0)
    red_cards: Mapped[int] = mapped_column(Integer, default=0)
    possession_pct: Mapped[float | None] = mapped_column(Float)
    passes: Mapped[int] = mapped_column(Integer, default=0)
    pass_accuracy_pct: Mapped[float | None] = mapped_column(Float)
    tackles: Mapped[int] = mapped_column(Integer, default=0)
    interceptions: Mapped[int] = mapped_column(Integer, default=0)
    offsides: Mapped[int] = mapped_column(Integer, default=0)
    xg: Mapped[float | None] = mapped_column(Float)

    match: Mapped[Match] = relationship(back_populates="stats")


class PlayerMatchStats(Base, TimestampMixin):
    __tablename__ = "player_match_stats"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    match_id: Mapped[str] = mapped_column(ForeignKey("matches.id"), nullable=False)
    player_id: Mapped[str] = mapped_column(ForeignKey("players.id"), nullable=False)
    team_id: Mapped[str] = mapped_column(ForeignKey("teams.id"), nullable=False)
    minutes_played: Mapped[int] = mapped_column(Integer, default=0)
    goals: Mapped[int] = mapped_column(Integer, default=0)
    assists: Mapped[int] = mapped_column(Integer, default=0)
    shots: Mapped[int] = mapped_column(Integer, default=0)
    shots_on_target: Mapped[int] = mapped_column(Integer, default=0)
    key_passes: Mapped[int] = mapped_column(Integer, default=0)
    passes: Mapped[int] = mapped_column(Integer, default=0)
    pass_accuracy_pct: Mapped[float | None] = mapped_column(Float)
    tackles: Mapped[int] = mapped_column(Integer, default=0)
    interceptions: Mapped[int] = mapped_column(Integer, default=0)
    clearances: Mapped[int] = mapped_column(Integer, default=0)
    blocks: Mapped[int] = mapped_column(Integer, default=0)
    dribbles_attempted: Mapped[int] = mapped_column(Integer, default=0)
    dribbles_succeeded: Mapped[int] = mapped_column(Integer, default=0)
    fouls_committed: Mapped[int] = mapped_column(Integer, default=0)
    fouls_drawn: Mapped[int] = mapped_column(Integer, default=0)
    yellow_cards: Mapped[int] = mapped_column(Integer, default=0)
    red_cards: Mapped[int] = mapped_column(Integer, default=0)
    corners_taken: Mapped[int] = mapped_column(Integer, default=0)
    offsides: Mapped[int] = mapped_column(Integer, default=0)
    xg: Mapped[float | None] = mapped_column(Float)

    match: Mapped[Match] = relationship(back_populates="player_stats")
    player = relationship("Player")
    team = relationship("Team")
