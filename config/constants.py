"""System-wide constants."""

# Rolling window sizes for feature calculations
ROLLING_WINDOWS = [3, 5, 10]

# Minimum minutes played to include in per-90 calculations
MIN_MINUTES_PER90 = 15

# Entity resolution
FUZZY_MATCH_THRESHOLD = 85  # rapidfuzz score threshold
ENTITY_CONFIDENCE_EXACT = 1.0
ENTITY_CONFIDENCE_ALIAS = 0.95
ENTITY_CONFIDENCE_NORMALIZED = 0.90
ENTITY_CONFIDENCE_FUZZY_MIN = 0.70
ENTITY_CONFIDENCE_CONTEXTUAL_BOOST = 0.05

# Consistency scoring thresholds (coefficient of variation)
CV_CONSISTENT = 0.3
CV_MODERATE = 0.6

# Model evaluation
MIN_TRAINING_SAMPLES = 100
CALIBRATION_WINDOW = 200  # last N predictions for recalibration

# Scheduling (CET timezone)
BETTING_HOURS_START = 8  # 08:00 CET
BETTING_HOURS_END = 23  # 23:00 CET
ODDS_POLL_INTERVAL_MIN = 30  # minutes
FIXTURE_POLL_INTERVAL_HOURS = 6
RESULTS_POLL_INTERVAL_HOURS = 1
CLOSING_ODDS_BEFORE_KICKOFF_MIN = 5

# Markets
MARKETS_TIER1 = [
    "player_shots_ou",
    "player_tackles_ou",
    "player_passes_ou",
    "anytime_goalscorer",
    "player_cards",
]
MARKETS_TIER2 = [
    "team_corners_ou",
    "team_goals_ou",
    "btts",
]
MARKETS_TIER3 = [
    "match_result_1x2",
    "asian_handicap",
]
ALL_MARKETS = MARKETS_TIER2 + MARKETS_TIER1 + MARKETS_TIER3  # Priority order
