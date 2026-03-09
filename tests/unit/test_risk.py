"""Tests for risk management: stops, exposure, bankroll, position sizer."""

import pytest

from risk.bankroll import BankrollManager
from risk.exposure import ExposureTracker
from risk.stops import StopLossManager


class TestStopLossManager:
    def test_daily_stop_triggers_above_threshold(self):
        """Loss of 5.1% of bankroll triggers daily stop (strict >)."""
        assert StopLossManager.check_daily_stop(-510, 10000, 0.05) is True

    def test_daily_stop_does_not_trigger_at_threshold(self):
        """Loss of exactly 5.0% does NOT trigger (strict >)."""
        assert StopLossManager.check_daily_stop(-500, 10000, 0.05) is False

    def test_daily_stop_does_not_trigger_below_threshold(self):
        """Loss of 4.9% does NOT trigger."""
        assert StopLossManager.check_daily_stop(-490, 10000, 0.05) is False

    def test_daily_stop_positive_pnl(self):
        """Positive P&L never triggers daily stop."""
        assert StopLossManager.check_daily_stop(100, 10000, 0.05) is False

    def test_daily_stop_zero_pnl(self):
        """Zero P&L never triggers daily stop."""
        assert StopLossManager.check_daily_stop(0, 10000, 0.05) is False

    def test_daily_stop_zero_bankroll(self):
        """Zero bankroll returns False (guard against division by zero)."""
        assert StopLossManager.check_daily_stop(-100, 0, 0.05) is False

    def test_drawdown_stop_triggers_above_threshold(self):
        """Drawdown of 20.1% triggers (strict >)."""
        # peak=10000, current=7990 -> drawdown = 2010/10000 = 0.201
        assert StopLossManager.check_drawdown_stop(7990, 10000, 0.20) is True

    def test_drawdown_stop_does_not_trigger_at_threshold(self):
        """Drawdown of exactly 20.0% does NOT trigger (strict >)."""
        # peak=10000, current=8000 -> drawdown = 2000/10000 = 0.20
        assert StopLossManager.check_drawdown_stop(8000, 10000, 0.20) is False

    def test_drawdown_stop_no_drawdown(self):
        """No drawdown -> does not trigger."""
        assert StopLossManager.check_drawdown_stop(10000, 10000, 0.20) is False

    def test_drawdown_stop_zero_peak(self):
        """Zero peak returns False."""
        assert StopLossManager.check_drawdown_stop(0, 0, 0.20) is False


class TestBankrollManager:
    def test_initial_state(self):
        """Initial state: current = peak = initial."""
        bm = BankrollManager(10000)
        assert bm.current == 10000
        assert bm.peak == 10000
        assert bm.initial == 10000

    def test_update_profit(self):
        """Profit increases current and peak."""
        bm = BankrollManager(10000)
        bm.update(500)
        assert bm.current == 10500
        assert bm.peak == 10500

    def test_update_loss(self):
        """Loss decreases current but not peak."""
        bm = BankrollManager(10000)
        bm.update(-300)
        assert bm.current == 9700
        assert bm.peak == 10000

    def test_drawdown_pct(self):
        """Drawdown % after a loss."""
        bm = BankrollManager(10000)
        bm.update(-1000)
        assert bm.drawdown_pct == pytest.approx(0.10)

    def test_drawdown_pct_no_loss(self):
        """No drawdown when at peak."""
        bm = BankrollManager(10000)
        assert bm.drawdown_pct == pytest.approx(0.0)

    def test_roi_pct_profit(self):
        """ROI after profit."""
        bm = BankrollManager(10000)
        bm.update(2000)
        assert bm.roi_pct == pytest.approx(0.20)

    def test_roi_pct_loss(self):
        """ROI after loss."""
        bm = BankrollManager(10000)
        bm.update(-1500)
        assert bm.roi_pct == pytest.approx(-0.15)

    def test_roi_pct_zero_initial(self):
        """Zero initial bankroll returns 0 ROI."""
        bm = BankrollManager(0)
        assert bm.roi_pct == 0.0

    def test_drawdown_pct_zero_peak(self):
        """Zero peak bankroll returns 0 drawdown."""
        bm = BankrollManager(0)
        assert bm.drawdown_pct == 0.0

    def test_peak_recovery(self):
        """Peak updates correctly after loss then recovery."""
        bm = BankrollManager(10000)
        bm.update(-2000)  # current=8000, peak=10000
        bm.update(3000)   # current=11000, peak=11000
        assert bm.current == 11000
        assert bm.peak == 11000
        assert bm.drawdown_pct == pytest.approx(0.0)


class TestExposureTracker:
    def test_check_daily_limit_under(self):
        """Under limit returns True."""
        tracker = ExposureTracker()
        assert tracker.check_daily_limit(0.08, 0.10) is True

    def test_check_daily_limit_at(self):
        """At exactly the limit returns False (strict <)."""
        tracker = ExposureTracker()
        assert tracker.check_daily_limit(0.10, 0.10) is False

    def test_check_daily_limit_over(self):
        """Over limit returns False."""
        tracker = ExposureTracker()
        assert tracker.check_daily_limit(0.12, 0.10) is False

    def test_check_fixture_limit_under(self):
        """Under fixture limit returns True."""
        tracker = ExposureTracker()
        assert tracker.check_fixture_limit(0.03, 0.05) is True

    def test_check_fixture_limit_at(self):
        """At exactly the fixture limit returns False (strict <)."""
        tracker = ExposureTracker()
        assert tracker.check_fixture_limit(0.05, 0.05) is False

    def test_check_fixture_limit_over(self):
        """Over fixture limit returns False."""
        tracker = ExposureTracker()
        assert tracker.check_fixture_limit(0.06, 0.05) is False
