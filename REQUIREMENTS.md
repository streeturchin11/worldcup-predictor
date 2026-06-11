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
- Python (Flask) backend
- Plain HTML/JS frontend
- Pandas + Scipy for stats
- Fixture data: openfootball/worldcup.json (GitHub, no API key needed)
- Historical results: martj42/international_results (GitHub, no API key needed)
  (Note: football-data.co.uk ruled out — club/league focused, not international)

## Project structure
worldcup-predictor/
├── REQUIREMENTS.md
├── PROGRESS.md
├── data/          # historical results + fixture data
├── model/         # Poisson model code
└── app/
    ├── app.py     # Flask backend
    └── templates/
        └── index.html

## Risks
- Data quality for smaller nations may be patchy — mitigated by shrinkage
- 2026 bracket complexity (48 teams, best third-place rules) — MVP scoped to
  group stage; knockout bracket is post-MVP
- Basic Poisson model won't account for injuries or squad motivation
- Competition weight tiers are a judgement call, not a derived truth
- Scope creep — protect MVP ruthlessly

## Current status
MVP complete and running. All model work, simulation, and frontend done. Post-MVP items remain.

Data last refreshed: 2026-06-08 (49,446 rows). Group draw verified against official FIFA source — all correct. Time-decay λ=0.10 confirmed optimal vs λ=0.15 on held-out set.

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
