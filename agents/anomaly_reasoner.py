"""Anomaly reasoning agent.

Uses Claude to assess whether an EV signal with suspicious characteristics
should be approved, flagged for human review, or rejected.

Design decisions:
- Inherits from BaseAgent to reuse the Anthropic client setup and conversation
  history management. However, this agent does NOT use the tool-use loop —
  it makes a single Claude API call per signal with no tools exposed.
- The assess() method calls self.run() from BaseAgent (which handles the
  message/response cycle) with an empty tools list.
- The response schema is validated manually (no third-party JSON schema lib).
  If parsing fails, the function returns a "flag" recommendation — fail closed.
- Model is CLAUDE_MODEL constant so it can be audited and changed in one place.
- No streaming. Response is a single complete message.

Assumptions:
- The input `signal` dict matches the shape returned by get_signals_for_match().
- The input `context` dict may contain keys: odds_movement (list[dict]),
  lineup_info (dict), weather_info (dict), detection_result (dict from
  detect_odds_anomaly). All are optional — Claude handles missing keys.
"""

from __future__ import annotations

import json
import logging
from typing import Any

import anthropic

from agents.base_agent import BaseAgent

logger = logging.getLogger(__name__)

# The Claude model used for anomaly reasoning.
# Change this constant to upgrade the model across the whole module.
CLAUDE_MODEL: str = "claude-opus-4-5"

# Maximum tokens for the reasoning response.
# Enough for detailed chain-of-thought plus the structured conclusion.
MAX_TOKENS: int = 1024

# The exact schema expected in Claude's response.
# Document it here so the prompt can reference it precisely.
RESPONSE_SCHEMA: str = """{
  "anomaly_detected": <boolean>,
  "risk_level": "<low|medium|high>",
  "reasoning": "<string — concise explanation of the assessment>",
  "recommendation": "<approve|flag|reject>"
}"""

SYSTEM_PROMPT: str = f"""You are an expert quantitative analyst reviewing a pre-match football EV betting signal
for potential anomalies. Your job is to assess whether the signal is genuine value or suspicious.

You will be given:
- The EV signal details (market, selection, odds, model probability, EV %)
- Odds movement data (how the odds have moved since opening)
- Anomaly detection flags (patterns already identified by rule-based checks)
- Context (lineup info, weather — may be unavailable)

Your assessment must be strict and sceptical. Most signals that look too good are errors.

Return ONLY a valid JSON object matching this exact schema. No other text:
{RESPONSE_SCHEMA}

Guidelines for each field:
- anomaly_detected: true if any concerning pattern is present
- risk_level: "low" = minor concerns only; "medium" = one significant concern;
  "high" = multiple concerns or one extreme concern (e.g. EXTREME_EV flag)
- reasoning: 1-3 sentences explaining the key factors in your assessment.
  Be specific — cite the EV %, odds, movement data, or flags.
- recommendation:
    "approve"  — signal passes scrutiny, proceed with bet
    "flag"     — uncertain, needs human review before betting
    "reject"   — signal is likely erroneous or too risky, do not bet

Decision heuristics:
- EXTREME_EV (EV >= 15%) alone → risk_level=high, recommendation=flag or reject
- STEAM_MOVE with EXTREME_EV → reject
- MODEL_MARKET_DISAGREEMENT alone (no other flags) → flag
- MOVEMENT_AGAINST_BET alone → flag
- No flags, EV 5-15%, consistent movement → approve
- Lineup/weather data unavailable → do NOT penalise; treat as neutral
"""


