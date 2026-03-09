import numpy as np
from sklearn.calibration import CalibratedClassifierCV
from sklearn.isotonic import IsotonicRegression


class ModelCalibrator:
    def __init__(self):
        self._calibrator: IsotonicRegression | None = None

    def fit(self, y_true: np.ndarray, y_pred: np.ndarray) -> None:
        """Fit isotonic regression calibrator."""
        self._calibrator = IsotonicRegression(out_of_bounds="clip")
        self._calibrator.fit(y_pred, y_true)

    def calibrate(self, y_pred: np.ndarray) -> np.ndarray:
        """Apply calibration to raw probabilities."""
        if self._calibrator is None:
            return y_pred
        return self._calibrator.predict(y_pred)

    @staticmethod
    def calibration_curve(y_true: np.ndarray, y_pred: np.ndarray, n_bins: int = 10) -> dict:
        """Compute calibration curve data.
        Returns: {"bin_edges": [...], "bin_means_pred": [...], "bin_means_true": [...], "bin_counts": [...]}
        """
        bin_edges = np.linspace(0, 1, n_bins + 1)
        bin_means_pred = []
        bin_means_true = []
        bin_counts = []

        for i in range(n_bins):
            mask = (y_pred >= bin_edges[i]) & (y_pred < bin_edges[i + 1])
            if mask.sum() > 0:
                bin_means_pred.append(y_pred[mask].mean())
                bin_means_true.append(y_true[mask].mean())
                bin_counts.append(int(mask.sum()))
            else:
                bin_means_pred.append((bin_edges[i] + bin_edges[i + 1]) / 2)
                bin_means_true.append(0.0)
                bin_counts.append(0)

        return {
            "bin_edges": bin_edges.tolist(),
            "bin_means_pred": bin_means_pred,
            "bin_means_true": bin_means_true,
            "bin_counts": bin_counts,
        }
