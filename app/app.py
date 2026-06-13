"""
2026 World Cup Predictor — Flask backend.

All predictions are pre-computed once at startup and held in memory.
The single route GET / renders index.html with all data passed as context.
"""

import json
import sys
from pathlib import Path

# Allow imports from model/ regardless of working directory
ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT / "model"))

from flask import Flask, render_template

from data_prep import prepare_data
from poisson_model import fit, predict
from simulator import load_fixtures, run as simulate
from annex_c import THIRD_PLACE_ASSIGNMENTS, THIRD_PLACE_MATCH_ORDER

app = Flask(__name__)

# Flag emoji keyed by display name (as used in fixture data)
FLAGS = {
    "Algeria":              "🇩🇿",
    "Argentina":            "🇦🇷",
    "Australia":            "🇦🇺",
    "Austria":              "🇦🇹",
    "Belgium":              "🇧🇪",
    "Bosnia & Herzegovina": "🇧🇦",
    "Brazil":               "🇧🇷",
    "Canada":               "🇨🇦",
    "Cape Verde":           "🇨🇻",
    "Colombia":             "🇨🇴",
    "Croatia":              "🇭🇷",
    "Curaçao":              "🇨🇼",
    "Czech Republic":       "🇨🇿",
    "DR Congo":             "🇨🇩",
    "Ecuador":              "🇪🇨",
    "Egypt":                "🇪🇬",
    "England":              "🏴󠁧󠁢󠁥󠁮󠁧󠁿",
    "France":               "🇫🇷",
    "Germany":              "🇩🇪",
    "Ghana":                "🇬🇭",
    "Haiti":                "🇭🇹",
    "Iran":                 "🇮🇷",
    "Iraq":                 "🇮🇶",
    "Ivory Coast":          "🇨🇮",
    "Japan":                "🇯🇵",
    "Jordan":               "🇯🇴",
    "Mexico":               "🇲🇽",
    "Morocco":              "🇲🇦",
    "Netherlands":          "🇳🇱",
    "New Zealand":          "🇳🇿",
    "Norway":               "🇳🇴",
    "Panama":               "🇵🇦",
    "Paraguay":             "🇵🇾",
    "Portugal":             "🇵🇹",
    "Qatar":                "🇶🇦",
    "Saudi Arabia":         "🇸🇦",
    "Scotland":             "🏴󠁧󠁢󠁳󠁣󠁴󠁿",
    "Senegal":              "🇸🇳",
    "South Africa":         "🇿🇦",
    "South Korea":          "🇰🇷",
    "Spain":                "🇪🇸",
    "Sweden":               "🇸🇪",
    "Switzerland":          "🇨🇭",
    "Tunisia":              "🇹🇳",
    "Turkey":               "🇹🇷",
    "USA":                  "🇺🇸",
    "Uruguay":              "🇺🇾",
    "Uzbekistan":           "🇺🇿",
}


def build_match_pred(model, home_model, away_model, home_disp, away_disp, neutral=True):
    """
    Predict a single match and package it into the fixture dict shape the
    template renders (prob bar, margin-of-victory bar, scoreline tiles, bests).
    Used for both group fixtures and knockout ties.
    """
    p = predict(model, home_model, away_model, neutral=neutral)
    matrix = p["score_matrix"]

    # ── Margin-of-victory probabilities: H3+, H2, H1, Draw, A1, A2, A3+ ──
    margin_buckets = {"h3p": 0.0, "h2": 0.0, "h1": 0.0,
                      "draw": 0.0,
                      "a1": 0.0, "a2": 0.0, "a3p": 0.0}
    for h in range(matrix.shape[0]):
        for a in range(matrix.shape[1]):
            prob = float(matrix[h, a])
            margin = h - a
            if   margin >= 3:  margin_buckets["h3p"]  += prob
            elif margin == 2:  margin_buckets["h2"]   += prob
            elif margin == 1:  margin_buckets["h1"]   += prob
            elif margin == 0:  margin_buckets["draw"] += prob
            elif margin == -1: margin_buckets["a1"]   += prob
            elif margin == -2: margin_buckets["a2"]   += prob
            else:              margin_buckets["a3p"]  += prob
    margin_pcts = {k: round(v * 100, 1) for k, v in margin_buckets.items()}

    # ── Scoreline tiles ≥1%, sorted by probability descending ──
    tiles = []
    best_hw = best_draw = best_aw = None
    for h in range(matrix.shape[0]):
        for a in range(matrix.shape[1]):
            prob = matrix[h, a]
            if prob < 0.01:
                continue
            if h > a:
                result = "home"
            elif h == a:
                result = "draw"
            else:
                result = "away"
            tile = {"score": f"{h}-{a}", "pct": round(prob * 100, 1), "result": result}
            tiles.append(tile)
            if result == "home" and (best_hw is None or prob > best_hw["_p"]):
                best_hw = {**tile, "_p": prob}
            elif result == "draw" and (best_draw is None or prob > best_draw["_p"]):
                best_draw = {**tile, "_p": prob}
            elif result == "away" and (best_aw is None or prob > best_aw["_p"]):
                best_aw = {**tile, "_p": prob}
    tiles.sort(key=lambda t: t["pct"], reverse=True)
    outcome_bests = {
        "home": {k: v for k, v in best_hw.items() if k != "_p"} if best_hw else None,
        "draw": {k: v for k, v in best_draw.items() if k != "_p"} if best_draw else None,
        "away": {k: v for k, v in best_aw.items() if k != "_p"} if best_aw else None,
    }

    return {
        "home":              home_disp,
        "away":              away_disp,
        "home_flag":         FLAGS.get(home_disp, ""),
        "away_flag":         FLAGS.get(away_disp, ""),
        "most_likely_score": p["most_likely_score"],
        "home_win_pct":      round(p["home_win"] * 100, 1),
        "draw_pct":          round(p["draw"]     * 100, 1),
        "away_win_pct":      round(p["away_win"] * 100, 1),
        "lambda_home":       p["lambda_home"],
        "lambda_away":       p["lambda_away"],
        "score_tiles":       tiles,
        "outcome_bests":     outcome_bests,
        "margin_pcts":       margin_pcts,
    }


