"""Analysis tools exposed to Claude agents.

These tools provide signal quality checks and market condition assessments.

Assumptions:
- check_weather_news and check_lineup_changes are explicitly placeholders.
  They return structured dicts with status="unavailable" and a reason code.
  No external API is called. Callers must treat these as informational only.
- detect_odds_anomaly operates on values already retrieved from the DB.
  It does NOT query the DB itself — the caller is responsible for providing
  the odds movement context.
- EV suspicion threshold is hardcoded at 0.15 (15%) per the system rules
  (EV > 15% is flagged as suspicious).
- Sharp bookmaker disagreement is defined as: model_prob implies odds of X
  but the best sharp price implies odds materially lower (i.e. the market
  disagrees with the model by more than SHARP_DISAGREEMENT_THRESHOLD).
- All thresholds are constants at module level so they are easy to audit.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Anomaly detection thresholds — all explicit, no magic numbers in logic.
# ---------------------------------------------------------------------------

# EV above this level triggers an extreme-value flag (expressed as a fraction).
EXTREME_EV_THRESHOLD: float = 0.15

# Odds movement (as a fraction of opening odds) above this triggers a flag.
# E.g., 0.10 means a 10% move from opening to current is suspicious.
LARGE_MOVEMENT_THRESHOLD: float = 0.10

# If model implied odds and the bookmaker odds diverge by more than this
# fraction of the bookmaker odds, it's flagged as potential model/market disagreement.
# E.g., 0.20 means model says fair value is 20%+ away from bookmaker's price.
SHARP_DISAGREEMENT_THRESHOLD: float = 0.20

# If the opening_odds for the same selection at any bookmaker moved toward
# shorter (i.e., movement_pct < 0, meaning odds shortened / money came in),
# this is consistent with sharp money. Threshold for calling it suspicious:
SHARP_STEAM_MOVE_PCT: float = -0.05  # 5% shortening


@dataclass
class OddsMovementSummary:
    """Compact view of odds movement data for a single market/selection.

    Attributes:
        bookmakers_moving_in: Number of bookmakers where odds shortened.
        bookmakers_moving_out: Number of bookmakers where odds lengthened.
        max_shortening_pct: Largest shortening seen (most negative movement_pct).
        max_lengthening_pct: Largest lengthening seen (most positive movement_pct).
        total_bookmakers: Total bookmakers in the movement dataset.
        steam_move_detected: True if any bookmaker shows a move >= SHARP_STEAM_MOVE_PCT.
    """

    bookmakers_moving_in: int = 0
    bookmakers_moving_out: int = 0
    max_shortening_pct: float = 0.0
    max_lengthening_pct: float = 0.0
    total_bookmakers: int = 0
    steam_move_detected: bool = False


def _summarise_movement(odds_movement_rows: list[dict]) -> OddsMovementSummary:
    """Convert raw odds movement dicts into a compact summary.

    Expects each row to have a 'movement_pct' key (float, from OddsMovement).
    movement_pct < 0 means odds shortened (money came in — bullish for the selection).
    movement_pct > 0 means odds lengthened (money went out — bearish for the selection).
    """
    summary = OddsMovementSummary(total_bookmakers=len(odds_movement_rows))

    for row in odds_movement_rows:
        pct: float = row.get("movement_pct", 0.0)
        if pct < 0:
            summary.bookmakers_moving_in += 1
            summary.max_shortening_pct = min(summary.max_shortening_pct, pct)
            if pct <= SHARP_STEAM_MOVE_PCT:
                summary.steam_move_detected = True
        elif pct > 0:
            summary.bookmakers_moving_out += 1
            summary.max_lengthening_pct = max(summary.max_lengthening_pct, pct)

    return summary


# ---------------------------------------------------------------------------
# Public tool functions
# ---------------------------------------------------------------------------


async def check_weather_news(team_name: str) -> dict:
    """Placeholder: check for relevant weather or news about a team.

    This is a placeholder function. No external API is called.
    Future implementation would query a news/weather API.

    Returns a structured dict with status='unavailable' and a reason code
    so that callers can handle the absence of data explicitly rather than
    silently treating it as "no issues found".

    Args:
        team_name: The name of the team to check (informational only).

    Returns:
        {
            "status": "unavailable",
            "reason": "NOT_IMPLEMENTED",
            "team_name": str,
            "weather_concern": None,
            "news_flags": [],
        }
    """
    logger.debug("check_weather_news called for %r — returning placeholder", team_name)
    return {
        "status": "unavailable",
        "reason": "NOT_IMPLEMENTED",
        "team_name": team_name,
        "weather_concern": None,
        "news_flags": [],
    }


async def check_lineup_changes(match_id: str) -> dict:
    """Placeholder: check for confirmed or projected lineup changes.

    This is a placeholder function. No external API is called.
    Future implementation would query SportMonks or a news aggregator
    for confirmed lineups or injury updates.

    Returns a structured dict with status='unavailable' and a reason code.

    Args:
        match_id: The internal match ID.

    Returns:
        {
            "status": "unavailable",
            "reason": "NOT_IMPLEMENTED",
            "match_id": str,
            "home_team_changes": [],
            "away_team_changes": [],
            "confirmed_lineups": False,
        }
    """
    logger.debug("check_lineup_changes called for match %r — returning placeholder", match_id)
    return {
        "status": "unavailable",
        "reason": "NOT_IMPLEMENTED",
        "match_id": match_id,
        "home_team_changes": [],
        "away_team_changes": [],
        "confirmed_lineups": False,
    }


def detect_odds_anomaly(
    match_id: str,
    market: str,
    selection: str,
    model_prob: float,
    odds: float,
    odds_movement_rows: list[dict] | None = None,
) -> dict:
    """Detect whether an EV signal has suspicious characteristics.

    This is a pure function (no DB access). All inputs are caller-provided.

    Patterns detected:
    1. EXTREME_EV — EV >= EXTREME_EV_THRESHOLD (15%). Signals this strong are
       almost always noise, model error, or a data error.
    2. STEAM_MOVE — Odds have shortened significantly across bookmakers,
       suggesting sharp money on the opposing side (or that the model's edge
       has already been priced in).
    3. MODEL_MARKET_DISAGREEMENT — Model probability implies a fair odds
       materially different from the current bookmaker odds. This is expected
       for value bets, but extreme disagreement warrants review.
    4. MOVEMENT_AGAINST_BET — Most bookmakers' odds moved AWAY from the
       selection (lengthened), while the model still shows value. This can
       indicate the market has information the model lacks.

    Args:
        match_id: Internal match ID (for logging/tracing only).
        market: Market type string (e.g., "over_under_2.5").
        selection: Selection string (e.g., "over").
        model_prob: The model's probability for this selection (0.0 to 1.0).
        odds: Current decimal odds at the target bookmaker.
        odds_movement_rows: List of OddsMovement dicts as returned by
            get_odds_movement(). May be empty or None if no movement data
            is available — the function handles this gracefully.

    Returns:
        {
            "anomaly_detected": bool,
            "flags": list[str],           # specific pattern codes triggered
            "ev_pct": float,              # computed EV for this signal
            "model_implied_fair_odds": float,  # 1 / model_prob
            "reason_summary": str,        # human-readable summary
            "movement_summary": dict | None,
        }

    NOTE: This function does NOT make the final approve/flag/reject decision.
    That decision is made by AnomalyReasoner using Claude. This function only
    surfaces the evidence.
    """
    if model_prob <= 0.0 or model_prob >= 1.0:
        # Degenerate probability — always flag.
        return {
            "anomaly_detected": True,
            "flags": ["INVALID_MODEL_PROB"],
            "ev_pct": 0.0,
            "model_implied_fair_odds": 0.0,
            "reason_summary": (
                f"Model probability {model_prob} is outside the valid range (0, 1). "
                "Signal cannot be evaluated."
            ),
            "movement_summary": None,
        }

    # EV = (model_prob * odds) - 1
    ev_pct: float = (model_prob * odds) - 1.0

    # Fair odds implied by the model (no margin).
    model_implied_fair_odds: float = 1.0 / model_prob

    flags: list[str] = []

    # --- Pattern 1: Extreme EV ---
    if ev_pct >= EXTREME_EV_THRESHOLD:
        flags.append("EXTREME_EV")

    # --- Pattern 3: Model vs market disagreement ---
    # Disagreement = |model_fair_odds - bookmaker_odds| / bookmaker_odds
    if odds > 0:
        disagreement_ratio = abs(model_implied_fair_odds - odds) / odds
        if disagreement_ratio > SHARP_DISAGREEMENT_THRESHOLD:
            flags.append("MODEL_MARKET_DISAGREEMENT")

    # --- Patterns 2 & 4: Odds movement analysis ---
    movement_rows = odds_movement_rows or []
    movement_summary_dict: dict | None = None

    if movement_rows:
        mv = _summarise_movement(movement_rows)
        movement_summary_dict = {
            "total_bookmakers": mv.total_bookmakers,
            "bookmakers_moving_in": mv.bookmakers_moving_in,
            "bookmakers_moving_out": mv.bookmakers_moving_out,
            "max_shortening_pct": mv.max_shortening_pct,
            "max_lengthening_pct": mv.max_lengthening_pct,
            "steam_move_detected": mv.steam_move_detected,
        }

        # Pattern 2: Steam move (sharp money on the opposing side).
        if mv.steam_move_detected:
            flags.append("STEAM_MOVE")

        # Pattern 4: Majority of books have odds moving against the selection
        # (lengthening) while we still think there's value.
        if mv.total_bookmakers > 0:
            pct_moving_out = mv.bookmakers_moving_out / mv.total_bookmakers
            if pct_moving_out > 0.6:  # majority (>60%) of books lengthened odds
                flags.append("MOVEMENT_AGAINST_BET")

    anomaly_detected = len(flags) > 0

    # Build human-readable summary.
    if not anomaly_detected:
        reason_summary = "No anomaly patterns detected."
    else:
        parts: list[str] = []
        if "EXTREME_EV" in flags:
            parts.append(
                f"EV of {ev_pct:.1%} exceeds the suspicion threshold of "
                f"{EXTREME_EV_THRESHOLD:.0%}."
            )
        if "MODEL_MARKET_DISAGREEMENT" in flags:
            parts.append(
                f"Model implies fair odds of {model_implied_fair_odds:.2f} but "
                f"bookmaker is offering {odds:.2f} — a large discrepancy."
            )
        if "STEAM_MOVE" in flags:
            parts.append("Steam move detected: odds shortened sharply at one or more bookmakers.")
        if "MOVEMENT_AGAINST_BET" in flags:
            parts.append(
                "Majority of bookmakers have lengthened odds for this selection, "
                "moving against the bet direction."
            )
        reason_summary = " ".join(parts)

    logger.debug(
        "detect_odds_anomaly: match=%s market=%s selection=%s flags=%s",
        match_id,
        market,
        selection,
        flags,
    )

    return {
        "anomaly_detected": anomaly_detected,
        "flags": flags,
        "ev_pct": round(ev_pct, 6),
        "model_implied_fair_odds": round(model_implied_fair_odds, 4),
        "reason_summary": reason_summary,
        "movement_summary": movement_summary_dict,
    }
