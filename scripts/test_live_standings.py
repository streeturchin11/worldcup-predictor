"""
Verify that played-result seeding works correctly.

Run from project root:
    python scripts/test_live_standings.py
"""

import sys
from pathlib import Path

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT / "model"))

from data_prep import prepare_data
from poisson_model import fit
from simulator import load_fixtures, run as simulate

FAKE_RESULTS = [
    {"group": "A", "home": "Mexico",      "away": "South Africa",   "home_score": 2, "away_score": 0},
    {"group": "A", "home": "South Korea", "away": "Czech Republic", "home_score": 1, "away_score": 1},
]

def main():
    print("Loading and fitting model...")
    df = prepare_data(verbose=False)
    model = fit(df)
    print("  Done.\n")

    fixtures = load_fixtures(results=FAKE_RESULTS)
    sim_output = simulate(fixtures, model)
    gs = sim_output["group_stage"]

    group_a = gs[gs["group"] == "Group A"].set_index("team")

    print("Group A mean_pts after seeding two played results:")
    for team, row in group_a.iterrows():
        print(f"  {team:<25} mean_pts={row['mean_pts']:.3f}")
    print()

    failures = []

    def check(name, condition, msg):
        if condition:
            print(f"  PASS  {name}")
        else:
            print(f"  FAIL  {name}: {msg}")
            failures.append(name)

    mexico_pts      = group_a.loc["Mexico",       "mean_pts"]
    south_africa_pts= group_a.loc["South Africa", "mean_pts"]
    south_korea_pts = group_a.loc["South Korea",  "mean_pts"]
    czech_pts       = group_a.loc["Czech Republic","mean_pts"]
    total           = mexico_pts + south_africa_pts + south_korea_pts + czech_pts

    check(
        "a: Mexico mean_pts >= 3.0",
        mexico_pts >= 3.0,
        f"Mexico mean_pts={mexico_pts:.3f}",
    )
    check(
        "b: South Africa mean_pts < 3.0",
        south_africa_pts < 3.0,
        f"South Africa mean_pts={south_africa_pts:.3f}",
    )
    check(
        "c: South Korea mean_pts >= 1.0",
        south_korea_pts >= 1.0,
        f"South Korea mean_pts={south_korea_pts:.3f}",
    )
    check(
        "d: Czech Republic mean_pts >= 1.0",
        czech_pts >= 1.0,
        f"Czech Republic mean_pts={czech_pts:.3f}",
    )
    check(
        "e: total pts in range (6, 18)",
        6.0 < total < 18.0,
        f"total={total:.3f}",
    )

    print()
    if failures:
        print(f"FAILED: {len(failures)} test(s) failed — {', '.join(failures)}")
        sys.exit(1)
    else:
        print(f"All {5} tests passed.")


if __name__ == "__main__":
    main()
