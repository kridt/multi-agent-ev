"""Player prop models with stat-based features.

Each model extends either NegBinModel (for count over/under markets) or
StatisticalModel via LogisticRegression (for binary yes/no markets).

Feature vectors are built from the pipeline output dict produced by
FeaturePipeline.build_player_features, which has the structure:

    {
        "player_id": str,
        "rolling": {
            "<stat>": {
                "w3": {"mean": float|None, "std": float|None,
                        "median": float|None, "trend": float|None},
                "w5": {...},
                "w10": {...},
            },
            ...
        },
        "opponent_adjusted": {"<stat>": float, ...},
        "consistency": {"<stat>": {"cv": float|None, "category": str, ...}, ...},
    }

Per-90 normalisation has already been applied by the pipeline before these
feature builders are called.
"""

import numpy as np
from sklearn.linear_model import LogisticRegression

from models.base_model import StatisticalModel
from models.negative_binomial import NegBinModel


class PlayerPropModel(NegBinModel):
    """NegBin model for player prop over/under markets.

    Works with per-90 normalized stats. Features expected:
    - Rolling mean (w3, w5, w10) of the stat
    - Opponent-adjusted mean
    - Consistency CV
    - Minutes played trend
    - Home/away indicator
    """

    def __init__(self, stat: str, version: str = "v1"):
        super().__init__(stat_type=stat, version=version)
        self.stat = stat

    @staticmethod
    def build_feature_vector(
        player_features: dict, stat: str, is_home: bool
    ) -> np.ndarray:
        """Build a feature vector from pipeline output for this stat.

        Returns array of:
            [w3_mean, w5_mean, w10_mean, w5_std, w5_trend,
             opp_adjusted, consistency_cv, is_home]

        Missing values (None from insufficient data windows) fall back to 0.0.
        consistency_cv falls back to 0.5 (neutral) when not available.
        """
        rolling = player_features.get("rolling", {}).get(stat, {})
        adjusted = player_features.get("opponent_adjusted", {})
        consistency = player_features.get("consistency", {})

        w3 = rolling.get("w3", {})
        w5 = rolling.get("w5", {})
        w10 = rolling.get("w10", {})

        return np.array([
            w3.get("mean") or 0.0,
            w5.get("mean") or 0.0,
            w10.get("mean") or 0.0,
            w5.get("std") or 0.0,
            w5.get("trend") or 0.0,
            adjusted.get(stat, 0.0),
            (consistency.get(stat) or {}).get("cv") or 0.5,
            1.0 if is_home else 0.0,
        ])


class PlayerShotsModel(PlayerPropModel):
    """Player total shots over/under."""

    def __init__(self, version: str = "v1"):
        super().__init__(stat="shots", version=version)


class PlayerShotsOnTargetModel(PlayerPropModel):
    """Player shots on target over/under."""

    def __init__(self, version: str = "v1"):
        super().__init__(stat="shots_on_target", version=version)


class PlayerTacklesModel(PlayerPropModel):
    """Player tackles over/under."""

    def __init__(self, version: str = "v1"):
        super().__init__(stat="tackles", version=version)


class PlayerPassesModel(PlayerPropModel):
    """Player passes over/under."""

    def __init__(self, version: str = "v1"):
        super().__init__(stat="passes", version=version)


class PlayerFoulsModel(PlayerPropModel):
    """Player fouls committed over/under."""

    def __init__(self, version: str = "v1"):
        super().__init__(stat="fouls_committed", version=version)


class PlayerOffsidesModel(PlayerPropModel):
    """Player offsides over/under."""

    def __init__(self, version: str = "v1"):
        super().__init__(stat="offsides", version=version)


