"""EV signal generation — scan fixtures and produce actionable signals."""

from datetime import datetime, timedelta, timezone

from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession

from db.models.base import new_uuid
from db.models.matches import Match
from db.models.predictions import EVSignal, ModelPrediction
from ev_engine.calculator import EVCalculator
from ev_engine.filters import FilterChain, SignalCandidate
from ev_engine.odds_comparison import OddsComparer
from risk.position_sizer import PositionSizer


class SignalGenerator:
    """Scan fixtures for expected value and produce EV signals."""

    def __init__(self, position_sizer: PositionSizer | None = None):
        self.calculator = EVCalculator()
        self.comparer = OddsComparer()
        self.filters = FilterChain()
        self.position_sizer = position_sizer

    async def scan_fixture(
        self,
        session: AsyncSession,
        match_id: str,
        predictions: dict[str, dict],
    ) -> list[EVSignal]:
        """Scan a single fixture for value.

        Args:
            session: Database session.
            match_id: The match to scan.
            predictions: Keyed by "market|selection", value is
                {"prob": float, "confidence": float, "model_type": str}.

        Returns:
            List of EVSignal objects ready for storage.

        Process:
        1. Find best price across bookmakers for each prediction.
        2. Calculate EV.
        3. Create SignalCandidate.
        4. Apply filters.
        5. Calculate suggested stake via position sizer.
        6. Create EVSignal.
        """
        candidates: list[SignalCandidate] = []

        for key, pred in predictions.items():
            parts = key.split("|", 1)
            if len(parts) != 2:
                continue
            market, selection = parts

            best = await self.comparer.find_best_price(session, match_id, market, selection)
            if best is None:
                continue

            ev = self.calculator.calculate_ev(pred["prob"], best.odds)

            candidates.append(
                SignalCandidate(
                    match_id=match_id,
                    market=market,
                    selection=selection,
                    bookmaker=best.bookmaker,
                    odds=best.odds,
                    model_prob=pred["prob"],
                    ev=ev,
                    confidence=pred["confidence"],
                )
            )

        passing = self.filters.apply(candidates)

        signals: list[EVSignal] = []
        now = datetime.now(timezone.utc)

        for cand in passing:
            # Position sizing
            stake_pct = 0.0
            stake_dkk = 0.0
            if self.position_sizer:
                sizing = await self.position_sizer.calculate_stake(
                    session, cand.model_prob, cand.odds, cand.match_id
                )
                stake_pct = sizing["kelly_fraction"]
                stake_dkk = sizing["stake_dkk"]

            signal = EVSignal(
                id=new_uuid(),
                match_id=cand.match_id,
                market=cand.market,
                selection=cand.selection,
                bookmaker=cand.bookmaker,
                odds_at_signal=cand.odds,
                model_prob=cand.model_prob,
                ev_pct=cand.ev,
                confidence=cand.confidence,
                suggested_stake_pct=stake_pct,
                suggested_stake_dkk=stake_dkk,
                status="pending",
                anomaly_flag=False,
                generated_at=now,
                expires_at=now + timedelta(hours=2),
            )
            signals.append(signal)

        return signals

    async def scan_upcoming(
        self, session: AsyncSession, hours_ahead: int = 24
    ) -> list[EVSignal]:
        """Scan all fixtures starting within hours_ahead.

        Loads model predictions, finds odds, calculates EV, filters,
        and returns signals.
        """
        now = datetime.now(timezone.utc)
        cutoff = now + timedelta(hours=hours_ahead)

        # Find upcoming matches
        match_stmt = select(Match).where(
            and_(
                Match.kickoff_at >= now,
                Match.kickoff_at <= cutoff,
                Match.status == "scheduled",
            )
        )
        match_result = await session.execute(match_stmt)
        matches = match_result.scalars().all()

        all_signals: list[EVSignal] = []

        for match in matches:
            # Load predictions for this match
            pred_stmt = select(ModelPrediction).where(
                ModelPrediction.match_id == match.id
            )
            pred_result = await session.execute(pred_stmt)
            model_preds = pred_result.scalars().all()

            if not model_preds:
                continue

            predictions: dict[str, dict] = {}
            for mp in model_preds:
                key = f"{mp.market}|{mp.selection}"
                predictions[key] = {
                    "prob": mp.predicted_prob,
                    "confidence": 0.80,  # Default confidence; refine with calibration later
                    "model_type": mp.model_type,
                }

            signals = await self.scan_fixture(session, match.id, predictions)
            all_signals.extend(signals)

        return all_signals

    async def store_signals(self, session: AsyncSession, signals: list[EVSignal]) -> int:
        """Store signals to the database. Returns count stored."""
        for signal in signals:
            session.add(signal)
        await session.flush()
        return len(signals)
