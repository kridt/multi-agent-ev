"""Entity tables — canonical teams, players, leagues, and aliases."""

from sqlalchemy import Boolean, Enum, Float, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from db.models.base import Base, FullTimestampMixin, TimestampMixin, new_uuid

EntityTypeEnum = Enum("team", "player", "league", name="entity_type")


class League(Base, TimestampMixin):
    __tablename__ = "leagues"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    country: Mapped[str] = mapped_column(String(100), nullable=False)
    optic_odds_id: Mapped[str | None] = mapped_column(String(100))
    the_odds_api_key: Mapped[str | None] = mapped_column(String(100))
    sportmonks_id: Mapped[int | None] = mapped_column(Integer)
    active: Mapped[bool] = mapped_column(Boolean, default=True)

    teams: Mapped[list["Team"]] = relationship(back_populates="league")


class Team(Base, TimestampMixin):
    __tablename__ = "teams"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    league_id: Mapped[str | None] = mapped_column(ForeignKey("leagues.id"))
    optic_odds_id: Mapped[str | None] = mapped_column(String(100))
    the_odds_api_name: Mapped[str | None] = mapped_column(String(200))
    sportmonks_id: Mapped[int | None] = mapped_column(Integer)
    active: Mapped[bool] = mapped_column(Boolean, default=True)

    league: Mapped[League | None] = relationship(back_populates="teams")
    players: Mapped[list["Player"]] = relationship(back_populates="team")


class Player(Base, FullTimestampMixin):
    __tablename__ = "players"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    team_id: Mapped[str | None] = mapped_column(ForeignKey("teams.id"))
    position: Mapped[str | None] = mapped_column(String(50))  # GK, DEF, MID, FWD
    optic_odds_id: Mapped[str | None] = mapped_column(String(100))
    sportmonks_id: Mapped[int | None] = mapped_column(Integer)
    active: Mapped[bool] = mapped_column(Boolean, default=True)

    team: Mapped[Team | None] = relationship(back_populates="players")


class Alias(Base, TimestampMixin):
    __tablename__ = "aliases"
    __table_args__ = (
        UniqueConstraint("entity_type", "alias_name", "source", name="uq_alias"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    entity_type: Mapped[str] = mapped_column(EntityTypeEnum, nullable=False)
    canonical_id: Mapped[str] = mapped_column(String(36), nullable=False)
    alias_name: Mapped[str] = mapped_column(String(300), nullable=False)
    source: Mapped[str] = mapped_column(String(50), nullable=False)
    confidence: Mapped[float] = mapped_column(Float, default=1.0)