class AnytimeGoalscorerModel(StatisticalModel):
    """Logistic regression for anytime goalscorer market.

    Binary outcome: did this player score at least one goal?

    Features:
    - Goals per 90 (w3, w5, w10 rolling)
    - Shots per 90 (w5 rolling)
    - Shots on target per 90 (w5 rolling)
    - Opponent-adjusted goals rate
    - Consistency CV for goals
    - Is home indicator

    class_weight="balanced" is used because goalscorer events are rare
    (typical base rate ~10-25%), making balanced weighting necessary
    to avoid the model collapsing to the majority class.
    """

    def __init__(self, version: str = "v1"):
        super().__init__("anytime_goalscorer", version)

    def fit(self, X: np.ndarray, y: np.ndarray) -> None:
        self._model = LogisticRegression(
            max_iter=1000, random_state=42, class_weight="balanced"
        )
        self._model.fit(X, y)
        self._is_fitted = True

    def predict_proba(self, X: np.ndarray) -> np.ndarray:
        return self._model.predict_proba(X)[:, 1]

    @staticmethod
    def build_feature_vector(player_features: dict, is_home: bool) -> np.ndarray:
        """Build feature vector for goalscorer prediction.

        Returns array of:
            [goals_w3, goals_w5, goals_w10,
             shots_w5, shots_on_target_w5,
             opp_adj_goals, consistency_cv, is_home]

        Missing values fall back to 0.0; consistency_cv falls back to 0.5.
        """
        rolling = player_features.get("rolling", {})
        adjusted = player_features.get("opponent_adjusted", {})
        consistency = player_features.get("consistency", {})

        goals_rolling = rolling.get("goals", {})
        shots_rolling = rolling.get("shots", {})
        sot_rolling = rolling.get("shots_on_target", {})

        return np.array([
            (goals_rolling.get("w3") or {}).get("mean") or 0.0,
            (goals_rolling.get("w5") or {}).get("mean") or 0.0,
            (goals_rolling.get("w10") or {}).get("mean") or 0.0,
            (shots_rolling.get("w5") or {}).get("mean") or 0.0,
            (sot_rolling.get("w5") or {}).get("mean") or 0.0,
            adjusted.get("goals", 0.0),
            (consistency.get("goals") or {}).get("cv") or 0.5,
            1.0 if is_home else 0.0,
        ])


class PlayerCardsModel(StatisticalModel):
    """Logistic regression for player to receive a card.

    Binary outcome: did this player receive at least one yellow card?

    Features:
    - Yellow cards per 90 (w3, w5, w10)
    - Fouls committed per 90 (w5)
    - Tackles per 90 (w5)
    - Opponent-adjusted fouls rate
    - Consistency CV for yellow cards
    - Is home indicator

    class_weight="balanced" is used because card events are relatively rare.
    """

    def __init__(self, version: str = "v1"):
        super().__init__("player_cards", version)

    def fit(self, X: np.ndarray, y: np.ndarray) -> None:
        self._model = LogisticRegression(
            max_iter=1000, random_state=42, class_weight="balanced"
        )
        self._model.fit(X, y)
        self._is_fitted = True

    def predict_proba(self, X: np.ndarray) -> np.ndarray:
        return self._model.predict_proba(X)[:, 1]

    @staticmethod
    def build_feature_vector(player_features: dict, is_home: bool) -> np.ndarray:
        """Build feature vector for cards prediction.

        Returns array of:
            [cards_w3, cards_w5, cards_w10,
             fouls_w5, tackles_w5,
             opp_adj_fouls, consistency_cv, is_home]

        Missing values fall back to 0.0; consistency_cv falls back to 0.5.
        """
        rolling = player_features.get("rolling", {})
        adjusted = player_features.get("opponent_adjusted", {})
        consistency = player_features.get("consistency", {})

        cards_rolling = rolling.get("yellow_cards", {})
        fouls_rolling = rolling.get("fouls_committed", {})
        tackles_rolling = rolling.get("tackles", {})

        return np.array([
            (cards_rolling.get("w3") or {}).get("mean") or 0.0,
            (cards_rolling.get("w5") or {}).get("mean") or 0.0,
            (cards_rolling.get("w10") or {}).get("mean") or 0.0,
            (fouls_rolling.get("w5") or {}).get("mean") or 0.0,
            (tackles_rolling.get("w5") or {}).get("mean") or 0.0,
            adjusted.get("fouls_committed", 0.0),
            (consistency.get("yellow_cards") or {}).get("cv") or 0.5,
            1.0 if is_home else 0.0,
        ])
