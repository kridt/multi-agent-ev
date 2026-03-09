"""Agent tools package.

Exports the tool functions that can be invoked by orchestrator agents.
"""

from agents.tools.analysis_tools import (
    check_lineup_changes,
    check_weather_news,
    detect_odds_anomaly,
)
from agents.tools.db_tools import (
    get_bankroll_status,
    get_model_performance,
    get_odds_movement,
    get_recent_bets,
    get_signals_for_match,
    get_upcoming_matches,
)

__all__ = [
    # DB tools
    "get_upcoming_matches",
    "get_signals_for_match",
    "get_odds_movement",
    "get_bankroll_status",
    "get_recent_bets",
    "get_model_performance",
    # Analysis tools
    "check_weather_news",
    "check_lineup_changes",
    "detect_odds_anomaly",
]
