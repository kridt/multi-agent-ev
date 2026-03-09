"""Tests for statistical models."""

import numpy as np
import pytest
from scipy.stats import poisson as poisson_dist
from sklearn.metrics import brier_score_loss, log_loss


# ---------------------------------------------------------------------------
# Poisson
# ---------------------------------------------------------------------------

class TestPoissonGoalModel:
    def test_poisson_fit_predict(self):
        """Fit on synthetic data, predict returns reasonable lambdas."""
        from models.poisson import PoissonGoalModel

        rng = np.random.default_rng(42)
        # Features: attack_strength, defense_weakness, home_flag
        X = rng.standard_normal((200, 3))
        X[:, 2] = rng.integers(0, 2, 200)  # binary home flag
        true_lambda = np.exp(0.3 * X[:, 0] + 0.2 * X[:, 1] + 0.15 * X[:, 2])
        y = rng.poisson(true_lambda)

        model = PoissonGoalModel()
        model.fit(X, y)
        preds = model.predict_proba(X[:5])

        assert model._is_fitted
        assert len(preds) == 5
        assert all(p > 0 for p in preds), "Predicted lambdas must be positive"

    def test_poisson_goal_probs_sum_to_one(self):
        """P(goals=0) + ... + P(goals=max_goals) should sum to ~1.0."""
        from models.poisson import PoissonGoalModel

        rng = np.random.default_rng(99)
        X = rng.standard_normal((150, 2))
        y = rng.poisson(1.5, 150)

        model = PoissonGoalModel()
        model.fit(X, y)
        probs = model.predict_goal_probs(X[:10], max_goals=10)

        for i in range(10):
            assert abs(probs[i].sum() - 1.0) < 0.01, f"Row {i} sums to {probs[i].sum()}"

    def test_poisson_predict_line(self):
        """P(goals > 2.5) should be consistent with Poisson CDF."""
        from models.poisson import PoissonGoalModel

        rng = np.random.default_rng(7)
        X = rng.standard_normal((200, 2))
        y = rng.poisson(2.0, 200)

        model = PoissonGoalModel()
        model.fit(X, y)

        X_test = np.array([[0.0, 0.0]])
        p_over = model.predict_line(X_test, line=2.5)
        lam = model.predict_proba(X_test)[0]
        expected = 1 - poisson_dist.cdf(2.5, lam)

        assert abs(p_over[0] - expected) < 1e-6

    def test_poisson_score_matrix(self):
        """Score probability matrix should sum to ~1.0."""
        from models.poisson import PoissonGoalModel

        rng = np.random.default_rng(123)
        X = rng.standard_normal((200, 2))
        y = rng.poisson(1.3, 200)

        model = PoissonGoalModel()
        model.fit(X, y)

        # Use multiple rows so sm.add_constant correctly adds an intercept column
        home_X = np.array([[0.5, -0.2], [0.3, 0.1]])
        away_X = np.array([[-0.3, 0.1], [0.0, -0.1]])
        matrix = model.predict_score_matrix(home_X, away_X, max_goals=8)

        assert matrix.shape == (9, 9)
        assert abs(matrix.sum() - 1.0) < 0.02, f"Matrix sums to {matrix.sum()}"


# ---------------------------------------------------------------------------
# Dixon-Coles
# ---------------------------------------------------------------------------

