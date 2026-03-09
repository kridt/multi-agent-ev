"""
Background EV scanner service.

Continuously scans upcoming fixtures for expected-value betting opportunities
and pushes enriched signal data via an async callback.

ASSUMPTIONS (all explicit):
- This module is imported inside a running asyncio event loop (FastAPI lifespan).
- get_session() provides a transactional async SQLAlchemy session that commits
  on normal exit and rolls back on exception.
- signal.ev_pct is stored as a decimal fraction (e.g., 0.12 for 12% EV),
  consistent with EVCalculator.calculate_ev() output.
- BetGrader.grade(ev_pct=...) expects a PERCENTAGE value (e.g., 12.0 for 12%).
  Conversion: ev_pct_pct = signal.ev_pct * 100.0
- ExplainabilityEngine.explain(ev_pct=...) also expects a PERCENTAGE value.
  Same conversion applies.
- edge passed to explain() is a decimal fraction (model_prob - implied_prob),
  consistent with EVCalculator.edge() semantics and explainability.py line 10.
- The on_signal callback is an async callable. If it raises, the error is logged
  and scanning continues (fail-open for the callback only; storage has already
  committed via session.flush()).
- Each scan cycle opens and closes its own DB session. The scanner does not hold
  a long-running session between cycles.
- Duplicate signal detection is NOT performed in this service — that is the
  responsibility of the caller or a deduplication layer. The scanner stores
  every signal that passes the FilterChain.
"""

import asyncio
import logging
from datetime import datetime, timedelta, timezone
from typing import Awaitable, Callable

logger = logging.getLogger(__name__)


