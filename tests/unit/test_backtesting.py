"""Tests for backtesting system: walk-forward splits, simulator, and metrics."""

import pytest

from backtesting.metrics import BacktestMetrics, compute_metrics
from backtesting.simulator import BetSimulator
from backtesting.walk_forward import WalkForwardBacktester


# ---------------------------------------------------------------------------
# Walk-forward split tests
# ---------------------------------------------------------------------------


def _make_chronological_data(n: int) -> list[dict]:
    """Create N data points with sequential dates."""
    return [
        {
            "match_id": f"match_{i}",
            "date": f"2025-01-{(i % 28) + 1:02d}",
            "market": "team_goals_ou",
            "selection": "over_2.5",
            "feat_a": float(i % 5),
            "feat_b": float(i % 3),
            "target": i % 2,
            "odds": 2.00,
            "closing_odds": 1.95,
        }
        for i in range(n)
    ]


def test_walk_forward_splits():
    """Verify walk-forward splits produce correct sizes and counts."""
    data = _make_chronological_data(300)
    wf = WalkForwardBacktester(train_window=200, test_window=50, step_size=25)
    splits = wf.split(data)

    # With 300 items, train=200, test=50, step=25:
    # start=0: 0..199 train, 200..249 test  (0+200+50=250 <= 300) OK
    # start=25: 25..224 train, 225..274 test (25+200+50=275 <= 300) OK
    # start=50: 50..249 train, 250..299 test (50+200+50=300 <= 300) OK
    # start=75: 75+200+50=325 > 300 STOP
    assert len(splits) == 3

    for train, test in splits:
        assert len(train) == 200
        assert len(test) == 50


def test_walk_forward_no_future_leakage():
    """Ensure training data dates are strictly before test data dates."""
    data = _make_chronological_data(300)
    # Give each data point a unique sequential timestamp
    for i, d in enumerate(data):
        d["timestamp"] = i

    wf = WalkForwardBacktester(train_window=200, test_window=50, step_size=25)
    splits = wf.split(data)

    for train, test in splits:
        max_train_ts = max(d["timestamp"] for d in train)
        min_test_ts = min(d["timestamp"] for d in test)
        assert max_train_ts < min_test_ts, (
            f"Future leakage: max train timestamp {max_train_ts} >= "
            f"min test timestamp {min_test_ts}"
        )


# ---------------------------------------------------------------------------
# Simulator tests
# ---------------------------------------------------------------------------


def _make_prediction(
    odds: float = 2.00,
    model_prob: float = 0.60,
    outcome: bool = True,
    date: str = "2025-01-01",
    match_id: str = "m1",
    closing_odds: float | None = None,
) -> dict:
    return {
        "match_id": match_id,
        "market": "team_goals_ou",
        "selection": "over_2.5",
        "model_prob": model_prob,
        "odds": odds,
        "outcome": outcome,
        "date": date,
        "closing_odds": closing_odds,
    }


def test_simulator_basic_win():
    """A single winning bet should increase bankroll correctly."""
    sim = BetSimulator(starting_bankroll=10000.0)
    pred = _make_prediction(odds=2.00, model_prob=0.60, outcome=True)
    bets, equity = sim.simulate([pred])

    assert len(bets) == 1
    bet = bets[0]
    assert bet.won is True
    assert bet.pnl > 0
    # Bankroll should increase: stake * (odds-1) = stake * 1.0
    assert bet.bankroll_after == pytest.approx(10000.0 + bet.pnl)
    assert bet.bankroll_after > 10000.0


def test_simulator_basic_loss():
    """A single losing bet should decrease bankroll correctly."""
    sim = BetSimulator(starting_bankroll=10000.0)
    pred = _make_prediction(odds=2.00, model_prob=0.60, outcome=False)
    bets, equity = sim.simulate([pred])

    assert len(bets) == 1
    bet = bets[0]
    assert bet.won is False
    assert bet.pnl < 0
    assert bet.pnl == pytest.approx(-bet.stake)
    assert bet.bankroll_after == pytest.approx(10000.0 - bet.stake)
    assert bet.bankroll_after < 10000.0