class AnomalyReasoner(BaseAgent):
    """Claude-powered agent for anomaly assessment of EV signals.

    Inherits from BaseAgent for client setup and history management.
    Does NOT use the tool-use loop — each assessment is a single Claude call.

    Usage:
        reasoner = AnomalyReasoner()
        result = await reasoner.assess(signal=signal_dict, context=context_dict)
    """

    def __init__(self) -> None:
        super().__init__(
            name="anomaly_reasoner",
            model=CLAUDE_MODEL,
            max_history=20,
            max_iterations=1,
            max_tokens=MAX_TOKENS,
        )

    # ------------------------------------------------------------------
    # BaseAgent abstract interface
    # ------------------------------------------------------------------

    @property
    def system_prompt(self) -> str:
        return SYSTEM_PROMPT

    @property
    def tools(self) -> list[dict]:
        # AnomalyReasoner does not use tools — single-shot assessment.
        return []

    async def execute_tool(
        self, tool_name: str, tool_input: dict[str, Any]
    ) -> Any:
        # Should never be called since tools is empty.
        raise NotImplementedError(
            f"AnomalyReasoner does not support tool calls (got {tool_name!r})"
        )

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def assess(
        self,
        signal: dict[str, Any],
        context: dict[str, Any],
    ) -> dict[str, Any]:
        """Assess an EV signal for anomalies using Claude.

        Args:
            signal: The EV signal dict (from get_signals_for_match or equivalent).
                Required keys: market, selection, bookmaker, odds_at_signal,
                model_prob, ev_pct, confidence.
            context: Additional context dict. Expected keys (all optional):
                - odds_movement: list[dict] from get_odds_movement()
                - lineup_info: dict from check_lineup_changes()
                - weather_info: dict from check_weather_news()
                - detection_result: dict from detect_odds_anomaly()
                - match_metadata: dict with fixture details

        Returns:
            {
                "anomaly_detected": bool,
                "risk_level": "low" | "medium" | "high",
                "reasoning": str,
                "recommendation": "approve" | "flag" | "reject",
                "model_used": str,
                "parse_error": bool,  # True if Claude response could not be parsed
            }

        Failure mode: If the Claude API call fails or the response cannot be
        parsed, returns a "flag" recommendation with parse_error=True.
        The caller must NOT auto-approve on a parse error.
        """
        user_content = self._build_user_message(signal, context)

        # Reset history before each assessment — each signal is independent.
        self.reset()

        # Use BaseAgent.run() for the Claude call.
        raw_text = await self.run(user_content)

        # Handle API errors propagated as error strings from BaseAgent.
        if raw_text.startswith("[ERROR]"):
            logger.error(
                "AnomalyReasoner: Claude call failed for signal %s — %s",
                signal.get("signal_id", "unknown"),
                raw_text,
            )
            return self._fallback_response(reason=raw_text)

        parsed = self._parse_response(raw_text, signal.get("signal_id", "unknown"))
        return parsed

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _build_user_message(
        self,
        signal: dict[str, Any],
        context: dict[str, Any],
    ) -> str:
        """Assemble the full user message for Claude.

        All values are rendered explicitly — no dynamic prompt injection risks
        because all inputs are validated as plain dicts from known DB queries.
        """
        detection: dict[str, Any] = context.get("detection_result") or {}
        movement: list[dict] = context.get("odds_movement") or []
        lineup: dict = context.get("lineup_info") or {}
        weather: dict = context.get("weather_info") or {}
        match_meta: dict = context.get("match_metadata") or {}

        lines: list[str] = [
            "=== EV SIGNAL ===",
            f"Signal ID:       {signal.get('signal_id', 'N/A')}",
            f"Match ID:        {signal.get('match_id', 'N/A')}",
            f"Kickoff:         {match_meta.get('kickoff_at', 'N/A')}",
            f"Market:          {signal.get('market', 'N/A')}",
            f"Selection:       {signal.get('selection', 'N/A')}",
            f"Bookmaker:       {signal.get('bookmaker', 'N/A')}",
            f"Odds at signal:  {signal.get('odds_at_signal', 'N/A')}",
            f"Model prob:      {signal.get('model_prob', 'N/A')}",
            f"EV %:            {signal.get('ev_pct', 'N/A')}",
            f"Confidence:      {signal.get('confidence', 'N/A')}",
            f"Status:          {signal.get('status', 'N/A')}",
            "",
            "=== ANOMALY DETECTION FLAGS ===",
            f"Flags triggered: {detection.get('flags', [])}",
            f"EV computed:     {detection.get('ev_pct', 'N/A')}",
            f"Reason summary:  {detection.get('reason_summary', 'N/A')}",
            "",
            "=== ODDS MOVEMENT (all bookmakers) ===",
        ]

        if movement:
            for row in movement:
                lines.append(
                    f"  {row.get('bookmaker', '?')}: "
                    f"open={row.get('opening_odds', '?')} "
                    f"close={row.get('closing_odds', '?')} "
                    f"move={row.get('movement_pct', '?'):.3%}"
                    if isinstance(row.get("movement_pct"), float)
                    else f"  {row.get('bookmaker', '?')}: "
                    f"open={row.get('opening_odds', '?')} "
                    f"close={row.get('closing_odds', '?')} "
                    f"move={row.get('movement_pct', '?')}"
                )
            mv_summary = detection.get("movement_summary") or {}
            if mv_summary:
                lines.append(
                    f"  Summary: {mv_summary.get('bookmakers_moving_in', 0)} books shortened, "
                    f"{mv_summary.get('bookmakers_moving_out', 0)} books lengthened. "
                    f"Steam move: {mv_summary.get('steam_move_detected', False)}"
                )
        else:
            lines.append("  No movement data available.")

        lines += [
            "",
            "=== LINEUP INFO ===",
            f"  Status: {lineup.get('status', 'N/A')} — {lineup.get('reason', '')}",
            "",
            "=== WEATHER / NEWS ===",
            f"  Status: {weather.get('status', 'N/A')} — {weather.get('reason', '')}",
        ]

        return "\n".join(lines)

    def _parse_response(self, raw_text: str, signal_id: str) -> dict[str, Any]:
        """Parse and validate Claude's JSON response.

        Attempts to extract a JSON object from the response text.
        If parsing fails or required fields are missing/invalid, returns a
        "flag" fallback with parse_error=True.
        """
        text = raw_text.strip()

        # Claude may wrap the JSON in markdown code fences — strip them.
        if text.startswith("```"):
            lines = text.splitlines()
            # Drop the opening ``` line and closing ``` line.
            inner_lines = [
                line for line in lines[1:] if not line.strip().startswith("```")
            ]
            text = "\n".join(inner_lines).strip()

        try:
            data = json.loads(text)
        except json.JSONDecodeError as exc:
            logger.error(
                "AnomalyReasoner: Failed to parse JSON for signal %s — %s\nRaw: %r",
                signal_id,
                exc,
                raw_text[:500],
            )
            return self._fallback_response(reason=f"JSON parse error: {exc}")

        # Validate required fields and allowed values.
        required_fields = {"anomaly_detected", "risk_level", "reasoning", "recommendation"}
        missing = required_fields - set(data.keys())
        if missing:
            logger.error(
                "AnomalyReasoner: Response missing fields %s for signal %s",
                missing,
                signal_id,
            )
            return self._fallback_response(reason=f"Missing fields in response: {missing}")

        valid_risk_levels = {"low", "medium", "high"}
        valid_recommendations = {"approve", "flag", "reject"}

        if data["risk_level"] not in valid_risk_levels:
            return self._fallback_response(
                reason=f"Invalid risk_level value: {data['risk_level']!r}"
            )

        if data["recommendation"] not in valid_recommendations:
            return self._fallback_response(
                reason=f"Invalid recommendation value: {data['recommendation']!r}"
            )

        if not isinstance(data["anomaly_detected"], bool):
            return self._fallback_response(
                reason=f"anomaly_detected must be bool, got {type(data['anomaly_detected'])}"
            )

        if not isinstance(data["reasoning"], str) or not data["reasoning"].strip():
            return self._fallback_response(reason="reasoning must be a non-empty string")

        return {
            "anomaly_detected": data["anomaly_detected"],
            "risk_level": data["risk_level"],
            "reasoning": data["reasoning"].strip(),
            "recommendation": data["recommendation"],
            "model_used": CLAUDE_MODEL,
            "parse_error": False,
        }

    @staticmethod
    def _fallback_response(reason: str) -> dict[str, Any]:
        """Return a safe fallback when Claude cannot be reached or parsed.

        Always returns recommendation='flag' — never auto-approve on failure.
        parse_error=True allows callers to distinguish genuine assessments
        from degraded-mode outputs.
        """
        return {
            "anomaly_detected": True,
            "risk_level": "high",
            "reasoning": f"Assessment could not be completed: {reason}. Signal held for human review.",
            "recommendation": "flag",
            "model_used": CLAUDE_MODEL,
            "parse_error": True,
        }
