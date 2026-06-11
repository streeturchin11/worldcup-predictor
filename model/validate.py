"""
RPS validation for the Poisson match predictor.

Split: train on pre-2024, hold out 2024 onward.
Baseline: naive model using overall historical win/draw/loss frequencies
          from the training set (no team-level information).

RPS formula (3 outcomes):
    RPS = 0.5 * [(p_win - o1)^2 + (p_win + p_draw - o1 - o2)^2]
where o1 = 1 if home win, o2 = 1 if draw.
"""

import sys
from pathlib import Path

import numpy as np
import pandas as pd

# Allow imports from the model/ directory when run directly
sys.path.insert(0, str(Path(__file__).parent))

from data_prep import NAME_ALIASES, COMPETITION_WEIGHTS, DEFAULT_WEIGHT
from poisson_model import fit, predict, WC_HOME_NATIONS

DATA_DIR = Path(__file__).parent.parent / "data"
HOLDOUT_FROM = 2024


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def outcome(row: pd.Series) -> str:
    if row["home_score"] > row["away_score"]:
        return "home_win"
    elif row["home_score"] == row["away_score"]:
        return "draw"
    else:
        return "away_win"


def rps(p_home_win: float, p_draw: float, p_away_win: float, result: str) -> float:
    """
    Ranked Probability Score for a single three-outcome match.
    Lower is better.
    """
    o1 = 1.0 if result == "home_win" else 0.0
    o2 = 1.0 if result == "draw"     else 0.0
    cum_pred_1 = p_home_win
    cum_pred_2 = p_home_win + p_draw
    cum_obs_1  = o1
    cum_obs_2  = o1 + o2
    return 0.5 * ((cum_pred_1 - cum_obs_1) ** 2 + (cum_pred_2 - cum_obs_2) ** 2)


# ---------------------------------------------------------------------------
# Data loading (mirrors data_prep.py logic, but date-split aware)
# ---------------------------------------------------------------------------

def load_and_split() -> tuple[pd.DataFrame, pd.DataFrame]:
    df = pd.read_csv(DATA_DIR / "intl_results.csv", parse_dates=["date"])
    df = df[df["date"].dt.year >= 2014].copy()
    df = df.dropna(subset=["home_score", "away_score"])
    df["home_team"] = df["home_team"].replace(NAME_ALIASES)
    df["away_team"] = df["away_team"].replace(NAME_ALIASES)

    train = df[df["date"].dt.year < HOLDOUT_FROM].copy()
    holdout = df[df["date"].dt.year >= HOLDOUT_FROM].copy()
    return train, holdout


def add_weights(df: pd.DataFrame, today: pd.Timestamp) -> pd.DataFrame:
    from datetime import date
    import numpy as np

    age_days = (today.date() - df["date"].dt.date).apply(lambda d: d.days)
    df = df.copy()
    df["age_years"] = age_days / 365.25
    df["time_decay"] = np.exp(-0.1 * df["age_years"])
    df["competition_weight"] = df["tournament"].map(COMPETITION_WEIGHTS).fillna(DEFAULT_WEIGHT)
    df["match_weight"] = df["competition_weight"] * df["time_decay"]
    return df


# ---------------------------------------------------------------------------
# Baseline: historical win/draw/loss frequencies from training set
# ---------------------------------------------------------------------------