def test_simulator_kelly_stake():
    """Verify quarter-Kelly stake calculation."""
    bankroll = 10000.0
    sim = BetSimulator(
        starting_bankroll=bankroll,
        kelly_fraction=0.25,
        max_stake_pct=1.0,  # Remove cap for this test
    )
    # model_prob=0.60, odds=2.00
    # Full Kelly = (0.60 * 2.00 - 1) / (2.00 - 1) = 0.20 / 1.00 = 0.20
    # Quarter Kelly = 0.20 * 0.25 = 0.05
    # Stake = 0.05 * 10000 = 500
    pred = _make_prediction(odds=2.00, model_prob=0.60, outcome=True)
    bets, _ = sim.simulate([pred])

    assert len(bets) == 1
    expected_stake = 0.05 * bankroll  # 500.0
    assert bets[0].stake == pytest.approx(expected_stake)


def test_simulator_max_stake_cap():
    """Stake should be capped at max_stake_pct of bankroll."""
    bankroll = 10000.0
    sim = BetSimulator(
        starting_bankroll=bankroll,
        kelly_fraction=0.25,
        max_stake_pct=0.03,  # 3% cap
    )
    # Use high model_prob to generate a large Kelly stake
    # model_prob=0.80, odds=2.00
    # Full Kelly = (0.80 * 2.00 - 1) / (2.00 - 1) = 0.60
    # Quarter Kelly = 0.60 * 0.25 = 0.15
    # Uncapped stake = 0.15 * 10000 = 1500
    # Capped stake = 0.03 * 10000 = 300
    pred = _make_prediction(odds=2.00, model_prob=0.80, outcome=True)
    bets, _ = sim.simulate([pred])

    assert len(bets) == 1
    max_allowed = 0.03 * bankroll  # 300
    assert bets[0].stake == pytest.approx(max_allowed)


def test_simulator_ev_filter():
    """Bets below min EV threshold (3%) should be skipped."""
    sim = BetSimulator(starting_bankroll=10000.0, min_ev=0.03)
    # model_prob=0.50, odds=2.00 -> EV = 0.50 * 2.00 - 1 = 0.00 (below 3%)
    pred = _make_prediction(odds=2.00, model_prob=0.50, outcome=True)
    bets, equity = sim.simulate([pred])

    assert len(bets) == 0
    assert equity == [10000.0]  # Only starting value


def test_simulator_odds_range_filter():
    """Odds outside 1.50-4.00 range should be skipped."""
    sim = BetSimulator(starting_bankroll=10000.0, min_odds=1.50, max_odds=4.00)

    # Odds too low (1.20)
    pred_low = _make_prediction(odds=1.20, model_prob=0.90, outcome=True)
    bets_low, _ = sim.simulate([pred_low])
    assert len(bets_low) == 0

    # Odds too high (5.00)
    pred_high = _make_prediction(odds=5.00, model_prob=0.30, outcome=True)
    bets_high, _ = sim.simulate([pred_high])
    assert len(bets_high) == 0

    # Odds in range (2.50) with sufficient EV
    pred_ok = _make_prediction(odds=2.50, model_prob=0.60, outcome=True)
    bets_ok, _ = sim.simulate([pred_ok])
    assert len(bets_ok) == 1


def test_simulator_daily_stop():
    """Should stop betting after 5% daily loss."""
    sim = BetSimulator(
        starting_bankroll=10000.0,
        daily_stop_pct=0.05,
        kelly_fraction=0.25,
        max_stake_pct=0.03,
    )
    # Create several losing bets on the same day to trigger daily stop
    # max_stake = 3% of 10000 = 300 per bet
    # 5% daily stop = 500 loss threshold
    # After ~2 losses (300 each = 600 > 500) the stop should trigger
    predictions = [
        _make_prediction(
            odds=2.00, model_prob=0.80, outcome=False, date="2025-01-01", match_id=f"m{i}"
        )
        for i in range(5)
    ]
    bets, _ = sim.simulate(predictions)

    # Should have placed some bets but not all 5 (daily stop kicks in)
    assert len(bets) < 5
    assert len(bets) >= 1  # At least the first bet


