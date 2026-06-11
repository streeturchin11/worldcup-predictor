"""
2026 World Cup group stage simulator.

Fits the Poisson model on the full historical dataset, then simulates
the group stage 10,000 times by sampling scorelines from the fitted
Poisson distributions. Reports each team's probability of finishing
in the top 2 of their group (i.e. progressing to the knockout round)
alongside their mean expected points.

Best-third-place qualification is post-MVP and not implemented here.
"""

import json
import sys
from collections import defaultdict
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).parent))

from data_prep import prepare_data, NAME_ALIASES
from poisson_model import fit, predict, WC_HOME_NATIONS
from annex_c import THIRD_PLACE_ASSIGNMENTS, THIRD_PLACE_MATCH_ORDER

DATA_DIR   = Path(__file__).parent.parent / "data"
N_SIMS     = 10_000
RNG_SEED   = 42
MAX_GOALS  = 15   # ceiling for Poisson sampling (negligible probability beyond this)


# ---------------------------------------------------------------------------
# Fixture loading
# ---------------------------------------------------------------------------

def load_fixtures() -> list[dict]:
    """Return group-stage fixtures with model-ready team names."""
    with open(DATA_DIR / "worldcup_2026.json") as f:
        data = json.load(f)

    fixtures = []
    for m in data["matches"]:
        if not m.get("group"):          # skip knockout placeholders
            continue
        home = NAME_ALIASES.get(m["team1"], m["team1"])
        away = NAME_ALIASES.get(m["team2"], m["team2"])
        # Home advantage only when a host nation is the designated home team (team1)
        is_home_fixture = m["team1"] in WC_HOME_NATIONS or home in WC_HOME_NATIONS
        fixtures.append({
            "group":        m["group"],
            "home_display": m["team1"],
            "away_display": m["team2"],
            "home":         home,
            "away":         away,
            "neutral":      not is_home_fixture,
        })
    return fixtures


# ---------------------------------------------------------------------------
# Simulation
# ---------------------------------------------------------------------------

