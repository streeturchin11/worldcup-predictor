# World Cup Predictor — Requirements

## Goal
Build a simple web app that predicts World Cup match results using a
Poisson regression model. Primary motivation is beating friends in a
results predictor competition while learning a bit of stats/Python along
the way.

## Tournament
2026 FIFA World Cup (USA/Canada/Mexico) — 48 teams, expanded format.

## What the app outputs
For each fixture:
- Most likely scoreline (e.g. 1-1)
- Win / Draw / Loss probabilities (e.g. 38% / 28% / 34%)

From those, a tournament bracket simulator that shows each team's
probability of progressing through each round.

## Post-MVP
- ~~Clickable fixture UI that shows full scoreline probability distribution~~ ✓ (Session 12)
- ~~Knockout bracket simulation~~ ✓ (Session 15) — best-third-place via Annex C, R32→Final
- ~~Static site on GitHub Pages~~ ✓ (Session 18) — `scripts/export_json.py` + `docs/index.html`
- ~~GitHub Actions one-click regeneration~~ ✓ (Session 19) — manual `workflow_dispatch` trigger
- ~~Record actual WC results + refit model~~ ✓ (Session 20) — `data/wc_results.json` feeds back into training
- ~~Display actual results vs predictions in UI~~ ✓ (Session 21) — result badge, actual score, FT label
- ~~Lock played fixtures into simulator standings~~ ✓ (Session 22) — real scorelines as constants, Poisson sampling only for remaining matches
- "Today's matches" panel — shown above the group grid, sorted by UK kickoff time (BST), showing UK time and venue-local time side by side

## The model
- Poisson regression on historical international results (2014 onward)
- Time-decay weighting: e^(-0.1 · age_in_years) so recent matches count more
- Competition weighting: matches weighted by competitive importance (Tier 1–5);
  weights confirmed after inspecting tournament labels — see Session 3 in PROGRESS.md.
  WCQ confederation split implemented: UEFA/CONMEBOL → 0.85, CAF/CONCACAF/AFC/OFC → 0.60
- Each team gets an attack strength and defensive weakness rating
- Global mean shrinkage applied to teams with sparse match history
- Home advantage coefficient trained from historical data; applied only to
  USA, Canada, and Mexico for fixtures in their own territory; zero for all
  other WC predictions (neutral venues)
- Simulate group stage 10,000 times to get progression probabilities

## Tech stack
- Python (Flask) backend — local development and preview only
- Static site (`docs/`) served on GitHub Pages — production
- Plain HTML/JS frontend (no framework, no CDN)
- Pandas + Scipy for stats
- `scripts/export_json.py` generates `docs/predictions.json` — all model output serialised once
- GitHub Actions (`workflow_dispatch` + daily schedule at 07:00 UTC) for automated regeneration
- Fixture data: openfootball/worldcup.json (GitHub, no API key needed)
- Historical results: martj42/international_results (GitHub, no API key needed)
  (Note: football-data.co.uk ruled out — club/league focused, not international)

## Project structure
worldcup-predictor/
├── REQUIREMENTS.md
├── PROGRESS.md
├── CLAUDE.md
├── data/
│   ├── intl_results.csv          # historical match data (49,477 rows)
│   ├── worldcup_2026.json        # 2026 fixture data
│   ├── wc_results.json           # actual WC scores recorded by hand
│   └── wc_results_schema.json    # schema documentation (manual entry now replaced by sync_wc_results.py)
├── model/                        # Poisson model code
├── scripts/
│   ├── export_json.py            # generates docs/predictions.json
│   ├── sync_wc_results.py        # syncs wc_results.json from intl_results.csv
│   └── test_live_standings.py    # verifies played-result seeding
├── docs/
│   ├── index.html                # static frontend (GitHub Pages)
│   └── predictions.json          # generated — all predictions + results
├── app/
│   ├── app.py                    # Flask backend (local dev / preview only)
│   └── templates/
│       └── index.html            # Jinja2 template (mirrors docs/index.html logic)
└── .github/
    └── workflows/
        └── update_predictions.yml  # daily + manual trigger: sync results, refit, push

## Design decisions

**D7 — "Today's matches" matchday determination and time handling**

*Matchday selection:* `export_json.py` determines the current matchday as the earliest
fixture date in `worldcup_2026.json` that has at least one fixture not yet recorded in
`wc_results.json`. This is robust to the Action running late, early, or being skipped —
it always picks the next pending matchday rather than today's calendar date.
If all fixtures are played, the `today` block is empty and the frontend shows "No matches today."