def baseline_probs(train: pd.DataFrame) -> tuple[float, float, float]:
    results = train.apply(outcome, axis=1)
    n = len(results)
    p_home = (results == "home_win").sum() / n
    p_draw  = (results == "draw").sum()    / n
    p_away  = (results == "away_win").sum() / n
    return float(p_home), float(p_draw), float(p_away)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    print("Loading and splitting data...")
    train_raw, holdout = load_and_split()
    print(f"  Training matches (2014–2023): {len(train_raw):,}")
    print(f"  Held-out matches (2024+):     {len(holdout):,}")

    # Weights anchored to the last day of the training set so they're
    # consistent at fit time (avoids leaking future recency info)
    cutoff = pd.Timestamp(f"{HOLDOUT_FROM - 1}-12-31")
    train = add_weights(train_raw, today=cutoff)

    print("\nFitting model on training set...")
    model = fit(train)
    print(f"  Converged: {model['converged']}")
    print(f"  Home advantage: {model['home_adv']:.4f}  "
          f"(+{(np.exp(model['home_adv']) - 1) * 100:.1f}% goals)")

    # Baseline probs from training outcomes
    bl_home, bl_draw, bl_away = baseline_probs(train_raw)
    print(f"\nBaseline (training frequencies): "
          f"H {bl_home:.1%}  D {bl_draw:.1%}  A {bl_away:.1%}")

    # Evaluate on held-out set
    print("\nEvaluating held-out matches...")
    model_rps_scores    = []
    baseline_rps_scores = []
    skipped = 0

    for _, row in holdout.iterrows():
        home, away = row["home_team"], row["away_team"]
        neutral = bool(row["neutral"])
        actual = outcome(row)

        # Skip if either team was never seen in training (too sparse to trust)
        if home not in model["attack"] or away not in model["attack"]:
            skipped += 1
            continue

        pred = predict(model, home, away, neutral=neutral)

        model_rps_scores.append(
            rps(pred["home_win"], pred["draw"], pred["away_win"], actual)
        )
        baseline_rps_scores.append(
            rps(bl_home, bl_draw, bl_away, actual)
        )

    n_evaluated = len(model_rps_scores)
    mean_model_rps    = float(np.mean(model_rps_scores))
    mean_baseline_rps = float(np.mean(baseline_rps_scores))
    improvement_pct   = (mean_baseline_rps - mean_model_rps) / mean_baseline_rps * 100

    print(f"\n{'─' * 45}")
    print(f"  Held-out matches evaluated: {n_evaluated:,}")
    if skipped:
        print(f"  Skipped (unseen teams):     {skipped:,}")
    print(f"{'─' * 45}")
    print(f"  Model RPS:    {mean_model_rps:.4f}")
    print(f"  Baseline RPS: {mean_baseline_rps:.4f}")
    print(f"{'─' * 45}")
    if mean_model_rps < mean_baseline_rps:
        print(f"  ✓ Model beats baseline by {improvement_pct:.1f}%")
    else:
        print(f"  ✗ Model does NOT beat baseline "
              f"(worse by {-improvement_pct:.1f}%)")
    print(f"{'─' * 45}\n")

    # Per-tournament breakdown (useful for spotting where the model struggles)
    holdout_eval = holdout.copy().reset_index(drop=True)
    holdout_eval = holdout_eval[
        holdout_eval["home_team"].isin(model["attack"]) &
        holdout_eval["away_team"].isin(model["attack"])
    ].copy()
    holdout_eval["model_rps"]    = model_rps_scores
    holdout_eval["baseline_rps"] = baseline_rps_scores

    print("Mean RPS by tournament (model vs baseline):")
    breakdown = (
        holdout_eval.groupby("tournament")[["model_rps", "baseline_rps"]]
        .agg(["mean", "count"])
    )
    breakdown.columns = ["model_rps", "n", "baseline_rps", "_n"]
    breakdown = breakdown.drop(columns=["_n"])
    breakdown = breakdown.sort_values("n", ascending=False)
    breakdown["beats_baseline"] = breakdown["model_rps"] < breakdown["baseline_rps"]
    print(breakdown[breakdown["n"] >= 5].to_string())

    # -----------------------------------------------------------------------
    # Tier-bias analysis
    # -----------------------------------------------------------------------
    print(f"\n{'═' * 55}")
    print("  TIER-BIAS ANALYSIS")
    print(f"{'═' * 55}")

    # --- 1. Composite strength score and quintile tiers ---
    teams_fitted = model["teams"]
    strength = {
        t: model["attack"][t] - model["defence"][t]
        for t in teams_fitted
    }
    strength_series = pd.Series(strength, name="strength")

    # pd.qcut with q=5 gives quintile labels 0–4; add 1 for human-readable 1–5
    tier_series = pd.qcut(strength_series, q=5, labels=False).astype(int) + 1
    tier_map = tier_series.to_dict()  # team -> tier (1=weakest, 5=strongest)

    print(f"\n  Strength quintile boundaries:")
    for q, label in enumerate(["Q1 (weakest)", "Q2", "Q3", "Q4", "Q5 (strongest)"], 1):
        members = [t for t, tier in tier_map.items() if tier == q]
        lo = min(strength[t] for t in members)
        hi = max(strength[t] for t in members)
        print(f"    {label}: {len(members):3d} teams  strength [{lo:+.3f}, {hi:+.3f}]")

    # --- 2. Label each held-out match ---
    def match_type(home_tier: int, away_tier: int) -> str:
        gap = abs(home_tier - away_tier)
        hi  = max(home_tier, away_tier)
        lo  = min(home_tier, away_tier)
        if hi >= 4 and lo >= 4:
            return "elite vs elite"
        if gap >= 3:
            return "elite vs minnow"
        if hi >= 4 and 2 <= lo <= 3:
            return "elite vs mid"
        if 2 <= hi <= 3 and 2 <= lo <= 3:
            return "mid vs mid"
        if 2 <= hi <= 3 and lo == 1:
            return "mid vs minnow"
        if hi == 1 and lo == 1:
            return "minnow vs minnow"
        return "other"

    # Re-run predictions to collect per-match tier data and p_home_win
    rows = []
    for _, row in holdout.iterrows():
        home, away = row["home_team"], row["away_team"]
        if home not in model["attack"] or away not in model["attack"]:
            continue
        neutral = bool(row["neutral"])
        actual  = outcome(row)
        pred    = predict(model, home, away, neutral=neutral)

        ht = tier_map.get(home)
        at = tier_map.get(away)
        if ht is None or at is None:
            continue

        rows.append({
            "home_tier":      ht,
            "away_tier":      at,
            "tier_gap":       abs(ht - at),
            "avg_tier":       (ht + at) / 2,
            "match_type":     match_type(ht, at),
            "model_rps":      rps(pred["home_win"], pred["draw"], pred["away_win"], actual),
            "baseline_rps":   rps(bl_home, bl_draw, bl_away, actual),
            "pred_home_win":  pred["home_win"],
            "actual_home_win": 1.0 if actual == "home_win" else 0.0,
        })

    tier_df = pd.DataFrame(rows)

    def summary_table(df: pd.DataFrame, group_col: str, sort_col: str, ascending: bool) -> pd.DataFrame:
        grp = df.groupby(group_col)
        tbl = pd.DataFrame({
            "n":              grp["model_rps"].count(),
            "model_rps":      grp["model_rps"].mean(),
            "baseline_rps":   grp["baseline_rps"].mean(),
            "pred_hw":        grp["pred_home_win"].mean(),
            "actual_hw":      grp["actual_home_win"].mean(),
        })
        tbl["rps_diff_%"]   = (tbl["baseline_rps"] - tbl["model_rps"]) / tbl["baseline_rps"] * 100
        tbl["hw_bias"]      = tbl["pred_hw"] - tbl["actual_hw"]   # + = over-predicts home wins
        return tbl.sort_values(sort_col, ascending=ascending)

    # --- 3. Table 1: RPS by tier gap ---
    print(f"\n  Table 1 — RPS by tier gap (0 = evenly matched, 4 = maximum mismatch)")
    print(f"  {'gap':>4}  {'n':>5}  {'model RPS':>9}  {'base RPS':>8}  {'diff %':>7}  "
          f"{'pred HW':>8}  {'act HW':>7}  {'HW bias':>8}")
    print(f"  {'─'*4}  {'─'*5}  {'─'*9}  {'─'*8}  {'─'*7}  {'─'*8}  {'─'*7}  {'─'*8}")
    tbl1 = summary_table(tier_df, "tier_gap", "tier_gap", ascending=True)
    for gap, r in tbl1.iterrows():
        print(f"  {gap:>4}  {int(r['n']):>5}  {r['model_rps']:>9.4f}  "
              f"{r['baseline_rps']:>8.4f}  {r['rps_diff_%']:>+7.1f}%  "
              f"{r['pred_hw']:>8.1%}  {r['actual_hw']:>7.1%}  {r['hw_bias']:>+8.3f}")

    # --- 3. Table 2: RPS by match type ---
    print(f"\n  Table 2 — RPS by match type (sorted by model RPS, best first)")
    print(f"  {'match type':<20}  {'n':>5}  {'model RPS':>9}  {'base RPS':>8}  {'diff %':>7}  "
          f"{'pred HW':>8}  {'act HW':>7}  {'HW bias':>8}")
    print(f"  {'─'*20}  {'─'*5}  {'─'*9}  {'─'*8}  {'─'*7}  {'─'*8}  {'─'*7}  {'─'*8}")
    tbl2 = summary_table(tier_df, "match_type", "model_rps", ascending=True)
    for mtype, r in tbl2.iterrows():
        print(f"  {mtype:<20}  {int(r['n']):>5}  {r['model_rps']:>9.4f}  "
              f"{r['baseline_rps']:>8.4f}  {r['rps_diff_%']:>+7.1f}%  "
              f"{r['pred_hw']:>8.1%}  {r['actual_hw']:>7.1%}  {r['hw_bias']:>+8.3f}")

    # --- 4. Bias summary ---
    print(f"\n  Bias check (HW bias = predicted P(home win) − actual home win rate):")
    print(f"  Positive = model over-predicts home wins for that bucket.")
    worst = tbl1["hw_bias"].abs().idxmax()
    print(f"  Largest bias: tier gap {worst}  "
          f"(bias {tbl1.loc[worst, 'hw_bias']:+.3f}, "
          f"n={int(tbl1.loc[worst, 'n'])})")
    overall_bias = tier_df["pred_home_win"].mean() - tier_df["actual_home_win"].mean()
    print(f"  Overall HW bias across all held-out matches: {overall_bias:+.4f}")

    # --- 5. USA / Canada / Mexico host diagnostic (gap-1 matches) ---
    print(f"\n  {'-' * 51}")
    print(f"  Host-nation HW bias diagnostic (tier gap = 1)")
    print(f"  {'-' * 51}")

    gap1_rows = []
    for _, row in holdout.iterrows():
        home, away = row["home_team"], row["away_team"]
        if home not in model["attack"] or away not in model["attack"]:
            continue
        ht = tier_map.get(home)
        at = tier_map.get(away)
        if ht is None or at is None or abs(ht - at) != 1:
            continue
        neutral = bool(row["neutral"])
        actual  = outcome(row)
        pred    = predict(model, home, away, neutral=neutral)
        gap1_rows.append({
            "home_team":       home,
            "is_host_nation":  home in WC_HOME_NATIONS,
            "pred_home_win":   pred["home_win"],
            "actual_home_win": 1.0 if actual == "home_win" else 0.0,
        })

    gap1_detail = pd.DataFrame(gap1_rows)

    for label, mask in [
        ("USA / Canada / Mexico as home", gap1_detail["is_host_nation"]),
        ("All other gap-1 home teams",   ~gap1_detail["is_host_nation"]),
    ]:
        sub = gap1_detail[mask]
        if sub.empty:
            print(f"  {label}: no matches in held-out set")
            continue
        pred_hw   = sub["pred_home_win"].mean()
        actual_hw = sub["actual_home_win"].mean()
        bias      = pred_hw - actual_hw
        print(f"  {label}")
        print(f"    n={len(sub):>4}   pred HW: {pred_hw:.1%}   "
              f"actual HW: {actual_hw:.1%}   bias: {bias:+.3f}")

    print(f"  {'-' * 51}")
    print(f"{'=' * 55}\n")


if __name__ == "__main__":
    main()
