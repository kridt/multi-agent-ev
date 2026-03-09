"""Rolling window statistical calculations."""

import numpy as np

from config.constants import ROLLING_WINDOWS


class RollingCalculator:
    """Compute rolling statistics over historical value sequences."""

    @staticmethod
    def rolling_mean(values: list[float], window: int) -> float | None:
        """Mean of last ``window`` values. None if not enough data."""
        if len(values) < window:
            return None
        return float(np.mean(values[-window:]))

    @staticmethod
    def rolling_median(values: list[float], window: int) -> float | None:
        """Median of last ``window`` values. None if not enough data."""
        if len(values) < window:
            return None
        return float(np.median(values[-window:]))

    @staticmethod
    def rolling_std(values: list[float], window: int) -> float | None:
        """Standard deviation of last ``window`` values. None if not enough data."""
        if len(values) < window:
            return None
        return float(np.std(values[-window:], ddof=1))

    @staticmethod
    def rolling_trend(values: list[float], window: int) -> float | None:
        """Linear regression slope over last ``window`` values.

        Positive = improving, negative = declining.
        Uses ordinary least squares: slope = cov(x, y) / var(x).
        """
        if len(values) < window:
            return None
        y = np.array(values[-window:], dtype=float)
        x = np.arange(window, dtype=float)
        x_mean = x.mean()
        y_mean = y.mean()
        slope = np.sum((x - x_mean) * (y - y_mean)) / np.sum((x - x_mean) ** 2)
        return float(slope)

    @staticmethod
    def compute_all_windows(
        values: list[float], windows: list[int] | None = None
    ) -> dict[str, dict[str, float | None]]:
        """Compute mean, median, std, trend for each window size.

        Returns::

            {
                "w3": {"mean": ..., "median": ..., "std": ..., "trend": ...},
                "w5": {...},
                "w10": {...},
            }
        """
        if windows is None:
            windows = ROLLING_WINDOWS

        calc = RollingCalculator
        result: dict[str, dict[str, float | None]] = {}
        for w in windows:
            key = f"w{w}"
            result[key] = {
                "mean": calc.rolling_mean(values, w),
                "median": calc.rolling_median(values, w),
                "std": calc.rolling_std(values, w),
                "trend": calc.rolling_trend(values, w),
            }
        return result
