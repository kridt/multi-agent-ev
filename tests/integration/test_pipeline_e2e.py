"""End-to-end pipeline integration test.

Tests the full flow:
  create entities -> create match -> create odds snapshots ->
  create model predictions -> run SignalGenerator -> apply PositionSizer ->
  create Bet -> verify the full chain.

Key constraints respected:
- OddsComparer.find_best_price queries by TARGET_BOOKMAKERS optic_odds_key values:
  "bet365", "unibet", "danske_spil". Tests must use one of these exact strings.
- FilterChain defaults: odds in [1.50, 4.00], EV >= 0.03, confidence >= 0.75.
- EVSignal.ev_pct stores the raw decimal EV (e.g., 0.10 means 10% EV).
- PositionSizer uses the module-level settings singleton. With a fresh
  BankrollManager(10000) and no existing bets the stop-loss and exposure checks
  will not trigger.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from db.models.base import new_uuid
from db.models.betting import Bet, BankrollSnapshot
from db.models.entities import League, Team
from db.models.matches import Match
from db.models.odds import OddsSnapshot
from db.models.predictions import EVSignal, ModelPrediction
from ev_engine.calculator import EVCalculator
from ev_engine.signal_generator import SignalGenerator
from risk.bankroll import BankrollManager
from risk.position_sizer import PositionSizer


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


async def _create_league_and_teams(session: AsyncSession) -> tuple[str, str, str]:
    """Insert a league and two teams; return (league_id, home_team_id, away_team_id)."""
    league = League(
        id=new_uuid(),
        name="Danish Superliga",
        country="Denmark",
        active=True,
    )
    session.add(league)
    await session.flush()

    home_team = Team(
        id=new_uuid(),
        name="FC Copenhagen",
        league_id=league.id,
        active=True,
    )
    away_team = Team(
        id=new_uuid(),
        name="Brondby",
        league_id=league.id,
        active=True,
    )
    session.add(home_team)
    session.add(away_team)
    await session.flush()

    return league.id, home_team.id, away_team.id


async def _create_match(
    session: AsyncSession,
    league_id: str,
    home_team_id: str,
    away_team_id: str,
    hours_ahead: int = 12,
) -> str:
    """Insert a scheduled match starting ``hours_ahead`` hours from now."""
    match = Match(
        id=new_uuid(),
        league_id=league_id,
        home_team_id=home_team_id,
        away_team_id=away_team_id,
        kickoff_at=_utcnow() + timedelta(hours=hours_ahead),
        status="scheduled",
    )
    session.add(match)
    await session.flush()
    return match.id


async def _create_odds_snapshot(
    session: AsyncSession,
    match_id: str,
    bookmaker: str,
    market: str,
    selection: str,
    odds: float,
) -> str:
    """Insert an OddsSnapshot and return its id."""
    snap = OddsSnapshot(
        id=new_uuid(),
        match_id=match_id,
        bookmaker=bookmaker,
        market=market,
        selection=selection,
        odds=odds,
        implied_prob=EVCalculator.calculate_implied_prob(odds),
        source="optic_odds",
        snapshot_at=_utcnow(),
        is_closing=False,
    )
    session.add(snap)
    await session.flush()
    return snap.id


async def _create_model_prediction(
    session: AsyncSession,
    match_id: str,
    market: str,
    selection: str,
    predicted_prob: float,
) -> str:
    """Insert a ModelPrediction and return its id."""
    pred = ModelPrediction(
        id=new_uuid(),
        match_id=match_id,
        model_type="poisson",
        model_version="v1",
        market=market,
        selection=selection,
        predicted_prob=predicted_prob,
        predicted_at=_utcnow(),
    )
    session.add(pred)
    await session.flush()
    return pred.id


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestFullPipelineE2E:
    """Full pipeline: entities -> match -> odds -> predictions -> signals -> bet."""

    async def test_entity_creation_persists_to_db(self, db_session: AsyncSession) -> None:
        """League and Team rows written in one flush can be queried back."""
        league_id, home_id, away_id = await _create_league_and_teams(db_session)

        league_row = await db_session.get(League, league_id)
        home_row = await db_session.get(Team, home_id)
        away_row = await db_session.get(Team, away_id)

        assert league_row is not None
        assert league_row.name == "Danish Superliga"
        assert home_row is not None
        assert home_row.name == "FC Copenhagen"
        assert home_row.league_id == league_id
        assert away_row is not None
        assert away_row.name == "Brondby"

    async def test_match_creation_links_to_entities(self, db_session: AsyncSession) -> None:
        """A Match row references the correct league and team IDs."""
        league_id, home_id, away_id = await _create_league_and_teams(db_session)
        match_id = await _create_match(db_session, league_id, home_id, away_id)

        match_row = await db_session.get(Match, match_id)
        assert match_row is not None
        assert match_row.league_id == league_id
        assert match_row.home_team_id == home_id
        assert match_row.away_team_id == away_id
        assert match_row.status == "scheduled"

    async def test_odds_snapshot_creation_and_query(self, db_session: AsyncSession) -> None:
        """OddsSnapshot is stored and implied_prob is correctly computed."""
        league_id, home_id, away_id = await _create_league_and_teams(db_session)
        match_id = await _create_match(db_session, league_id, home_id, away_id)

        # "bet365" is the optic_odds_key for bet365_dk — it is in TARGET_BOOKMAKERS
        snap_id = await _create_odds_snapshot(
            db_session,
            match_id=match_id,
            bookmaker="bet365",
            market="team_goals_ou",
            selection="over_2.5",
            odds=2.10,
        )

        row = await db_session.get(OddsSnapshot, snap_id)
        assert row is not None
        assert row.match_id == match_id
        assert row.bookmaker == "bet365"
        assert row.odds == pytest.approx(2.10)
        # implied_prob = 1 / 2.10
        assert row.implied_prob == pytest.approx(1 / 2.10, rel=1e-6)

    async def test_model_prediction_creation(self, db_session: AsyncSession) -> None:
        """ModelPrediction is stored with correct fields."""
        league_id, home_id, away_id = await _create_league_and_teams(db_session)
        match_id = await _create_match(db_session, league_id, home_id, away_id)

        pred_id = await _create_model_prediction(
            db_session,
            match_id=match_id,
            market="team_goals_ou",
            selection="over_2.5",
            predicted_prob=0.60,
        )

        row = await db_session.get(ModelPrediction, pred_id)
        assert row is not None
        assert row.match_id == match_id
        assert row.predicted_prob == pytest.approx(0.60)
        assert row.market == "team_goals_ou"
        assert row.selection == "over_2.5"

    async def test_signal_generator_produces_signal_from_value_odds(
        self, db_session: AsyncSession
    ) -> None:
        """SignalGenerator.scan_fixture returns a signal when EV >= 3% and
        odds are in [1.50, 4.00] and confidence >= 0.75.

        Setup:
          model_prob = 0.60, bookmaker odds = 2.00
          EV = (0.60 * 2.00) - 1 = 0.20 (20%) => passes all filters.
        """
        league_id, home_id, away_id = await _create_league_and_teams(db_session)
        match_id = await _create_match(db_session, league_id, home_id, away_id)

        # "bet365" is a TARGET_BOOKMAKER optic_odds_key
        await _create_odds_snapshot(
            db_session,
            match_id=match_id,
            bookmaker="bet365",
            market="team_goals_ou",
            selection="over_2.5",
            odds=2.00,
        )

        generator = SignalGenerator()
        predictions = {
            "team_goals_ou|over_2.5": {
                "prob": 0.60,
                "confidence": 0.85,
                "model_type": "poisson",
            }
        }

        signals = await generator.scan_fixture(db_session, match_id, predictions)

        assert len(signals) == 1
        sig = signals[0]
        assert sig.match_id == match_id
        assert sig.market == "team_goals_ou"
        assert sig.selection == "over_2.5"
        assert sig.bookmaker == "bet365"
        assert sig.odds_at_signal == pytest.approx(2.00)
        assert sig.model_prob == pytest.approx(0.60)
        # EV = (0.60 * 2.00) - 1 = 0.20
        assert sig.ev_pct == pytest.approx(0.20)
        assert sig.status == "pending"
        assert sig.anomaly_flag is False

    async def test_signal_generator_rejects_low_ev(
        self, db_session: AsyncSession
    ) -> None:
        """SignalGenerator produces no signal when EV < 3%.

        Setup: model_prob = 0.50, bookmaker odds = 2.00
        EV = (0.50 * 2.00) - 1 = 0.00 => fails EVThresholdFilter.
        """
        league_id, home_id, away_id = await _create_league_and_teams(db_session)
        match_id = await _create_match(db_session, league_id, home_id, away_id)

        await _create_odds_snapshot(
            db_session,
            match_id=match_id,
            bookmaker="bet365",
            market="btts",
            selection="yes",
            odds=2.00,
        )

        generator = SignalGenerator()
        predictions = {
            "btts|yes": {
                "prob": 0.50,
                "confidence": 0.85,
                "model_type": "poisson",
            }
        }

        signals = await generator.scan_fixture(db_session, match_id, predictions)
        assert signals == []

    async def test_signal_generator_rejects_odds_out_of_range(
        self, db_session: AsyncSession
    ) -> None:
        """SignalGenerator produces no signal when odds > 4.00 (OddsRangeFilter).

        The default OddsRangeFilter max is 4.00.
        EV = (0.30 * 5.00) - 1 = 0.50, but odds of 5.00 fail the range filter.
        """
        league_id, home_id, away_id = await _create_league_and_teams(db_session)
        match_id = await _create_match(db_session, league_id, home_id, away_id)

        await _create_odds_snapshot(
            db_session,
            match_id=match_id,
            bookmaker="bet365",
            market="team_goals_ou",
            selection="over_3.5",
            odds=5.00,
        )

        generator = SignalGenerator()
        predictions = {
            "team_goals_ou|over_3.5": {
                "prob": 0.30,
                "confidence": 0.85,
                "model_type": "poisson",
            }
        }

        signals = await generator.scan_fixture(db_session, match_id, predictions)
        assert signals == []

    async def test_signal_generator_rejects_low_confidence(
        self, db_session: AsyncSession
    ) -> None:
        """SignalGenerator produces no signal when confidence < 0.75 (ConfidenceFilter)."""
        league_id, home_id, away_id = await _create_league_and_teams(db_session)
        match_id = await _create_match(db_session, league_id, home_id, away_id)

        await _create_odds_snapshot(
            db_session,
            match_id=match_id,
            bookmaker="bet365",
            market="team_goals_ou",
            selection="over_2.5",
            odds=2.00,
        )

        generator = SignalGenerator()
        predictions = {
            "team_goals_ou|over_2.5": {
                "prob": 0.60,
                "confidence": 0.50,  # Below the 0.75 threshold
                "model_type": "poisson",
            }
        }

        signals = await generator.scan_fixture(db_session, match_id, predictions)
        assert signals == []

    async def test_signal_stored_to_db(self, db_session: AsyncSession) -> None:
        """SignalGenerator.store_signals persists EVSignal rows to DB."""
        league_id, home_id, away_id = await _create_league_and_teams(db_session)
        match_id = await _create_match(db_session, league_id, home_id, away_id)

        await _create_odds_snapshot(
            db_session,
            match_id=match_id,
            bookmaker="bet365",
            market="team_goals_ou",
            selection="over_2.5",
            odds=2.00,
        )

        generator = SignalGenerator()
        predictions = {
            "team_goals_ou|over_2.5": {
                "prob": 0.60,
                "confidence": 0.85,
                "model_type": "poisson",
            }
        }

        signals = await generator.scan_fixture(db_session, match_id, predictions)
        assert len(signals) == 1

        count = await generator.store_signals(db_session, signals)
        assert count == 1

        # Verify row exists in DB
        stmt = select(EVSignal).where(EVSignal.match_id == match_id)
        result = await db_session.execute(stmt)
        db_signal = result.scalar_one_or_none()
        assert db_signal is not None
        assert db_signal.ev_pct == pytest.approx(0.20)
        assert db_signal.status == "pending"

    async def test_position_sizer_produces_nonzero_stake(
        self, db_session: AsyncSession
    ) -> None:
        """PositionSizer returns a positive stake for a clear positive-EV bet.

        With bankroll=10000, no existing bets (zero exposure), and a valid
        positive-edge bet, PositionSizer should return stake_dkk > 0.
        """
        bankroll_mgr = BankrollManager(initial_bankroll=10000.0)
        sizer = PositionSizer(bankroll_manager=bankroll_mgr)

        league_id, home_id, away_id = await _create_league_and_teams(db_session)
        match_id = await _create_match(db_session, league_id, home_id, away_id)

        # model_prob=0.60, odds=2.00 -> full_kelly = (0.60*2-1)/(2-1) = 0.20
        # quarter_kelly = 0.05 -> but settings.max_stake_pct=0.03, so capped at 0.03
        result = await sizer.calculate_stake(
            db_session,
            model_prob=0.60,
            decimal_odds=2.00,
            match_id=match_id,
        )

        assert result["blocked"] is False
        assert result["stake_dkk"] > 0.0
        assert result["kelly_fraction"] > 0.0

    async def test_full_chain_entities_to_bet(self, db_session: AsyncSession) -> None:
        """Full chain: entities, match, odds, prediction, signal, bet creation.

        Verifies every layer of the pipeline writes consistent data.
        """
        # --- Entities ---
        league_id, home_id, away_id = await _create_league_and_teams(db_session)

        # --- Match ---
        match_id = await _create_match(db_session, league_id, home_id, away_id)

        # --- Odds (bookmaker "unibet" is TARGET_BOOKMAKERS optic_odds_key) ---
        await _create_odds_snapshot(
            db_session,
            match_id=match_id,
            bookmaker="unibet",
            market="btts",
            selection="yes",
            odds=2.20,
        )

        # --- Model prediction ---
        await _create_model_prediction(
            db_session,
            match_id=match_id,
            market="btts",
            selection="yes",
            predicted_prob=0.58,
        )

        # --- Signal generation ---
        # EV = (0.58 * 2.20) - 1 = 0.276 => passes all filters
        generator = SignalGenerator()
        predictions = {
            "btts|yes": {
                "prob": 0.58,
                "confidence": 0.82,
                "model_type": "poisson",
            }
        }

        signals = await generator.scan_fixture(db_session, match_id, predictions)
        assert len(signals) == 1, "Expected exactly one passing signal"
        sig = signals[0]

        await generator.store_signals(db_session, signals)

        # --- Create Bet from signal ---
        stake = 250.0
        bet = Bet(
            id=new_uuid(),
            signal_id=sig.id,
            match_id=match_id,
            market=sig.market,
            selection=sig.selection,
            bookmaker=sig.bookmaker,
            odds=sig.odds_at_signal,
            stake_dkk=stake,
            potential_return_dkk=round(stake * sig.odds_at_signal, 2),
            outcome="pending",
            placed_at=_utcnow(),
        )
        db_session.add(bet)
        await db_session.flush()

        # --- Verify bet persisted ---
        bet_row = await db_session.get(Bet, bet.id)
        assert bet_row is not None
        assert bet_row.signal_id == sig.id
        assert bet_row.match_id == match_id
        assert bet_row.odds == pytest.approx(2.20)
        assert bet_row.stake_dkk == pytest.approx(250.0)
        assert bet_row.potential_return_dkk == pytest.approx(550.0)
        assert bet_row.outcome == "pending"

    async def test_scan_upcoming_uses_db_predictions(
        self, db_session: AsyncSession
    ) -> None:
        """SignalGenerator.scan_upcoming reads ModelPrediction rows from DB
        and produces signals for upcoming matches."""
        league_id, home_id, away_id = await _create_league_and_teams(db_session)
        match_id = await _create_match(
            db_session, league_id, home_id, away_id, hours_ahead=6
        )

        # Prediction in DB
        await _create_model_prediction(
            db_session,
            match_id=match_id,
            market="team_goals_ou",
            selection="over_2.5",
            predicted_prob=0.62,
        )

        # Odds
        await _create_odds_snapshot(
            db_session,
            match_id=match_id,
            bookmaker="bet365",
            market="team_goals_ou",
            selection="over_2.5",
            odds=2.00,
        )

        # scan_upcoming reads predictions from DB using default confidence 0.80
        # EV = (0.62 * 2.00) - 1 = 0.24 => passes
        generator = SignalGenerator()
        signals = await generator.scan_upcoming(db_session, hours_ahead=24)

        assert len(signals) >= 1
        match_signals = [s for s in signals if s.match_id == match_id]
        assert len(match_signals) == 1
        assert match_signals[0].ev_pct == pytest.approx(0.24)

    async def test_scan_upcoming_ignores_past_matches(
        self, db_session: AsyncSession
    ) -> None:
        """scan_upcoming should NOT return signals for matches that have already kicked off."""
        league_id, home_id, away_id = await _create_league_and_teams(db_session)

        # A match that kicked off 2 hours ago
        past_match = Match(
            id=new_uuid(),
            league_id=league_id,
            home_team_id=home_id,
            away_team_id=away_id,
            kickoff_at=_utcnow() - timedelta(hours=2),
            status="scheduled",  # status is still scheduled, but kickoff is past
        )
        db_session.add(past_match)
        await db_session.flush()

        await _create_model_prediction(
            db_session,
            match_id=past_match.id,
            market="btts",
            selection="yes",
            predicted_prob=0.70,
        )
        await _create_odds_snapshot(
            db_session,
            match_id=past_match.id,
            bookmaker="bet365",
            market="btts",
            selection="yes",
            odds=2.00,
        )

        generator = SignalGenerator()
        signals = await generator.scan_upcoming(db_session, hours_ahead=24)

        past_signals = [s for s in signals if s.match_id == past_match.id]
        assert past_signals == []

    async def test_bankroll_snapshot_stored(self, db_session: AsyncSession) -> None:
        """BankrollManager.snapshot() writes a BankrollSnapshot row to DB."""
        bm = BankrollManager(initial_bankroll=10000.0)
        bm.update(500.0)  # Simulating a winning bet

        await bm.snapshot(db_session)

        stmt = select(BankrollSnapshot).order_by(BankrollSnapshot.snapshot_at.desc())
        result = await db_session.execute(stmt)
        snap = result.scalar_one_or_none()

        assert snap is not None
        assert snap.balance_dkk == pytest.approx(10500.0)
        assert snap.peak_dkk == pytest.approx(10500.0)
        assert snap.drawdown_pct == pytest.approx(0.0)
        assert snap.roi_pct == pytest.approx(0.05)
