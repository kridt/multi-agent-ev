"""Tests for ev_engine.filters."""

import pytest

from ev_engine.filters import (
    ConfidenceFilter,
    ConsistencyFilter,
    EVThresholdFilter,
    FilterChain,
    OddsRangeFilter,
    SignalCandidate,
)


def _make_candidate(**overrides) -> SignalCandidate:
    """Helper to create a SignalCandidate with sensible defaults."""
    defaults = {
        "match_id": "match-001",
        "market": "player_shots_ou",
        "selection": "over_0.5",
        "bookmaker": "bet365",
        "odds": 2.00,
        "model_prob": 0.60,
        "ev": 0.05,
        "confidence": 0.85,
        "consistency_cv": None,
    }
    defaults.update(overrides)
    return SignalCandidate(**defaults)


class TestOddsRangeFilter:
    def test_below_min_fails(self):
        """Odds 1.49 fails default min of 1.50."""
        f = OddsRangeFilter()
        assert f.passes(_make_candidate(odds=1.49)) is False

    def test_at_min_passes(self):
        """Odds exactly 1.50 passes."""
        f = OddsRangeFilter()
        assert f.passes(_make_candidate(odds=1.50)) is True

    def test_at_max_passes(self):
        """Odds exactly 4.00 passes."""
        f = OddsRangeFilter()
        assert f.passes(_make_candidate(odds=4.00)) is True

    def test_above_max_fails(self):
        """Odds 4.01 fails default max of 4.00."""
        f = OddsRangeFilter()
        assert f.passes(_make_candidate(odds=4.01)) is False

    def test_mid_range_passes(self):
        """Odds 2.50 in range passes."""
        f = OddsRangeFilter()
        assert f.passes(_make_candidate(odds=2.50)) is True

    def test_custom_range(self):
        """Custom range [1.80, 3.00]: 1.79 fails, 1.80 passes, 3.01 fails."""
        f = OddsRangeFilter(min_odds=1.80, max_odds=3.00)
        assert f.passes(_make_candidate(odds=1.79)) is False
        assert f.passes(_make_candidate(odds=1.80)) is True
        assert f.passes(_make_candidate(odds=3.01)) is False


class TestEVThresholdFilter:
    def test_below_threshold_fails(self):
        """EV 0.029 fails default threshold of 0.03."""
        f = EVThresholdFilter()
        assert f.passes(_make_candidate(ev=0.029)) is False

    def test_at_threshold_passes(self):
        """EV exactly 0.03 passes."""
        f = EVThresholdFilter()
        assert f.passes(_make_candidate(ev=0.03)) is True

    def test_above_threshold_passes(self):
        """EV 0.10 passes."""
        f = EVThresholdFilter()
        assert f.passes(_make_candidate(ev=0.10)) is True

    def test_negative_ev_fails(self):
        """Negative EV always fails."""
        f = EVThresholdFilter()
        assert f.passes(_make_candidate(ev=-0.05)) is False


class TestConfidenceFilter:
    def test_below_min_fails(self):
        """Confidence 0.74 fails default min of 0.75."""
        f = ConfidenceFilter()
        assert f.passes(_make_candidate(confidence=0.74)) is False

    def test_at_min_passes(self):
        """Confidence exactly 0.75 passes."""
        f = ConfidenceFilter()
        assert f.passes(_make_candidate(confidence=0.75)) is True

    def test_high_confidence_passes(self):
        """Confidence 0.95 passes."""
        f = ConfidenceFilter()
        assert f.passes(_make_candidate(confidence=0.95)) is True


class TestConsistencyFilter:
    def test_none_cv_passes(self):
        """None consistency_cv always passes (no data available)."""
        f = ConsistencyFilter()
        assert f.passes(_make_candidate(consistency_cv=None)) is True

    def test_low_cv_passes(self):
        """CV of 0.3 passes default max of 0.6."""
        f = ConsistencyFilter()
        assert f.passes(_make_candidate(consistency_cv=0.3)) is True

    def test_at_max_cv_passes(self):
        """CV exactly 0.6 passes (<=)."""
        f = ConsistencyFilter()
        assert f.passes(_make_candidate(consistency_cv=0.6)) is True

    def test_above_max_cv_fails(self):
        """CV 0.61 fails default max of 0.6."""
        f = ConsistencyFilter()
        assert f.passes(_make_candidate(consistency_cv=0.61)) is False


class TestFilterChain:
    def test_all_passing(self):
        """Candidate meeting all criteria survives."""
        chain = FilterChain()
        candidates = [_make_candidate(odds=2.00, ev=0.05, confidence=0.85)]
        result = chain.apply(candidates)
        assert len(result) == 1

    def test_ev_too_low_filtered(self):
        """Candidate with low EV is filtered out."""
        chain = FilterChain()
        candidates = [_make_candidate(ev=0.02)]
        result = chain.apply(candidates)
        assert len(result) == 0

    def test_odds_out_of_range_filtered(self):
        """Candidate with odds outside range is filtered out."""
        chain = FilterChain()
        candidates = [_make_candidate(odds=5.00)]
        result = chain.apply(candidates)
        assert len(result) == 0

    def test_low_confidence_filtered(self):
        """Candidate with low confidence is filtered out."""
        chain = FilterChain()
        candidates = [_make_candidate(confidence=0.60)]
        result = chain.apply(candidates)
        assert len(result) == 0

    def test_high_cv_filtered(self):
        """Candidate with high consistency CV is filtered out."""
        chain = FilterChain()
        candidates = [_make_candidate(consistency_cv=0.8)]
        result = chain.apply(candidates)
        assert len(result) == 0

    def test_mixed_batch(self):
        """Only candidates passing ALL filters survive."""
        chain = FilterChain()
        candidates = [
            _make_candidate(odds=2.00, ev=0.05, confidence=0.85),  # passes
            _make_candidate(odds=1.20, ev=0.05, confidence=0.85),  # fails odds
            _make_candidate(odds=2.00, ev=0.01, confidence=0.85),  # fails EV
            _make_candidate(odds=2.00, ev=0.05, confidence=0.50),  # fails confidence
            _make_candidate(odds=2.00, ev=0.05, confidence=0.85, consistency_cv=0.9),  # fails CV
        ]
        result = chain.apply(candidates)
        assert len(result) == 1
        assert result[0].match_id == "match-001"

    def test_empty_input(self):
        """Empty input returns empty output."""
        chain = FilterChain()
        assert chain.apply([]) == []

    def test_custom_filter_chain(self):
        """Custom filter chain with relaxed thresholds."""
        chain = FilterChain(filters=[EVThresholdFilter(min_ev=0.01)])
        candidates = [_make_candidate(ev=0.02, confidence=0.50)]  # low confidence OK here
        result = chain.apply(candidates)
        assert len(result) == 1