def build_bracket(model, sim_results, fixtures) -> dict:
    """
    Construct a single 'chalk' knockout bracket: fill each slot with the
    most-likely team (modal group winners/runners-up + the 8 most-likely
    third-placers via Annex C), then advance the favourite each round.
    Every tie is a concrete matchup with a full predicted-score fixture.
    """
    disp2model = {}
    for f in fixtures:
        disp2model[f["home_display"]] = f["home"]
        disp2model[f["away_display"]] = f["away"]

    # Chalk ordering within each group (by progression): [winner, runner, third, last]
    group_rank = {}            # letter -> [team_disp, ...] length 4
    third_qual_by_group = {}   # letter -> P(this group's chalk third qualifies)
    for group_name, gdf in sim_results.groupby("group"):
        letter = group_name.split()[-1]
        gg = gdf.sort_values("progression", ascending=False).reset_index(drop=True)
        group_rank[letter] = list(gg["team"])
        third_qual_by_group[letter] = float(gg.loc[2, "third_place_qualified"])

    # The 8 groups whose third-placer is most likely to qualify
    ranked = sorted(third_qual_by_group.items(), key=lambda kv: kv[1], reverse=True)
    qual_groups = sorted(letter for letter, _ in ranked[:8])
    assignment = THIRD_PLACE_ASSIGNMENTS["".join(qual_groups)]
    third_group_for_match = {
        THIRD_PLACE_MATCH_ORDER[i]: assignment[i] for i in range(8)
    }

    def slot(code):
        """'1A' -> chalk winner of A, '2B' -> chalk runner-up of B."""
        idx = 0 if code[0] == "1" else 1
        return group_rank[code[1]][idx]

    def match(home_disp, away_disp):
        d = build_match_pred(model, disp2model[home_disp], disp2model[away_disp],
                             home_disp, away_disp, neutral=True)
        winner = home_disp if d["home_win_pct"] >= d["away_win_pct"] else away_disp
        d["pred_winner"] = winner
        d["pred_winner_flag"] = FLAGS.get(winner, "")
        return d

    # R32 — fixed pairings + Annex-C third-place pairings
    r32_pairs = {
        73: ("2A", "2B"), 75: ("1F", "2C"), 76: ("1C", "2F"), 78: ("2E", "2I"),
        83: ("2K", "2L"), 84: ("1H", "2J"), 86: ("1J", "2H"), 88: ("2D", "2G"),
        74: ("1E", None), 77: ("1I", None), 79: ("1A", None), 80: ("1L", None),
        81: ("1D", None), 82: ("1G", None), 85: ("1B", None), 87: ("1K", None),
    }
    r32 = {}
    for mn, (hc, ac) in r32_pairs.items():
        home_disp = slot(hc)
        away_disp = (group_rank[third_group_for_match[mn]][2] if ac is None else slot(ac))
        r32[mn] = match(home_disp, away_disp)
    w = {mn: r32[mn]["pred_winner"] for mn in r32}

    # R16 — bracket quadrants
    r16_pairs = {
        "A": (73, 75), "B": (74, 77), "C": (76, 78), "D": (79, 80),
        "E": (84, 83), "F": (81, 82), "G": (86, 88), "H": (85, 87),
    }
    r16 = {k: match(w[a], w[b]) for k, (a, b) in r16_pairs.items()}
    w16 = {k: r16[k]["pred_winner"] for k in r16}

    qf_pairs = {1: ("A", "B"), 2: ("C", "D"), 3: ("E", "F"), 4: ("G", "H")}
    qf = {k: match(w16[a], w16[b]) for k, (a, b) in qf_pairs.items()}
    wqf = {k: qf[k]["pred_winner"] for k in qf}

    sf = {1: match(wqf[1], wqf[2]), 2: match(wqf[3], wqf[4])}
    wsf = {k: sf[k]["pred_winner"] for k in sf}

    final = match(wsf[1], wsf[2])
    champion = final["pred_winner"]

    # Display order groups ties by the QF they feed (so paths read top-to-bottom)
    r32_order = [73, 75, 74, 77, 76, 78, 79, 80, 84, 83, 81, 82, 86, 88, 85, 87]
    return {
        "champion":      champion,
        "champion_flag": FLAGS.get(champion, ""),
        "rounds": [
            {"name": "Round of 32",    "matches": [r32[mn] for mn in r32_order]},
            {"name": "Round of 16",    "matches": [r16[k] for k in "ABCDEFGH"]},
            {"name": "Quarter-finals", "matches": [qf[k] for k in (1, 2, 3, 4)]},
            {"name": "Semi-finals",    "matches": [sf[k] for k in (1, 2)]},
            {"name": "Final",          "matches": [final]},
        ],
    }


