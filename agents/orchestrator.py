"""Orchestrator agent.

The main control loop that:
1. Fetches upcoming matches and their pending EV signals.
2. Runs anomaly detection and Claude reasoning on each suspicious signal.
3. Updates signal status (approved / flagged / rejected) in the DB.
4. Generates daily summary reports.

Design decisions:
- Inherits from BaseAgent to reuse the Claude tool-use loop, conversation
  history management, and Anthropic client setup.
- Uses Claude tool_use to let Claude invoke the db_tools and analysis_tools
  functions when reasoning about signals. This keeps the reasoning transparent
  and auditable — every data access Claude performs is logged.
- Signal updates are written in a separate DB session from reads to avoid
  long-lived transactions.
- run_daily_report() does NOT call Claude with tools. It assembles the report
  data directly and calls Claude once for a plain-text summary. This is
  cheaper and faster for a reporting use case.

Assumptions:
- Only signals with status='pending' are processed by run_scan_cycle().
- A signal with anomaly_flag=True but status='pending' has already been
  detected by rule-based checks; it will be escalated to Claude reasoning.
- A signal with no anomaly flags and EV within normal bounds is auto-approved
  without a Claude call (to save API costs).
- The orchestrator does not perform position sizing or order placement.
  It only updates signal status.

Tool schema notes:
- Each tool exposed to Claude maps 1:1 to a function in db_tools or
  analysis_tools.
- detect_odds_anomaly is a pure function (no DB), called by the orchestrator
  before passing to Claude, so its result is injected into context rather
  than exposed as a tool.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import Any

import anthropic

from agents.base_agent import BaseAgent
from agents.anomaly_reasoner import AnomalyReasoner
from agents.tools.analysis_tools import check_lineup_changes, check_weather_news, detect_odds_anomaly
from agents.tools.db_tools import (
    get_bankroll_status,
    get_model_performance,
    get_odds_movement,
    get_recent_bets,
    get_signals_for_match,
    get_upcoming_matches,
)
from db.models.predictions import EVSignal
from db.session import get_session
from sqlalchemy import select

logger = logging.getLogger(__name__)

# The Claude model used for orchestration tool-use calls.
CLAUDE_MODEL: str = "claude-opus-4-5"

# Hard cap on the Claude tool-use loop iterations per scan cycle.
# Prevents runaway API calls if Claude keeps requesting tools.
MAX_TOOL_ITERATIONS: int = 10

# Maximum tokens for orchestrator Claude responses.
MAX_TOKENS: int = 2048

# EV threshold below which we skip anomaly reasoning (signal is too marginal).
# Signals below this EV are left as 'pending' for manual review.
MIN_EV_FOR_REASONING: float = 0.03

# EV above this threshold triggers anomaly detection even if no flags exist.
# Consistent with EXTREME_EV_THRESHOLD in analysis_tools.
EXTREME_EV_THRESHOLD: float = 0.15

# ---------------------------------------------------------------------------
# Tool definitions for Claude tool_use
# ---------------------------------------------------------------------------

TOOLS: list[dict] = [
    {
        "name": "get_upcoming_matches",
        "description": (
            "Get scheduled matches kicking off within the next N hours. "
            "Returns a list of match metadata dicts."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "hours_ahead": {
                    "type": "integer",
                    "description": "How many hours ahead to look. Default 24.",
                    "default": 24,
                }
            },
            "required": [],
        },
    },
    {
        "name": "get_signals_for_match",
        "description": "Get all EV signals for a given match ID.",
        "input_schema": {
            "type": "object",
            "properties": {
                "match_id": {
                    "type": "string",
                    "description": "The internal UUID of the match.",
                }
            },
            "required": ["match_id"],
        },
    },
    {
        "name": "get_odds_movement",
        "description": (
            "Get odds movement data for a specific match/market/selection combination. "
            "Returns rows with opening_odds, closing_odds, movement_pct per bookmaker."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "match_id": {"type": "string"},
                "market": {"type": "string"},
                "selection": {"type": "string"},
            },
            "required": ["match_id", "market", "selection"],
        },
    },
    {
        "name": "get_bankroll_status",
        "description": "Get the current bankroll status from the most recent snapshot.",
        "input_schema": {
            "type": "object",
            "properties": {},
            "required": [],
        },
    },
    {
        "name": "get_recent_bets",
        "description": "Get recent bets placed within the last N days.",
        "input_schema": {
            "type": "object",
            "properties": {
                "days": {
                    "type": "integer",
                    "description": "Number of days to look back. Default 7.",
                    "default": 7,
                }
            },
            "required": [],
        },
    },
    {
        "name": "get_model_performance",
        "description": "Get the latest model performance metrics for a given model type.",
        "input_schema": {
            "type": "object",
            "properties": {
                "model_type": {
                    "type": "string",
                    "description": "The model type string (e.g. 'xgboost_btts', 'logistic_ou25').",
                }
            },
            "required": ["model_type"],
        },
    },
    {
        "name": "check_lineup_changes",
        "description": "Check for confirmed or projected lineup changes for a match (placeholder).",
        "input_schema": {
            "type": "object",
            "properties": {
                "match_id": {"type": "string"}
            },
            "required": ["match_id"],
        },
    },
    {
        "name": "check_weather_news",
        "description": "Check for weather or news relevant to a team (placeholder).",
        "input_schema": {
            "type": "object",
            "properties": {
                "team_name": {"type": "string"}
            },
            "required": ["team_name"],
        },
    },
]

# System prompt for the orchestration scan cycle.
SCAN_SYSTEM_PROMPT: str = """You are an EV betting signal scanner for a pre-match football betting system.
Your role is to review pending EV signals and assess whether they should be approved, flagged for
human review, or rejected.

