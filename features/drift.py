"""Distribution drift detection using PSI and KS tests."""

from __future__ import annotations

import numpy as np
from scipy import stats as scipy_stats


class DriftDetector:
    """Detect distribution drift between reference and current data windows."""

    @staticmethod
    def calculate_psi(
        reference: np.ndarray, current: np.ndarray, bins: int = 10
    ) -> float:
        """Population Stability Index.

        PSI < 0.1: no significant shift.
        0.1 <= PSI <= 0.2: moderate shift.
        PSI > 0.2: significant shift.

        Uses equal-width bins derived from the reference distribution's range.
        A small epsilon is added to avoid log(0).
        """
        reference = np.asarray(reference, dtype=float)
        current = np.asarray(current, dtype=float)

        # Determine bin edges from the combined range to handle edge cases
        combined_min = min(reference.min(), current.min())
        combined_max = max(reference.max(), current.max())

        # Guard against constant distributions
        if combined_min == combined_max:
            return 0.0

        bin_edges = np.linspace(combined_min, combined_max, bins + 1)

        ref_counts, _ = np.histogram(reference, bins=bin_edges)
        cur_counts, _ = np.histogram(current, bins=bin_edges)

        # Convert to proportions with epsilon to avoid division by zero / log(0)
        eps = 1e-8
        ref_pct = ref_counts / len(reference) + eps
        cur_pct = cur_counts / len(current) + eps

        psi = float(np.sum((cur_pct - ref_pct) * np.log(cur_pct / ref_pct)))
        return psi

    @staticmethod
    def calculate_ks(
        reference: np.ndarray, current: np.ndarray
    ) -> tuple[float, float]:
        """Kolmogorov-Smirnov two-sample test.

        Returns (statistic, p_value).
        p_value < 0.05 indicates a significant distribution shift.
        """
        reference = np.asarray(reference, dtype=float)
        current = np.asarray(current, dtype=float)
        stat, pvalue = scipy_stats.ks_2samp(reference, current)
        return float(stat), float(pvalue)

    @staticmethod
    def check_drift(
        reference: np.ndarray,
        current: np.ndarray,
        psi_threshold: float = 0.2,
        ks_alpha: float = 0.05,
    ) -> dict:
        """Run both PSI and KS tests and return a combined drift report.

        Returns::

            {
                "psi": float,
                "ks_stat": float,
                "ks_pvalue": float,
                "drifted": bool,
                "reason": str,
            }
        """
        psi = DriftDetector.calculate_psi(reference, current)
        ks_stat, ks_pvalue = DriftDetector.calculate_ks(reference, current)

        reasons: list[str] = []
        if psi > psi_threshold:
            reasons.append(f"PSI={psi:.4f} > {psi_threshold}")
        if ks_pvalue < ks_alpha:
            reasons.append(f"KS p-value={ks_pvalue:.4f} < {ks_alpha}")

        drifted = len(reasons) > 0
        reason = "; ".join(reasons) if reasons else "no significant drift detected"

        return {
            "psi": psi,
            "ks_stat": ks_stat,
            "ks_pvalue": ks_pvalue,
            "drifted": drifted,
            "reason": reason,
        }
