"""Position sizing — combines Kelly, exposure limits, and stop-losses."""

from config.settings import settings
from risk.bankroll import BankrollManager
from risk.exposure import ExposureTracker
from risk.kelly import KellyCalculator
from risk.stops import StopLossManager

from sqlalchemy.ext.asyncio import AsyncSession


class PositionSizer:
    """Calculate final stake amount applying all risk constraints."""

    def __init__(self, bankroll_manager: BankrollManager):
        self.bankroll = bankroll_manager
        self.kelly = KellyCalculator()
        self.exposure = ExposureTracker()
        self.stops = StopLossManager()

    async def calculate_stake(
        self,
        session: AsyncSession,
        model_prob: float,
        decimal_odds: float,
        match_id: str,
        daily_pnl: float = 0.0,
    ) -> dict:
        """Calculate final stake amount applying all constraints.

        Returns:
            {
                "stake_dkk": float,
                "kelly_fraction": float,
                "capped": bool,
                "reason": str | None (why reduced/zeroed),
                "blocked": bool,
            }

        Process:
        1. Check stop-loss conditions -> if triggered, return 0.
        2. Calculate quarter-Kelly.
        3. Cap at max_stake_pct of bankroll.
        4. Check daily exposure limit.
        5. Check fixture exposure limit.
        6. Return final stake.
        """
        bankroll = self.bankroll.current

        # 1. Check stop-loss conditions
        if self.stops.check_daily_stop(daily_pnl, bankroll, settings.daily_stop_loss_pct):
            return {
                "stake_dkk": 0.0,
                "kelly_fraction": 0.0,
                "capped": False,
                "reason": "daily stop-loss triggered",
                "blocked": True,
            }

        if self.stops.check_drawdown_stop(
            bankroll, self.bankroll.peak, settings.max_drawdown_pct
        ):
            return {
                "stake_dkk": 0.0,
                "kelly_fraction": 0.0,
                "capped": False,
                "reason": "max drawdown triggered",
                "blocked": True,
            }

        # 2. Calculate quarter-Kelly
        kelly_frac = self.kelly.fractional_kelly(
            model_prob, decimal_odds, settings.kelly_fraction
        )

        if kelly_frac <= 0:
            return {
                "stake_dkk": 0.0,
                "kelly_fraction": 0.0,
                "capped": False,
                "reason": "no positive edge",
                "blocked": True,
            }

        # 3. Cap at max_stake_pct
        capped = False
        reason = None
        if kelly_frac > settings.max_stake_pct:
            kelly_frac = settings.max_stake_pct
            capped = True
            reason = f"capped at max_stake_pct ({settings.max_stake_pct:.1%})"

        stake_dkk = self.kelly.stake_amount(bankroll, kelly_frac)

        # 4. Check daily exposure limit
        daily_exp = await self.exposure.get_daily_exposure(session, bankroll)
        if not self.exposure.check_daily_limit(
            daily_exp, settings.max_daily_exposure_pct
        ):
            return {
                "stake_dkk": 0.0,
                "kelly_fraction": kelly_frac,
                "capped": capped,
                "reason": "daily exposure limit reached",
                "blocked": True,
            }

        # 5. Check fixture exposure limit
        fixture_exp = await self.exposure.get_fixture_exposure(
            session, match_id, bankroll
        )
        if not self.exposure.check_fixture_limit(
            fixture_exp, settings.max_fixture_exposure_pct
        ):
            return {
                "stake_dkk": 0.0,
                "kelly_fraction": kelly_frac,
                "capped": capped,
                "reason": "fixture exposure limit reached",
                "blocked": True,
            }

        return {
            "stake_dkk": round(stake_dkk, 2),
            "kelly_fraction": kelly_frac,
            "capped": capped,
            "reason": reason,
            "blocked": False,
        }
