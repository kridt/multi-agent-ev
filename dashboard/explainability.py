"""
Signal explanation generator for EV betting opportunities.

Produces human-readable explanations for WHY a bet has expected value,
including a one-line summary, bullet-point reasons, risk factors, and a
recommendation label derived from the BetGrader overall grade.

ASSUMPTIONS (all explicit):
- ev_pct is a DECIMAL FRACTION (e.g., 0.155 for 15.5%), consistent with
  EVCalculator.calculate_ev() and the rest of the ev_engine.  All display
  text converts to percentage points by multiplying by 100.
- model_prob is a decimal fraction (e.g., 0.55 for 55%).
- implied_prob is a decimal fraction (e.g., 0.476 for 47.6%).
  It is expected to satisfy implied_prob = 1 / odds, but this module does
  not re-derive or validate that; the caller is responsible for consistency
  between these two values.
- edge is a decimal fraction: model_prob - implied_prob (e.g., 0.074 for
  7.4 percentage points).  Display text converts to pp by multiplying by 100.
- odds is a European decimal odds value > 1.0.
- confidence is a decimal fraction in [0.0, 1.0].
- model_agreement is a decimal fraction in [0.0, 1.0], or None.
- consistency_cv is the coefficient of variation as a decimal >= 0.0, or None.
- odds_movement is a dict with keys "from" (float) and "to" (float) representing
  the opening/previous odds and the current odds respectively, or None.
  "Drifting" means to > from (odds lengthened; market moving against the pick).
  "Shortening" means to < from (odds compressed; market agreeing with model).
- sharp_odds is the price at a sharp reference bookmaker (e.g., Pinnacle), or None.
- market and selection are free-text strings passed through verbatim.
- bookmaker is the name of the Danish bookmaker offering the odds.

RECOMMENDATION MAPPING (derived from BetGrader overall grade):
  A -> "Strong Buy"
  B -> "Buy"
  C -> "Marginal"
  D -> "Pass"

The recommendation is determined by running BetGrader internally, ensuring it
always agrees with the grading output for the same inputs.

MINIMUM EV DISPLAY THRESHOLD used in reasons text: 3% (0.03 as decimal).
HIGH EV ALERT THRESHOLD used in risk text: 15% (0.15 as decimal).
"""

from __future__ import annotations

from dataclasses import dataclass, field

from dashboard.grading import BetGrader


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------


@dataclass
class SignalExplanation:
    """Human-readable explanation for a single EV signal."""

    summary: str
    """Concise one-line summary of the opportunity."""

    reasons: list[str] = field(default_factory=list)
    """Ordered bullet-point reasons explaining why positive EV exists."""

    risk_factors: list[str] = field(default_factory=list)
    """Ordered list of potential risks or concerns with this signal."""

    recommendation: str = ""
    """One of: 'Strong Buy', 'Buy', 'Marginal', 'Pass'."""


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

# Odds sweet-spot range that earns an A grade (mirrors grading.py definition).
_SWEET_SPOT_LOW: float = 1.80
_SWEET_SPOT_HIGH: float = 2.50

# Minimum EV threshold in DECIMAL form (3% = 0.03).
_MIN_EV_THRESHOLD: float = 0.03

# EV level above which a high-EV anomaly warning is added to risk factors.
_HIGH_EV_ALERT: float = 0.15

# Model confidence below which a concern is added to risk factors.
_CONFIDENCE_WARN_THRESHOLD: float = 0.85

# Consistency CV above which a volatility warning is added to risk factors.
_CV_WARN_THRESHOLD: float = 0.50

# Model agreement above which a positive reason is included.
_AGREEMENT_POSITIVE_THRESHOLD: float = 0.75

# Consistency CV below which a positive consistency reason is included.
_CV_POSITIVE_THRESHOLD: float = 0.35

# Edge (decimal fraction) above which "significantly exceeds" phrasing is used.
_EDGE_SIGNIFICANT_THRESHOLD: float = 0.05

_GRADE_TO_RECOMMENDATION: dict[str, str] = {
    "A": "Strong Buy",
    "B": "Buy",
    "C": "Marginal",
    "D": "Pass",
}


# ---------------------------------------------------------------------------
# Main engine
# ---------------------------------------------------------------------------


