"""
Bet quality grading system for EV signals.

Grades each signal on 6 parameters (A/B/C/D) and produces a weighted overall grade.

ASSUMPTIONS (all explicit):
- ev_pct is a DECIMAL FRACTION (e.g., 0.155 for 15.5%), consistent with the rest
  of the ev_engine which stores EV as (model_prob * odds) - 1.
  EVCalculator.calculate_ev() returns 0.10 for 10% EV.  All display text converts
  to percentage points by multiplying by 100.
- model_prob is a decimal fraction (e.g., 0.55 for 55%).
- odds is a decimal (European) odds value > 1.0.
- model_agreement is a decimal fraction (e.g., 0.90 for 90%), or None.
  When None, the value 0.75 is substituted (earns grade B per spec).
  This substitution is stored in ParameterGrade.value for traceability.
- consistency_cv is the coefficient of variation as a decimal (e.g., 0.20), or None.
  When None, the value 0.40 is substituted (earns grade C per spec).
  This substitution is stored in ParameterGrade.value for traceability.
- edge is computed internally as (model_prob - implied_prob) as a decimal fraction.
  Thresholds compare in decimal form (A>=0.08, B>=0.05, C>=0.03, D<0.03).
  Display text converts to percentage points by multiplying by 100.

GRADING THRESHOLDS:

  EV % (decimal fraction):
    A: >= 0.10   B: >= 0.06   C: >= 0.03   D: < 0.03

  Edge = model_prob - (1/odds), decimal fraction:
    A: >= 0.08   B: >= 0.05   C: >= 0.03   D: < 0.03

  Confidence (decimal fraction):
    A: >= 0.92   B: >= 0.85   C: >= 0.80   D: < 0.80

  Odds Value (decimal European odds):
    A: [1.80, 2.50]  sweet spot, inclusive both ends
    B: [1.50, 1.80) or (2.50, 3.00]  solid range
    C: [1.30, 1.50) or (3.00, 4.00]  acceptable
    D: outside [1.30, 4.00]

  Model Agreement (decimal fraction, default 0.75 if None):
    A: >= 0.90   B: >= 0.75   C: >= 0.60   D: < 0.60

  Consistency CV (decimal, default 0.40 if None):
    A: < 0.20   B: < 0.35   C: < 0.50   D: >= 0.50

GRADING WEIGHTS:
  EV %:            25%
  Edge:            25%
  Confidence:      20%
  Odds Value:      15%
  Model Agreement: 10%
  Consistency:      5%

GRADE SCALE: A=4, B=3, C=2, D=1
OVERALL THRESHOLDS: >= 3.5 -> A, >= 2.75 -> B, >= 2.0 -> C, else D
"""

from __future__ import annotations

from dataclasses import dataclass


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------


@dataclass
class ParameterGrade:
    """Grade result for a single grading parameter."""

    parameter: str
    """One of: 'ev', 'edge', 'confidence', 'odds_value', 'model_agreement', 'consistency'."""

    grade: str
    """Letter grade: 'A', 'B', 'C', or 'D'."""

    value: float
    """
    The raw value that was graded, in the natural unit of the parameter:
    - ev: decimal fraction (e.g., 0.155 for 15.5%)
    - edge: decimal fraction (e.g., 0.074 for 7.4 pp)
    - confidence: decimal fraction (e.g., 0.88)
    - odds_value: decimal odds (e.g., 2.10)
    - model_agreement: decimal fraction; 0.75 when caller passed None
    - consistency: decimal CV; 0.40 when caller passed None
    """

    label: str
    """Human-readable label for the parameter and its display value."""

    description: str
    """Short human-readable explanation of what this grade means in context."""


@dataclass
class BetGrade:
    """Aggregate grade result for a single EV signal."""

    overall_grade: str
    """Letter grade: 'A', 'B', 'C', or 'D'."""

    overall_score: float
    """Weighted score on the 1.0-4.0 scale before mapping to a letter. Rounded to 4 dp."""

    parameters: list[ParameterGrade]
    """Individual grades for each of the 6 parameters, in weight-descending order."""


# ---------------------------------------------------------------------------
# Grade conversion helpers
# ---------------------------------------------------------------------------

_GRADE_TO_SCORE: dict[str, float] = {"A": 4.0, "B": 3.0, "C": 2.0, "D": 1.0}

# Ordered highest-to-lowest; anything that does not satisfy a threshold falls to "D".
_OVERALL_THRESHOLDS: list[tuple[float, str]] = [
    (3.5, "A"),
    (2.75, "B"),
    (2.0, "C"),
]

