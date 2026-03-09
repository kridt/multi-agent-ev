"""All database models — import here so Alembic can discover them."""

from db.models.base import Base
from db.models.betting import BankrollSnapshot, Bet
from db.models.entities import Alias, League, Player, Team
from db.models.matches import Match, MatchStats, PlayerMatchStats
from db.models.odds import OddsMovement, OddsSnapshot
from db.models.predictions import EVSignal, FeatureVector, ModelPrediction
from db.models.raw import RawFixture, RawOdds, RawPlayerStats
from db.models.system import EntityResolutionLog, IngestionLog, ModelRun

__all__ = [
    "Base",
    "RawFixture",
    "RawOdds",
    "RawPlayerStats",
    "League",
    "Team",
    "Player",
    "Alias",
    "Match",
    "MatchStats",
    "PlayerMatchStats",
    "OddsSnapshot",
    "OddsMovement",
    "FeatureVector",
    "ModelPrediction",
    "EVSignal",
    "Bet",
    "BankrollSnapshot",
    "ModelRun",
    "IngestionLog",
    "EntityResolutionLog",
]