class ExplainabilityEngine:
    """
    Generates structured, human-readable explanations for EV betting signals.

    The engine performs no I/O or external lookups.  All inputs are passed in;
    the engine derives explanations deterministically from those inputs.

    The recommendation is derived by running BetGrader internally so that it
    always agrees with the grading output for the same set of inputs.

    This class is stateless and thread-safe.  A single instance may be reused.
    """

    def __init__(self) -> None:
        self._grader = BetGrader()

    def explain(
        self,
        ev_pct: float,
        model_prob: float,
        odds: float,
        implied_prob: float,
        edge: float,
        confidence: float,
        market: str,
        selection: str,
        bookmaker: str,
        model_agreement: float | None = None,
        consistency_cv: float | None = None,
        odds_movement: dict | None = None,
        sharp_odds: float | None = None,
    ) -> SignalExplanation:
        """
        Generate a full explanation for a single EV signal.

        Parameters
        ----------
        ev_pct:
            Expected value as a DECIMAL FRACTION (e.g., 0.155 for 15.5%).
        model_prob:
            Model-derived win probability as a decimal fraction (e.g., 0.55).
        odds:
            Decimal bookmaker odds at the Danish book (e.g., 2.10). Must be > 1.0.
        implied_prob:
            Implied probability from the bookmaker's odds: 1/odds (e.g., 0.476).
            Passed explicitly so the caller's calculation is part of the audit trail.
        edge:
            Model edge as a decimal fraction: model_prob - implied_prob (e.g., 0.074).
            Displayed in percentage points in all output text.
        confidence:
            Model confidence score as a decimal fraction (e.g., 0.92).
        market:
            Market type string (e.g., "Over/Under 2.5").
        selection:
            Selection string (e.g., "Over 2.5", "Arsenal Home Win").
        bookmaker:
            Name of the Danish bookmaker offering the odds.
        model_agreement:
            Fraction of ensemble models agreeing, as a decimal fraction, or None.
        consistency_cv:
            Coefficient of variation of historical performance, or None.
        odds_movement:
            Dict with "from" (float) and "to" (float) keys. Example:
            {"from": 2.25, "to": 2.10} means odds shortened (positive signal).
            {"from": 2.00, "to": 2.20} means odds drifted (risk factor).
            Pass None if no prior snapshot is available.
        sharp_odds:
            Current odds at a sharp reference bookmaker (e.g., Pinnacle), or None.

        Returns
        -------
        SignalExplanation
            Structured explanation with summary, reasons, risk_factors, recommendation.

        Raises
        ------
        ValueError
            Any validation error from BetGrader is propagated unchanged.
        """
        # Derive overall grade by running the grader so recommendation is always
        # consistent with the grading output for the same inputs.
        bet_grade = self._grader.grade(
            ev_pct=ev_pct,
            model_prob=model_prob,
            odds=odds,
            confidence=confidence,
            model_agreement=model_agreement,
            consistency_cv=consistency_cv,
        )
        overall_grade = bet_grade.overall_grade
        recommendation = _GRADE_TO_RECOMMENDATION[overall_grade]

        # Precompute display values (percentage points) for use in text builders.
        # All decimal fractions are multiplied by 100 for human-readable display.
        edge_pp: float = edge * 100.0              # 0.074 -> 7.4 pp
        model_prob_pct: float = model_prob * 100.0       # 0.55 -> 55.0%
        implied_prob_pct: float = implied_prob * 100.0   # 0.476 -> 47.6%
        ev_pct_display: float = ev_pct * 100.0           # 0.155 -> 15.5%

        # Multiple of the minimum EV threshold (3%).
        # Example: ev_pct=0.09 -> ev_multiple = 0.09/0.03 = 3.0 (3x the minimum).
        ev_multiple: float = ev_pct / _MIN_EV_THRESHOLD

        summary = self._build_summary(
            ev_pct_display=ev_pct_display,
            market=market,
            selection=selection,
            odds=odds,
            model_prob_pct=model_prob_pct,
            implied_prob_pct=implied_prob_pct,
            bookmaker=bookmaker,
        )

        reasons = self._build_reasons(
            ev_pct_display=ev_pct_display,
            ev_multiple=ev_multiple,
            model_prob_pct=model_prob_pct,
            implied_prob_pct=implied_prob_pct,
            edge_pp=edge_pp,
            odds=odds,
            confidence=confidence,
            model_agreement=model_agreement,
            consistency_cv=consistency_cv,
            odds_movement=odds_movement,
            sharp_odds=sharp_odds,
        )

        risk_factors = self._build_risk_factors(
            ev_pct_display=ev_pct_display,
            confidence=confidence,
            odds=odds,
            consistency_cv=consistency_cv,
            odds_movement=odds_movement,
            sharp_odds=sharp_odds,
        )

        return SignalExplanation(
            summary=summary,
            reasons=reasons,
            risk_factors=risk_factors,
            recommendation=recommendation,
        )

    # -----------------------------------------------------------------------
    # Private builders
    # -----------------------------------------------------------------------

    @staticmethod
    def _build_summary(
        ev_pct_display: float,
        market: str,
        selection: str,
        odds: float,
        model_prob_pct: float,
        implied_prob_pct: float,
        bookmaker: str,
    ) -> str:
        """
        Produce a concise one-line summary.

        Format:
            "{Strength} {ev%}% EV on {selection} at {odds} ({market}) --
             model sees {model%}% vs market's {implied%}% at {bookmaker}"

        Strength adjective is derived from the EV percentage display value
        (not the overall grade) so it reflects the EV magnitude directly.
        """
        if ev_pct_display >= 10.0:
            strength = "Strong"
        elif ev_pct_display >= 6.0:
            strength = "Solid"
        elif ev_pct_display >= 3.0:
            strength = "Viable"
        else:
            strength = "Marginal"

        return (
            f"{strength} {ev_pct_display:.1f}% EV on {selection} at {odds:.2f} ({market}) -- "
            f"model sees {model_prob_pct:.1f}% vs market's {implied_prob_pct:.1f}% "
            f"at {bookmaker}"
        )

    @staticmethod
    def _build_reasons(
        ev_pct_display: float,
        ev_multiple: float,
        model_prob_pct: float,
        implied_prob_pct: float,
        edge_pp: float,
        odds: float,
        confidence: float,
        model_agreement: float | None,
        consistency_cv: float | None,
        odds_movement: dict | None,
        sharp_odds: float | None,
    ) -> list[str]:
        """
        Build ordered list of bullet-point reasons explaining the positive EV.

        Four core reasons are always included: edge, EV multiple, odds range,
        confidence.  Contextual reasons are added when the relevant data is
        available and meets the positive threshold.

        Order:
          1. Model-market edge (core)
          2. EV multiple vs threshold (core)
          3. Odds range assessment (core)
          4. Model confidence (core)
          5. Sharp bookmaker cross-validation (contextual)
          6. Odds shortening (contextual)
          7. Ensemble model agreement (contextual)
          8. Historical consistency (contextual)
        """
        reasons: list[str] = []

        # 1. Core: model vs market edge (always present).
        # Use stronger phrasing when edge >= 5 pp (_EDGE_SIGNIFICANT_THRESHOLD).
        if edge_pp >= _EDGE_SIGNIFICANT_THRESHOLD * 100.0:
            edge_qualifier = "significantly exceeds"
        else:
            edge_qualifier = "exceeds"
        reasons.append(
            f"Model probability ({model_prob_pct:.1f}%) {edge_qualifier} "
            f"implied probability ({implied_prob_pct:.1f}%) -- "
            f"{edge_pp:.1f} percentage point edge"
        )

        # 2. Core: EV vs minimum threshold (always present).
        reasons.append(
            f"Expected value of {ev_pct_display:.1f}% is "
            f"{ev_multiple:.1f}x the minimum {_MIN_EV_THRESHOLD * 100:.0f}% threshold"
        )

        # 3. Core: odds range assessment (always present).
        if _SWEET_SPOT_LOW <= odds <= _SWEET_SPOT_HIGH:
            reasons.append(
                f"Odds of {odds:.2f} fall in the optimal sweet-spot range "
                f"({_SWEET_SPOT_LOW:.2f}-{_SWEET_SPOT_HIGH:.2f})"
            )
        elif (1.50 <= odds < _SWEET_SPOT_LOW) or (_SWEET_SPOT_HIGH < odds <= 3.00):
            reasons.append(
                f"Odds of {odds:.2f} are in a solid, productive range"
            )
        elif (1.30 <= odds < 1.50) or (3.00 < odds <= 4.00):
            reasons.append(
                f"Odds of {odds:.2f} are in an acceptable range, though not optimal"
            )
        else:
            # Outside 1.30-4.00: note factually; risk section will flag it.
            reasons.append(
                f"Odds of {odds:.2f} are outside the preferred range -- reviewed and accepted"
            )

        # 4. Core: model confidence (always present).
        confidence_qualifier = "high" if confidence >= 0.85 else "moderate"
        reasons.append(
            f"Model confidence of {confidence:.0%} indicates {confidence_qualifier} reliability"
        )

        # 5. Contextual: sharp bookmaker cross-validation.
        if sharp_odds is not None:
            sharp_implied_pct = (1.0 / sharp_odds) * 100.0
            reasons.append(
                f"Sharp bookmaker prices this at {sharp_odds:.2f} "
                f"(implied {sharp_implied_pct:.1f}%), close to our model -- "
                f"confirms the edge is real"
            )

        # 6. Contextual: odds shortening (market moving toward the pick).
        if odds_movement is not None:
            odds_from = odds_movement.get("from")
            odds_to = odds_movement.get("to")
            if odds_from is not None and odds_to is not None and odds_to < odds_from:
                movement_pct = abs(odds_to - odds_from) / odds_from * 100.0
                reasons.append(
                    f"Odds shortened from {odds_from:.2f} to {odds_to:.2f} "
                    f"({movement_pct:.1f}% movement), suggesting market agrees with model"
                )

        # 7. Contextual: ensemble model agreement (only when >= positive threshold).
        if model_agreement is not None and model_agreement >= _AGREEMENT_POSITIVE_THRESHOLD:
            reasons.append(
                f"{model_agreement:.0%} of models in the ensemble agree on this outcome"
            )

        # 8. Contextual: historical consistency (only when CV is low enough).
        if consistency_cv is not None and consistency_cv < _CV_POSITIVE_THRESHOLD:
            reasons.append(
                f"Historical performance data shows consistent pattern "
                f"(CV: {consistency_cv:.2f})"
            )

        return reasons

    @staticmethod
    def _build_risk_factors(
        ev_pct_display: float,
        confidence: float,
        odds: float,
        consistency_cv: float | None,
        odds_movement: dict | None,
        sharp_odds: float | None,
    ) -> list[str]:
        """
        Build ordered list of risk factors and concerns for this signal.

        Risk factors are only included when the relevant condition is met.
        An empty list is a valid result when no conditions trigger.

        Order:
          1. Anomaly check (EV suspiciously high)
          2. Low model confidence
          3. Long-shot odds (> 4.00)
          4. Extremely short odds (< 1.30)
          5. Slightly elevated odds (3.00 < odds <= 4.00)
          6. High performance volatility
          7. Odds drifting (market moving against the pick)
          8. No sharp bookmaker cross-validation
        """
        risks: list[str] = []

        # 1. Anomaly check: very high EV warrants manual verification.
        if ev_pct_display > _HIGH_EV_ALERT * 100.0:
            risks.append(
                f"Exceptionally high EV ({ev_pct_display:.1f}%) -- verify this is not "
                f"a data anomaly or stale odds snapshot"
            )

        # 2. Low model confidence.
        if confidence < _CONFIDENCE_WARN_THRESHOLD:
            risks.append(
                f"Model confidence below {_CONFIDENCE_WARN_THRESHOLD:.0%} "
                f"(actual: {confidence:.0%}) -- smaller sample or uncertain features "
                f"may reduce reliability"
            )

        # 3-5. Odds territory.
        if odds > 4.00:
            risks.append(
                f"Odds of {odds:.2f} are in long-shot territory -- "
                f"higher variance expected, Kelly stake should be reduced"
            )
        elif odds < 1.30:
            risks.append(
                f"Odds of {odds:.2f} are extremely short -- "
                f"minimal return potential, any edge can be wiped by margin uncertainty"
            )
        elif odds > 3.00:
            # Inside 1.30-4.00 but above the preferred upper bound.
            risks.append(
                f"Odds of {odds:.2f} are above the preferred range -- "
                f"moderate variance expected"
            )

        # 6. High performance volatility.
        if consistency_cv is not None and consistency_cv >= _CV_WARN_THRESHOLD:
            risks.append(
                f"High performance volatility (CV: {consistency_cv:.2f}) -- "
                f"outcomes may be unpredictable"
            )

        # 7. Odds drifting (market moving against the pick).
        if odds_movement is not None:
            odds_from = odds_movement.get("from")
            odds_to = odds_movement.get("to")
            if odds_from is not None and odds_to is not None and odds_to > odds_from:
                movement_pct = (odds_to - odds_from) / odds_from * 100.0
                risks.append(
                    f"Odds are drifting (from {odds_from:.2f} to {odds_to:.2f}, "
                    f"+{movement_pct:.1f}%), which may indicate market moving "
                    f"against this pick"
                )

        # 8. No sharp bookmaker cross-validation.
        if sharp_odds is None:
            risks.append(
                "No sharp bookmaker data available for cross-validation -- "
                "edge cannot be independently confirmed"
            )

        return risks
