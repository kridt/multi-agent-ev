import numpy as np
import statsmodels.api as sm
from scipy.stats import nbinom

from models.base_model import StatisticalModel


class NegBinModel(StatisticalModel):
    """Negative Binomial regression for overdispersed count data (corners, shots, tackles)."""

    def __init__(self, stat_type: str = "corners", version: str = "v1"):
        super().__init__(f"negbin_{stat_type}", version)
        self.stat_type = stat_type

    def fit(self, X: np.ndarray, y: np.ndarray) -> None:
        X_const = sm.add_constant(X)
        self._model = sm.GLM(y, X_const, family=sm.families.NegativeBinomial()).fit()
        self._is_fitted = True

    def predict_proba(self, X: np.ndarray) -> np.ndarray:
        """Predict expected count (mu)."""
        X_const = sm.add_constant(X)
        return self._model.predict(X_const)

    def predict_line(self, X: np.ndarray, line: float) -> np.ndarray:
        """P(count > line)."""
        mus = self.predict_proba(X)
        alpha = self._model.scale  # overdispersion parameter
        results = []
        for mu in mus:
            n = 1.0 / alpha if alpha > 0 else 1e6
            p = n / (n + mu)
            results.append(1 - nbinom.cdf(int(line), n, p))
        return np.array(results)

    @property
    def overdispersion(self) -> float | None:
        if self._is_fitted:
            return self._model.scale
        return None
