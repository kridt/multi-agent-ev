"""Signal to bet workflow integration tests.

Tests the full workflow:
  1. Create a match with odds snapshots.
  2. Generate an EV signal via SignalGenerator.
  3. Apply PositionSizer to size the stake.
  4. Create a Bet record linked to the signal.
  5. Settle the bet (won/lost).
  6. Verify bankroll changes via BankrollManager.
  7. Verify CLV calculation via ClosingLineTracker.

Design constraints:
  - PositionSizer uses the module-level settings singleton.
    With initial_bankroll=10000, no existing bets, and no drawdown,
    stop-loss and exposure checks will not trigger.
  - CLV formula: (signal_odds / closing_odds) - 1.
    Positive CLV = got better odds than closing line (favourable).
  - Bet.outcome must be one of: pending, won, lost, void, half_won, half_lost.
  - BankrollManager.update(pnl) is called AFTER settlement to reflect P&L.
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
from db.models.predictions import EVSignal
from ev_engine.calculator import EVCalculator
from ev_engine.closing_line import ClosingLineTracker
from ev_engine.signal_generator import SignalGenerator
from risk.bankroll import BankrollManager
from risk.kelly import KellyCalculator
from risk.position_sizer import PositionSizer


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


async def _setup_entities(session: AsyncSession) -> tuple[str, str, str]:
    """Create a league and two teams; return (league_id, home_id, away_id)."""
    league = League(id=new_uuid(), name="Superliga DK", country="Denmark", active=True)
    session.add(league)
    await session.flush()

    home = Team(id=new_uuid(), name="Odense BK", league_id=league.id, active=True)
    away = Team(id=new_uuid(), name="Aalborg BK", league_id=league.id, active=True)
    session.add(home)
    session.add(away)
    await session.flush()

    return league.id, home.id, away.id


async def _setup_match(
    session: AsyncSession,
    league_id: str,
    home_id: str,
    away_id: str,
    hours_ahead: int = 8,
) -> str:
    """Create a scheduled match and return its id."""
    match = Match(
        id=new_uuid(),
        league_id=league_id,
        home_team_id=home_id,
        away_team_id=away_id,
        kickoff_at=_utcnow() + timedelta(hours=hours_ahead),
        status="scheduled",
    )
    session.add(match)
    await session.flush()
    return match.id


async def _add_odds_snapshot(
    session: AsyncSession,
    match_id: str,
    bookmaker: str,
    market: str,
    selection: str,
    odds: float,
    is_closing: bool = False,
    snapshot_at: datetime | None = None,
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
        snapshot_at=snapshot_at or _utcnow(),
        is_closing=is_closing,
    )
    session.add(snap)
    await session.flush()
    return snap.id


async def _generate_signal(
    session: AsyncSession,
    match_id: str,
    market: str,
    selection: str,
    model_prob: float,
    confidence: float,
) -> EVSignal:
    """Generate and store a single EV signal; raises if none produced."""
    generator = SignalGenerator()
    predictions = {
        f"{market}|{selection}": {
            "prob": model_prob,
            "confidence": confidence,
            "model_type": "poisson",
        }
    }
    signals = await generator.scan_fixture(session, match_id, predictions)
    if not signals:
        raise ValueError(
            f"No signal generated for match={match_id} market={market} "
            f"selection={selection} model_prob={model_prob}"
        )
    await generator.store_signals(session, signals)
    return signals[0]


async def _create_bet_from_signal(
    session: AsyncSession,
    signal: EVSignal,
    stake_dkk: float,
) -> Bet:
    """Create a Bet linked to the given signal and persist it."""
    bet = Bet(
        id=new_uuid(),
        signal_id=signal.id,
        match_id=signal.match_id,
        market=signal.market,
        selection=signal.selection,
        bookmaker=signal.bookmaker,
        odds=signal.odds_at_signal,
        stake_dkk=stake_dkk,
        potential_return_dkk=round(stake_dkk * signal.odds_at_signal, 2),
        outcome="pending",
        placed_at=_utcnow(),
    )
    session.add(bet)
    await session.flush()
    return bet


# ---------------------------------------------------------------------------
# Tests: signal generation and bet creation
# ---------------------------------------------------------------------------

class TestSignalToBetWorkflow:

    async def test_signal_created_with_correct_ev(
        self, db_session: AsyncSession
    ) -> None:
        """SignalGenerator computes EV correctly: EV = (prob * odds) - 1."""
        league_id, home_id, away_id = await _setup_entities(db_session)
        match_id = await _setup_match(db_session, league_id, home_id, away_id)

        # "bet365" = optic_odds_key for bet365_dk (TARGET_BOOKMAKER)
        await _add_odds_snapshot(
            db_session,
            match_id=match_id,
            bookmaker="bet365",
            market="team_goals_ou",
            selection="over_2.5",
            odds=2.10,
        )

        # EV = (0.58 * 2.10) - 1 = 0.218
        expected_ev = (0.58 * 2.10) - 1.0

        signal = await _generate_signal(
            db_session,
            match_id=match_id,
            market="team_goals_ou",
            selection="over_2.5",
            model_prob=0.58,
            confidence=0.82,
        )

        assert signal.ev_pct == pytest.approx(expected_ev, rel=1e-6)
        assert signal.model_prob == pytest.approx(0.58)
        assert signal.odds_at_signal == pytest.approx(2.10)

    async def test_bet_linked_to_signal(self, db_session: AsyncSession) -> None:
        """Bet.signal_id is correctly set to EVSignal.id."""
        league_id, home_id, away_id = await _setup_entities(db_session)
        match_id = await _setup_match(db_session, league_id, home_id, away_id)

        await _add_odds_snapshot(
            db_session, match_id, "bet365", "btts", "yes", 2.00
        )

        signal = await _generate_signal(
            db_session, match_id, "btts", "yes", 0.60, 0.85
        )
        bet = await _create_bet_from_signal(db_session, signal, stake_dkk=100.0)

        assert bet.signal_id == signal.id
        assert bet.match_id == match_id

    async def test_potential_return_computed_correctly(
        self, db_session: AsyncSession
    ) -> None:
        """potential_return_dkk = stake * odds (rounded to 2 dp)."""
        league_id, home_id, away_id = await _setup_entities(db_session)
        match_id = await _setup_match(db_session, league_id, home_id, away_id)

        await _add_odds_snapshot(
            db_session, match_id, "bet365", "team_goals_ou", "over_2.5", 2.00
        )

        signal = await _generate_signal(
            db_session, match_id, "team_goals_ou", "over_2.5", 0.60, 0.85
        )
        stake = 250.0
        bet = await _create_bet_from_signal(db_session, signal, stake_dkk=stake)

        assert bet.potential_return_dkk == pytest.approx(stake * signal.odds_at_signal)

    async def test_bet_initial_outcome_is_pending(
        self, db_session: AsyncSession
    ) -> None:
        """A newly created bet has outcome='pending'."""
        league_id, home_id, away_id = await _setup_entities(db_session)
        match_id = await _setup_match(db_session, league_id, home_id, away_id)

        await _add_odds_snapshot(
            db_session, match_id, "unibet", "btts", "yes", 1.90
        )

        signal = await _generate_signal(
            db_session, match_id, "btts", "yes", 0.60, 0.85
        )
        bet = await _create_bet_from_signal(db_session, signal, stake_dkk=50.0)

        assert bet.outcome == "pending"
        assert bet.pnl_dkk is None
        assert bet.settled_at is None


# ---------------------------------------------------------------------------
# Tests: bet settlement and bankroll changes
# ---------------------------------------------------------------------------

class TestBetSettlement:

    async def test_winning_bet_updates_bankroll(
        self, db_session: AsyncSession
    ) -> None:
        """Settling a bet as 'won' updates BankrollManager.current correctly.

        P&L on a winning bet = stake * (odds - 1).
        """
        league_id, home_id, away_id = await _setup_entities(db_session)
        match_id = await _setup_match(db_session, league_id, home_id, away_id)

        await _add_odds_snapshot(
            db_session, match_id, "bet365", "team_goals_ou", "over_2.5", 2.00
        )

        signal = await _generate_signal(
            db_session, match_id, "team_goals_ou", "over_2.5", 0.60, 0.85
        )

        stake = 200.0
        bet = await _create_bet_from_signal(db_session, signal, stake_dkk=stake)

        # Settle as won: P&L = stake * (odds - 1) = 200 * 1.00 = 200
        bet.outcome = "won"
        bet.pnl_dkk = stake * (bet.odds - 1.0)
        bet.settled_at = _utcnow()
        await db_session.flush()

        bm = BankrollManager(initial_bankroll=10000.0)
        bm.update(bet.pnl_dkk)

        assert bm.current == pytest.approx(10200.0)
        assert bm.peak == pytest.approx(10200.0)
        assert bm.drawdown_pct == pytest.approx(0.0)

    async def test_losing_bet_updates_bankroll(
        self, db_session: AsyncSession
    ) -> None:
        """Settling a bet as 'lost' reduces BankrollManager.current by stake."""
        league_id, home_id, away_id = await _setup_entities(db_session)
        match_id = await _setup_match(db_session, league_id, home_id, away_id)

        await _add_odds_snapshot(
            db_session, match_id, "bet365", "btts", "yes", 2.00
        )

        signal = await _generate_signal(
            db_session, match_id, "btts", "yes", 0.60, 0.85
        )

        stake = 150.0
        bet = await _create_bet_from_signal(db_session, signal, stake_dkk=stake)

        # Settle as lost: P&L = -stake
        bet.outcome = "lost"
        bet.pnl_dkk = -stake
        bet.settled_at = _utcnow()
        await db_session.flush()

        bm = BankrollManager(initial_bankroll=10000.0)
        bm.update(bet.pnl_dkk)

        assert bm.current == pytest.approx(9850.0)
        assert bm.peak == pytest.approx(10000.0)  # Peak unchanged after loss
        assert bm.drawdown_pct == pytest.approx(150.0 / 10000.0, rel=1e-6)

    async def test_settled_bet_stored_in_db(self, db_session: AsyncSession) -> None:
        """After settlement, the Bet row in DB reflects the updated outcome."""
        league_id, home_id, away_id = await _setup_entities(db_session)
        match_id = await _setup_match(db_session, league_id, home_id, away_id)

        await _add_odds_snapshot(
            db_session, match_id, "bet365", "team_goals_ou", "over_2.5", 2.00
        )

        signal = await _generate_signal(
            db_session, match_id, "team_goals_ou", "over_2.5", 0.60, 0.85
        )
        stake = 100.0
        bet = await _create_bet_from_signal(db_session, signal, stake_dkk=stake)
        bet_id = bet.id

        bet.outcome = "won"
        bet.pnl_dkk = stake * (bet.odds - 1.0)
        bet.settled_at = _utcnow()
        await db_session.flush()

        # Re-query from DB
        row = await db_session.get(Bet, bet_id)
        assert row is not None
        assert row.outcome == "won"
        assert row.pnl_dkk == pytest.approx(stake * (signal.odds_at_signal - 1.0))
        assert row.settled_at is not None

    async def test_multiple_bets_bankroll_sequence(
        self, db_session: AsyncSession
    ) -> None:
        """Multiple bet settlements apply cumulatively to bankroll."""
        league_id, home_id, away_id = await _setup_entities(db_session)

        bm = BankrollManager(initial_bankroll=10000.0)

        pnl_sequence = [200.0, -100.0, 300.0, -150.0]
        for pnl in pnl_sequence:
            bm.update(pnl)

        # Net P&L = 200 - 100 + 300 - 150 = 250
        assert bm.current == pytest.approx(10250.0)
        assert bm.peak == pytest.approx(10400.0)  # peak after 10000+200+300=10400... let's check
        # After: 10200 -> 10100 -> 10400 -> 10250. Peak = 10400
        assert bm.roi_pct == pytest.approx(0.025)


# ---------------------------------------------------------------------------
# Tests: CLV calculation
# ---------------------------------------------------------------------------

class TestCLVCalculation:

    async def test_clv_positive_when_signal_odds_better_than_closing(
        self, db_session: AsyncSession
    ) -> None:
        """CLV > 0 when signal odds are higher than closing odds (we got value).

        CLV = (signal_odds / closing_odds) - 1.
        """
        tracker = ClosingLineTracker()

        # signal_odds=2.00, closing_odds=1.80 -> CLV = (2.00/1.80) - 1 = 0.1111
        clv = tracker.calculate_clv(signal_odds=2.00, closing_odds=1.80)
        assert clv == pytest.approx(2.00 / 1.80 - 1.0, rel=1e-6)
        assert clv > 0.0

    async def test_clv_negative_when_closing_odds_better(
        self, db_session: AsyncSession
    ) -> None:
        """CLV < 0 when closing odds are higher than our signal odds.

        CLV = (1.80 / 2.00) - 1 = -0.10.
        """
        tracker = ClosingLineTracker()
        clv = tracker.calculate_clv(signal_odds=1.80, closing_odds=2.00)
        assert clv == pytest.approx(1.80 / 2.00 - 1.0, rel=1e-6)
        assert clv < 0.0

    async def test_clv_zero_when_odds_equal(self, db_session: AsyncSession) -> None:
        """CLV = 0 when signal odds equal closing odds."""
        tracker = ClosingLineTracker()
        clv = tracker.calculate_clv(signal_odds=2.00, closing_odds=2.00)
        assert clv == pytest.approx(0.0)

    async def test_clv_for_bet_from_db(self, db_session: AsyncSession) -> None:
        """ClosingLineTracker.calculate_clv_for_bet reads closing odds from DB
        and updates the Bet row."""
        league_id, home_id, away_id = await _setup_entities(db_session)
        match_id = await _setup_match(db_session, league_id, home_id, away_id)

        signal_odds = 2.10
        closing_odds = 1.90

        # Opening snapshot (signal odds)
        await _add_odds_snapshot(
            db_session,
            match_id=match_id,
            bookmaker="bet365",
            market="team_goals_ou",
            selection="over_2.5",
            odds=signal_odds,
            is_closing=False,
            snapshot_at=_utcnow() - timedelta(hours=2),
        )

        # Closing snapshot (is_closing=True, later timestamp)
        await _add_odds_snapshot(
            db_session,
            match_id=match_id,
            bookmaker="bet365",
            market="team_goals_ou",
            selection="over_2.5",
            odds=closing_odds,
            is_closing=True,
            snapshot_at=_utcnow() - timedelta(minutes=5),
        )

        signal = await _generate_signal(
            db_session,
            match_id=match_id,
            market="team_goals_ou",
            selection="over_2.5",
            model_prob=0.58,
            confidence=0.82,
        )

        bet = Bet(
            id=new_uuid(),
            signal_id=signal.id,
            match_id=match_id,
            market="team_goals_ou",
            selection="over_2.5",
            bookmaker="bet365",
            odds=signal_odds,
            stake_dkk=100.0,
            potential_return_dkk=round(100.0 * signal_odds, 2),
            outcome="pending",
            placed_at=_utcnow() - timedelta(hours=2),
        )
        db_session.add(bet)
        await db_session.flush()

        tracker = ClosingLineTracker()
        clv = await tracker.calculate_clv_for_bet(db_session, bet.id)

        # CLV = (signal_odds / closing_odds) - 1 = (2.10 / 1.90) - 1
        expected_clv = (signal_odds / closing_odds) - 1.0
        assert clv == pytest.approx(expected_clv, rel=1e-6)

        # The bet row should be updated
        updated_bet = await db_session.get(Bet, bet.id)
        assert updated_bet is not None
        assert updated_bet.closing_odds == pytest.approx(closing_odds)
        assert updated_bet.clv_pct == pytest.approx(expected_clv, rel=1e-6)

    async def test_clv_for_bet_returns_none_when_no_closing_odds(
        self, db_session: AsyncSession
    ) -> None:
        """calculate_clv_for_bet returns None when no closing odds snapshot exists."""
        league_id, home_id, away_id = await _setup_entities(db_session)
        match_id = await _setup_match(db_session, league_id, home_id, away_id)

        await _add_odds_snapshot(
            db_session, match_id, "bet365", "btts", "yes", 2.00
        )

        signal = await _generate_signal(
            db_session, match_id, "btts", "yes", 0.60, 0.85
        )

        # No is_closing snapshot set
        bet = Bet(
            id=new_uuid(),
            signal_id=signal.id,
            match_id=match_id,
            market="btts",
            selection="yes",
            bookmaker="bet365",
            odds=2.00,
            stake_dkk=100.0,
            potential_return_dkk=200.0,
            outcome="pending",
            placed_at=_utcnow(),
        )
        db_session.add(bet)
        await db_session.flush()

        tracker = ClosingLineTracker()
        clv = await tracker.calculate_clv_for_bet(db_session, bet.id)
        assert clv is None


# ---------------------------------------------------------------------------
# Tests: PositionSizer with bankroll state
# ---------------------------------------------------------------------------

class TestPositionSizerWithDB:

    async def test_position_sizer_stake_capped_at_max_stake_pct(
        self, db_session: AsyncSession
    ) -> None:
        """With quarter-Kelly exceeding max_stake_pct, stake is capped.

        settings.max_stake_pct = 0.03, bankroll = 10000.
        Kelly for prob=0.60, odds=2.00: full_kelly = (0.60*2-1)/(2-1) = 0.20
        quarter_kelly = 0.05 > 0.03 -> capped at 0.03.
        Expected stake_dkk = 10000 * 0.03 = 300.
        """
        league_id, home_id, away_id = await _setup_entities(db_session)
        match_id = await _setup_match(db_session, league_id, home_id, away_id)

        bm = BankrollManager(initial_bankroll=10000.0)
        sizer = PositionSizer(bankroll_manager=bm)

        result = await sizer.calculate_stake(
            db_session,
            model_prob=0.60,
            decimal_odds=2.00,
            match_id=match_id,
        )

        assert result["blocked"] is False
        assert result["capped"] is True
        assert result["kelly_fraction"] == pytest.approx(0.03)
        assert result["stake_dkk"] == pytest.approx(300.0)

    async def test_position_sizer_returns_zero_for_negative_edge(
        self, db_session: AsyncSession
    ) -> None:
        """PositionSizer returns blocked=True when there is no positive Kelly fraction.

        prob=0.40, odds=2.00 -> full_kelly = (0.40*2-1)/(2-1) = -0.20 -> 0.
        """
        league_id, home_id, away_id = await _setup_entities(db_session)
        match_id = await _setup_match(db_session, league_id, home_id, away_id)

        bm = BankrollManager(initial_bankroll=10000.0)
        sizer = PositionSizer(bankroll_manager=bm)

        result = await sizer.calculate_stake(
            db_session,
            model_prob=0.40,
            decimal_odds=2.00,
            match_id=match_id,
        )

        assert result["blocked"] is True
        assert result["stake_dkk"] == pytest.approx(0.0)
        assert result["reason"] == "no positive edge"

    async def test_kelly_calculator_fractional_kelly(self) -> None:
        """KellyCalculator.fractional_kelly applies the fraction correctly.

        prob=0.60, odds=2.00, fraction=0.25:
        full_kelly = (0.60*2-1)/(2-1) = 0.20
        fractional = 0.20 * 0.25 = 0.05
        """
        kelly = KellyCalculator.fractional_kelly(0.60, 2.00, fraction=0.25)
        assert kelly == pytest.approx(0.05)

    async def test_position_sizer_with_bankroll_after_loss(
        self, db_session: AsyncSession
    ) -> None:
        """Stake scales with updated (smaller) bankroll after a loss."""
        league_id, home_id, away_id = await _setup_entities(db_session)
        match_id = await _setup_match(db_session, league_id, home_id, away_id)

        bm = BankrollManager(initial_bankroll=10000.0)
        bm.update(-2000.0)  # Bankroll now 8000
        assert bm.current == pytest.approx(8000.0)

        sizer = PositionSizer(bankroll_manager=bm)
        result = await sizer.calculate_stake(
            db_session,
            model_prob=0.60,
            decimal_odds=2.00,
            match_id=match_id,
        )

        # max_stake_pct=0.03 of 8000 = 240
        assert result["blocked"] is False
        assert result["stake_dkk"] == pytest.approx(240.0)

    async def test_bankroll_load_from_db(self, db_session: AsyncSession) -> None:
        """BankrollManager.load_from_db restores state from the latest snapshot."""
        # Write a snapshot to DB directly
        snap = BankrollSnapshot(
            id=new_uuid(),
            balance_dkk=9500.0,
            peak_dkk=10000.0,
            drawdown_pct=0.05,
            roi_pct=-0.05,
            snapshot_at=_utcnow(),
        )
        db_session.add(snap)
        await db_session.flush()

        bm = BankrollManager(initial_bankroll=10000.0)
        await bm.load_from_db(db_session)

        assert bm.current == pytest.approx(9500.0)
        assert bm.peak == pytest.approx(10000.0)

    async def test_signal_generator_with_position_sizer(
        self, db_session: AsyncSession
    ) -> None:
        """SignalGenerator with PositionSizer populates suggested_stake_dkk on signals."""
        league_id, home_id, away_id = await _setup_entities(db_session)
        match_id = await _setup_match(db_session, league_id, home_id, away_id)

        await _add_odds_snapshot(
            db_session, match_id, "bet365", "team_goals_ou", "over_2.5", 2.00
        )

        bm = BankrollManager(initial_bankroll=10000.0)
        sizer = PositionSizer(bankroll_manager=bm)
        generator = SignalGenerator(position_sizer=sizer)

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

        # Position sizer should have set stake values
        assert sig.suggested_stake_pct > 0.0
        assert sig.suggested_stake_dkk > 0.0
        # With capping at max_stake_pct=0.03 and bankroll=10000: stake = 300
        assert sig.suggested_stake_dkk == pytest.approx(300.0)
