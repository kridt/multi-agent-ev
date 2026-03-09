import numpy as np
from scipy.optimize import minimize
from scipy.stats import poisson as poisson_dist

from models.base_model import StatisticalModel


class DixonColesModel(StatisticalModel):
    """Dixon-Coles bivariate Poisson model for football scores."""

    def __init__(self, version: str = "v1"):
        super().__init__("dixon_coles", version)
        self.team_params: dict[str, dict[str, float]] = {}  # {team: {attack, defense}}
        self.home_advantage: float = 0.0
        self.rho: float = 0.0  # bivariate correction

    @staticmethod
    def _tau(x: int, y: int, lambda_home: float, lambda_away: float, rho: float) -> float:
        """Dixon-Coles correction factor for low-scoring games."""
        if x == 0 and y == 0:
            return 1 - lambda_home * lambda_away * rho
        elif x == 0 and y == 1:
            return 1 + lambda_home * rho
        elif x == 1 and y == 0:
            return 1 + lambda_away * rho
        elif x == 1 and y == 1:
            return 1 - rho
        return 1.0

    def _log_likelihood(self, params: np.ndarray, teams: list[str], home_teams: np.ndarray,
                        away_teams: np.ndarray, home_goals: np.ndarray, away_goals: np.ndarray,
                        weights: np.ndarray) -> float:
        """Negative log-likelihood for optimization."""
        n_teams = len(teams)
        attacks = dict(zip(teams, params[:n_teams]))
        defenses = dict(zip(teams, params[n_teams:2 * n_teams]))
        home_adv = params[2 * n_teams]
        rho = params[2 * n_teams + 1]

        log_lik = 0.0
        for i in range(len(home_goals)):
            ht, at = home_teams[i], away_teams[i]
            lambda_h = np.exp(attacks[ht] + defenses[at] + home_adv)
            lambda_a = np.exp(attacks[at] + defenses[ht])
            hg, ag = int(home_goals[i]), int(away_goals[i])

            p = poisson_dist.pmf(hg, lambda_h) * poisson_dist.pmf(ag, lambda_a)
            tau = self._tau(hg, ag, lambda_h, lambda_a, rho)
            p *= tau
            if p > 0:
                log_lik += weights[i] * np.log(p)

        return -log_lik  # minimize negative

    def fit(self, X: np.ndarray, y: np.ndarray, teams: list[str] | None = None,
            home_teams: list[str] | None = None, away_teams: list[str] | None = None,
            home_goals: np.ndarray | None = None, away_goals: np.ndarray | None = None,
            half_life: int = 30) -> None:
        """Fit via MLE. Pass match data directly.
        X is ignored (use named params instead). y is ignored.
        """
        if home_teams is None or away_teams is None or home_goals is None or away_goals is None:
            raise ValueError("Must provide home_teams, away_teams, home_goals, away_goals")

        unique_teams = teams or sorted(set(list(home_teams) + list(away_teams)))
        n_teams = len(unique_teams)

        # Time-decay weights
        n_matches = len(home_goals)
        weights = np.array([np.exp(-i / half_life) for i in range(n_matches - 1, -1, -1)])

        # Initial params: attacks=0, defenses=0, home_adv=0.25, rho=-0.05
        x0 = np.zeros(2 * n_teams + 2)
        x0[2 * n_teams] = 0.25
        x0[2 * n_teams + 1] = -0.05

        # Constraint: sum of attacks = 0 (identifiability)
        constraints = [{"type": "eq", "fun": lambda p: sum(p[:n_teams])}]

        result = minimize(
            self._log_likelihood,
            x0,
            args=(unique_teams, np.array(home_teams), np.array(away_teams), home_goals, away_goals, weights),
            method="SLSQP",
            constraints=constraints,
            options={"maxiter": 500},
        )

        self.team_params = {
            team: {"attack": result.x[i], "defense": result.x[n_teams + i]}
            for i, team in enumerate(unique_teams)
        }
        self.home_advantage = result.x[2 * n_teams]
        self.rho = result.x[2 * n_teams + 1]
        self._model = result
        self._is_fitted = True

    def predict_proba(self, X: np.ndarray) -> np.ndarray:
        """Not used directly. Use predict_match instead."""
        return np.array([])

    def predict_match(self, home_team: str, away_team: str) -> dict:
        """Predict match outcome probabilities.
        Returns: {"home_win": p, "draw": p, "away_win": p,
                  "home_lambda": float, "away_lambda": float,
                  "score_matrix": np.ndarray}
        """
        h_att = self.team_params.get(home_team, {}).get("attack", 0)
        a_def = self.team_params.get(away_team, {}).get("defense", 0)
        a_att = self.team_params.get(away_team, {}).get("attack", 0)
        h_def = self.team_params.get(home_team, {}).get("defense", 0)

        lambda_h = np.exp(h_att + a_def + self.home_advantage)
        lambda_a = np.exp(a_att + h_def)

        max_goals = 7
        matrix = np.zeros((max_goals + 1, max_goals + 1))
        for h in range(max_goals + 1):
            for a in range(max_goals + 1):
                p = poisson_dist.pmf(h, lambda_h) * poisson_dist.pmf(a, lambda_a)
                p *= self._tau(h, a, lambda_h, lambda_a, self.rho)
                matrix[h, a] = p

        home_win = sum(matrix[h, a] for h in range(max_goals + 1) for a in range(h))
        draw = sum(matrix[h, h] for h in range(max_goals + 1))
        away_win = sum(matrix[h, a] for h in range(max_goals + 1) for a in range(h + 1, max_goals + 1))

        return {
            "home_win": home_win, "draw": draw, "away_win": away_win,
            "home_lambda": lambda_h, "away_lambda": lambda_a,
            "score_matrix": matrix,
        }

    def predict_goals_ou(self, home_team: str, away_team: str, line: float) -> float:
        """P(total goals > line)."""
        result = self.predict_match(home_team, away_team)
        matrix = result["score_matrix"]
        return sum(matrix[h, a] for h in range(matrix.shape[0]) for a in range(matrix.shape[1]) if h + a > line)

    def predict_btts(self, home_team: str, away_team: str) -> float:
        """P(both teams to score)."""
        result = self.predict_match(home_team, away_team)
        matrix = result["score_matrix"]
        return 1 - sum(matrix[0, :]) - sum(matrix[:, 0]) + matrix[0, 0]
