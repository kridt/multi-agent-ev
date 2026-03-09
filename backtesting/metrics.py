"""Backtest performance metrics computation."""

from dataclasses import dataclass

import numpy as np


@dataclass
class BacktestMetrics:
    total_bets: int
    wins: int
    losses: int
    win_rate: float
    total_staked: float
    total_return: float
    profit: float
    roi_pct: float
    max_drawdown_pct: float
    sharpe_ratio: float
    longest_losing_streak: int
    longest_winning_streak: int
    avg_odds: float
    avg_ev: float
    brier_score: float
    clv_pct: float  # % of bets that beat closing line

    def meets_go_live(self) -> dict:
        """Check against go-live criteria.

        Returns: {"brier": bool (<0.22), "roi": bool (>3% over 500+),
                  "drawdown": bool (<15%), "clv": bool (>55%)}
        """
        return {
            "brier": self.brier_score < 0.22,
            "roi": self.roi_pct > 0.03 and self.total_bets >= 500,
            "drawdown": self.max_drawdown_pct < 0.15,
            "clv": self.clv_pct > 0.55,
        }


def compute_metrics(bets: list[dict]) -> BacktestMetrics:
    """Compute all backtest metrics from a list of bet dicts.

    Each bet dict: {"odds": float, "stake": float, "won": bool, "model_prob": float,
                    "closing_odds": float | None, "ev": float}
    """
    if not bets:
        return BacktestMetrics(
            total_bets=0,
            wins=0,
            losses=0,
            win_rate=0.0,
            total_staked=0.0,
            total_return=0.0,
            profit=0.0,
            roi_pct=0.0,
            max_drawdown_pct=0.0,
            sharpe_ratio=0.0,
            longest_losing_streak=0,
            longest_winning_streak=0,
            avg_odds=0.0,
            avg_ev=0.0,
            brier_score=0.0,
            clv_pct=0.0,
        )

    total_bets = len(bets)
    wins = sum(1 for b in bets if b["won"])
    losses = total_bets - wins
    win_rate = wins / total_bets

    total_staked = sum(b["stake"] for b in bets)
    total_return = sum(
        b["stake"] * b["odds"] if b["won"] else 0.0 for b in bets
    )
    profit = total_return - total_staked
    roi_pct = profit / total_staked if total_staked > 0 else 0.0

    # Equity curve and max drawdown
    equity = [0.0]
    for b in bets:
        pnl = b["stake"] * (b["odds"] - 1) if b["won"] else -b["stake"]
        equity.append(equity[-1] + pnl)

    equity_arr = np.array(equity)
    running_max = np.maximum.accumulate(equity_arr)
    # Avoid division by zero: use starting bankroll reference of total_staked
    # Drawdown is measured relative to the peak equity value
    # We add total_staked as base so equity represents actual bankroll
    bankroll_curve = equity_arr + total_staked
    bankroll_peak = np.maximum.accumulate(bankroll_curve)
    drawdowns = np.where(
        bankroll_peak > 0,
        (bankroll_peak - bankroll_curve) / bankroll_peak,
        0.0,
    )
    max_drawdown_pct = float(np.max(drawdowns))

    # Sharpe ratio: annualised from per-bet returns
    returns = []
    for b in bets:
        if b["won"]:
            returns.append(b["stake"] * (b["odds"] - 1) / b["stake"])
        else:
            returns.append(-1.0)
    returns_arr = np.array(returns)
    if len(returns_arr) > 1 and np.std(returns_arr) > 0:
        sharpe_ratio = float(
            np.mean(returns_arr) / np.std(returns_arr) * np.sqrt(252)
        )
    else:
        sharpe_ratio = 0.0

    # Longest streaks
    longest_winning_streak = 0
    longest_losing_streak = 0
    current_win = 0
    current_loss = 0
    for b in bets:
        if b["won"]:
            current_win += 1
            current_loss = 0
            longest_winning_streak = max(longest_winning_streak, current_win)
        else:
            current_loss += 1
            current_win = 0
            longest_losing_streak = max(longest_losing_streak, current_loss)

    # Average odds and EV
    avg_odds = float(np.mean([b["odds"] for b in bets]))
    avg_ev = float(np.mean([b["ev"] for b in bets]))

    # Brier score: mean((model_prob - outcome)^2)
    brier_score = float(
        np.mean([(b["model_prob"] - (1.0 if b["won"] else 0.0)) ** 2 for b in bets])
    )

    # CLV %: fraction of bets where signal_odds > closing_odds (we got better odds)
    bets_with_closing = [b for b in bets if b.get("closing_odds") is not None]
    if bets_with_closing:
        clv_pct = sum(
            1 for b in bets_with_closing if b["odds"] > b["closing_odds"]
        ) / len(bets_with_closing)
    else:
        clv_pct = 0.0

    return BacktestMetrics(
        total_bets=total_bets,
        wins=wins,
        losses=losses,
        win_rate=win_rate,
        total_staked=total_staked,
        total_return=total_return,
        profit=profit,
        roi_pct=roi_pct,
        max_drawdown_pct=max_drawdown_pct,
        sharpe_ratio=sharpe_ratio,
        longest_losing_streak=longest_losing_streak,
        longest_winning_streak=longest_winning_streak,
        avg_odds=avg_odds,
        avg_ev=avg_ev,
        brier_score=brier_score,
        clv_pct=clv_pct,
    )