You have access to database tools to retrieve signal details, odds movement, and model performance.

For each signal you are asked to assess:
1. Check the odds movement data to understand market direction.
2. Check model performance to assess whether the model is currently well-calibrated.
3. Identify any concerning patterns (extreme EV, adverse odds movement, model/market disagreement).
4. Provide a final recommendation: "approve", "flag", or "reject".

Be sceptical. Value betting requires discipline. Reject signals that look too good to be true.
Always check odds movement before approving a signal with EV > 10%.

When you have finished your assessment, output a JSON object:
{
  "recommendation": "approve" | "flag" | "reject",
  "reasoning": "<concise explanation>",
  "anomaly_detected": true | false,
  "risk_level": "low" | "medium" | "high"
}
"""


class Orchestrator(BaseAgent):
    """Main orchestrator agent for the EV betting system.

    Inherits from BaseAgent for Claude API calls and tool-use loop.

    Usage:
        orchestrator = Orchestrator()
        results = await orchestrator.run_scan_cycle()
        report = await orchestrator.run_daily_report()
    """

    def __init__(self) -> None:
        super().__init__(
            name="orchestrator",
            model=CLAUDE_MODEL,
            max_history=50,
            max_iterations=MAX_TOOL_ITERATIONS,
            max_tokens=MAX_TOKENS,
        )
        self._reasoner = AnomalyReasoner()

    # ------------------------------------------------------------------
    # BaseAgent abstract interface
    # ------------------------------------------------------------------

    @property
    def system_prompt(self) -> str:
        return SCAN_SYSTEM_PROMPT

    @property
    def tools(self) -> list[dict]:
        return TOOLS

    async def execute_tool(
        self, tool_name: str, tool_input: dict[str, Any]
    ) -> Any:
        """Dispatch a tool call to the appropriate function.

        Each tool maps 1:1 to a function in db_tools or analysis_tools.
        Raises KeyError for unknown tools (caught by BaseAgent._dispatch_tool).
        """
        if tool_name == "get_upcoming_matches":
            return await get_upcoming_matches(**tool_input)
        elif tool_name == "get_signals_for_match":
            return await get_signals_for_match(**tool_input)
        elif tool_name == "get_odds_movement":
            return await get_odds_movement(**tool_input)
        elif tool_name == "get_bankroll_status":
            return await get_bankroll_status()
        elif tool_name == "get_recent_bets":
            return await get_recent_bets(**tool_input)
        elif tool_name == "get_model_performance":
            return await get_model_performance(**tool_input)
        elif tool_name == "check_lineup_changes":
            return await check_lineup_changes(**tool_input)
        elif tool_name == "check_weather_news":
            return await check_weather_news(**tool_input)
        else:
            raise KeyError(f"Unknown tool: {tool_name!r}")

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def run_scan_cycle(self, hours_ahead: int = 24) -> dict[str, Any]:
        """Main scan cycle.

        Process:
        a. Fetch upcoming matches within hours_ahead.
        b. For each match, load pending EV signals.
        c. Run rule-based anomaly detection on each signal.
        d. For signals with anomaly flags OR extreme EV, invoke Claude reasoning.
        e. For clean signals (no flags, EV within normal range), auto-approve.
        f. Write updated signal statuses back to DB.

        Returns a summary dict with counts of approved, flagged, rejected signals.
        """
        logger.info("Orchestrator: starting scan cycle (hours_ahead=%d)", hours_ahead)

        matches = await get_upcoming_matches(hours_ahead=hours_ahead)
        logger.info("Orchestrator: found %d upcoming matches", len(matches))

        approved_count = 0
        flagged_count = 0
        rejected_count = 0
        skipped_count = 0
        errors: list[str] = []

        for match in matches:
            match_id: str = match["match_id"]
            signals = await get_signals_for_match(match_id)

            pending_signals = [s for s in signals if s["status"] == "pending"]
            if not pending_signals:
                continue

            for signal in pending_signals:
                try:
                    result = await self._process_signal(signal, match)
                except Exception as exc:
                    logger.error(
                        "Orchestrator: unhandled error processing signal %s — %s",
                        signal.get("signal_id"),
                        exc,
                        exc_info=True,
                    )
                    errors.append(f"signal {signal.get('signal_id')}: {exc}")
                    skipped_count += 1
                    continue

                recommendation = result["recommendation"]

                if recommendation == "approve":
                    approved_count += 1
                elif recommendation == "flag":
                    flagged_count += 1
                elif recommendation == "reject":
                    rejected_count += 1
                else:
                    # Unknown recommendation — fail closed.
                    logger.error(
                        "Orchestrator: unknown recommendation %r for signal %s — flagging",
                        recommendation,
                        signal.get("signal_id"),
                    )
                    flagged_count += 1
                    result["recommendation"] = "flag"

                await self._update_signal_status(signal["signal_id"], result)

        summary = {
            "scan_at": datetime.now(timezone.utc).isoformat(),
            "matches_scanned": len(matches),
            "approved": approved_count,
            "flagged": flagged_count,
            "rejected": rejected_count,
            "skipped": skipped_count,
            "errors": errors,
        }
        logger.info("Orchestrator: scan cycle complete — %s", summary)
        return summary

    async def run_daily_report(self) -> dict[str, Any]:
        """Generate a daily summary report.

        Assembles:
        a. Today's signal outcomes (approved/flagged/rejected counts).
        b. Recent bet performance and bankroll status.
        c. Model calibration summary.
        d. CLV tracking summary.

        Then calls Claude once (no tools) to produce a plain-text narrative
        summary of the day.

        Returns a structured dict containing both raw stats and the narrative.
        """
        logger.info("Orchestrator: generating daily report")

        # Assemble raw data.
        bankroll = await get_bankroll_status()
        recent_bets = await get_recent_bets(days=1)
        recent_7d_bets = await get_recent_bets(days=7)

        # Today's signals — fetch matches in the past 24h and upcoming 48h.
        today_matches = await get_upcoming_matches(hours_ahead=48)
        today_signals: list[dict] = []
        for m in today_matches:
            sigs = await get_signals_for_match(m["match_id"])
            today_signals.extend(sigs)

        signal_status_counts = _count_by_key(today_signals, "status")

        # CLV summary from recent bets.
        clv_values = [b["clv_pct"] for b in recent_7d_bets if b.get("clv_pct") is not None]
        clv_summary = _clv_summary(clv_values)

        # PnL summary.
        pnl_today = sum(b["pnl_dkk"] or 0.0 for b in recent_bets)
        pnl_7d = sum(b["pnl_dkk"] or 0.0 for b in recent_7d_bets)

        raw_stats = {
            "report_date": datetime.now(timezone.utc).date().isoformat(),
            "bankroll": bankroll,
            "signal_status_counts": signal_status_counts,
            "bets_today": len(recent_bets),
            "bets_7d": len(recent_7d_bets),
            "pnl_today_dkk": round(pnl_today, 2),
            "pnl_7d_dkk": round(pnl_7d, 2),
            "clv_summary": clv_summary,
        }

        # Claude narrative (one call, no tools).
        narrative = await self._generate_report_narrative(raw_stats)

        return {
            "raw_stats": raw_stats,
            "narrative": narrative,
            "generated_at": datetime.now(timezone.utc).isoformat(),
        }

    # ------------------------------------------------------------------
    # Private: signal processing
    # ------------------------------------------------------------------

    async def _process_signal(
        self,
        signal: dict[str, Any],
        match_metadata: dict[str, Any],
    ) -> dict[str, Any]:
        """Process a single pending signal through anomaly detection and Claude reasoning.

        Returns a dict with:
        {
            "recommendation": "approve" | "flag" | "reject",
            "reasoning": str,
            "anomaly_detected": bool,
            "risk_level": "low" | "medium" | "high",
            "parse_error": bool,
        }
        """
        ev_pct: float = signal.get("ev_pct", 0.0)
        model_prob: float = signal.get("model_prob", 0.0)
        odds: float = signal.get("odds_at_signal", 0.0)
        market: str = signal.get("market", "")
        selection: str = signal.get("selection", "")
        match_id: str = signal.get("match_id", "")

        # --- Step 1: Fetch odds movement data ---
        movement_rows = await get_odds_movement(match_id, market, selection)

        # --- Step 2: Rule-based anomaly detection (pure function, no API cost) ---
        detection_result = detect_odds_anomaly(
            match_id=match_id,
            market=market,
            selection=selection,
            model_prob=model_prob,
            odds=odds,
            odds_movement_rows=movement_rows,
        )

        # --- Step 3: Decide whether Claude reasoning is needed ---
        needs_reasoning = (
            detection_result["anomaly_detected"]
            or ev_pct >= EXTREME_EV_THRESHOLD
            or signal.get("anomaly_flag", False)
        )

        if not needs_reasoning:
            # Auto-approve: no flags, EV is within normal bounds.
            logger.debug(
                "Orchestrator: auto-approving signal %s (EV=%.3f, no flags)",
                signal.get("signal_id"),
                ev_pct,
            )
            return {
                "recommendation": "approve",
                "reasoning": (
                    f"No anomaly flags detected. EV={ev_pct:.3%}, "
                    f"model_prob={model_prob:.4f}, odds={odds:.2f}. Auto-approved."
                ),
                "anomaly_detected": False,
                "risk_level": "low",
                "parse_error": False,
            }

        # --- Step 4: AnomalyReasoner (Claude) assessment ---
        logger.info(
            "Orchestrator: invoking AnomalyReasoner for signal %s (flags=%s, EV=%.3f)",
            signal.get("signal_id"),
            detection_result.get("flags"),
            ev_pct,
        )

        context = {
            "odds_movement": movement_rows,
            "detection_result": detection_result,
            "match_metadata": match_metadata,
            "lineup_info": {"status": "unavailable", "reason": "NOT_REQUESTED"},
            "weather_info": {"status": "unavailable", "reason": "NOT_REQUESTED"},
        }

        assessment = await self._reasoner.assess(signal=signal, context=context)
        return assessment

    # ------------------------------------------------------------------
    # Private: daily report narrative
    # ------------------------------------------------------------------

    async def _generate_report_narrative(self, raw_stats: dict[str, Any]) -> str:
        """Call Claude once (no tools) to narrate the daily stats.

        Returns a plain text summary. On failure, returns a fallback string
        so the report dict is always populated.
        """
        user_message = (
            "Please write a concise daily briefing (3-5 sentences) for a football EV betting "
            "system based on the following stats. Focus on: overall performance, bankroll health, "
            "any concern about CLV drift, and key signals.\n\n"
            f"Stats:\n{json.dumps(raw_stats, indent=2, default=str)}"
        )

        try:
            response = await self._client.messages.create(
                model=self.model,
                max_tokens=512,
                system=(
                    "You are a brief, data-driven analyst summarising a football EV betting "
                    "system's daily performance. Be factual and concise. No hype."
                ),
                messages=[{"role": "user", "content": user_message}],
            )
            text = response.content[0].text if response.content else ""
            return text.strip()
        except anthropic.APIError as exc:
            logger.error("Orchestrator: failed to generate report narrative — %s", exc)
            return f"[Report narrative unavailable: {type(exc).__name__}]"

    # ------------------------------------------------------------------
    # Private: DB writes
    # ------------------------------------------------------------------

    async def _update_signal_status(
        self,
        signal_id: str,
        assessment: dict[str, Any],
    ) -> None:
        """Write the assessment result back to the ev_signals table.

        Maps recommendation -> EVSignal.status:
            "approve"  -> "approved"
            "flag"     -> "pending"  (left for human review)
            "reject"   -> "rejected"

        Also writes anomaly_flag and anomaly_reasoning.
        """
        recommendation: str = assessment.get("recommendation", "flag")
        reasoning: str = assessment.get("reasoning", "")
        anomaly_detected: bool = assessment.get("anomaly_detected", False)

        status_map = {
            "approve": "approved",
            "flag": "pending",
            "reject": "rejected",
        }
        new_status = status_map.get(recommendation, "pending")

        async with get_session() as session:
            stmt = select(EVSignal).where(EVSignal.id == signal_id)
            result = await session.execute(stmt)
            signal = result.scalar_one_or_none()

            if signal is None:
                logger.error(
                    "Orchestrator: signal %s not found in DB — cannot update status",
                    signal_id,
                )
                return

            signal.status = new_status
            signal.anomaly_flag = anomaly_detected
            signal.anomaly_reasoning = reasoning
            # session.commit() is called by get_session()'s context manager.

        logger.info(
            "Orchestrator: updated signal %s -> status=%s anomaly_flag=%s",
            signal_id,
            new_status,
            anomaly_detected,
        )


# ---------------------------------------------------------------------------
# Private utility functions
# ---------------------------------------------------------------------------


def _count_by_key(items: list[dict], key: str) -> dict[str, int]:
    """Count items by the value of a given key."""
    counts: dict[str, int] = {}
    for item in items:
        val = str(item.get(key, "unknown"))
        counts[val] = counts.get(val, 0) + 1
    return counts


def _clv_summary(clv_values: list[float]) -> dict[str, Any]:
    """Compute a summary of CLV values.

    Returns avg_clv, pct_positive, total as a dict.
    If clv_values is empty, returns zeroed dict.
    """
    if not clv_values:
        return {"avg_clv": 0.0, "pct_positive_clv": 0.0, "total_bets_with_clv": 0}

    avg_clv = sum(clv_values) / len(clv_values)
    pct_positive = sum(1 for v in clv_values if v > 0) / len(clv_values)

    return {
        "avg_clv": round(avg_clv, 6),
        "pct_positive_clv": round(pct_positive, 4),
        "total_bets_with_clv": len(clv_values),
    }