def run(fixtures: list[dict], model: dict, n_sims: int = N_SIMS) -> dict:
    """
    Simulate the full tournament n_sims times: group stage, best-third-place
    selection, then the knockout bracket (R32 → R16 → QF → SF → Final).

    Returns a dict with two DataFrames:
        "group_stage" — one row per team; progression, finish-position splits,
                        mean pts/goals/record, plus third_place_qualified
        "knockout"    — one row per team that entered R32 in ≥1 sim, with the
                        fraction of sims reaching each round (r32 … winner)
    """
    rng = np.random.default_rng(RNG_SEED)

    n_matches = len(fixtures)

    # Pre-compute lambda_home and lambda_away for every group match
    lambdas_home = np.empty(n_matches)
    lambdas_away = np.empty(n_matches)
    for i, fx in enumerate(fixtures):
        p = predict(model, fx["home"], fx["away"], neutral=fx["neutral"])
        lambdas_home[i] = p["lambda_home"]
        lambdas_away[i] = p["lambda_away"]

    # Sample all group-stage goals at once: shape (n_sims, n_matches)
    goals_home = rng.poisson(lambdas_home[np.newaxis, :], size=(n_sims, n_matches))
    goals_away = rng.poisson(lambdas_away[np.newaxis, :], size=(n_sims, n_matches))

    # Neutral-venue lambda cache for all knockout matchups.
    # lambda_cache[(team_a_model, team_b_model)] = (λ_a, λ_b); both neutral.
    all_ko_teams = {f["home"] for f in fixtures} | {f["away"] for f in fixtures}
    lambda_cache = {}
    for ta in all_ko_teams:
        for tb in all_ko_teams:
            if ta != tb:
                p = predict(model, ta, tb, neutral=True)
                lambda_cache[(ta, tb)] = (p["lambda_home"], p["lambda_away"])

    # Display ↔ model name maps (each WC team name is unique)
    model2disp = {}
    for f in fixtures:
        model2disp[f["home"]] = f["home_display"]
        model2disp[f["away"]] = f["away_display"]

    # Organise fixtures by group
    groups: dict[str, list[int]] = {}
    for i, fx in enumerate(fixtures):
        groups.setdefault(fx["group"], []).append(i)

    results = []
    # Per-group finisher names and third-place stats, keyed by group letter
    group_results = {}       # letter -> {first, second, third, *_model}
    group_third_stats = {}   # letter -> {pts, gd, gf} each (n_sims,)

    for group_name, match_idxs in sorted(groups.items()):
        match_idxs = np.array(match_idxs)

        # Collect unique teams in this group (preserving display names)
        teams_display = []
        teams_model   = []
        seen: set[str] = set()
        for i in match_idxs:
            for display, model_name in [
                (fixtures[i]["home_display"], fixtures[i]["home"]),
                (fixtures[i]["away_display"], fixtures[i]["away"]),
            ]:
                if model_name not in seen:
                    teams_display.append(display)
                    teams_model.append(model_name)
                    seen.add(model_name)

        n_teams   = len(teams_model)
        team_idx  = {t: j for j, t in enumerate(teams_model)}

        # For each sim accumulate points, GD, GF, GA, W/D/L per team
        # Shape: (n_sims, n_teams)
        pts  = np.zeros((n_sims, n_teams), dtype=np.int32)
        gd   = np.zeros((n_sims, n_teams), dtype=np.int32)
        gf   = np.zeros((n_sims, n_teams), dtype=np.int32)
        ga   = np.zeros((n_sims, n_teams), dtype=np.int32)
        wins = np.zeros((n_sims, n_teams), dtype=np.int32)
        drws = np.zeros((n_sims, n_teams), dtype=np.int32)
        loss = np.zeros((n_sims, n_teams), dtype=np.int32)

        for i in match_idxs:
            hi = team_idx[fixtures[i]["home"]]
            ai = team_idx[fixtures[i]["away"]]
            gh = goals_home[:, i]   # (n_sims,)
            gaw = goals_away[:, i]

            home_win = gh > gaw
            draw     = gh == gaw
            away_win = gh < gaw

            pts[:, hi]  += np.where(home_win, 3, np.where(draw, 1, 0))
            pts[:, ai]  += np.where(away_win, 3, np.where(draw, 1, 0))
            gd[:, hi]   += (gh - gaw).astype(np.int32)
            gd[:, ai]   += (gaw - gh).astype(np.int32)
            gf[:, hi]   += gh.astype(np.int32)
            gf[:, ai]   += gaw.astype(np.int32)
            ga[:, hi]   += gaw.astype(np.int32)
            ga[:, ai]   += gh.astype(np.int32)
            wins[:, hi] += home_win.astype(np.int32)
            wins[:, ai] += away_win.astype(np.int32)
            drws[:, hi] += draw.astype(np.int32)
            drws[:, ai] += draw.astype(np.int32)
            loss[:, hi] += away_win.astype(np.int32)
            loss[:, ai] += home_win.astype(np.int32)

        # Rank teams: pts desc → GD desc → GF desc
        # ranks[sim, j] = finishing position (0 = 1st, n-1 = last)
        ranks = np.empty((n_sims, n_teams), dtype=np.int32)
        for s in range(n_sims):
            order = np.lexsort((-gf[s], -gd[s], -pts[s]))
            ranks[s, order] = np.arange(n_teams)

        top2 = ranks < 2   # (n_sims, n_teams) bool
        top1 = ranks == 0

        # Per-sim finisher indices (ranks is a permutation, so argsort is exact)
        sorted_idx = np.argsort(ranks, axis=1, kind="stable")  # (n_sims, n_teams)
        first_i  = sorted_idx[:, 0]
        second_i = sorted_idx[:, 1]
        third_i  = sorted_idx[:, 2]

        letter = group_name.split()[-1]
        group_results[letter] = {
            "first":        [teams_display[first_i[s]]  for s in range(n_sims)],
            "second":       [teams_display[second_i[s]] for s in range(n_sims)],
            "third":        [teams_display[third_i[s]]  for s in range(n_sims)],
            "first_model":  [teams_model[first_i[s]]    for s in range(n_sims)],
            "second_model": [teams_model[second_i[s]]   for s in range(n_sims)],
            "third_model":  [teams_model[third_i[s]]    for s in range(n_sims)],
        }
        rows = np.arange(n_sims)
        group_third_stats[letter] = {
            "pts": pts[rows, third_i],
            "gd":  gd[rows, third_i],
            "gf":  gf[rows, third_i],
        }

        for j, (display, model_name) in enumerate(zip(teams_display, teams_model)):
            results.append({
                "group":        group_name,
                "team":         display,
                "progression":  float(top2[:, j].mean()),
                "first_place":  float(top1[:, j].mean()),
                "second_place": float((ranks[:, j] == 1).mean()),
                "eliminated":   float((ranks[:, j] >= 2).mean()),
                "mean_pts":     float(pts[:, j].mean()),
                "mean_gf":      float(gf[:, j].mean()),
                "mean_ga":      float(ga[:, j].mean()),
                "mean_wins":    float(wins[:, j].mean()),
                "mean_draws":   float(drws[:, j].mean()),
                "mean_losses":  float(loss[:, j].mean()),
            })

    # ----------------------------------------------------------------------
    # Best-third-place selection + Annex C bracket assignment
    # ----------------------------------------------------------------------
    group_order = sorted(group_third_stats.keys())  # A … L in column order
    tp_pts = np.column_stack([group_third_stats[l]["pts"] for l in group_order])
    tp_gd  = np.column_stack([group_third_stats[l]["gd"]  for l in group_order])
    tp_gf  = np.column_stack([group_third_stats[l]["gf"]  for l in group_order])

    # Tiny random jitter breaks exact ties between third-placers (drawn once)
    noise = rng.uniform(0, 1e-6, size=(n_sims, 12))

    # third_side[match_num][s] = model name of the third-placer hosted by that
    # R32 match in sim s, per Annex C
    third_side = {mn: np.empty(n_sims, dtype=object) for mn in THIRD_PLACE_MATCH_ORDER}
    third_qual_counts = defaultdict(int)  # display name -> #sims as best-third

    for s in range(n_sims):
        # Rank the 12 third-placers: pts desc → gd desc → (gf + jitter) desc
        order = np.lexsort((-(tp_gf[s] + noise[s]), -tp_gd[s], -tp_pts[s]))
        top8 = sorted(group_order[i] for i in order[:8])  # sorted A-L for key
        key_s = "".join(top8)
        value_s = THIRD_PLACE_ASSIGNMENTS[key_s]
        for i, match_num in enumerate(THIRD_PLACE_MATCH_ORDER):
            grp = value_s[i]
            third_side[match_num][s] = group_results[grp]["third_model"][s]
        for letter in top8:
            third_qual_counts[group_results[letter]["third"][s]] += 1

    # ----------------------------------------------------------------------
    # Knockout bracket simulation
    # ----------------------------------------------------------------------
    ko_counts = defaultdict(
        lambda: {"r32": 0, "r16": 0, "qf": 0, "sf": 0, "final": 0, "winner": 0}
    )

    def seed(code: str) -> np.ndarray:
        """Model-name array for a group-winner/runner-up slot code, e.g. '1F', '2B'."""
        pos, letter = code[0], code[1]
        key = "first_model" if pos == "1" else "second_model"
        return np.array(group_results[letter][key], dtype=object)

    def tally(round_name: str, model_array: np.ndarray) -> None:
        """Count, per team, how many sims placed it (entering) in round_name."""
        vals, counts = np.unique(model_array, return_counts=True)
        for v, c in zip(vals, counts):
            ko_counts[model2disp[v]][round_name] += int(c)

    def play(model_a: np.ndarray, model_b: np.ndarray) -> np.ndarray:
        """Neutral-venue single match across all sims; returns winner model names."""
        lam_a = np.empty(n_sims)
        lam_b = np.empty(n_sims)
        for s in range(n_sims):
            la, lb = lambda_cache[(model_a[s], model_b[s])]
            lam_a[s] = la
            lam_b[s] = lb
        g_a = rng.poisson(lam_a)
        g_b = rng.poisson(lam_b)
        # Ties broken by a coin flip (no extra-time model at this resolution)
        a_wins = (g_a > g_b) | ((g_a == g_b) & (rng.integers(0, 2, n_sims) == 0))
        return np.where(a_wins, model_a, model_b)

    # R32 — fixed pairings + Annex-C third-place pairings
    r32 = {
        73: (seed("2A"), seed("2B")),
        75: (seed("1F"), seed("2C")),
        76: (seed("1C"), seed("2F")),
        78: (seed("2E"), seed("2I")),
        83: (seed("2K"), seed("2L")),
        84: (seed("1H"), seed("2J")),
        86: (seed("1J"), seed("2H")),
        88: (seed("2D"), seed("2G")),
        74: (seed("1E"), third_side[74]),
        77: (seed("1I"), third_side[77]),
        79: (seed("1A"), third_side[79]),
        80: (seed("1L"), third_side[80]),
        81: (seed("1D"), third_side[81]),
        82: (seed("1G"), third_side[82]),
        85: (seed("1B"), third_side[85]),
        87: (seed("1K"), third_side[87]),
    }
    for a, b in r32.values():
        tally("r32", a)
        tally("r32", b)
    w32 = {mn: play(*r32[mn]) for mn in sorted(r32)}
    for mn in r32:
        tally("r16", w32[mn])

    # R16 — bracket quadrants (NOT sequential pairing)
    r16 = {
        "A": (w32[73], w32[75]),
        "B": (w32[74], w32[77]),
        "C": (w32[76], w32[78]),
        "D": (w32[79], w32[80]),
        "E": (w32[84], w32[83]),
        "F": (w32[81], w32[82]),
        "G": (w32[86], w32[88]),
        "H": (w32[85], w32[87]),
    }
    w16 = {k: play(*r16[k]) for k in sorted(r16)}
    for k in r16:
        tally("qf", w16[k])

    # QF
    qf = {
        1: (w16["A"], w16["B"]),
        2: (w16["C"], w16["D"]),
        3: (w16["E"], w16["F"]),
        4: (w16["G"], w16["H"]),
    }
    wqf = {k: play(*qf[k]) for k in sorted(qf)}
    for k in qf:
        tally("sf", wqf[k])

    # SF
    sf = {1: (wqf[1], wqf[2]), 2: (wqf[3], wqf[4])}
    wsf = {k: play(*sf[k]) for k in sorted(sf)}
    for k in sf:
        tally("final", wsf[k])

    # Final
    champion = play(wsf[1], wsf[2])
    tally("winner", champion)

    # ----------------------------------------------------------------------
    # Assemble return DataFrames
    # ----------------------------------------------------------------------
    gs_df = pd.DataFrame(results)
    gs_df["third_place_qualified"] = gs_df["team"].map(
        lambda t: third_qual_counts.get(t, 0) / n_sims
    )
    # progression = top-2 + qualified-as-best-third (mutually exclusive events)
    gs_df["progression"] = gs_df["progression"] + gs_df["third_place_qualified"]
    gs_df["eliminated"]  = 1.0 - gs_df["progression"]

    ko_rows = []
    for disp, c in ko_counts.items():
        if c["r32"] > 0:
            ko_rows.append({
                "team":   disp,
                "r32":    c["r32"]    / n_sims,
                "r16":    c["r16"]    / n_sims,
                "qf":     c["qf"]     / n_sims,
                "sf":     c["sf"]     / n_sims,
                "final":  c["final"]  / n_sims,
                "winner": c["winner"] / n_sims,
            })
    ko_df = pd.DataFrame(ko_rows)

    return {"group_stage": gs_df, "knockout": ko_df}


