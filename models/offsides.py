"""Team offsides model using Negative Binomial regression.

Offsides are overdispersed count data — teams with aggressive
attacking play (high pressing, through balls) tend to have
higher and more variable offside counts.
"""

from models.negative_binomial import NegBinModel


class TeamOffsidesModel(NegBinModel):
    """Negative Binomial model for team offsides over/under.

    Offsides are overdispersed count data — teams with aggressive
    attacking play (high pressing, through balls) tend to have
    higher and more variable offside counts.

    Features expected:
    - Team's rolling offsides mean (w3, w5, w10)
    - Opponent's defensive line height (proxy: opponent offsides conceded)
    - Team's shots and passes rate (attacking intent proxy)
    - Home/away indicator
    """

    def __init__(self, version: str = "v1"):
        super().__init__(stat_type="offsides", version=version)

    @staticmethod
    def build_feature_vector(team_features: dict, is_home: bool) -> list[float]:
        """Build feature vector from pipeline output.

        Returns: [offsides_w3, offsides_w5, offsides_w10, offsides_w5_std,
                  shots_w5, passes_w5, opp_adj_offsides, consistency_cv, is_home]

        Missing keys default to 0.0 (for consistency_cv defaults to 0.5, which
        represents moderate uncertainty when no data is available).
        """
        rolling = team_features.get("rolling", {})
        adjusted = team_features.get("opponent_adjusted", {})
        consistency = team_features.get("consistency", {})

        off_rolling = rolling.get("offsides", {})
        shots_rolling = rolling.get("shots", {})
        passes_rolling = rolling.get("passes", {})

        return [
            off_rolling.get("w3", {}).get("mean", 0.0),
            off_rolling.get("w5", {}).get("mean", 0.0),
            off_rolling.get("w10", {}).get("mean", 0.0),
            off_rolling.get("w5", {}).get("std", 0.0),
            shots_rolling.get("w5", {}).get("mean", 0.0),
            passes_rolling.get("w5", {}).get("mean", 0.0),
            adjusted.get("offsides", 0.0),
            consistency.get("offsides", {}).get("cv", 0.5),
            1.0 if is_home else 0.0,
        ]
