"""Per-90-minute stat normalization."""

from config.constants import MIN_MINUTES_PER90

# Stats that should be normalized per 90 minutes.
# Rate-based stats like pass_accuracy_pct and xg are excluded.
PER90_STATS = [
    "goals",
    "assists",
    "shots",
    "shots_on_target",
    "key_passes",
    "passes",
    "tackles",
    "interceptions",
    "clearances",
    "blocks",
    "dribbles_attempted",
    "dribbles_succeeded",
    "fouls_committed",
    "fouls_drawn",
    "yellow_cards",
    "corners_taken",
    "offsides",
]

# Stats that are already rate-based and should NOT be normalized.
RATE_BASED_STATS = {"pass_accuracy_pct", "xg"}


def normalize_per90(
    stat_value: float, minutes_played: int, min_minutes: int = MIN_MINUTES_PER90
) -> float | None:
    """Normalize a stat to per-90-minute rate.

    Returns None if minutes_played < min_minutes.
    Formula: stat_value * 90 / minutes_played
    """
    if minutes_played < min_minutes:
        return None
    if minutes_played == 0:
        return None
    return stat_value * 90 / minutes_played


def normalize_player_stats_per90(
    stats: dict[str, float], minutes_played: int
) -> dict[str, float | None]:
    """Normalize all applicable player stats to per-90.

    Stats listed in PER90_STATS are normalized.
    Stats in RATE_BASED_STATS (pass_accuracy_pct, xg) are passed through unchanged.
    Other stats are passed through unchanged.
    """
    result: dict[str, float | None] = {}
    for stat_name, value in stats.items():
        if stat_name in RATE_BASED_STATS:
            result[stat_name] = value
        elif stat_name in PER90_STATS:
            result[stat_name] = normalize_per90(value, minutes_played)
        else:
            result[stat_name] = value
    return result
