import numpy as np
import statsmodels.api as sm
from scipy.stats import poisson as poisson_dist

from models.base_model import StatisticalModel


class PoissonGoalModel(StatisticalModel):
    """Poisson regression for team goal prediction."""

    def __init__(self, version: str = "v1"):
        super().__init__("poisson", version)

    def fit(self, X: np.ndarray, y: np.ndarray) -> None:
        """Fit Poisson GLM. X = features (attack, defense, home), y = goals."""
        X_const = sm.add_constant(X)
        self._model = sm.GLM(y, X_const, family=sm.families.Poisson()).fit()
        self._is_fitted = True

    def predict_proba(self, X: np.ndarray) -> np.ndarray:
        """Predict expected goals (lambda)."""
        X_const = sm.add_constant(X)
        return self._model.predict(X_const)

    def predict_goal_probs(self, X: np.ndarray, max_goals: int = 7) -> np.ndarray:
        """Return P(goals=k) for k=0..max_goals. Shape: (n_samples, max_goals+1)"""
        lambdas = self.predict_proba(X)
        probs = np.zeros((len(lambdas), max_goals + 1))
        for i, lam in enumerate(lambdas):
            for k in range(max_goals + 1):
                probs[i, k] = poisson_dist.pmf(k, lam)
        return probs

    def predict_line(self, X: np.ndarray, line: float) -> np.ndarray:
        """P(goals > line) for over/under markets."""
        lambdas = self.predict_proba(X)
        return np.array([1 - poisson_dist.cdf(line, lam) for lam in lambdas])

    def predict_score_matrix(self, home_X: np.ndarray, away_X: np.ndarray, max_goals: int = 6) -> np.ndarray:
        """Return (max_goals+1 x max_goals+1) score probability matrix.
        Assumes independence between home and away goals.
        """
        home_lambda = self.predict_proba(home_X)[0]
        away_lambda = self.predict_proba(away_X)[0]
        matrix = np.zeros((max_goals + 1, max_goals + 1))
        for h in range(max_goals + 1):
            for a in range(max_goals + 1):
                matrix[h, a] = poisson_dist.pmf(h, home_lambda) * poisson_dist.pmf(a, away_lambda)
        return matrix

    def get_params(self) -> dict:
        params = super().get_params()
        if self._is_fitted:
            params["coefficients"] = self._model.params.tolist()
            params["aic"] = self._model.aic
        return params
