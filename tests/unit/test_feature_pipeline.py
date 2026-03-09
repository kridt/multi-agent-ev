"""Unit tests for the feature engineering pipeline components."""

import math

import numpy as np
import pytest

from features.consistency import ConsistencyScorer
from features.drift import DriftDetector
from features.opponent_adjustment import OpponentAdjuster
from features.per90 import normalize_per90, normalize_player_stats_per90
from features.rolling import RollingCalculator


# ────────────────────────────────────────────────────────
#  Per-90 normalisation
# ────────────────────────────────────────────────────────


class TestPer90:
    def test_per90_basic(self):
        """2 goals in 90 minutes = 2.0 per 90."""
        assert normalize_per90(2, 90) == pytest.approx(2.0)

    def test_per90_partial(self):
        """1 goal in 45 minutes = 2.0 per 90."""
        assert normalize_per90(1, 45) == pytest.approx(2.0)

    def test_per90_below_minimum(self):
        """< 15 minutes played returns None."""
        assert normalize_per90(1, 10) is None
        assert normalize_per90(1, 14) is None

    def test_per90_exact_minimum(self):
        """Exactly 15 minutes should be included."""
        result = normalize_per90(1, 15)
        assert result is not None
        assert result == pytest.approx(6.0)

    def test_normalize_player_stats_per90_includes_goals(self):
        """Goals should be normalized."""
        stats = {"goals": 1, "assists": 0, "shots": 3}
        result = normalize_player_stats_per90(stats, 90)
        assert result["goals"] == pytest.approx(1.0)

    def test_normalize_player_stats_per90_skips_rate_based(self):
        """pass_accuracy_pct and xg should NOT be normalized."""
        stats = {"pass_accuracy_pct": 85.0, "xg": 0.7, "goals": 2}
        result = normalize_player_stats_per90(stats, 90)
        # Rate-based stats stay unchanged
        assert result["pass_accuracy_pct"] == pytest.approx(85.0)
        assert result["xg"] == pytest.approx(0.7)
        # goals is normalized
        assert result["goals"] == pytest.approx(2.0)

    def test_normalize_player_stats_per90_below_min(self):
        """When minutes < min, per90 stats become None."""
        stats = {"goals": 1, "pass_accuracy_pct": 80.0}
        result = normalize_player_stats_per90(stats, 10)
        assert result["goals"] is None
        # Rate-based stat is still passed through
        assert result["pass_accuracy_pct"] == pytest.approx(80.0)


# ────────────────────────────────────────────────────────
#  Rolling calculations
# ────────────────────────────────────────────────────────


class TestRolling:
    def test_rolling_mean(self):
        """Mean of last 3 values of [1,2,3,4,5] is 4.0."""
        assert RollingCalculator.rolling_mean([1, 2, 3, 4, 5], 3) == pytest.approx(4.0)

    def test_rolling_median(self):
        """Median of last 3 values of [1,2,3,4,5] is 4.0."""
        assert RollingCalculator.rolling_median([1, 2, 3, 4, 5], 3) == pytest.approx(4.0)

    def test_rolling_std(self):
        """Standard deviation of [3, 4, 5] (sample std) = 1.0."""
        result = RollingCalculator.rolling_std([1, 2, 3, 4, 5], 3)
        assert result == pytest.approx(1.0)

    def test_rolling_trend_positive(self):
        """Increasing values should give a positive slope."""
        result = RollingCalculator.rolling_trend([1, 2, 3, 4, 5], 5)
        assert result is not None
        assert result > 0

    def test_rolling_trend_negative(self):
        """Decreasing values should give a negative slope."""
        result = RollingCalculator.rolling_trend([5, 4, 3, 2, 1], 5)
        assert result is not None
        assert result < 0

    def test_rolling_trend_flat(self):
        """Constant values should give a slope of 0."""
        result = RollingCalculator.rolling_trend([3, 3, 3, 3, 3], 5)
        assert result == pytest.approx(0.0)

    def test_rolling_insufficient_data(self):
        """Window > len(values) returns None for all stats."""
        assert RollingCalculator.rolling_mean([1, 2], 5) is None
        assert RollingCalculator.rolling_median([1, 2], 5) is None
        assert RollingCalculator.rolling_std([1, 2], 5) is None
        assert RollingCalculator.rolling_trend([1, 2], 5) is None

    def test_compute_all_windows(self):
        """compute_all_windows returns correct structure with w3, w5, w10 keys."""
        values = list(range(1, 11))  # [1, 2, ..., 10]
        result = RollingCalculator.compute_all_windows(values, [3, 5, 10])
        assert set(result.keys()) == {"w3", "w5", "w10"}
        for key in result:
            assert set(result[key].keys()) == {"mean", "median", "std", "trend"}
        # w3 mean of [8, 9, 10]
        assert result["w3"]["mean"] == pytest.approx(9.0)


# ────────────────────────────────────────────────────────
#  Opponent adjustment
# ────────────────────────────────────────────────────────