_WEIGHTS: dict[str, float] = {
    "ev": 0.25,
    "edge": 0.25,
    "confidence": 0.20,
    "odds_value": 0.15,
    "model_agreement": 0.10,
    "consistency": 0.05,
}

# Sanity-check at import time: if weights are edited incorrectly the module fails fast.
assert abs(sum(_WEIGHTS.values()) - 1.0) < 1e-9, "Weights must sum to 1.0"

# Default substitution values when optional inputs are None.
# 0.75 earns grade B  (0.75 >= 0.75, not >= 0.90)
# 0.40 earns grade C  (0.35 <= 0.40 < 0.50)
_DEFAULT_MODEL_AGREEMENT: float = 0.75
_DEFAULT_CONSISTENCY_CV: float = 0.40


def _score_to_grade(weighted_score: float) -> str:
    """Map a weighted score on the 1.0-4.0 scale to a letter grade."""
    for threshold, grade in _OVERALL_THRESHOLDS:
        if weighted_score >= threshold:
            return grade
    return "D"


# ---------------------------------------------------------------------------
# Individual parameter graders
# ---------------------------------------------------------------------------


def _grade_ev(ev_pct: float) -> ParameterGrade:
    """
    Grade EV percentage.

    ev_pct is a DECIMAL FRACTION (e.g., 0.155 for 15.5%).

    Thresholds (decimal fraction):
      A: >= 0.10  exceptional value
      B: >= 0.06  strong value
      C: >= 0.03  viable value
      D:  < 0.03  marginal / below minimum threshold

    Display converts to percentage points (* 100).
    Description states the multiple vs the grade's own threshold, giving context
    on the magnitude of the advantage over that boundary.
    """
    # Display value in percentage points (multiply by 100).
    ev_display: float = ev_pct * 100.0

    if ev_pct >= 0.10:
        multiple: float = ev_pct / 0.10
        grade = "A"
        description = f"Exceptional value -- {multiple:.1f}x the A threshold (10%)"
    elif ev_pct >= 0.06:
        multiple = ev_pct / 0.06
        grade = "B"
        description = f"Strong value -- {multiple:.1f}x the B threshold (6%)"
    elif ev_pct >= 0.03:
        multiple = ev_pct / 0.03
        grade = "C"
        description = f"Viable value -- {multiple:.1f}x the minimum threshold (3%)"
    else:
        grade = "D"
        description = f"Marginal value -- {ev_display:.1f}% EV is below the 3% minimum"

    return ParameterGrade(
        parameter="ev",
        grade=grade,
        value=ev_pct,
        label=f"EV: {ev_display:.1f}%",
        description=description,
    )


def _grade_edge(edge: float) -> ParameterGrade:
    """
    Grade model edge (model_prob - implied_prob) as a decimal fraction.

    edge is a DECIMAL FRACTION (e.g., 0.074 for 7.4 percentage points).
    Display converts to percentage points (* 100).

    Thresholds (decimal fraction):
      A: >= 0.08  dominant edge
      B: >= 0.05  solid edge
      C: >= 0.03  thin but playable
      D:  < 0.03  razor thin / may be noise
    """
    # Display value in percentage points.
    edge_display: float = edge * 100.0

    if edge >= 0.08:
        grade = "A"
        description = f"Dominant edge -- model outpaces market by {edge_display:.1f} pp"
    elif edge >= 0.05:
        grade = "B"
        description = f"Solid edge -- clear {edge_display:.1f} pp model-market divergence"
    elif edge >= 0.03:
        grade = "C"
        description = f"Thin but playable -- {edge_display:.1f} pp edge within acceptable range"
    else:
        grade = "D"
        description = f"Razor thin -- {edge_display:.1f} pp edge, high risk of being noise"

    return ParameterGrade(
        parameter="edge",
        grade=grade,
        value=edge,
        label=f"Edge: {edge_display:.1f} pp",
        description=description,
    )


def _grade_confidence(confidence: float) -> ParameterGrade:
    """
    Grade model confidence score (decimal fraction, 0.0-1.0).

    Thresholds:
      A: >= 0.92  very high confidence
      B: >= 0.85  high confidence
      C: >= 0.80  acceptable
      D:  < 0.80  low confidence
    """
    if confidence >= 0.92:
        grade = "A"
        description = "Very high confidence -- strong, consistent feature signals"
    elif confidence >= 0.85:
        grade = "B"
        description = "High confidence -- reliable prediction with good feature coverage"
    elif confidence >= 0.80:
        grade = "C"
        description = "Acceptable confidence -- some uncertainty remains in features"
    else:
        grade = "D"
        description = f"Low confidence ({confidence:.0%}) -- prediction may be unreliable"

    return ParameterGrade(
        parameter="confidence",
        grade=grade,
        value=confidence,
        label=f"Confidence: {confidence:.0%}",
        description=description,
    )


