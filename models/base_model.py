from abc import ABC, abstractmethod
import joblib
import numpy as np
from pathlib import Path


class StatisticalModel(ABC):
    def __init__(self, model_type: str, version: str = "v1"):
        self.model_type = model_type
        self.version = version
        self._model = None
        self._is_fitted = False

    @abstractmethod
    def fit(self, X: np.ndarray, y: np.ndarray) -> None: ...

    @abstractmethod
    def predict_proba(self, X: np.ndarray) -> np.ndarray: ...

    def predict_line(self, X: np.ndarray, line: float) -> np.ndarray:
        """P(stat > line). Default: 1 - CDF(line). Override for custom logic."""
        raise NotImplementedError

    def evaluate(self, X_test: np.ndarray, y_test: np.ndarray) -> dict:
        """Return metrics dict: brier_score, log_loss, calibration_error."""
        from models.evaluation import ModelEvaluator
        probs = self.predict_proba(X_test)
        return ModelEvaluator.compute_metrics(y_test, probs)

    def save(self, path: str) -> None:
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        joblib.dump({"model": self._model, "params": self.get_params()}, path)

    def load(self, path: str) -> None:
        data = joblib.load(path)
        self._model = data["model"]
        self._is_fitted = True

    def get_params(self) -> dict:
        return {"model_type": self.model_type, "version": self.version}