class TestOpponentAdjustment:
    def test_opponent_adjustment(self):
        """stat=3, opponent_avg=2, league_avg=4 -> 3*4/2 = 6."""
        adjuster = OpponentAdjuster({"goals": 4.0})
        result = adjuster.adjust(3.0, 2.0, "goals")
        assert result == pytest.approx(6.0)

    def test_opponent_adjustment_zero_opponent(self):
        """When opponent_avg is 0, returns raw stat unchanged."""
        adjuster = OpponentAdjuster({"goals": 4.0})
        result = adjuster.adjust(3.0, 0.0, "goals")
        assert result == pytest.approx(3.0)

    def test_opponent_adjustment_zero_league_avg(self):
        """When league_avg is 0, returns raw stat unchanged."""
        adjuster = OpponentAdjuster({"goals": 0.0})
        result = adjuster.adjust(3.0, 2.0, "goals")
        assert result == pytest.approx(3.0)

    def test_adjust_batch(self):
        """adjust_batch applies adjustment to all stats."""
        adjuster = OpponentAdjuster({"goals": 2.0, "shots": 10.0})
        stats = {"goals": 3.0, "shots": 15.0}
        opp_avgs = {"goals": 1.0, "shots": 12.0}
        result = adjuster.adjust_batch(stats, opp_avgs)
        # goals: 3 * 2 / 1 = 6
        assert result["goals"] == pytest.approx(6.0)
        # shots: 15 * 10 / 12 = 12.5
        assert result["shots"] == pytest.approx(12.5)

    def test_compute_league_averages(self):
        """League averages are the mean across all teams."""
        team_stats = [
            {"goals": 2.0, "shots": 10.0},
            {"goals": 4.0, "shots": 14.0},
        ]
        result = OpponentAdjuster.compute_league_averages(team_stats)
        assert result["goals"] == pytest.approx(3.0)
        assert result["shots"] == pytest.approx(12.0)

    def test_compute_league_averages_empty(self):
        """Empty team_stats list returns empty dict."""
        assert OpponentAdjuster.compute_league_averages([]) == {}


# ────────────────────────────────────────────────────────
#  Consistency scoring
# ────────────────────────────────────────────────────────


class TestConsistency:
    def test_cv_consistent(self):
        """Low variance values should have CV < 0.3."""
        values = [10.0, 10.1, 9.9, 10.0, 10.2]
        cv = ConsistencyScorer.coefficient_of_variation(values)
        assert cv is not None
        assert cv < 0.3
        assert ConsistencyScorer.categorize(cv) == "consistent"

    def test_cv_volatile(self):
        """High variance values should have CV > 0.6."""
        values = [1.0, 10.0, 2.0, 15.0, 0.5]
        cv = ConsistencyScorer.coefficient_of_variation(values)
        assert cv is not None
        assert cv > 0.6
        assert ConsistencyScorer.categorize(cv) == "volatile"

    def test_cv_moderate(self):
        """Moderate variance values should be categorised as 'moderate'."""
        # Construct values with CV between 0.3 and 0.6
        # mean=10, std~4 => CV~0.4
        values = [8.0, 6.0, 14.0, 10.0, 12.0]
        cv = ConsistencyScorer.coefficient_of_variation(values)
        assert cv is not None
        assert 0.3 <= cv <= 0.6
        assert ConsistencyScorer.categorize(cv) == "moderate"

    def test_cv_too_few_values(self):
        """< 3 values returns None."""
        assert ConsistencyScorer.coefficient_of_variation([1.0, 2.0]) is None
        assert ConsistencyScorer.coefficient_of_variation([]) is None

    def test_cv_zero_mean(self):
        """When mean is 0, CV is None."""
        assert ConsistencyScorer.coefficient_of_variation([0.0, 0.0, 0.0]) is None

    def test_score_player(self):
        """score_player returns a dict with cv, category, values_used."""
        values = [10.0, 10.1, 9.9, 10.0, 10.2]
        result = ConsistencyScorer.score_player(values, window=5)
        assert "cv" in result
        assert "category" in result
        assert result["values_used"] == 5
        assert result["category"] == "consistent"


# ────────────────────────────────────────────────────────
#  Drift detection
# ────────────────────────────────────────────────────────


class TestDrift:
    def test_psi_no_drift(self):
        """Same distribution -> PSI approximately 0."""
        rng = np.random.default_rng(42)
        data = rng.normal(0, 1, 1000)
        psi = DriftDetector.calculate_psi(data, data)
        assert psi == pytest.approx(0.0, abs=0.01)

    def test_psi_significant_drift(self):
        """Very different distributions -> PSI > 0.2."""
        rng = np.random.default_rng(42)
        ref = rng.normal(0, 1, 1000)
        cur = rng.normal(5, 1, 1000)
        psi = DriftDetector.calculate_psi(ref, cur)
        assert psi > 0.2

    def test_psi_constant_distribution(self):
        """Constant values (no variance) -> PSI = 0."""
        ref = np.ones(100)
        cur = np.ones(100)
        psi = DriftDetector.calculate_psi(ref, cur)
        assert psi == pytest.approx(0.0)

    def test_ks_same_distribution(self):
        """Same distribution should yield high p-value (> 0.05)."""
        rng = np.random.default_rng(42)
        data = rng.normal(0, 1, 500)
        stat, pvalue = DriftDetector.calculate_ks(data, data)
        assert pvalue > 0.05

    def test_ks_different_distribution(self):
        """Very different distributions should yield low p-value (< 0.05)."""
        rng = np.random.default_rng(42)
        ref = rng.normal(0, 1, 500)
        cur = rng.normal(5, 1, 500)
        stat, pvalue = DriftDetector.calculate_ks(ref, cur)
        assert pvalue < 0.05

    def test_check_drift_no_drift(self):
        """check_drift with same data should report no drift."""
        rng = np.random.default_rng(42)
        data = rng.normal(0, 1, 500)
        result = DriftDetector.check_drift(data, data)
        assert result["drifted"] is False
        assert "no significant drift" in result["reason"]

    def test_check_drift_significant(self):
        """check_drift with very different distributions should report drift."""
        rng = np.random.default_rng(42)
        ref = rng.normal(0, 1, 500)
        cur = rng.normal(5, 1, 500)
        result = DriftDetector.check_drift(ref, cur)
        assert result["drifted"] is True
        assert result["psi"] > 0.2
        assert result["ks_pvalue"] < 0.05
        assert "PSI" in result["reason"] or "KS" in result["reason"]
