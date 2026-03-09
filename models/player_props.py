import numpy as np
from sklearn.linear_model import LogisticRegression

from models.base_model import StatisticalModel
from models.negative_binomial import NegBinModel


class PlayerPropModel(NegBinModel):
    """NegBin model for player prop over/under markets."""

    def __init__(self, stat: str, version: str = "v1"):
        super().__init__(stat_type=stat, version=version)
        self.stat = stat


class AnytimeGoalscorerModel(StatisticalModel):
    """Logistic regression for anytime goalscorer market."""

    def __init__(self, version: str = "v1"):
        super().__init__("anytime_goalscorer", version)

    def fit(self, X: np.ndarray, y: np.ndarray) -> None:
        self._model = LogisticRegression(max_iter=1000, random_state=42)
        self._model.fit(X, y)
        self._is_fitted = True

    def predict_proba(self, X: np.ndarray) -> np.ndarray:
        return self._model.predict_proba(X)[:, 1]


class PlayerCardsModel(StatisticalModel):
    """Logistic regression for player cards market."""

    def __init__(self, version: str = "v1"):
        super().__init__("player_cards", version)

    def fit(self, X: np.ndarray, y: np.ndarray) -> None:
        self._model = LogisticRegression(max_iter=1000, random_state=42)
        self._model.fit(X, y)
        self._is_fitted = True

    def predict_proba(self, X: np.ndarray) -> np.ndarray:
        return self._model.predict_proba(X)[:, 1]