def _grade_odds_value(odds: float) -> ParameterGrade:
    """
    Grade whether decimal odds fall in a productive range.

    Boundary note: at shared boundary values the higher grade wins.
    All comparisons use >= on the lower bound and strict < on the upper bound,
    except where the highest-priority range uses <= on both ends.

    Thresholds:
      A: [1.80, 2.50]         sweet spot, inclusive both ends
      B: [1.50, 1.80)  or  (2.50, 3.00]
      C: [1.30, 1.50)  or  (3.00, 4.00]
      D: outside [1.30, 4.00]
    """
    if 1.80 <= odds <= 2.50:
        grade = "A"
        description = "Sweet-spot odds -- optimal balance of probability and return"
    elif (1.50 <= odds < 1.80) or (2.50 < odds <= 3.00):
        grade = "B"
        description = "Solid odds range -- good expected value territory"
    elif (1.30 <= odds < 1.50) or (3.00 < odds <= 4.00):
        grade = "C"
        description = "Acceptable odds -- slightly outside the optimal range"
    else:
        grade = "D"
        description = "Risky odds range -- either too short or long-shot territory"

    return ParameterGrade(
        parameter="odds_value",
        grade=grade,
        value=odds,
        label=f"Odds: {odds:.2f}",
        description=description,
    )


def _grade_model_agreement(model_agreement: float | None) -> ParameterGrade:
    """
    Grade ensemble model agreement (decimal fraction, 0.0-1.0).

    When model_agreement is None, the value 0.75 is substituted (earns B).
    The substituted value is stored in ParameterGrade.value for traceability;
    callers can detect the substitution from the label which includes "(default B)".

    Thresholds:
      A: >= 0.90  strong consensus
      B: >= 0.75  majority agreement
      C: >= 0.60  weak majority
      D:  < 0.60  split models
    """
    effective_value: float = (
        _DEFAULT_MODEL_AGREEMENT if model_agreement is None else model_agreement
    )
    is_default: bool = model_agreement is None

    if effective_value >= 0.90:
        grade = "A"
        description = "Strong consensus -- models unanimously agree on the outcome"
    elif effective_value >= 0.75:
        grade = "B"
        if is_default:
            description = (
                "No ensemble data -- default value (0.75) applied, earning grade B per policy"
            )
        else:
            description = "Majority agreement -- most models are aligned"
    elif effective_value >= 0.60:
        grade = "C"
        description = "Weak majority -- meaningful disagreement across ensemble models"
    else:
        grade = "D"
        description = "Split models -- high uncertainty in ensemble"

    label = (
        "Model Agreement: N/A (default B)"
        if is_default
        else f"Model Agreement: {effective_value:.0%}"
    )

    return ParameterGrade(
        parameter="model_agreement",
        grade=grade,
        value=effective_value,
        label=label,
        description=description,
    )


def _grade_consistency(consistency_cv: float | None) -> ParameterGrade:
    """
    Grade historical performance consistency via coefficient of variation (CV).

    When consistency_cv is None, the value 0.40 is substituted (earns C).
    The substituted value is stored in ParameterGrade.value for traceability;
    callers can detect the substitution from the label which includes "(default C)".

    Thresholds (lower CV = more consistent):
      A: CV < 0.20  very stable performance
      B: CV < 0.35  stable performance
      C: CV < 0.50  moderate variance
      D: CV >= 0.50  volatile performance
    """
    effective_cv: float = (
        _DEFAULT_CONSISTENCY_CV if consistency_cv is None else consistency_cv
    )
    is_default: bool = consistency_cv is None

    if effective_cv < 0.20:
        grade = "A"
        description = "Very stable -- low historical variance in performance"
    elif effective_cv < 0.35:
        grade = "B"
        description = "Stable performance -- manageable variance in historical results"
    elif effective_cv < 0.50:
        grade = "C"
        if is_default:
            description = (
                "No consistency data -- default value (CV=0.40) applied, earning grade C per policy"
            )
        else:
            description = "Moderate variance -- some unpredictability in historical performance"
    else:
        grade = "D"
        description = (
            f"Volatile -- high historical variance (CV={effective_cv:.2f}), caution warranted"
        )

    label = (
        "Consistency CV: N/A (default C)"
        if is_default
        else f"Consistency CV: {effective_cv:.2f}"
    )

    return ParameterGrade(
        parameter="consistency",
        grade=grade,
        value=effective_cv,
        label=label,
        description=description,
    )