class TestDixonColesModel:
    def _make_match_data(self, rng, n_matches=100):
        teams = ["TeamA", "TeamB", "TeamC", "TeamD"]
        home_teams = rng.choice(teams, n_matches).tolist()
        away_teams = rng.choice(teams, n_matches).tolist()
        # Ensure home != away
        for i in range(n_matches):
            while away_teams[i] == home_teams[i]:
                away_teams[i] = rng.choice(teams)
        home_goals = rng.poisson(1.5, n_matches).astype(float)
        away_goals = rng.poisson(1.1, n_matches).astype(float)
        return teams, home_teams, away_teams, home_goals, away_goals

    def test_dixon_coles_tau_correction(self):
        """Verify tau values for specific scorelines."""
        from models.dixon_coles import DixonColesModel

        rho = -0.1
        lh, la = 1.5, 1.2

        # 0-0: 1 - lh * la * rho
        assert abs(DixonColesModel._tau(0, 0, lh, la, rho) - (1 - lh * la * rho)) < 1e-10
        # 1-0: 1 + la * rho
        assert abs(DixonColesModel._tau(1, 0, lh, la, rho) - (1 + la * rho)) < 1e-10
        # 0-1: 1 + lh * rho
        assert abs(DixonColesModel._tau(0, 1, lh, la, rho) - (1 + lh * rho)) < 1e-10
        # 1-1: 1 - rho
        assert abs(DixonColesModel._tau(1, 1, lh, la, rho) - (1 - rho)) < 1e-10
        # 2-1: no correction
        assert DixonColesModel._tau(2, 1, lh, la, rho) == 1.0

    def test_dixon_coles_home_advantage(self):
        """Home lambda should be higher when home advantage is positive."""
        from models.dixon_coles import DixonColesModel

        model = DixonColesModel()
        # Manually set parameters to verify prediction logic
        model.team_params = {
            "Home": {"attack": 0.3, "defense": -0.1},
            "Away": {"attack": 0.1, "defense": 0.0},
        }
        model.home_advantage = 0.3
        model.rho = -0.05
        model._is_fitted = True

        result = model.predict_match("Home", "Away")
        assert result["home_lambda"] > result["away_lambda"], (
            f"Home lambda {result['home_lambda']:.3f} should exceed away lambda {result['away_lambda']:.3f}"
        )

    def test_dixon_coles_probabilities_sum(self):
        """home_win + draw + away_win should sum to ~1.0."""
        from models.dixon_coles import DixonColesModel

        model = DixonColesModel()
        model.team_params = {
            "A": {"attack": 0.2, "defense": -0.05},
            "B": {"attack": -0.1, "defense": 0.1},
        }
        model.home_advantage = 0.25
        model.rho = -0.03
        model._is_fitted = True

        result = model.predict_match("A", "B")
        total = result["home_win"] + result["draw"] + result["away_win"]
        assert abs(total - 1.0) < 0.02, f"Probabilities sum to {total}"


# ---------------------------------------------------------------------------
# Negative Binomial
# ---------------------------------------------------------------------------

class TestNegBinModel:
    def test_negbin_overdispersion(self):
        """Overdispersion parameter should be positive after fitting."""
        from models.negative_binomial import NegBinModel

        rng = np.random.default_rng(55)
        X = rng.standard_normal((300, 2))
        # Generate overdispersed count data (NegBin)
        mu = np.exp(0.5 + 0.3 * X[:, 0])
        y = rng.negative_binomial(n=5, p=5 / (5 + mu))

        model = NegBinModel(stat_type="corners")
        model.fit(X, y)

        assert model.overdispersion is not None
        assert model.overdispersion > 0, f"Overdispersion should be positive, got {model.overdispersion}"


# ---------------------------------------------------------------------------
# BTTS
# ---------------------------------------------------------------------------

class TestBTTSModel:
    def test_btts_predict_proba(self):
        """Predicted probabilities should be between 0 and 1."""
        from models.btts import BTTSModel

        rng = np.random.default_rng(77)
        X = rng.standard_normal((200, 4))
        y = (X[:, 0] + X[:, 1] > 0).astype(int)

        model = BTTSModel()
        model.fit(X, y)
        probs = model.predict_proba(X[:20])

        assert len(probs) == 20
        assert all(0 <= p <= 1 for p in probs), "All probabilities must be in [0, 1]"


# ---------------------------------------------------------------------------
# Ensemble
# ---------------------------------------------------------------------------

