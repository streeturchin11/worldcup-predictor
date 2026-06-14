"""
Export pre-computed predictions to docs/predictions.json for the static site.

Run from the project root:
    python3 scripts/export_json.py

If data/wc_results.json contains actual match results they are:
  1. Appended to the historical training data before fitting (weight 1.00,
     tournament "FIFA World Cup"), so the model refits on real WC scores.
  2. Used to annotate each fixture in the output with its actual result and
     whether the model's prediction was correct.
"""

import json
import sys
import pandas as pd
from pathlib import Path

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT / "model"))

from data_prep import prepare_data, apply_weights, NAME_ALIASES
from poisson_model import fit, predict, WC_HOME_NATIONS
from simulator import load_fixtures, run as simulate

DATA_DIR = ROOT / "data"
OUT      = ROOT / "docs" / "predictions.json"

# ── Flag emoji keyed by display name ─────────────────────────────────────────
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
    p = predict(model, home_model, away_model, neutral=neutral)
    matrix = p["score_matrix"]

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

    tiles = []
    best_hw = best_draw = best_aw = None
    for h in range(matrix.shape[0]):
        for a in range(matrix.shape[1]):
            prob = matrix[h, a]
            if prob < 0.01:
                continue
            result = "home" if h > a else "draw" if h == a else "away"
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
        "home": {k: v for k, v in best_hw.items()   if k != "_p"} if best_hw   else None,
        "draw": {k: v for k, v in best_draw.items() if k != "_p"} if best_draw else None,
        "away": {k: v for k, v in best_aw.items()   if k != "_p"} if best_aw   else None,
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


def build_bracket(model, sim_results, fixtures):
    from annex_c import THIRD_PLACE_ASSIGNMENTS, THIRD_PLACE_MATCH_ORDER

    disp2model = {}
    for f in fixtures:
        disp2model[f["home_display"]] = f["home"]
        disp2model[f["away_display"]] = f["away"]

    group_rank = {}
    third_qual_by_group = {}
    for group_name, gdf in sim_results.groupby("group"):
        letter = group_name.split()[-1]
        gg = gdf.sort_values("progression", ascending=False).reset_index(drop=True)
        group_rank[letter] = list(gg["team"])
        third_qual_by_group[letter] = float(gg.loc[2, "third_place_qualified"])

    ranked = sorted(third_qual_by_group.items(), key=lambda kv: kv[1], reverse=True)
    qual_groups = sorted(letter for letter, _ in ranked[:8])
    assignment = THIRD_PLACE_ASSIGNMENTS["".join(qual_groups)]
    third_group_for_match = {
        THIRD_PLACE_MATCH_ORDER[i]: assignment[i] for i in range(8)
    }

    def slot(code):
        idx = 0 if code[0] == "1" else 1
        return group_rank[code[1]][idx]

    def match(home_disp, away_disp):
        d = build_match_pred(model, disp2model[home_disp], disp2model[away_disp],
                             home_disp, away_disp, neutral=True)
        winner = home_disp if d["home_win_pct"] >= d["away_win_pct"] else away_disp
        d["pred_winner"] = winner
        d["pred_winner_flag"] = FLAGS.get(winner, "")
        return d

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

    r16_pairs = {
        "A": (73, 75), "B": (74, 77), "C": (76, 78), "D": (79, 80),
        "E": (84, 83), "F": (81, 82), "G": (86, 88), "H": (85, 87),
    }
    r16 = {k: match(w[a], w[b]) for k, (a, b) in r16_pairs.items()}
    w16 = {k: r16[k]["pred_winner"] for k in r16}

    qf_pairs = {1: ("A", "B"), 2: ("C", "D"), 3: ("E", "F"), 4: ("G", "H")}
    qf  = {k: match(w16[a], w16[b]) for k, (a, b) in qf_pairs.items()}
    wqf = {k: qf[k]["pred_winner"] for k in qf}

    sf  = {1: match(wqf[1], wqf[2]), 2: match(wqf[3], wqf[4])}
    wsf = {k: sf[k]["pred_winner"] for k in sf}

    final    = match(wsf[1], wsf[2])
    champion = final["pred_winner"]

    r32_order = [73, 75, 74, 77, 76, 78, 79, 80, 84, 83, 81, 82, 86, 88, 85, 87]
    return {
        "champion":      champion,
        "champion_flag": FLAGS.get(champion, ""),
        "rounds": [
            {"name": "Round of 32",    "matches": [r32[mn] for mn in r32_order]},
            {"name": "Round of 16",    "matches": [r16[k] for k in "ABCDEFGH"]},
            {"name": "Quarter-finals", "matches": [qf[k]  for k in (1, 2, 3, 4)]},
            {"name": "Semi-finals",    "matches": [sf[k]  for k in (1, 2)]},
            {"name": "Final",          "matches": [final]},
        ],
    }


