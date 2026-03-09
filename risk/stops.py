"""Stop-loss conditions for risk management."""


class StopLossManager:
    """Evaluate stop-loss conditions to halt betting."""

    @staticmethod
    def check_daily_stop(
        daily_pnl: float, bankroll: float, max_loss_pct: float = 0.05
    ) -> bool:
        """True if should STOP — daily loss exceeds threshold.

        Uses strict > comparison: a loss of exactly max_loss_pct does NOT trigger.
        """
        if bankroll <= 0:
            return False
        return (daily_pnl < 0) and (abs(daily_pnl) / bankroll > max_loss_pct)

    @staticmethod
    def check_drawdown_stop(
        current_bankroll: float,
        peak_bankroll: float,
        max_drawdown_pct: float = 0.20,
    ) -> bool:
        """True if should STOP — drawdown exceeds threshold.

        Uses strict > comparison: a drawdown of exactly max_drawdown_pct does NOT trigger.
        """
        if peak_bankroll == 0:
            return False
        drawdown = (peak_bankroll - current_bankroll) / peak_bankroll
        return drawdown > max_drawdown_pct
