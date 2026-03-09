"""Opponent strength adjustment for raw stats."""

from __future__ import annotations

import numpy as np


class OpponentAdjuster:
    """Adjust raw stats based on opponent defensive/offensive strength
    relative to league averages.
    """

    def __init__(self, league_averages: dict[str, float]):
        """Initialize with league-wide averages.

        Args:
            league_averages: e.g. {"goals_conceded": 1.3, "corners_conceded": 5.2, ...}
        """
        self.league_averages = league_averages

    @staticmethod
    def compute_league_averages(team_stats: list[dict[str, float]]) -> dict[str, float]:
        """Compute league-wide averages for each stat from all teams.

        Args:
            team_stats: List of stat dicts, one per team. Each dict maps
                stat name -> value. All dicts should have the same keys.

        Returns:
            Dict mapping each stat name to its league-wide mean.
        """
        if not team_stats:
            return {}

        all_keys: set[str] = set()
        for ts in team_stats:
            all_keys.update(ts.keys())

        averages: dict[str, float] = {}
        for key in all_keys:
            vals = [ts[key] for ts in team_stats if key in ts]
            if vals:
                averages[key] = float(np.mean(vals))
            else:
                averages[key] = 0.0
        return averages

    def adjust(self, raw_stat: float, opponent_stat_avg: float, stat_name: str) -> float:
        """Adjust a raw stat for opponent strength.

        Formula: raw_stat * league_avg / opponent_avg

        If opponent_avg is 0, returns raw_stat unchanged.

        Args:
            raw_stat: The raw stat value to adjust.
            opponent_stat_avg: The opponent's average for this stat category.
            stat_name: The stat name (used to look up the league average).

        Returns:
            Opponent-adjusted stat value.
        """
        league_avg = self.league_averages.get(stat_name, 0.0)
        if opponent_stat_avg == 0 or league_avg == 0:
            return raw_stat
        return raw_stat * league_avg / opponent_stat_avg

    def adjust_batch(
        self, stats: dict[str, float], opponent_averages: dict[str, float]
    ) -> dict[str, float]:
        """Adjust all stats in a dict against opponent averages.

        Args:
            stats: Raw stat dict, e.g. {"goals": 2.1, "shots": 14.5}.
            opponent_averages: Opponent's averages keyed by the same stat names.

        Returns:
            Dict with the same keys, values adjusted for opponent strength.
        """
        adjusted: dict[str, float] = {}
        for stat_name, raw_value in stats.items():
            opp_avg = opponent_averages.get(stat_name, 0.0)
            adjusted[stat_name] = self.adjust(raw_value, opp_avg, stat_name)
        return adjusted
