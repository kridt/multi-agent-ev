"""Filters for EV signal candidates."""

from dataclasses import dataclass


@dataclass
class SignalCandidate:
    """A potential EV signal before final filtering."""

    match_id: str
    market: str
    selection: str
    bookmaker: str
    odds: float
    model_prob: float
    ev: float
    confidence: float
    consistency_cv: float | None = None


class OddsRangeFilter:
    """Filter candidates by acceptable odds range."""

    def __init__(self, min_odds: float = 1.50, max_odds: float = 4.00):
        self.min_odds = min_odds
        self.max_odds = max_odds

    def passes(self, candidate: SignalCandidate) -> bool:
        return self.min_odds <= candidate.odds <= self.max_odds


class EVThresholdFilter:
    """Filter candidates by minimum EV percentage."""

    def __init__(self, min_ev: float = 0.03):
        self.min_ev = min_ev

    def passes(self, candidate: SignalCandidate) -> bool:
        return candidate.ev >= self.min_ev


class ConfidenceFilter:
    """Filter candidates by minimum model confidence."""

    def __init__(self, min_confidence: float = 0.75):
        self.min_confidence = min_confidence

    def passes(self, candidate: SignalCandidate) -> bool:
        return candidate.confidence >= self.min_confidence


class ConsistencyFilter:
    """Filter candidates by maximum coefficient of variation.

    If consistency_cv is None (no consistency data available), the candidate passes.
    """

    def __init__(self, max_cv: float = 0.6):
        self.max_cv = max_cv

    def passes(self, candidate: SignalCandidate) -> bool:
        if candidate.consistency_cv is None:
            return True
        return candidate.consistency_cv <= self.max_cv


class FilterChain:
    """Apply a chain of filters to signal candidates.

    Default chain: OddsRange, EVThreshold, Confidence, Consistency.
    """

    def __init__(self, filters: list | None = None):
        self.filters = filters or [
            OddsRangeFilter(),
            EVThresholdFilter(),
            ConfidenceFilter(),
            ConsistencyFilter(),
        ]

    def apply(self, candidates: list[SignalCandidate]) -> list[SignalCandidate]:
        """Apply all filters and return passing candidates."""
        return [c for c in candidates if all(f.passes(c) for f in self.filters)]