def test_simulator_drawdown_stop():
    """Should stop betting after 20% overall drawdown."""
    sim = BetSimulator(
        starting_bankroll=10000.0,
        max_drawdown_pct=0.20,
        kelly_fraction=0.25,
        max_stake_pct=0.10,  # Higher cap so drawdown triggers faster
        daily_stop_pct=1.0,  # Disable daily stop for this test
    )
    # Create many losing bets across different days to hit 20% drawdown
    predictions = [
        _make_prediction(
            odds=2.00,
            model_prob=0.80,
            outcome=False,
            date=f"2025-01-{(i + 1):02d}",
            match_id=f"m{i}",
        )
        for i in range(20)
    ]
    bets, equity = sim.simulate(predictions)

    # Should stop before placing all 20 bets
    assert len(bets) < 20
    assert len(bets) >= 1

    # Final bankroll should not have dropped more than ~20% from peak
    final_bankroll = equity[-1]
    assert final_bankroll >= 10000.0 * (1 - 0.20 - 0.10)  # Some tolerance


# ---------------------------------------------------------------------------
# Metrics tests
# ---------------------------------------------------------------------------


def _make_bet_dict(
    odds: float = 2.00,
    stake: float = 100.0,
    won: bool = True,
    model_prob: float = 0.60,
    ev: float = 0.05,
    closing_odds: float | None = None,
) -> dict:
    return {
        "odds": odds,
        "stake": stake,
        "won": won,
        "model_prob": model_prob,
        "ev": ev,
        "closing_odds": closing_odds,
    }


def test_metrics_roi():
    """Verify correct ROI calculation."""
    # 5 wins at odds 2.00, stake 100 each = 5 * 100 profit
    # 5 losses at stake 100 each = -500
    # Total staked = 1000, profit = 500 - 500 = 0 => ROI = 0%
    bets = [_make_bet_dict(won=True) for _ in range(5)] + [
        _make_bet_dict(won=False) for _ in range(5)
    ]
    metrics = compute_metrics(bets)

    assert metrics.total_bets == 10
    assert metrics.wins == 5
    assert metrics.losses == 5
    assert metrics.total_staked == pytest.approx(1000.0)
    # wins return: 5 * 100 * 2.00 = 1000, total return = 1000
    # profit = 1000 - 1000 = 0
    assert metrics.profit == pytest.approx(0.0)
    assert metrics.roi_pct == pytest.approx(0.0)


def test_metrics_max_drawdown():
    """Verify max drawdown calculation."""
    # Pattern: win, win, loss, loss, loss -> drawdown from peak
    bets = [
        _make_bet_dict(odds=2.00, stake=100, won=True),   # +100 (equity: +100)
        _make_bet_dict(odds=2.00, stake=100, won=True),   # +100 (equity: +200)
        _make_bet_dict(odds=2.00, stake=100, won=False),  # -100 (equity: +100)
        _make_bet_dict(odds=2.00, stake=100, won=False),  # -100 (equity: 0)
        _make_bet_dict(odds=2.00, stake=100, won=False),  # -100 (equity: -100)
    ]
    metrics = compute_metrics(bets)

    # Peak equity: +200 above base (bankroll = base + 200)
    # Lowest after peak: -100 (bankroll = base - 100)
    # Drawdown from peak: 300 / (base + 200)
    # With total_staked as base reference = 500, bankroll peak = 700, trough = 400
    # drawdown = 300 / 700 ~ 0.4286
    assert metrics.max_drawdown_pct > 0.0
    assert metrics.max_drawdown_pct < 1.0


def test_metrics_go_live_pass():
    """Metrics that meet all go-live criteria should pass."""
    metrics = BacktestMetrics(
        total_bets=600,
        wins=350,
        losses=250,
        win_rate=350 / 600,
        total_staked=60000.0,
        total_return=63000.0,
        profit=3000.0,
        roi_pct=0.05,  # 5% > 3%
        max_drawdown_pct=0.10,  # 10% < 15%
        sharpe_ratio=1.5,
        longest_losing_streak=5,
        longest_winning_streak=8,
        avg_odds=2.10,
        avg_ev=0.06,
        brier_score=0.18,  # < 0.22
        clv_pct=0.60,  # 60% > 55%
    )
    criteria = metrics.meets_go_live()

    assert criteria["brier"] is True
    assert criteria["roi"] is True
    assert criteria["drawdown"] is True
    assert criteria["clv"] is True
    assert all(criteria.values())


