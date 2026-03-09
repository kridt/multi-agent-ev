import numpy as np


class ModelEnsemble:
    def __init__(self):
        self.models: list = []
        self.weights: list[float] = []

    def add_model(self, model, weight: float = 1.0):
        self.models.append(model)
        self.weights.append(weight)

    def predict_proba(self, *args, **kwargs) -> np.ndarray:
        """Weighted average of model predictions."""
        predictions = []
        for model in self.models:
            predictions.append(model.predict_proba(*args, **kwargs))

        total_weight = sum(self.weights)
        result = np.zeros_like(predictions[0])
        for pred, weight in zip(predictions, self.weights):
            result += pred * (weight / total_weight)
        return result

    def update_weights_from_brier(self, brier_scores: list[float]):
        """Update weights inversely proportional to Brier scores."""
        inv_brier = [1.0 / (bs + 1e-6) for bs in brier_scores]
        total = sum(inv_brier)
        self.weights = [ib / total for ib in inv_brier]