# ---------------------------------------------------------------------------
# Main grader class
# ---------------------------------------------------------------------------


class BetGrader:
    """
    Grades an EV betting signal across 6 parameters and produces an overall grade.

    All inputs are validated before grading. Invalid inputs raise ValueError
    rather than silently producing a grade (fail-closed principle).

    This class is stateless and thread-safe. A single instance may be reused.
    """

    def grade(
        self,
        ev_pct: float,
        model_prob: float,
        odds: float,
        confidence: float,
        model_agreement: float | None = None,
        consistency_cv: float | None = None,
    ) -> BetGrade:
        """
        Grade an EV signal across 6 parameters.

        Parameters
        ----------
        ev_pct:
            Expected value as a DECIMAL FRACTION (e.g., 0.155 for 15.5%).
            This matches EVCalculator.calculate_ev() output: (prob * odds) - 1.
        model_prob:
            Model-derived win probability as a decimal fraction (e.g., 0.55).
            Must be in (0.0, 1.0) exclusive.
        odds:
            Decimal bookmaker odds (e.g., 2.10). Must be > 1.0.
        confidence:
            Model confidence score as a decimal fraction (e.g., 0.88).
            Must be in [0.0, 1.0].
        model_agreement:
            Fraction of ensemble models agreeing, as a decimal fraction.
            Must be in [0.0, 1.0] if provided. Pass None if unavailable.
            When None, substitutes 0.75 internally (earns grade B).
        consistency_cv:
            Coefficient of variation of recent performance (decimal, e.g., 0.30).
            Must be >= 0.0 if provided. Pass None if unavailable.
            When None, substitutes 0.40 internally (earns grade C).

        Returns
        -------
        BetGrade
            Structured grade with individual parameter grades and weighted overall grade.
            parameters list is in weight-descending order.

        Raises
        ------
        ValueError
            If any required parameter is outside its valid range.
        """
        # --- Input validation (fail closed -- no silent fallbacks for required fields) ---
        if odds <= 1.0:
            raise ValueError(
                f"odds must be > 1.0 to be a valid decimal odds value; got {odds}"
            )
        if not (0.0 < model_prob < 1.0):
            raise ValueError(
                f"model_prob must be in (0.0, 1.0) exclusive; got {model_prob}"
            )
        if not (0.0 <= confidence <= 1.0):
            raise ValueError(
                f"confidence must be in [0.0, 1.0]; got {confidence}"
            )
        if model_agreement is not None and not (0.0 <= model_agreement <= 1.0):
            raise ValueError(
                f"model_agreement must be in [0.0, 1.0] or None; got {model_agreement}"
            )
        if consistency_cv is not None and consistency_cv < 0.0:
            raise ValueError(
                f"consistency_cv must be >= 0.0 or None; got {consistency_cv}"
            )

        # --- Derived values ---
        # implied_prob = 1 / decimal_odds  (standard inverse-odds formula)
        # This is the raw bookmaker-implied probability, not devigged.
        # The caller is responsible for passing devigged odds if devigging has occurred.
        implied_prob: float = 1.0 / odds

        # edge = model_prob - implied_prob as a decimal fraction.
        # Example: model_prob=0.55, implied_prob=0.4762 -> edge=0.0738 (7.38 pp)
        edge: float = model_prob - implied_prob

        # --- Grade each parameter ---
        param_ev = _grade_ev(ev_pct)
        param_edge = _grade_edge(edge)
        param_confidence = _grade_confidence(confidence)
        param_odds_value = _grade_odds_value(odds)
        param_model_agreement = _grade_model_agreement(model_agreement)
        param_consistency = _grade_consistency(consistency_cv)

        # Listed in weight-descending order (25%, 25%, 20%, 15%, 10%, 5%).
        parameters: list[ParameterGrade] = [
            param_ev,
            param_edge,
            param_confidence,
            param_odds_value,
            param_model_agreement,
            param_consistency,
        ]

        # --- Weighted overall score ---
        # Each letter grade maps to a numeric score: A=4, B=3, C=2, D=1.
        # Weighted sum -> overall letter grade via _OVERALL_THRESHOLDS.
        weighted_score: float = sum(
            _GRADE_TO_SCORE[pg.grade] * _WEIGHTS[pg.parameter]
            for pg in parameters
        )

        overall_grade: str = _score_to_grade(weighted_score)

        return BetGrade(
            overall_grade=overall_grade,
            overall_score=round(weighted_score, 4),
            parameters=parameters,
        )