def test_metrics_go_live_fail():
    """Metrics failing criteria should report failures correctly."""
    metrics = BacktestMetrics(
        total_bets=200,  # < 500, so roi check fails
        wins=100,
        losses=100,
        win_rate=0.50,
        total_staked=20000.0,
        total_return=20800.0,
        profit=800.0,
        roi_pct=0.04,  # 4% > 3% but total_bets < 500
        max_drawdown_pct=0.18,  # 18% > 15%
        sharpe_ratio=0.8,
        longest_losing_streak=7,
        longest_winning_streak=5,
        avg_odds=2.00,
        avg_ev=0.04,
        brier_score=0.25,  # > 0.22
        clv_pct=0.50,  # < 55%
    )
    criteria = metrics.meets_go_live()

    assert criteria["brier"] is False  # 0.25 >= 0.22
    assert criteria["roi"] is False  # total_bets < 500
    assert criteria["drawdown"] is False  # 0.18 >= 0.15
    assert criteria["clv"] is False  # 0.50 <= 0.55
    assert not any(criteria.values())


def test_metrics_win_rate():
    """Win rate should be computed correctly."""
    bets = [_make_bet_dict(won=True)] * 7 + [_make_bet_dict(won=False)] * 3
    metrics = compute_metrics(bets)
    assert metrics.win_rate == pytest.approx(0.7)


def test_metrics_brier_score():
    """Brier score should compute mean squared error of probabilities vs outcomes."""
    # Perfect predictions: prob=1.0 for wins, prob=0.0 for losses -> brier=0
    bets = [
        _make_bet_dict(won=True, model_prob=1.0),
        _make_bet_dict(won=False, model_prob=0.0),
    ]
    metrics = compute_metrics(bets)
    assert metrics.brier_score == pytest.approx(0.0)

    # Worst predictions: prob=0.0 for wins, prob=1.0 for losses -> brier=1.0
    bets_bad = [
        _make_bet_dict(won=True, model_prob=0.0),
        _make_bet_dict(won=False, model_prob=1.0),
    ]
    metrics_bad = compute_metrics(bets_bad)
    assert metrics_bad.brier_score == pytest.approx(1.0)


def test_metrics_clv():
    """CLV percentage should reflect fraction beating closing line."""
    bets = [
        _make_bet_dict(odds=2.10, closing_odds=2.00),  # Beat closing
        _make_bet_dict(odds=1.90, closing_odds=2.00),  # Did not beat
        _make_bet_dict(odds=2.50, closing_odds=2.30),  # Beat closing
        _make_bet_dict(odds=1.80, closing_odds=1.80),  # Equal, not beat
    ]
    metrics = compute_metrics(bets)
    # 2 out of 4 beat closing line
    assert metrics.clv_pct == pytest.approx(0.5)


def test_metrics_streaks():
    """Longest winning and losing streaks should be computed correctly."""
    bets = [
        _make_bet_dict(won=True),
        _make_bet_dict(won=True),
        _make_bet_dict(won=True),   # 3-win streak
        _make_bet_dict(won=False),
        _make_bet_dict(won=False),  # 2-loss streak
        _make_bet_dict(won=True),
        _make_bet_dict(won=False),
        _make_bet_dict(won=False),
        _make_bet_dict(won=False),
        _make_bet_dict(won=False),  # 4-loss streak
    ]
    metrics = compute_metrics(bets)
    assert metrics.longest_winning_streak == 3
    assert metrics.longest_losing_streak == 4


def test_metrics_empty_bets():
    """Empty bet list should return zeroed metrics."""
    metrics = compute_metrics([])
    assert metrics.total_bets == 0
    assert metrics.roi_pct == 0.0
    assert metrics.max_drawdown_pct == 0.0
