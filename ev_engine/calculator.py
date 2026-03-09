"""Core EV calculation utilities."""


class EVCalculator:
    @staticmethod
    def calculate_ev(model_prob: float, decimal_odds: float) -> float:
        """EV = (model_prob * decimal_odds) - 1

        Positive EV means expected profit per unit staked.
        E.g., model_prob=0.55, odds=2.00 -> (0.55 * 2.00) - 1 = 0.10 (10% EV).
        """
        return (model_prob * decimal_odds) - 1

    @staticmethod
    def calculate_implied_prob(decimal_odds: float) -> float:
        """Convert decimal odds to implied probability.

        implied_prob = 1 / decimal_odds
        """
        if decimal_odds <= 0:
            return 0.0
        return 1.0 / decimal_odds

    @staticmethod
    def calculate_margin(odds_list: list[float]) -> float:
        """Calculate bookmaker margin (overround) from a set of odds.

        Margin = sum of implied probabilities - 1.
        E.g., for a fair 2-way market: [2.00, 2.00] -> 0.5 + 0.5 - 1 = 0.0
        E.g., with margin: [1.90, 1.90] -> 0.526 + 0.526 - 1 = 0.053
        """
        if not odds_list:
            return 0.0
        return sum(1.0 / o for o in odds_list if o > 0) - 1.0

    @staticmethod
    def meets_threshold(ev: float, threshold: float = 0.03) -> bool:
        """True if EV >= threshold (default 3%)."""
        return ev >= threshold

    @staticmethod
    def edge(model_prob: float, implied_prob: float) -> float:
        """Raw edge = model probability - implied probability."""
        return model_prob - implied_prob
