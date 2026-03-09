import numpy as np
from sklearn.metrics import brier_score_loss, log_loss, roc_auc_score


class ModelEvaluator:
    @staticmethod
    def compute_metrics(y_true: np.ndarray, y_pred: np.ndarray, odds: np.ndarray | None = None) -> dict:
        """Compute comprehensive evaluation metrics."""
        metrics = {
            "brier_score": float(brier_score_loss(y_true, y_pred)),
            "log_loss": float(log_loss(y_true, y_pred, labels=[0, 1])),
        }

        try:
            metrics["auc_roc"] = float(roc_auc_score(y_true, y_pred))
        except ValueError:
            metrics["auc_roc"] = None

        # Expected Calibration Error
        from models.calibration import ModelCalibrator
        cal = ModelCalibrator.calibration_curve(y_true, y_pred)
        weighted_errors = []
        total = sum(cal["bin_counts"])
        for pred, true, count in zip(cal["bin_means_pred"], cal["bin_means_true"], cal["bin_counts"]):
            if count > 0:
                weighted_errors.append(abs(pred - true) * count / total)
        metrics["calibration_error"] = sum(weighted_errors)

        # Hypothetical ROI if betting when EV > 0
        if odds is not None:
            ev = y_pred * odds - 1
            bet_mask = ev > 0.03
            if bet_mask.sum() > 0:
                returns = np.where(y_true[bet_mask] == 1, odds[bet_mask] - 1, -1)
                metrics["hypothetical_roi"] = float(returns.mean())
                metrics["n_bets"] = int(bet_mask.sum())

        return metrics
