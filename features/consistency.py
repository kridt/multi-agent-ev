"""Consistency scoring via coefficient of variation."""

from __future__ import annotations

import numpy as np

from config.constants import CV_CONSISTENT, CV_MODERATE


class ConsistencyScorer:
    """Evaluate how consistent a player/team is for a given stat."""

    @staticmethod
    def coefficient_of_variation(values: list[float]) -> float | None:
        """Coefficient of variation = std / mean.

        Returns None if mean is 0 or not enough data (< 3 values).
        Uses sample standard deviation (ddof=1).
        """
        if len(values) < 3:
            return None
        arr = np.array(values, dtype=float)
        mean = float(arr.mean())
        if mean == 0:
            return None
        std = float(arr.std(ddof=1))
        return std / abs(mean)

    @staticmethod
    def categorize(cv: float) -> str:
        """Categorize a CV value.

        - CV < 0.3  -> 'consistent'
        - 0.3 <= CV <= 0.6 -> 'moderate'
        - CV > 0.6  -> 'volatile'
        """
        if cv < CV_CONSISTENT:
            return "consistent"
        elif cv <= CV_MODERATE:
            return "moderate"
        else:
            return "volatile"

    @staticmethod
    def score_player(stat_values: list[float], window: int = 10) -> dict:
        """Score a player's consistency for a particular stat.

        Uses the last ``window`` values (or all if fewer are available).

        Returns::

            {"cv": float | None, "category": str | None, "values_used": int}
        """
        subset = stat_values[-window:]
        cv = ConsistencyScorer.coefficient_of_variation(subset)
        category = ConsistencyScorer.categorize(cv) if cv is not None else None
        return {
            "cv": cv,
            "category": category,
            "values_used": len(subset),
        }
