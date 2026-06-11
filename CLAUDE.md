# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this project is

A Python/Flask web app that predicts 2026 World Cup match outcomes. It fits a weighted Poisson regression model on historical international results, simulates the group stage 10,000 times, and serves the results as a single-page web app.

## Running the app

```bash
python app/app.py          # starts Flask on http://localhost:5000
```

Startup takes ~15 seconds (model fit + 10,000-run simulation). All predictions are pre-computed once and held in memory — no recomputation per request.

## Running validation

```bash
python model/validate.py   # RPS validation + tier-bias analysis; prompts for Enter
```

## Running the simulator standalone

```bash
python model/simulator.py  # prints group stage progression probabilities to stdout
```

## Architecture

All model logic lives in `model/`; the Flask app imports from there via `sys.path`.

| File | Purpose |
|---|---|
| `model/data_prep.py` | Loads `data/intl_results.csv`, filters 2014+, applies name aliases, time-decay and competition weights. Entry point: `prepare_data(verbose=True)` |
| `model/poisson_model.py` | Weighted Poisson MLE via L-BFGS-B. Entry points: `fit(df)` → model dict, `predict(model, home, away, neutral)` → probs + score matrix. `WC_HOME_NATIONS` = `{"United States", "Canada", "Mexico"}` |
| `model/simulator.py` | Loads `data/worldcup_2026.json`, vectorises 10k × 72 Poisson samples, computes group standings. Entry points: `load_fixtures()`, `run(fixtures, model)` |
| `model/validate.py` | Train/holdout split at 2024-01-01, RPS vs naive baseline, tier-bias analysis, host-nation diagnostic |
| `app/app.py` | Flask app. Calls `prepare_data` → `fit` → `load_fixtures` → `simulate` at startup. Single route `GET /` |
| `app/templates/index.html` | Single-page Jinja template. No external CSS/JS dependencies |

## Key design decisions (see PROGRESS.md for full rationale)

- **Team names:** fixture JSON uses `"USA"` and `"Bosnia & Herzegovina"`; model uses `"United States"` and `"Bosnia and Herzegovina"`. Aliases defined in `data_prep.NAME_ALIASES` and applied in both `data_prep.py` and `simulator.load_fixtures()`.
- **Home advantage:** trained from historical data but applied in WC predictions **only** for USA, Canada, Mexico when listed as `team1` (designated home team) in the fixture JSON. All other WC matches are `neutral=True`.
- **Competition weights:** tiered dict at the top of `data_prep.py` — easy to adjust. Tier 1 = 1.0 (World Cup, major continental), down to 0.20 (friendlies). `DEFAULT_WEIGHT = 0.35` for unlisted tournaments.
- **Shrinkage:** L2 regularisation in `poisson_model.py` scaled by `1/n_matches` per team. `REGULARISATION = 20.0` constant controls strength.
- **Identifiability:** sum-to-zero constraint on attack/defence parameters (last team derived as `-sum(others)`). Without this the intercept and attack mean drift.
- **Validation result:** model beats naive baseline by 26.7% RPS on 2,456 held-out 2024+ matches. Known limitation: slight home-win under-prediction for USA/Canada/Mexico at tier gap 1 (~−0.097 bias, n=19).

## Data files

- `data/intl_results.csv` — 49,390 rows, 1872–2026, from martj42/international_results
- `data/worldcup_2026.json` — 104 matches (72 group stage + 32 knockout placeholders) from openfootball

Re-fetch commands:
```bash
curl -o data/intl_results.csv https://raw.githubusercontent.com/martj42/international_results/master/results.csv
curl -o data/worldcup_2026.json https://raw.githubusercontent.com/openfootball/worldcup.json/master/2026/worldcup.json
```

## Post-MVP scope

- Knockout bracket simulator (best third-place qualification rules deferred)
- Scoreline distribution click-through per fixture