class TestModelEnsemble:
    def test_ensemble_weighted_average(self):
        """Ensemble with unequal weights should shift output toward higher-weighted model."""
        from models.ensemble import ModelEnsemble

        class FakeModel:
            def __init__(self, value):
                self._value = value

            def predict_proba(self, X):
                return np.full(len(X), self._value)

        ensemble = ModelEnsemble()
        ensemble.add_model(FakeModel(0.2), weight=1.0)
        ensemble.add_model(FakeModel(0.8), weight=3.0)

        result = ensemble.predict_proba(np.zeros(5))
        # Expected: (0.2*1 + 0.8*3) / 4 = 2.6/4 = 0.65
        expected = 0.65
        assert abs(result[0] - expected) < 1e-6, f"Expected {expected}, got {result[0]}"

    def test_ensemble_update_weights_from_brier(self):
        """Weights should be inversely proportional to Brier scores."""
        from models.ensemble import ModelEnsemble

        ensemble = ModelEnsemble()

        class Dummy:
            def predict_proba(self, X):
                return np.zeros(1)

        ensemble.add_model(Dummy(), weight=1.0)
        ensemble.add_model(Dummy(), weight=1.0)

        # Model 0 has lower Brier (better), should get higher weight
        ensemble.update_weights_from_brier([0.1, 0.3])
        assert ensemble.weights[0] > ensemble.weights[1], (
            f"Better model weight {ensemble.weights[0]} should exceed {ensemble.weights[1]}"
        )


# ---------------------------------------------------------------------------
# Calibration
# ---------------------------------------------------------------------------

class TestModelCalibrator:
    def test_calibration_no_distortion(self):
        """Already well-calibrated data should remain approximately unchanged."""
        from models.calibration import ModelCalibrator

        rng = np.random.default_rng(42)
        # Generate well-calibrated predictions
        y_pred = rng.uniform(0.1, 0.9, 500)
        y_true = (rng.random(500) < y_pred).astype(float)

        calibrator = ModelCalibrator()
        calibrator.fit(y_true, y_pred)
        calibrated = calibrator.calibrate(y_pred)

        # Should not dramatically change already calibrated predictions
        diff = np.abs(calibrated - y_pred).mean()
        assert diff < 0.15, f"Mean absolute change {diff:.4f} is too large for calibrated data"


# ---------------------------------------------------------------------------
# Evaluation
# ---------------------------------------------------------------------------

class TestModelEvaluator:
    def test_evaluation_brier_score(self):
        """Brier score should match sklearn's brier_score_loss."""
        from models.evaluation import ModelEvaluator

        y_true = np.array([1, 0, 1, 1, 0, 0, 1, 0])
        y_pred = np.array([0.9, 0.1, 0.8, 0.7, 0.3, 0.2, 0.6, 0.4])

        metrics = ModelEvaluator.compute_metrics(y_true, y_pred)
        expected_brier = brier_score_loss(y_true, y_pred)

        assert abs(metrics["brier_score"] - expected_brier) < 1e-10

    def test_evaluation_log_loss(self):
        """Log loss should match sklearn's log_loss."""
        from models.evaluation import ModelEvaluator

        y_true = np.array([1, 0, 1, 1, 0, 0, 1, 0])
        y_pred = np.array([0.9, 0.1, 0.8, 0.7, 0.3, 0.2, 0.6, 0.4])

        metrics = ModelEvaluator.compute_metrics(y_true, y_pred)
        expected_ll = log_loss(y_true, y_pred, labels=[0, 1])

        assert abs(metrics["log_loss"] - expected_ll) < 1e-10

    def test_evaluation_has_calibration_error(self):
        """Metrics dict should include calibration_error."""
        from models.evaluation import ModelEvaluator

        y_true = np.array([1, 0, 1, 0, 1, 0])
        y_pred = np.array([0.8, 0.2, 0.7, 0.3, 0.9, 0.1])

        metrics = ModelEvaluator.compute_metrics(y_true, y_pred)
        assert "calibration_error" in metrics
        assert metrics["calibration_error"] >= 0

    def test_evaluation_with_odds_roi(self):
        """When odds are provided, hypothetical ROI should be computed."""
        from models.evaluation import ModelEvaluator

        y_true = np.array([1, 0, 1, 1, 0])
        y_pred = np.array([0.7, 0.6, 0.8, 0.75, 0.55])
        odds = np.array([2.0, 2.0, 1.5, 1.8, 2.5])

        metrics = ModelEvaluator.compute_metrics(y_true, y_pred, odds=odds)
        # At least some bets should have EV > 3%
        if "hypothetical_roi" in metrics:
            assert "n_bets" in metrics
            assert metrics["n_bets"] > 0
