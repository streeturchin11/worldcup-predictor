"""
Weighted Poisson model for international football.

Attack/defence parameters are estimated via weighted maximum likelihood.
L2 regularisation scaled by 1/n_matches provides automatic shrinkage toward
the global mean for teams with sparse history (D3 in PROGRESS.md).

Home advantage is trained from historical data but applied only to USA,
Canada, and Mexico for WC predictions (D2 in PROGRESS.md).
"""

import numpy as np
import pandas as pd
from scipy.optimize import minimize
from scipy.stats import poisson

# Only these three receive home advantage in WC predictions (D2)
WC_HOME_NATIONS = {"United States", "Canada", "Mexico"}

# Regularisation strength — higher = more shrinkage toward global mean
REGULARISATION = 20.0


def _build_team_index(df: pd.DataFrame) -> list[str]:
    teams = sorted(set(df["home_team"]) | set(df["away_team"]))
    return teams


def _match_counts(df: pd.DataFrame, teams: list[str]) -> np.ndarray:
    counts = np.zeros(len(teams))
    idx = {t: i for i, t in enumerate(teams)}
    for team in df["home_team"]:
        counts[idx[team]] += 1
    for team in df["away_team"]:
        counts[idx[team]] += 1
    return counts


def _unpack(params: np.ndarray, n_teams: int):
    """
    Params layout: [intercept, home_adv, attack x (n-1), defence x (n-1)].
    The last team's attack and defence are derived from the sum-to-zero constraint,
    which makes the model identifiable.
    """
    intercept = params[0]
    home_adv = params[1]
    attack_free = params[2 : 2 + (n_teams - 1)]
    defence_free = params[2 + (n_teams - 1) :]
    attack = np.append(attack_free, -attack_free.sum())
    defence = np.append(defence_free, -defence_free.sum())
    return intercept, home_adv, attack, defence


def _neg_log_likelihood(
    params: np.ndarray,
    home_idx: np.ndarray,
    away_idx: np.ndarray,
    home_goals: np.ndarray,
    away_goals: np.ndarray,
    weights: np.ndarray,
    is_home: np.ndarray,
    match_counts: np.ndarray,
    n_teams: int,
) -> float:
    intercept, home_adv, attack, defence = _unpack(params, n_teams)

    log_lambda_home = intercept + attack[home_idx] + defence[away_idx] + home_adv * is_home
    log_lambda_away = intercept + attack[away_idx] + defence[home_idx]

    lambda_home = np.exp(log_lambda_home)
    lambda_away = np.exp(log_lambda_away)

    ll = weights * (
        home_goals * log_lambda_home - lambda_home
        + away_goals * log_lambda_away - lambda_away
    )

    # L2 regularisation: strength proportional to 1/n_matches (sparse → stronger pull)
    reg = REGULARISATION * np.sum((attack ** 2 + defence ** 2) / np.maximum(match_counts, 1))

    return -ll.sum() + reg


def fit(df: pd.DataFrame) -> dict:
    """Fit the model and return a params dict."""
    teams = _build_team_index(df)
    n_teams = len(teams)
    idx = {t: i for i, t in enumerate(teams)}

    home_idx = np.array([idx[t] for t in df["home_team"]])
    away_idx = np.array([idx[t] for t in df["away_team"]])
    home_goals = df["home_score"].to_numpy()
    away_goals = df["away_score"].to_numpy()
    weights = df["match_weight"].to_numpy()
    is_home = (~df["neutral"].astype(bool)).astype(float).to_numpy()
    match_counts = _match_counts(df, teams)

    # Initial params: [intercept, home_adv, attack x (n-1), defence x (n-1)]
    x0 = np.zeros(2 + 2 * (n_teams - 1))
    x0[0] = np.log(df["home_score"].mean())  # intercept ≈ log(mean goals)

    result = minimize(
        _neg_log_likelihood,
        x0,
        args=(home_idx, away_idx, home_goals, away_goals, weights, is_home, match_counts, n_teams),
        jac=None,
        method="L-BFGS-B",
        options={"maxiter": 5000, "maxfun": 1_000_000, "ftol": 1e-12},
    )

    if not result.success:
        print(f"Warning: optimiser did not fully converge — {result.message}")

    intercept, home_adv, attack, defence = _unpack(result.x, n_teams)

    return {
        "teams": teams,
        "intercept": float(intercept),
        "home_adv": float(home_adv),
        "attack": dict(zip(teams, attack.tolist())),
        "defence": dict(zip(teams, defence.tolist())),
        "converged": result.success,
    }


def predict(
    model: dict,
    home_team: str,
    away_team: str,
    neutral: bool = True,
    max_goals: int = 10,
) -> dict:
    """
    Return scoreline probabilities and summary stats for a single match.

    For WC predictions pass neutral=True for all fixtures except those where
    home_team is USA, Canada, or Mexico playing in their own territory.
    """
    intercept = model["intercept"]
    home_adv = model["home_adv"]

    global_attack = np.mean(list(model["attack"].values()))
    global_defence = np.mean(list(model["defence"].values()))

    atk_home = model["attack"].get(home_team, global_attack)
    def_home = model["defence"].get(home_team, global_defence)
    atk_away = model["attack"].get(away_team, global_attack)
    def_away = model["defence"].get(away_team, global_defence)

    apply_home_adv = (not neutral) or (home_team in WC_HOME_NATIONS)
    ha = home_adv if apply_home_adv else 0.0

    lambda_home = np.exp(intercept + atk_home + def_away + ha)
    lambda_away = np.exp(intercept + atk_away + def_home)

    # Scoreline probability matrix
    home_probs = poisson.pmf(np.arange(max_goals + 1), lambda_home)
    away_probs = poisson.pmf(np.arange(max_goals + 1), lambda_away)
    matrix = np.outer(home_probs, away_probs)

    home_win = float(np.tril(matrix, -1).sum())
    draw     = float(np.trace(matrix))
    away_win = float(np.triu(matrix, 1).sum())

    # Most likely scoreline
    best = np.unravel_index(matrix.argmax(), matrix.shape)

    return {
        "home_team": home_team,
        "away_team": away_team,
        "lambda_home": round(lambda_home, 3),
        "lambda_away": round(lambda_away, 3),
        "home_win": round(home_win, 4),
        "draw":     round(draw, 4),
        "away_win": round(away_win, 4),
        "most_likely_score": f"{best[0]}-{best[1]}",
        "score_matrix": matrix,
    }


if __name__ == "__main__":
    from data_prep import prepare_data

    print("Loading data...")
    df = prepare_data(verbose=False)
    print(f"  {len(df):,} matches")

    print("Fitting model...")
    model = fit(df)
    print(f"  Converged: {model['converged']}")
    print(f"  Intercept: {model['intercept']:.4f}  (mean goals ≈ {np.exp(model['intercept']):.2f})")
    print(f"  Home advantage: {model['home_adv']:.4f}  (+{(np.exp(model['home_adv'])-1)*100:.1f}% goals)")
    print(f"  Teams fitted: {len(model['teams'])}")

    # Spot-check a couple of fixtures
    for home, away in [("Brazil", "Argentina"), ("England", "France"), ("United States", "Mexico")]:
        p = predict(model, home, away, neutral=True)
        print(f"\n  {home} vs {away} (neutral)")
        print(f"    Expected goals: {p['lambda_home']:.2f} – {p['lambda_away']:.2f}")
        print(f"    Win/Draw/Loss:  {p['home_win']:.1%} / {p['draw']:.1%} / {p['away_win']:.1%}")
        print(f"    Most likely:    {p['most_likely_score']}")
