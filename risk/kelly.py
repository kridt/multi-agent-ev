"""Kelly criterion stake sizing."""


class KellyCalculator:
    """Calculate optimal bet sizing using the Kelly criterion."""

    @staticmethod
    def full_kelly(model_prob: float, decimal_odds: float) -> float:
        """Full Kelly fraction.

        Formula: (model_prob * decimal_odds - 1) / (decimal_odds - 1)
        Returns 0 if negative edge (no bet).
        """
        if decimal_odds <= 1.0:
            return 0.0
        numerator = model_prob * decimal_odds - 1.0
        denominator = decimal_odds - 1.0
        if numerator <= 0:
            return 0.0
        return numerator / denominator

    @staticmethod
    def fractional_kelly(
        model_prob: float, decimal_odds: float, fraction: float = 0.25
    ) -> float:
        """Fractional Kelly (default quarter-Kelly).

        full_kelly * fraction. More conservative than full Kelly.
        """
        full = KellyCalculator.full_kelly(model_prob, decimal_odds)
        return full * fraction

    @staticmethod
    def stake_amount(bankroll: float, kelly_fraction: float) -> float:
        """Convert Kelly fraction to currency amount (DKK)."""
        return bankroll * kelly_fraction