class EVScanner:
    """Background service that continuously scans for EV betting opportunities."""

    def __init__(
        self,
        scan_interval_seconds: int = 60,
        on_signal: Callable[[dict], Awaitable[None]] | None = None,
    ) -> None:
        self.scan_interval = scan_interval_seconds
        self.on_signal = on_signal  # async callback invoked when a new signal is found
        self._running = False
        self._scan_count: int = 0
        self._last_scan_at: datetime | None = None
        self._signals_found: int = 0

    async def start(self) -> None:
        """Start the continuous scanning loop.

        Runs until stop() is called. Each cycle calls _scan_cycle() and then
        waits scan_interval seconds before the next cycle.
        Exceptions within a cycle are caught and logged so the loop continues.
        """
        self._running = True
        logger.info("EVScanner started — scanning every %ds", self.scan_interval)
        while self._running:
            try:
                await self._scan_cycle()
            except Exception as e:
                logger.error("Scan cycle error: %s", e, exc_info=True)
            await asyncio.sleep(self.scan_interval)

    def stop(self) -> None:
        """Signal the scanning loop to stop after the current cycle completes."""
        self._running = False
        logger.info("EVScanner stopped")

    @property
    def status(self) -> dict:
        """Current scanner status snapshot (safe to call from any thread)."""
        return {
            "running": self._running,
            "scan_count": self._scan_count,
            "last_scan_at": self._last_scan_at.isoformat() if self._last_scan_at else None,
            "signals_found": self._signals_found,
        }

    async def _scan_cycle(self) -> None:
        """
        Run one complete scan cycle.

        Process:
        1. Open a DB session.
        2. Query matches starting within the next 24 hours with status="scheduled".
        3. For each match that has ModelPrediction rows:
           a. Build a predictions dict keyed by "market|selection".
           b. Call SignalGenerator.scan_fixture() to get EVSignal candidates.
           c. For each signal:
              i.   Grade it via BetGrader (ev_pct converted to percentage).
              ii.  Generate explanation via ExplainabilityEngine (ev_pct converted
                   to percentage; edge kept as decimal fraction).
              iii. Persist the signal via session.add() + session.flush().
              iv.  Increment self._signals_found.
              v.   Call self.on_signal with the enriched payload.
        4. Update scan statistics.

        Unit note:
        - signal.ev_pct is a decimal fraction (EVCalculator output).
        - BetGrader.grade(ev_pct=...) requires a percentage value.
        - ExplainabilityEngine.explain(ev_pct=...) requires a percentage value.
        - edge is passed as a decimal fraction to explain() per explainability.py.
        """
        # Defer all heavy imports to avoid circular import issues at module load time.
        from sqlalchemy import and_, select

        from dashboard.explainability import ExplainabilityEngine
        from dashboard.grading import BetGrader
        from db.models.entities import League, Team
        from db.models.matches import Match
        from db.models.predictions import EVSignal, ModelPrediction
        from db.session import get_session
        from ev_engine.calculator import EVCalculator
        from ev_engine.signal_generator import SignalGenerator

        self._scan_count += 1
        self._last_scan_at = datetime.now(timezone.utc)
        logger.info("Starting scan cycle #%d", self._scan_count)

        grader = BetGrader()
        explainer = ExplainabilityEngine()
        generator = SignalGenerator()
        calc = EVCalculator()

        now = datetime.now(timezone.utc)
        cutoff = now + timedelta(hours=24)

        try:
            async with get_session() as session:
                # ------------------------------------------------------------------
                # Step 1: find upcoming scheduled matches within the next 24 hours.
                # ------------------------------------------------------------------
                match_stmt = select(Match).where(
                    and_(
                        Match.kickoff_at >= now,
                        Match.kickoff_at <= cutoff,
                        Match.status == "scheduled",
                    )
                )
                match_result = await session.execute(match_stmt)
                matches = match_result.scalars().all()

                new_signals_this_cycle: int = 0

                for match in matches:
                    # --------------------------------------------------------------
                    # Step 2: load model predictions for this match.
                    # --------------------------------------------------------------
                    pred_stmt = select(ModelPrediction).where(
                        ModelPrediction.match_id == match.id
                    )
                    pred_result = await session.execute(pred_stmt)
                    model_preds = pred_result.scalars().all()

                    if not model_preds:
                        # No predictions available — skip this match.
                        continue

                    # Build predictions dict keyed by "market|selection".
                    # confidence is fixed at 0.85 as a default until calibration
                    # is implemented. This is explicitly documented here.
                    # ASSUMPTION: model confidence is not stored on ModelPrediction;
                    # using a fixed default of 0.85 (high but not maximum).
                    predictions: dict[str, dict] = {}
                    for mp in model_preds:
                        key = f"{mp.market}|{mp.selection}"
                        predictions[key] = {
                            "prob": mp.predicted_prob,
                            "confidence": 0.85,
                            "model_type": mp.model_type,
                        }

                    # --------------------------------------------------------------
                    # Step 3: scan for EV signals.
                    # SignalGenerator applies FilterChain (odds range, EV threshold,
                    # confidence, consistency) before returning signals.
                    # --------------------------------------------------------------
                    signals: list[EVSignal] = await generator.scan_fixture(
                        session, match.id, predictions
                    )

                    if not signals:
                        continue

                    # Load team and league names once per match (only if signals exist).
                    home_team = await session.get(Team, match.home_team_id)
                    away_team = await session.get(Team, match.away_team_id)
                    league = await session.get(League, match.league_id)

                    for signal in signals:
                        # ----------------------------------------------------------
                        # Step 4a: grade the signal.
                        # BetGrader.grade(ev_pct=...) expects a PERCENTAGE value.
                        # signal.ev_pct is a decimal fraction (EVCalculator output).
                        # Conversion: decimal fraction -> percentage = * 100.
                        # Example: 0.12 -> 12.0
                        # ----------------------------------------------------------
                        ev_pct_as_percentage = signal.ev_pct * 100.0

                        grade = grader.grade(
                            ev_pct=ev_pct_as_percentage,
                            model_prob=signal.model_prob,
                            odds=signal.odds_at_signal,
                            confidence=signal.confidence,
                            # model_agreement and consistency_cv are not stored on
                            # EVSignal. Passing None invokes the documented defaults
                            # in BetGrader: model_agreement defaults to B,
                            # consistency_cv defaults to C.
                            model_agreement=None,
                            consistency_cv=None,
                        )

                        # ----------------------------------------------------------
                        # Step 4b: generate explanation.
                        # implied_prob = 1 / odds (EVCalculator.calculate_implied_prob).
                        # edge = model_prob - implied_prob (decimal fraction).
                        # ExplainabilityEngine.explain(ev_pct=...) expects PERCENTAGE.
                        # ExplainabilityEngine.explain(edge=...) expects decimal fraction.
                        # ----------------------------------------------------------
                        implied_prob = calc.calculate_implied_prob(signal.odds_at_signal)
                        edge = calc.edge(signal.model_prob, implied_prob)

                        explanation = explainer.explain(
                            ev_pct=ev_pct_as_percentage,
                            model_prob=signal.model_prob,
                            odds=signal.odds_at_signal,
                            implied_prob=implied_prob,
                            edge=edge,
                            confidence=signal.confidence,
                            market=signal.market,
                            selection=signal.selection,
                            bookmaker=signal.bookmaker,
                            # Optional enrichment fields not currently available;
                            # pass None. ExplainabilityEngine handles None gracefully.
                            model_agreement=None,
                            consistency_cv=None,
                            odds_movement=None,
                            sharp_odds=None,
                        )

                        # ----------------------------------------------------------
                        # Step 4c: persist the signal to the database.
                        # session.flush() writes to DB within the transaction but
                        # does not commit. get_session() commits on context exit.
                        # ----------------------------------------------------------
                        session.add(signal)
                        await session.flush()

                        self._signals_found += 1
                        new_signals_this_cycle += 1

                        # ----------------------------------------------------------
                        # Step 4d: invoke the on_signal callback if registered.
                        # The callback is fire-and-forget within the cycle: if it
                        # raises, we log and continue so the DB commit is not rolled
                        # back due to a callback error.
                        # ----------------------------------------------------------
                        if self.on_signal is not None:
                            enriched: dict = {
                                "id": signal.id,
                                "match": {
                                    "home": home_team.name if home_team else "Unknown",
                                    "away": away_team.name if away_team else "Unknown",
                                    "league": league.name if league else "Unknown",
                                    "kickoff": match.kickoff_at.isoformat(),
                                },
                                "market": signal.market,
                                "selection": signal.selection,
                                "bookmaker": signal.bookmaker,
                                "odds": signal.odds_at_signal,
                                "model_prob": signal.model_prob,
                                # ev_pct exposed to API consumers as a decimal fraction,
                                # consistent with storage format. The UI is responsible
                                # for displaying it as a percentage.
                                "ev_pct": signal.ev_pct,
                                "edge": edge,
                                "confidence": signal.confidence,
                                "suggested_stake_pct": signal.suggested_stake_pct,
                                "suggested_stake_dkk": signal.suggested_stake_dkk,
                                "overall_grade": grade.overall_grade,
                                "overall_score": grade.overall_score,
                                "grades": {
                                    pg.parameter: {
                                        "grade": pg.grade,
                                        # pg.value is float('nan') when model_agreement
                                        # or consistency_cv is None (BetGrader documented
                                        # policy). NaN is not valid JSON; coerce to None.
                                        "value": (
                                            None if pg.value != pg.value else pg.value
                                        ),
                                        "label": pg.label,
                                        "description": pg.description,
                                    }
                                    for pg in grade.parameters
                                },
                                "explanation": {
                                    "summary": explanation.summary,
                                    "reasons": explanation.reasons,
                                    "risk_factors": explanation.risk_factors,
                                    "recommendation": explanation.recommendation,
                                },
                                "generated_at": signal.generated_at.isoformat(),
                                "expires_at": signal.expires_at.isoformat(),
                            }

                            try:
                                await self.on_signal(enriched)
                            except Exception as cb_err:
                                logger.error(
                                    "on_signal callback failed for signal %s: %s",
                                    signal.id,
                                    cb_err,
                                    exc_info=True,
                                )

                logger.info(
                    "Scan cycle #%d complete — %d matches checked, "
                    "%d new signals this cycle, %d total signals found",
                    self._scan_count,
                    len(matches),
                    new_signals_this_cycle,
                    self._signals_found,
                )

        except Exception as e:
            logger.error(
                "Scan cycle #%d failed at DB level: %s",
                self._scan_count,
                e,
                exc_info=True,
            )
            raise
