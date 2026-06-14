"""
Sync wc_results.json from intl_results.csv.

Reads data/intl_results.csv, finds rows where tournament == "FIFA World Cup"
and scores are not NA, maps team names back to fixture display names, looks up
the group from worldcup_2026.json, and writes data/wc_results.json.

Run from project root:
    python3 scripts/sync_wc_results.py
"""

import json
import sys
from pathlib import Path

import pandas as pd

ROOT     = Path(__file__).parent.parent
DATA_DIR = ROOT / "data"
sys.path.insert(0, str(ROOT / "model"))

from data_prep import NAME_ALIASES

# Reverse of NAME_ALIASES: model name → fixture display name
# e.g. "United States" → "USA", "Bosnia and Herzegovina" → "Bosnia & Herzegovina"
REVERSE_ALIASES = {v: k for k, v in NAME_ALIASES.items()}


def build_fixture_lookup() -> dict:
    """Return {(model_home, model_away): {group, home_display, away_display}}."""
    with open(DATA_DIR / "worldcup_2026.json") as f:
        data = json.load(f)

    lookup = {}
    for m in data["matches"]:
        if not m.get("group"):
            continue
        disp_home = m["team1"]
        disp_away = m["team2"]
        model_home = NAME_ALIASES.get(disp_home, disp_home)
        model_away = NAME_ALIASES.get(disp_away, disp_away)
        group_letter = m["group"].split()[-1]
        lookup[(model_home, model_away)] = {
            "group":        group_letter,
            "home_display": disp_home,
            "away_display": disp_away,
        }
    return lookup


def main():
    fixture_lookup = build_fixture_lookup()

    df = pd.read_csv(DATA_DIR / "intl_results.csv", dtype=str)
    wc = df[
        (df["tournament"] == "FIFA World Cup") &
        (df["date"] >= "2026-06-01") &
        (df["home_score"].notna()) &
        (df["home_score"] != "NA") &
        (df["away_score"] != "NA")
    ].copy()

    results = []
    unmatched = []
    for _, row in wc.iterrows():
        # CSV uses model names directly for most teams; apply reverse alias for
        # any that differ (e.g. "United States" is already the model name, but
        # if the CSV ever uses a display name we catch it via REVERSE_ALIASES).
        csv_home = row["home_team"]
        csv_away = row["away_team"]

        # Try direct lookup first, then with aliases applied either direction
        key = (csv_home, csv_away)
        if key not in fixture_lookup:
            # Normalise via NAME_ALIASES (csv might use display name)
            key = (NAME_ALIASES.get(csv_home, csv_home),
                   NAME_ALIASES.get(csv_away, csv_away))

        if key not in fixture_lookup:
            unmatched.append((row["date"], csv_home, csv_away))
            continue

        fx = fixture_lookup[key]
        results.append({
            "group":      fx["group"],
            "home":       fx["home_display"],
            "away":       fx["away_display"],
            "home_score": int(row["home_score"]),
            "away_score": int(row["away_score"]),
            "date":       row["date"],
        })

    results.sort(key=lambda r: r["date"])

    out_path = DATA_DIR / "wc_results.json"
    with out_path.open("w") as f:
        json.dump(results, f, indent=2)

    print(f"Wrote {len(results)} result(s) to {out_path}")
    if unmatched:
        print(f"  Warning: {len(unmatched)} CSV row(s) not matched to a fixture:")
        for date, h, a in unmatched:
            print(f"    {date}  {h} vs {a}")


if __name__ == "__main__":
    main()