def build_context() -> dict:
    print("Loading and preparing data...")
    df = prepare_data(verbose=False)
    print(f"  {len(df):,} matches loaded")

    print("Fitting model...")
    model = fit(df)
    print(f"  Converged: {model['converged']}")

    print("Loading fixtures...")
    wc_results_path = ROOT / "data" / "wc_results.json"
    wc_results = json.loads(wc_results_path.read_text()) if wc_results_path.exists() else []
    fixtures = load_fixtures(results=wc_results)

    print("Running group stage + knockout simulator (10,000 iterations)...")
    sim_output   = simulate(fixtures, model)
    sim_results  = sim_output["group_stage"]
    ko_results   = sim_output["knockout"]

    # Knockout odds keyed by display name for O(1) lookup in the standings loop
    ko_lookup = ko_results.set_index("team").to_dict("index")

    # --- Per-match predictions ---
    # Keyed by (group, home_display, away_display)
    match_preds = {}
    for fx in fixtures:
        match_preds[(fx["group"], fx["home_display"], fx["away_display"])] = \
            build_match_pred(model, fx["home"], fx["away"],
                             fx["home_display"], fx["away_display"], neutral=fx["neutral"])

    # --- Predicted knockout bracket (chalk: favourites advance) ---
    print("Building predicted knockout bracket...")
    bracket = build_bracket(model, sim_results, fixtures)

    # --- Organise by group ---
    groups = []
    for group_name, gdf in sim_results.groupby("group"):
        gdf = gdf.sort_values("progression", ascending=False)

        standings = []
        for _, row in gdf.iterrows():
            prog_pct = round(row["progression"] * 100, 1)
            if prog_pct >= 70:
                colour = "green"
            elif prog_pct >= 40:
                colour = "amber"
            else:
                colour = "red"
            ko = ko_lookup.get(row["team"], {})
            standings.append({
                "team":         row["team"],
                "flag":         FLAGS.get(row["team"], ""),
                "prog_pct":     prog_pct,
                "mean_pts":     round(row["mean_pts"], 2),
                "colour":       colour,
                "first_pct":    round(row["first_place"]  * 100, 1),
                "second_pct":   round(row["second_place"] * 100, 1),
                "elim_pct":     round(row["eliminated"]   * 100, 1),
                "mean_gf":      round(row["mean_gf"],  2),
                "mean_ga":      round(row["mean_ga"],  2),
                "mean_wins":    round(row["mean_wins"],   2),
                "mean_draws":   round(row["mean_draws"],  2),
                "mean_losses":  round(row["mean_losses"], 2),
                "r32_pct":      round(ko.get("r32",    0) * 100, 1),
                "r16_pct":      round(ko.get("r16",    0) * 100, 1),
                "qf_pct":       round(ko.get("qf",     0) * 100, 1),
                "sf_pct":       round(ko.get("sf",     0) * 100, 1),
                "final_pct":    round(ko.get("final",  0) * 100, 1),
                "winner_pct":   round(ko.get("winner", 0) * 100, 1),
            })

        group_fixtures = [
            v for k, v in match_preds.items() if k[0] == group_name
        ]

        groups.append({
            "name":      group_name,
            "standings": standings,
            "fixtures":  group_fixtures,
        })

    print("Ready.\n")
    return {"groups": groups, "bracket": bracket}


# Pre-compute once at startup
context = build_context()


@app.route("/")
def index():
    return render_template("index.html", **context)


if __name__ == "__main__":
    app.run(debug=False, port=5000)
