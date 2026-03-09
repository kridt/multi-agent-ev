"""Tests for ev_engine.calculator.EVCalculator."""

import pytest

from ev_engine.calculator import EVCalculator


class TestCalculateEV:
    def test_positive_ev(self):
        """55% model prob at 2.00 odds -> 10% EV."""
        assert EVCalculator.calculate_ev(0.55, 2.00) == pytest.approx(0.10)

    def test_zero_ev(self):
        """50% model prob at 2.00 odds -> 0% EV (fair price)."""
        assert EVCalculator.calculate_ev(0.50, 2.00) == pytest.approx(0.00)

    def test_negative_ev(self):
        """45% model prob at 2.00 odds -> -10% EV."""
        assert EVCalculator.calculate_ev(0.45, 2.00) == pytest.approx(-0.10)

    def test_certain_outcome(self):
        """100% model prob at 2.00 odds -> 100% EV."""
        assert EVCalculator.calculate_ev(1.0, 2.00) == pytest.approx(1.00)

    def test_zero_prob(self):
        """0% model prob at any odds -> -100% EV."""
        assert EVCalculator.calculate_ev(0.0, 2.00) == pytest.approx(-1.00)

    def test_odds_of_one(self):
        """Any prob at 1.00 odds -> (prob * 1) - 1 = prob - 1."""
        assert EVCalculator.calculate_ev(0.55, 1.00) == pytest.approx(-0.45)

    def test_high_odds(self):
        """10% prob at 12.00 odds -> (0.10 * 12) - 1 = 0.20."""
        assert EVCalculator.calculate_ev(0.10, 12.00) == pytest.approx(0.20)


class TestCalculateImpliedProb:
    def test_even_money(self):
        """2.00 odds -> 50% implied probability."""
        assert EVCalculator.calculate_implied_prob(2.00) == pytest.approx(0.50)

    def test_heavy_favorite(self):
        """1.25 odds -> 80% implied probability."""
        assert EVCalculator.calculate_implied_prob(1.25) == pytest.approx(0.80)

    def test_longshot(self):
        """10.00 odds -> 10% implied probability."""
        assert EVCalculator.calculate_implied_prob(10.00) == pytest.approx(0.10)

    def test_zero_odds_returns_zero(self):
        """Zero odds should return 0 (guard against division by zero)."""
        assert EVCalculator.calculate_implied_prob(0.0) == 0.0

    def test_negative_odds_returns_zero(self):
        """Negative odds should return 0."""
        assert EVCalculator.calculate_implied_prob(-1.0) == 0.0


class TestCalculateMargin:
    def test_fair_two_way(self):
        """[2.00, 2.00] -> margin = 0.0 (no overround)."""
        assert EVCalculator.calculate_margin([2.00, 2.00]) == pytest.approx(0.0)

    def test_with_margin(self):
        """[1.90, 1.90] -> 1/1.90 + 1/1.90 - 1 = ~0.05263."""
        expected = (1 / 1.90) + (1 / 1.90) - 1.0
        assert EVCalculator.calculate_margin([1.90, 1.90]) == pytest.approx(expected)

    def test_three_way_margin(self):
        """Three-way market: [2.50, 3.30, 2.80]."""
        expected = (1 / 2.50) + (1 / 3.30) + (1 / 2.80) - 1.0
        assert EVCalculator.calculate_margin([2.50, 3.30, 2.80]) == pytest.approx(expected)

    def test_empty_list(self):
        """Empty list returns 0."""
        assert EVCalculator.calculate_margin([]) == 0.0


class TestMeetsThreshold:
    def test_exactly_at_threshold(self):
        """EV of 0.03 meets default threshold of 0.03."""
        assert EVCalculator.meets_threshold(0.03) is True

    def test_just_below_threshold(self):
        """EV of 0.029 does NOT meet default threshold of 0.03."""
        assert EVCalculator.meets_threshold(0.029) is False

    def test_above_threshold(self):
        """EV of 0.10 meets default threshold."""
        assert EVCalculator.meets_threshold(0.10) is True

    def test_custom_threshold(self):
        """Custom threshold of 0.05: 0.04 fails, 0.05 passes."""
        assert EVCalculator.meets_threshold(0.04, threshold=0.05) is False
        assert EVCalculator.meets_threshold(0.05, threshold=0.05) is True


class TestEdge:
    def test_positive_edge(self):
        """Model 55% vs implied 50% -> edge = 0.05."""
        assert EVCalculator.edge(0.55, 0.50) == pytest.approx(0.05)

    def test_negative_edge(self):
        """Model 45% vs implied 50% -> edge = -0.05."""
        assert EVCalculator.edge(0.45, 0.50) == pytest.approx(-0.05)

    def test_zero_edge(self):
        """Model matches implied -> edge = 0."""
        assert EVCalculator.edge(0.50, 0.50) == pytest.approx(0.0)
