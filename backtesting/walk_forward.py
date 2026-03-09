"""Walk-forward backtesting with strict temporal separation."""

import numpy as np


class WalkForwardBacktester:
    """Walk-forward backtester that ensures no future data leakage.

    Splits data into rolling train/test windows where training data
    is always strictly before test data temporally.
    """

    def __init__(
        self,
        train_window: int = 200,
        test_window: int = 50,
        step_size: int = 25,
    ):
        self.train_window = train_window
        self.test_window = test_window
        self.step_size = step_size

    def split(
        self, data: list[dict]
    ) -> list[tuple[list[dict], list[dict]]]:
        """Generate walk-forward train/test splits.

        Data must be sorted chronologically.
        Returns list of (train_data, test_data) tuples.

        Strict: training data is ALWAYS before test data temporally.
        """
        splits: list[tuple[list[dict], list[dict]]] = []
        n = len(data)
        start = 0

        while start + self.train_window + self.test_window <= n:
            train = data[start : start + self.train_window]
            test = data[
                start + self.train_window : start + self.train_window + self.test_window
            ]
            splits.append((train, test))
            start += self.step_size

        return splits

    def run(
        self,
        data: list[dict],
        model_factory,
        feature_cols: list[str],
        target_col: str,
        odds_col: str = "odds",
    ) -> list[dict]:
        """Run walk-forward backtest.

        Args:
            data: Chronologically sorted list of data dicts.
            model_factory: Callable that returns a fresh model instance with
                          fit(X, y) and predict_proba(X) methods.
            feature_cols: List of feature column names to extract from data dicts.
            target_col: Name of the target/outcome column.
            odds_col: Name of the odds column (default "odds").

        For each split:
        1. Extract X_train, y_train from train data
        2. Fit model
        3. Predict on test data
        4. Record predictions with actual outcomes and odds

        Returns combined predictions suitable for BetSimulator.
        """
        all_predictions: list[dict] = []

        for train_data, test_data in self.split(data):
            model = model_factory()

            X_train = np.array(
                [[d[c] for c in feature_cols] for d in train_data]
            )
            y_train = np.array([d[target_col] for d in train_data])

            model.fit(X_train, y_train)

            X_test = np.array(
                [[d[c] for c in feature_cols] for d in test_data]
            )
            probs = model.predict_proba(X_test)

            # Handle both 1D array and 2D array (sklearn returns 2D for binary)
            if np.ndim(probs) == 2:
                # Take probability of the positive class (column 1)
                prob_values = probs[:, 1]
            else:
                prob_values = probs

            for i, d in enumerate(test_data):
                all_predictions.append(
                    {
                        "match_id": d.get("match_id", f"match_{i}"),
                        "market": d.get("market", "unknown"),
                        "selection": d.get("selection", "unknown"),
                        "model_prob": float(prob_values[i]),
                        "odds": d[odds_col],
                        "outcome": bool(d[target_col]),
                        "date": d.get("date", ""),
                        "closing_odds": d.get("closing_odds"),
                    }
                )

        return all_predictions