*Time parsing:* fixture times in `worldcup_2026.json` are formatted `"HH:MM UTC±N"`.
Before implementation, all offsets were scanned and confirmed to be whole-hour integers
(UTC-4, UTC-5, UTC-6, UTC-7). Minute components within the time (e.g. 16:30, 19:30, 20:30)
are correctly parsed by the `HH:MM` portion.

*BST conversion:* `BST = venue_time − venue_offset + 1 hour`.
The tournament runs entirely within BST (late June – mid-July 2026), so no DST-transition
logic is needed.

*Output:* the `today` block in `predictions.json` is a list of fixture dicts (same shape
as group fixtures, plus `time_uk` and `time_local` strings), sorted by `time_uk`.
The frontend reuses `renderFixture()` so scoreline tiles and prob bars work identically.

## Risks
- Data quality for smaller nations may be patchy — mitigated by shrinkage
- 2026 bracket complexity (48 teams, best third-place rules) — MVP scoped to
  group stage; knockout bracket is post-MVP
- Basic Poisson model won't account for injuries or squad motivation
- Competition weight tiers are a judgement call, not a derived truth
- Scope creep — protect MVP ruthlessly

## Current status
MVP and all scoped post-MVP items complete. Static site live on GitHub Pages; predictions
regenerated by running `python3 scripts/export_json.py` or triggering the GitHub Actions workflow.
Actual WC results can be recorded in `data/wc_results.json` — they are folded back into model
training on the next export run and displayed in the UI with result badges.

Data last refreshed: 2026-06-11 (49,477 rows). Group draw verified against official FIFA source — all correct. Time-decay λ=0.10 confirmed optimal vs λ=0.15 on held-out set.

## Known limitations
- **Host-nation HW under-prediction:** model under-predicts P(home win) for USA/Canada/Mexico
  by ~10pp in gap-1 fixtures (n=19, so some variance). WC predictions for these teams will
  be slightly conservative. Post-MVP: consider a calibration adjustment to host-nation home advantage.
- ~~**WCQ confederation weighting:** single label covers all confederations~~ — resolved in Session 11: UEFA/CONMEBOL WCQ weighted 0.85, all others 0.60.

## Next steps
1. ~~Data-prep script~~ ✓ (`model/data_prep.py`)
2. ~~Fit Poisson model with shrinkage and home advantage~~ ✓ (`model/poisson_model.py`)
3. ~~RPS validation on 2024+ held-out set~~ ✓ (`model/validate.py`) — beats baseline by 26.7%
4. ~~Tier-bias analysis~~ ✓ (`model/validate.py`) — model edge scales with mismatch; slight HW under-prediction at gap 1
5. ~~Host-nation HW diagnostic~~ ✓ (`model/validate.py`) — −0.097 bias for USA/CAN/MEX at gap 1; logged as known limitation
6. ~~Group stage simulator (10,000 runs)~~ ✓ (`model/simulator.py`) — 0.3s runtime, results look good
7. ~~Flask backend~~ ✓ (`app/app.py`) — single route, all predictions pre-computed at startup
8. ~~Frontend~~ ✓ (`app/templates/index.html`) — probability bars, flags, accordion, colour-coded progression
9. ~~Scoreline distribution click-through~~ ✓ (`app/app.py` + `app/templates/index.html`) — nested details, colour-coded tiles, best-of summaries
10. ~~Team detail panel~~ ✓ (`model/simulator.py` + `app/app.py` + `app/templates/index.html`) — click team name to see 1st/2nd/elim %, GF/GA, W/D/L record
11. ~~Knockout bracket simulator~~ ✓ (`model/simulator.py` + `app/app.py` + `app/templates/index.html`) — best-third-place via Annex C, full R32→Final, Tournament odds column
12. ~~Static site export~~ ✓ (`scripts/export_json.py` + `docs/`) — self-contained, no server needed
13. ~~GitHub Actions workflow~~ ✓ (`.github/workflows/update_predictions.yml`) — one-click regeneration from GitHub UI
14. ~~WC results pipeline~~ ✓ (`data/wc_results.json` + `scripts/export_json.py`) — actual results fold back into training and annotate predictions
15. ~~Played-match UI~~ ✓ (`docs/index.html`) — result badge, large actual score, FT chip, muted background