# ---------------------------------------------------------------------------
# Output
# ---------------------------------------------------------------------------

def print_results(df: pd.DataFrame) -> None:
    for group, gdf in df.groupby("group"):
        gdf = gdf.sort_values("progression", ascending=False)
        print(f"\n{group}")
        print(f"  {'Team':<25} {'Progression':>12}  {'Mean pts':>8}")
        print(f"  {'-'*25}  {'-'*11}  {'-'*8}")
        for _, row in gdf.iterrows():
            print(f"  {row['team']:<25} {row['progression']:>11.1%}  {row['mean_pts']:>8.2f}")


def print_knockout(df: pd.DataFrame) -> None:
    df = df.sort_values("winner", ascending=False)
    print(f"\nKnockout progression (fraction of {N_SIMS:,} sims)")
    print(f"  {'Team':<25} {'R32':>7} {'R16':>7} {'QF':>7} "
          f"{'SF':>7} {'Final':>7} {'Winner':>7}")
    print(f"  {'-'*25} {'-'*7} {'-'*7} {'-'*7} {'-'*7} {'-'*7} {'-'*7}")
    for _, row in df.iterrows():
        print(f"  {row['team']:<25} {row['r32']:>6.1%} {row['r16']:>6.1%} "
              f"{row['qf']:>6.1%} {row['sf']:>6.1%} {row['final']:>6.1%} "
              f"{row['winner']:>6.1%}")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    print("Loading and preparing data...")
    df_full = prepare_data(verbose=False)
    print(f"  {len(df_full):,} matches")

    print("Fitting model on full dataset...")
    model = fit(df_full)
    print(f"  Converged: {model['converged']}")
    print(f"  Teams fitted: {len(model['teams'])}")

    print("Loading fixtures...")
    fixtures = load_fixtures()
    print(f"  {len(fixtures)} group stage matches across "
          f"{len(set(f['group'] for f in fixtures))} groups")

    # Warn about any WC teams not seen in training data
    missing = {f["home_display"] for f in fixtures if f["home"] not in model["attack"]}
    missing |= {f["away_display"] for f in fixtures if f["away"] not in model["attack"]}
    if missing:
        print(f"  ⚠ Teams not in training data (will use global mean): {sorted(missing)}")

    print(f"\nSimulating {N_SIMS:,} tournaments (seed={RNG_SEED})...")
    import time
    t0 = time.time()
    output = run(fixtures, model)
    elapsed = time.time() - t0
    print(f"  Done in {elapsed:.1f}s")

    print_results(output["group_stage"])
    print_knockout(output["knockout"])