# ── Time helpers ─────────────────────────────────────────────────────────────

def parse_time(time_str: str) -> tuple[int, int, int]:
    """Parse "HH:MM UTC±N" → (hour, minute, offset_hours).

    All offsets in worldcup_2026.json are confirmed whole-hour integers
    (UTC-4, UTC-5, UTC-6, UTC-7 only — validated by scanning all fixtures
    before implementation).
    """
    time_part, utc_part = time_str.split(" ")
    h, m = map(int, time_part.split(":"))
    offset = int(utc_part.replace("UTC", ""))  # e.g. "UTC-6" → -6
    return h, m, offset


def compute_times(time_str: str) -> dict:
    """Return {"time_uk": "HH:MM BST", "time_local": "HH:MM"} for a fixture."""
    h, m, offset = parse_time(time_str)
    # UTC = venue_time − offset
    utc_total_min = h * 60 + m - offset * 60
    # BST = UTC + 1 hour
    bst_total_min = utc_total_min + 60
    bst_h = (bst_total_min // 60) % 24
    bst_m = bst_total_min % 60
    return {
        "time_uk":    f"{bst_h:02d}:{bst_m:02d} BST",
        "time_local": f"{h:02d}:{m:02d}",
    }


def build_today(fixtures_raw: list[dict], wc_results: list[dict], model: dict) -> list[dict]:
    """Return today's fixture list sorted by time_uk (BST).

    "Today" = the earliest date in the fixture list that has at least one
    fixture not yet recorded in wc_results.  Returns [] when all played.
    """
    played_keys = {(r["home"], r["away"]) for r in wc_results}

    # Load raw fixture data (with time fields) keyed by display pair
    with open(DATA_DIR / "worldcup_2026.json") as f:
        raw_data = json.load(f)

    raw_by_pair: dict[tuple, dict] = {}
    for m in raw_data["matches"]:
        if m.get("group") and m.get("time"):
            raw_by_pair[(m["team1"], m["team2"])] = m

    # Find the earliest date with ≥1 unplayed fixture
    date_fixtures: dict[str, list] = {}
    for fx in fixtures_raw:
        raw = raw_by_pair.get((fx["home_display"], fx["away_display"]))
        if raw is None:
            continue
        date = raw.get("date", "")
        date_fixtures.setdefault(date, []).append((fx, raw))

    today_date = None
    for date in sorted(date_fixtures):
        pairs = date_fixtures[date]
        if any((fx["home_display"], fx["away_display"]) not in played_keys
               for fx, _ in pairs):
            today_date = date
            break

    if today_date is None:
        return []

    result = []
    for fx, raw in date_fixtures[today_date]:
        times = compute_times(raw["time"])
        pred = build_match_pred(model, fx["home"], fx["away"],
                                fx["home_display"], fx["away_display"],
                                neutral=fx["neutral"])
        pred.update(times)
        pred["date"] = today_date
        result.append(pred)

    result.sort(key=lambda x: x["time_uk"])
    return result


# ── WC results helpers ────────────────────────────────────────────────────────

def load_wc_results() -> list[dict]:
    with (DATA_DIR / "wc_results.json").open() as f:
        return json.load(f)


def wc_results_to_rows(wc_results: list[dict]) -> pd.DataFrame:
    rows = []
    for r in wc_results:
        home_model = NAME_ALIASES.get(r["home"], r["home"])
        away_model = NAME_ALIASES.get(r["away"], r["away"])
        neutral    = home_model not in WC_HOME_NATIONS
        rows.append({
            "date":       pd.Timestamp(r["date"]),
            "home_team":  home_model,
            "away_team":  away_model,
            "home_score": int(r["home_score"]),
            "away_score": int(r["away_score"]),
            "tournament": "FIFA World Cup",
            "neutral":    neutral,
        })
    df = pd.DataFrame(rows)
    df = apply_weights(df)
    keep = [
        "date", "home_team", "away_team",
        "home_score", "away_score",
        "tournament", "neutral",
        "age_years", "time_decay", "competition_weight", "match_weight",
    ]
    return df[keep]


def build_result_index(wc_results: list[dict]) -> dict:
    return {(r["home"], r["away"]): r for r in wc_results}


def annotate_fixture(fx: dict, result_index: dict) -> dict:
    r = result_index.get((fx["home"], fx["away"]))
    if r is None:
        fx["played"] = False
        return fx

    ah, aa = int(r["home_score"]), int(r["away_score"])
    fx["played"]      = True
    fx["actual_home"] = ah
    fx["actual_away"] = aa

    actual_outcome = "home" if ah > aa else "draw" if ah == aa else "away"

    hw, dp, aw = fx["home_win_pct"], fx["draw_pct"], fx["away_win_pct"]
    if hw >= dp and hw >= aw:
        pred_outcome = "home"
    elif aw >= hw and aw >= dp:
        pred_outcome = "away"
    else:
        pred_outcome = "draw"

    fx["correct_outcome"] = (pred_outcome == actual_outcome)
    fx["correct_score"]   = (fx["most_likely_score"] == f"{ah}-{aa}")
    return fx


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    print("Loading and preparing historical data...")
    df_hist = prepare_data(verbose=False)
    print(f"  {len(df_hist):,} historical matches loaded")

    wc_results = load_wc_results()
    if wc_results:
        print(f"  Appending {len(wc_results)} WC result(s) to training data...")
        df_hist = pd.concat([df_hist, wc_results_to_rows(wc_results)], ignore_index=True)
        print(f"  Total: {len(df_hist):,} matches for model fit")
    else:
        print("  No WC results recorded yet — proceeding with historical data only")

    print("Fitting model...")
    model = fit(df_hist)
    print(f"  Converged: {model['converged']}")

    print("Loading fixtures...")
    fixtures = load_fixtures(results=wc_results)

    print("Running group stage + knockout simulator (10,000 iterations)...")
    sim_output  = simulate(fixtures, model)
    sim_results = sim_output["group_stage"]
    ko_results  = sim_output["knockout"]
    ko_lookup   = ko_results.set_index("team").to_dict("index")

    result_index = build_result_index(wc_results)

    match_preds = {}
    for fx in fixtures:
        pred = build_match_pred(model, fx["home"], fx["away"],
                                fx["home_display"], fx["away_display"],
                                neutral=fx["neutral"])
        pred = annotate_fixture(pred, result_index)
        match_preds[(fx["group"], fx["home_display"], fx["away_display"])] = pred

    print("Building today's fixtures...")
    today = build_today(fixtures, wc_results, model)
    print(f"  {len(today)} fixture(s) on today's matchday"
          + (f" ({today[0]['date']})" if today else ""))

    print("Building predicted knockout bracket...")
    bracket = build_bracket(model, sim_results, fixtures)

    groups = []
    for group_name, gdf in sim_results.groupby("group"):
        gdf = gdf.sort_values("progression", ascending=False)
        standings = []
        for _, row in gdf.iterrows():
            prog_pct = round(row["progression"] * 100, 1)
            colour   = "green" if prog_pct >= 70 else "amber" if prog_pct >= 40 else "red"
            ko       = ko_lookup.get(row["team"], {})
            standings.append({
                "team":        row["team"],
                "flag":        FLAGS.get(row["team"], ""),
                "prog_pct":    prog_pct,
                "mean_pts":    round(row["mean_pts"], 2),
                "colour":      colour,
                "first_pct":   round(row["first_place"]  * 100, 1),
                "second_pct":  round(row["second_place"] * 100, 1),
                "elim_pct":    round(row["eliminated"]   * 100, 1),
                "mean_gf":     round(row["mean_gf"],  2),
                "mean_ga":     round(row["mean_ga"],  2),
                "mean_wins":   round(row["mean_wins"],   2),
                "mean_draws":  round(row["mean_draws"],  2),
                "mean_losses": round(row["mean_losses"], 2),
                "r32_pct":     round(ko.get("r32",    0) * 100, 1),
                "r16_pct":     round(ko.get("r16",    0) * 100, 1),
                "qf_pct":      round(ko.get("qf",     0) * 100, 1),
                "sf_pct":      round(ko.get("sf",     0) * 100, 1),
                "final_pct":   round(ko.get("final",  0) * 100, 1),
                "winner_pct":  round(ko.get("winner", 0) * 100, 1),
            })

        group_fixtures = [v for k, v in match_preds.items() if k[0] == group_name]
        groups.append({"name": group_name, "standings": standings, "fixtures": group_fixtures})

    context = {"today": today, "groups": groups, "bracket": bracket}

    OUT.parent.mkdir(exist_ok=True)
    with OUT.open("w") as f:
        json.dump(context, f, indent=2)

    matches_written = sum(len(g["fixtures"]) for g in groups)
    played          = sum(1 for g in groups for fx in g["fixtures"] if fx.get("played"))
    size_kb         = OUT.stat().st_size / 1024

    print(f"\nWritten: {OUT}")
    print(f"  Groups  : {len(groups)}")
    print(f"  Matches : {matches_written}  ({played} played, {matches_written - played} unplayed)")
    print(f"  Size    : {size_kb:.1f} KB")


if __name__ == "__main__":
    main()
