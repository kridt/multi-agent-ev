"""Bet simulation engine with Kelly staking and risk controls."""

from dataclasses import dataclass


@dataclass
class SimulatedBet:
    match_id: str
    market: str
    selection: str
    odds: float
    model_prob: float
    ev: float
    stake: float
    won: bool
    pnl: float
    bankroll_after: float
    closing_odds: float | None = None


class BetSimulator:
    """Simulate betting through a sequence of predictions with risk controls."""

    def __init__(
        self,
        starting_bankroll: float = 10000.0,
        kelly_fraction: float = 0.25,
        max_stake_pct: float = 0.03,
        min_ev: float = 0.03,
        min_odds: float = 1.50,
        max_odds: float = 4.00,
        daily_stop_pct: float = 0.05,
        max_drawdown_pct: float = 0.20,
    ):
        self.starting_bankroll = starting_bankroll
        self.kelly_fraction = kelly_fraction
        self.max_stake_pct = max_stake_pct
        self.min_ev = min_ev
        self.min_odds = min_odds
        self.max_odds = max_odds
        self.daily_stop_pct = daily_stop_pct
        self.max_drawdown_pct = max_drawdown_pct

    def simulate(
        self, predictions: list[dict]
    ) -> tuple[list[SimulatedBet], list[float]]:
        """Run simulation through predictions.

        Each prediction dict: {
            "match_id": str, "market": str, "selection": str,
            "model_prob": float, "odds": float, "outcome": bool,
            "date": str, "closing_odds": float | None
        }

        Process for each prediction (in chronological order):
        1. Calculate EV, check threshold
        2. Check odds range
        3. Check stop conditions (daily loss, drawdown)
        4. Calculate quarter-Kelly stake, cap at max_stake_pct
        5. Record bet result
        6. Update bankroll

        Returns (list of SimulatedBet, equity curve as list of bankroll values)
        """
        bets: list[SimulatedBet] = []
        equity_curve = [self.starting_bankroll]
        bankroll = self.starting_bankroll
        peak = self.starting_bankroll
        daily_pnl = 0.0
        current_date = ""

        for pred in predictions:
            # Reset daily PnL on new day
            if pred["date"] != current_date:
                daily_pnl = 0.0
                current_date = pred["date"]

            # Calculate EV
            ev = pred["model_prob"] * pred["odds"] - 1
            if ev < self.min_ev:
                continue

            # Check odds range
            if not (self.min_odds <= pred["odds"] <= self.max_odds):
                continue

            # Check stop conditions
            if daily_pnl < 0 and abs(daily_pnl) / bankroll > self.daily_stop_pct:
                continue
            if (peak - bankroll) / peak > self.max_drawdown_pct:
                continue

            # Quarter-Kelly stake
            kelly = (pred["model_prob"] * pred["odds"] - 1) / (pred["odds"] - 1)
            kelly *= self.kelly_fraction
            kelly = max(0, kelly)
            stake = min(kelly * bankroll, self.max_stake_pct * bankroll)

            if stake <= 0:
                continue

            # Resolve bet
            if pred["outcome"]:
                pnl = stake * (pred["odds"] - 1)
            else:
                pnl = -stake

            bankroll += pnl
            daily_pnl += pnl
            if bankroll > peak:
                peak = bankroll

            bets.append(
                SimulatedBet(
                    match_id=pred["match_id"],
                    market=pred["market"],
                    selection=pred["selection"],
                    odds=pred["odds"],
                    model_prob=pred["model_prob"],
                    ev=ev,
                    stake=stake,
                    won=pred["outcome"],
                    pnl=pnl,
                    bankroll_after=bankroll,
                    closing_odds=pred.get("closing_odds"),
                )
            )
            equity_curve.append(bankroll)

        return bets, equity_curve
