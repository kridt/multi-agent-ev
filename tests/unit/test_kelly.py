"""Tests for risk.kelly.KellyCalculator."""

import pytest

from risk.kelly import KellyCalculator


class TestFullKelly:
    def test_positive_edge(self):
        """55% prob at 2.00 odds: (0.55*2 - 1) / (2 - 1) = 0.10."""
        assert KellyCalculator.full_kelly(0.55, 2.00) == pytest.approx(0.10)

    def test_large_edge(self):
        """70% prob at 2.00 odds: (0.70*2 - 1) / (2 - 1) = 0.40."""
        assert KellyCalculator.full_kelly(0.70, 2.00) == pytest.approx(0.40)

    def test_no_edge(self):
        """50% prob at 2.00 odds: (0.50*2 - 1) / (2 - 1) = 0.0."""
        assert KellyCalculator.full_kelly(0.50, 2.00) == pytest.approx(0.0)

    def test_negative_edge_returns_zero(self):
        """40% prob at 2.00 odds -> negative numerator -> returns 0."""
        assert KellyCalculator.full_kelly(0.40, 2.00) == 0.0

    def test_odds_equal_one_returns_zero(self):
        """Odds of 1.00 -> denominator is 0 -> returns 0."""
        assert KellyCalculator.full_kelly(0.90, 1.00) == 0.0

    def test_odds_below_one_returns_zero(self):
        """Odds below 1.0 are invalid -> returns 0."""
        assert KellyCalculator.full_kelly(0.90, 0.50) == 0.0

    def test_higher_odds_scenario(self):
        """30% prob at 4.00 odds: (0.30*4 - 1) / (4 - 1) = 0.20/3 = 0.06667."""
        assert KellyCalculator.full_kelly(0.30, 4.00) == pytest.approx(0.06667, rel=1e-3)


class TestFractionalKelly:
    def test_quarter_kelly_default(self):
        """55% prob at 2.00: full=0.10, quarter=0.10*0.25=0.025."""
        assert KellyCalculator.fractional_kelly(0.55, 2.00) == pytest.approx(0.025)

    def test_half_kelly(self):
        """55% prob at 2.00: full=0.10, half=0.10*0.50=0.05."""
        assert KellyCalculator.fractional_kelly(0.55, 2.00, fraction=0.50) == pytest.approx(0.05)

    def test_negative_edge_returns_zero(self):
        """No edge -> 0 regardless of fraction."""
        assert KellyCalculator.fractional_kelly(0.40, 2.00) == 0.0

    def test_third_kelly(self):
        """70% prob at 2.00: full=0.40, third=0.40/3=0.13333."""
        assert KellyCalculator.fractional_kelly(0.70, 2.00, fraction=1 / 3) == pytest.approx(
            0.13333, rel=1e-3
        )


class TestStakeAmount:
    def test_basic_stake(self):
        """Bankroll 10000, kelly 0.025 -> 250 DKK."""
        assert KellyCalculator.stake_amount(10000, 0.025) == pytest.approx(250.0)

    def test_zero_kelly(self):
        """Zero Kelly -> zero stake."""
        assert KellyCalculator.stake_amount(10000, 0.0) == pytest.approx(0.0)

    def test_small_bankroll(self):
        """Bankroll 1000, kelly 0.03 -> 30 DKK."""
        assert KellyCalculator.stake_amount(1000, 0.03) == pytest.approx(30.0)
