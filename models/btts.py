import numpy as np
from sklearn.linear_model import LogisticRegression

from models.base_model import StatisticalModel


class BTTSModel(StatisticalModel):
    """Logistic regression for Both Teams To Score."""

    def __init__(self, version: str = "v1"):
        super().__init__("btts", version)

    def fit(self, X: np.ndarray, y: np.ndarray) -> None:
        self._model = LogisticRegression(max_iter=1000, random_state=42)
        self._model.fit(X, y)
        self._is_fitted = True

    def predict_proba(self, X: np.ndarray) -> np.ndarray:
        """P(BTTS=Yes). Returns 1D array of probabilities."""
        return self._model.predict_proba(X)[:, 1]
