# Progress Log

## Session 23 — "Today's Matches" panel (2026-06-14)

### Design decisions

**D7 — Matchday determination and time handling** (pre-implementation)

*Matchday selection:* `export_json.py` will identify the current matchday as the
earliest fixture date in `worldcup_2026.json` with at least one fixture not yet in
`wc_results.json`. This is robust to the GitHub Action running late, early, or being
skipped — it always picks the next pending matchday, not today's calendar date.

*Time-offset validation:* All fixture time strings in `worldcup_2026.json` were scanned
before implementation. Format is `"HH:MM UTC±N"`. Result:
- All UTC offsets are **whole-hour integers** (UTC-4, UTC-5, UTC-6, UTC-7 only) ✓
- Minute components within the kick-off time do include `:30` values (16:30, 19:30,
  20:30) — these are correctly handled by the standard `HH:MM` parse; no special casing needed
- No non-integer offsets (e.g. UTC-3:30) exist in the data

*BST conversion:* `BST = venue_time − venue_offset + 1 hour`.
Tournament runs late June – mid-July 2026, entirely within BST — no DST-transition logic needed.

*Output shape:* the `today` block in `predictions.json` is a list of fixture dicts
(same shape as group fixtures produced by `build_match_pred()`, plus `time_uk` and
`time_local` strings), sorted ascending by `time_uk`. If all fixtures are played the
block is empty and the frontend shows "No matches today."

### Implementation

**`scripts/export_json.py`**
- `parse_time(time_str)` — parses `"HH:MM UTC±N"` → `(hour, minute, offset_hours)`
- `compute_times(time_str)` — returns `{"time_uk": "HH:MM BST", "time_local": "HH:MM local"}`
  using BST = venue_time − offset + 1h; wraps past midnight correctly
- `build_today(fixtures_raw, wc_results, model)` — finds earliest unplayed matchday,
  builds a list of `build_match_pred()` dicts augmented with `time_uk`/`time_local`,
  sorted by `time_uk`; returns `[]` if all played
- `today` key added to serialised `predictions.json`

**`docs/index.html`**
- New "Today's Matches" section inserted above the group grid
- Empty state: "No matches today" message
- Non-empty: renders each fixture using the existing `renderFixture()` helper,
  with a time header row showing `time_uk` and `time_local` above each fixture

### Verification
- Offset-integer check: all 11 unique offsets are whole-hour ✓
- Matchday logic vs real `wc_results.json`: correctly picks the next pending matchday
- BST spot-checks: Mexico City 13:00 UTC-6 → 20:00 BST ✓
- No-matches-today state tested with synthetic full-matchday results
- Sort order verified including cross-timezone cases

---

## Session 22 — Live standings seeding (2026-06-13)

### Done
Wired actual match results into the group-stage simulator so played fixtures
contribute fixed, real scorelines rather than Poisson samples.

**`model/simulator.py` — `load_fixtures()`**
- Added optional `results: list[dict] | None = None` argument
- Builds a `(home_display, away_display)` lookup from the results list
- Stamps each fixture with three new fields: `played` (bool), `actual_home` (int|None),
  `actual_away` (int|None)
- No change to return type or callers that pass no argument

**`model/simulator.py` — `run()` group-stage loop**
- Before each group's match iteration, splits `match_idxs` into `played_idxs` and
  `remaining_idxs`
- Played fixtures: scalar arithmetic from `actual_home`/`actual_away` added as integer
  constants to all `n_sims` rows of `pts`, `gd`, `gf`, `ga`, `wins`, `drws`, `loss`
  — every simulation starts from the same locked-in scoreline
- Unplayed fixtures: existing vectorised Poisson sampling path unchanged
- `goals_home`/`goals_away` still sampled for all `n_matches` upfront; played columns
  are simply never read during accumulation

**`scripts/export_json.py`**
- Passes the already-loaded `wc_results` list to `load_fixtures(results=wc_results)`

**`app/app.py`**
- Reads `data/wc_results.json` at startup (falls back to `[]` if file absent)
- Passes the list to `load_fixtures(results=wc_results)` in `build_context()`

**`scripts/test_live_standings.py`** (new)
- Injects two synthetic played results in-memory (no disk writes):
  Mexico 2–0 South Africa and South Korea 1–1 Czech Republic in Group A
- Asserts: Mexico mean_pts ≥ 3.0, South Africa < 3.0, both draw teams ≥ 1.0,
  group total in (6, 18)
- All 5 assertions pass; prints PASS/FAIL per check and a summary line

### Verification
`python3 scripts/test_live_standings.py` output:
```
Mexico          mean_pts=6.436
South Africa    mean_pts=1.992
South Korea     mean_pts=3.653
Czech Republic  mean_pts=3.800
All 5 tests passed.
```

---

## Session 21 — Played-match UI (2026-06-11)

### Done
Updated `docs/index.html` to render played and unplayed fixtures differently.

**Played fixture changes (inside `renderFixture()`):**
- `.fixture-details` gains the `played` class → slightly muted `#f7f8fa` background
- "vs" replaced by a grey **FT** chip between team names
- W/D/L probability bar replaced by a large bold actual scoreline (`2 – 1`) with the
  original predicted score in small grey alongside (`predicted 1-0`)
- Three-state result badge below the score:
  - **✓ Correct score** (green) — outcome and exact scoreline both right
  - **~ Score wrong** (amber) — correct outcome, wrong score
  - **✗ Outcome wrong** (red) — predicted wrong winner/draw
- Accordion still expands to the full margin bar + scoreline tile breakdown for played matches

**Unplayed fixtures:** unchanged.

### Verification
Tested with `Mexico 2–1 South Africa` injected into `wc_results.json`. Model predicted
`1-0` Mexico win — correct outcome, wrong score → amber "~ Score wrong" badge rendered correctly.
All unplayed fixtures in Group A still show the standard prob bar.

---

## Session 20 — WC results recording pipeline (2026-06-11)

### Done
Added the full data pipeline for recording actual match results and feeding them back
into the model.

**New files:**
- `data/wc_results.json` — empty array initially; append one object per played match:
  `{group, home, away, home_score, away_score, date}`
- `data/wc_results_schema.json` — field-level documentation with an example entry

**`scripts/export_json.py`** — major rewrite (now fully self-contained; no longer imports
from `app.py`, eliminating the accidental double model-fit from the previous version):
- `load_wc_results()` — reads `wc_results.json`
- `wc_results_to_rows()` — converts each result to a DataFrame row: `tournament="FIFA World Cup"`
  (weight 1.00), `neutral` derived from whether the home team is in `WC_HOME_NATIONS`,
  name aliases applied via `NAME_ALIASES`; `apply_weights()` computes `match_weight` as normal
- Appended rows concatenated with historical DataFrame before `fit()` — model continuously
  refits on real WC scores as they arrive
- `build_result_index()` + `annotate_fixture()` — annotate each fixture dict with
  `played`, `actual_home`, `actual_away`, `correct_outcome`, `correct_score`

**Workflow:** add result to `wc_results.json` → run `python3 scripts/export_json.py`
(or trigger GitHub Actions) → `docs/predictions.json` updated with new odds + annotations.

### Verification
Single synthetic result (Mexico 2–1 South Africa) injected: model refitted on 11,848 rows,
output showed `1 played / 71 unplayed`, annotation fields correct. Restored to `[]`.

---

## Session 19 — GitHub Actions workflow (2026-06-11)

### Done
Created `.github/workflows/update_predictions.yml`:
- **Trigger:** `workflow_dispatch` only (manual from Actions tab — no schedule, no push trigger)
- **Steps:** checkout (full history) → Python 3.11 → pip install → run `scripts/export_json.py`
  → commit + push only if `docs/predictions.json` changed (`git diff --quiet` guard)
- **Push safety:** `git fetch origin main && git rebase origin/main` before commit to handle
  concurrent pushes without failing
- **Auth:** `permissions: contents: write` + built-in `GITHUB_TOKEN` — no PAT needed

---

## Session 18 — Static site / GitHub Pages conversion (2026-06-11)

### Done
Converted the project from a Flask-served app to a static site that can be hosted
on GitHub Pages with zero server infrastructure.

**`scripts/export_json.py`** (initial version):
- Imports model pipeline directly (bypassing Flask app)
- Calls `build_context()` once, serialises result to `docs/predictions.json` with `json.dump`
- Excludes `score_matrix` numpy arrays (already processed into `score_tiles`/`margin_pcts`)
- Prints summary: groups written, matches written, file size

**`docs/index.html`**:
- Pure HTML/CSS/JS — no framework, no CDN, no build step
- `fetch('./predictions.json')` on load; loading state while fetching; clear error state
  on failure (with specific message if opened as `file://` URL)
- Full feature parity with `app/templates/index.html`:
  - Two-column group grid, standings with colour-coded progression % and KO odds chain
  - Expandable team detail panels (click standing row)
  - Fixtures accordion with prob bar, outcome line, score tiles, margin bar, bests
  - Predicted knockout bracket (chalk, R32 → Final) with expandable ties
- Error message detects `file://` protocol and directs user to `python3 -m http.server`

**`.claude/launch.json`**: added `worldcup-static` entry (Python http.server on port 5001)
for preview panel.

### Verification
Preview server confirmed: all 12 group cards render, standings expand correctly, fixtures
accordion opens with correct prob bars and score tiles, bracket section shows R32 → Final.

---

## Session 17 — Data refresh (2026-06-11)

### Done
- Re-fetched `data/intl_results.csv` from martj42/international_results
- Row count: 49,446 → 49,477 (+31 new matches, last night's results)
- Re-ran `scripts/export_json.py` — model re-converged on 11,847 matches; all results stable
- `docs/predictions.json` regenerated

---

## Session 16 — Predicted knockout bracket view (2026-06-10)

### Done
Added a visual "chalk" knockout bracket below the group phase, with every tie
expandable to its predicted scoreline (reusing the group-fixture UI).

**Design decision:** the simulated bracket varies sim to sim, so there's no single
bracket to print. Chose a single *modal/chalk* bracket — each slot filled by the
most-likely team, favourite advancing each round — so every matchup is concrete and
can show a predicted score. (Discussed alternatives: slot-occupancy skeleton,
most-likely-matchup-per-round. Chalk chosen for the expandable-score reuse.)

**`app/app.py`**
- Factored the per-fixture prediction logic into a reusable `build_match_pred()`
  helper (margins, scoreline tiles, bests) — now used by both group fixtures and KO ties
- New `build_bracket()`: chalk winners/runners-up per group (by progression), the 8
  groups whose chalk-third has the highest `third_place_qualified` → Annex C assignment,
  then advance the higher-win-prob team through R32 → R16 → QF → SF → Final
- Returns `bracket` in context: champion + rounds, each round a list of fixture dicts
  carrying `pred_winner` / `pred_winner_flag`

**`app/templates/index.html`**
- Refactored the fixture markup into a `render_fixture(fx)` Jinja macro; group fixtures
  and bracket ties both call it (KO ties additionally show a green "Predicted to advance" line)
- New `.bracket-section` below the groups: champion banner, methodology note, one card
  per round (R32 → Final) of expandable ties

### Verification
- Bracket internally consistent: round counts 16/8/4/2/1, zero feed-forward issues
  (every team each round is a verified advancer of the previous round)
- This run: Brazil–Argentina final, Brazil predicted champion — matches the simulator's
  knockout odds (Brazil highest winner %)
- KO ties expand to the same margin bar + scoreline tiles + bests as group fixtures

---

## Session 15 — Knockout bracket simulator (2026-06-10)

### Done
Added full knockout simulation (R32 → R16 → QF → SF → Final) with best-third-place
selection. Three files changed; `annex_c.py` (Annex C third-place allocation table)
consumed read-only.

**`model/simulator.py`**
- New import: `THIRD_PLACE_ASSIGNMENTS, THIRD_PLACE_MATCH_ORDER` from `annex_c`
- Neutral-venue `lambda_cache` for all ordered team pairs, built once
- Group loop now records per-sim 1st/2nd/3rd finishers (display + model names) and
  third-place pts/gd/gf via `argsort(ranks)`
- Best-third-place: ranks all 12 third-placers per sim by (-pts, -gd, -gf+jitter);
  jitter drawn once from the shared RNG. Top 8 → Annex C key → bracket assignment
- Knockout played round-by-round, vectorised per match slot across sims; ties broken
  by coin flip. Single RNG serves group goals → tiebreak jitter → all KO rounds
- `run()` now returns `{"group_stage": df, "knockout": df}`. `group_stage` keeps all
  prior columns + `third_place_qualified`; `knockout` has r32/r16/qf/sf/final/winner
- Added `print_knockout()`; `__main__` prints both tables

**`app/app.py`**
- Unpacks the new dict; builds `ko_lookup`; adds r32/r16/qf/sf/final/winner pct to
  each standings entry

**`app/templates/index.html`**
- New "Tournament odds" column (legend `R32 · R16 · QF · SF · F · W`); winner figure
  colour-coded (≥15 green / ≥5 amber / else red), other figures plain
- Standings grid widened to 4 columns; headers shortened to Prog/Pts to fit
- Detail-panel note updated (best-third-place now modelled)

### Verification
- Invariants exact: Σr32=32, Σr16=16, Σqf=8, Σsf=4, Σfinal=2, Σwinner=1,
  Σthird_place_qualified=8, and `r32 == 1st+2nd+3rd_qual` to machine precision
- Runtime 0.7s for 10,000 sims (well under 30s budget)
- Top winners: Brazil 14.0%, Spain 11.5%, Argentina 11.5% — sensible
- All 48 winner cells render the correct colour class

### Post-MVP status
- ✅ Scoreline click-through · ✅ Team detail panel · ✅ Knockout bracket simulator

---

## Session 14 — Data refresh (2026-06-10)

### Done
- Re-fetched `data/intl_results.csv` — 49,446 → 49,473 rows (+27 new matches)
- Re-ran simulator: model re-converged on 11,842 matches, all results stable
- Largest movers: Netherlands +2.1pp (Group F), Belgium +1.6pp (Group G)
- Only rank-within-group change: Egypt overtakes New Zealand in Group G (34.9% vs 33.5%)
- App server restarted — live predictions updated

---

## Session 13 — Team detail panel in standings (2026-06-08)

### Done
- Extended `model/simulator.py` to return additional per-team stats from the 10,000 simulations:
  - `first_place` / `second_place` / `eliminated` — finish position split
  - `mean_gf` / `mean_ga` — mean goals for and against across group stage
  - `mean_wins` / `mean_draws` / `mean_losses` — expected W/D/L record over 3 games
- Updated `app/app.py` to pass all new fields through to template context
- Replaced the standings `<table>` in `app/templates/index.html` with a CSS grid layout
  using `<details class="standing-row">` elements — necessary because `<details>` is
  invalid inside `<tbody>`, so the table had to become flex/grid divs
- Each team row is now clickable; expanding reveals a 3-column detail panel:
  - Row 1: Finish 1st % / Finish 2nd % / Eliminated %
  - Row 2: Goals For (per group stage) / Goals Against / W/D/L record
  - Footer note: "Progression = top-2 finish only. Best third-place rules not modelled."
- Column alignment fixed via an inner `.summary-row` div with explicit `width: 100%; box-sizing: border-box`
  (browser quirk: `display: grid` on `<summary>` doesn't inherit parent width reliably)

### Next steps
- MVP complete. Post-MVP items: knockout bracket simulator.

---

## Session 12 — Scoreline distribution click-through (2026-06-08)

### Done
- Implemented the post-MVP scoreline click-through with no JavaScript and no external dependencies

**`app/app.py`**
- At startup, the existing `score_matrix` (10×10 numpy outer product) from `predict()` is now
  processed per fixture into two new context keys:
  - `score_tiles`: list of `{score, pct, result}` dicts for all scorelines ≥1%, sorted by
    probability descending; `result` ∈ `{home, draw, away}` for colour-coding
  - `outcome_bests`: dict with `home`/`draw`/`away` keys, each holding the single most-likely
    scoreline for that outcome

**`app/templates/index.html`**
- Each fixture row converted from a plain `<div class="fixture-row">` to a
  `<details class="fixture-details">` element — the existing probability bar and outcome
  line move into `<summary>`, so the collapsed state is pixel-identical to before
- Expanded state shows:
  - `.scoreline-grid`: flex-wrap grid of `.score-tile` chips (52×44px), colour-coded
    blue/grey/red for home/draw/away
  - `.scoreline-bests`: three summary lines — most likely scoreline per outcome with %
- CSS carefully scoped to avoid leaking between outer group accordion and inner fixture details:
  - Outer `details` styles scoped to `.group-card > details` and `.group-card > details > summary`
  - Inner `details` overrides all inherited summary styles via `.fixture-details > summary`
  - Arrow indicator (▶) only on outer summary; inner summary has no arrow

### Verified
- Nested `<details>` renders correctly; outer and inner accordions are fully independent
- Mexico vs South Africa expanded: 15 tiles, correct colour coding, correct best-of summaries

### Post-MVP status
- ✅ Scoreline distribution click-through — complete
- ⬜ Knockout bracket simulator — remains post-MVP

---

## Session 11 — WCQ confederation weight split (2026-06-08)

### Done
- Updated `model/data_prep.py` to split "FIFA World Cup qualification" into two tiers
  based on the home team's confederation, resolving the known limitation logged in D6/Session 3:
  - **UEFA / CONMEBOL → 0.85** (strongly competitive qualifiers)
  - **CAF / CONCACAF / AFC / OFC → 0.60** (less competitive qualifiers)
- Built a `CONFEDERATION` dict in `data_prep.py` covering all ~300 fitted team nations
- `apply_weights()` applies the split via a home-team lookup only for WCQ rows;
  all other competition weights are unchanged
- Sanity-checked: 998 WCQ rows at 0.85 (CONMEBOL/UEFA), 1,620 at 0.60 (other confs)

### RPS result
| | Model RPS | Baseline RPS | Improvement |
|---|---|---|---|
| Before (single weight 0.75) | 0.1668 | 0.2274 | +26.69% |
| After (split 0.85 / 0.60)   | 0.1667 | 0.2274 | +26.72% |

- Directionally correct (+0.0001) and architecturally cleaner — change retained
- Small delta expected: held-out set is 2024+ matches dominated by UNL/friendlies,
  not WCQ; the benefit shows up in better-calibrated attack/defence parameters
  rather than directly in the holdout score

### Known limitation resolved
- D6 "WCQ confederation weighting: treated as single tier" is now resolved.
  Removed from known-limitations sections in both REQUIREMENTS.md and PROGRESS.md.

### Next steps
- MVP complete. Post-MVP items from REQUIREMENTS.md remain.

---

## Session 10 — Data refresh, draw verification, λ sensitivity (2026-06-08)

### Done

**Data refresh**
- Re-fetched `data/intl_results.csv` from martj42/international_results
- Row count: 49,390 → 49,446 (+56 new matches)
- Re-ran `model/simulator.py` — model re-converged cleanly on 11,815 matches (was 11,760)
- All 12 group leaders unchanged; largest single shift was Belgium +2.1pp (Group G)
- No ranking changes anywhere; results are stable

**Group draw verification**
- Cross-checked all 12 groups in `data/worldcup_2026.json` against the official FIFA draw
- All 48 team assignments and all group labels (A–L) are correct
- Two cosmetic name variants noted (no action needed — consistent throughout codebase):
  - "Czech Republic" (our data) vs FIFA's "Czechia"
  - "Turkey" (our data) vs FIFA's "Türkiye"

**λ sensitivity test**
- Ran a one-off comparison of time-decay parameter λ=0.10 vs λ=0.15 on the same
  2024+ held-out set (2,511 matches), without modifying any production files
- Results:

| λ | Model RPS | Baseline RPS | Improvement |
|---|---|---|---|
| 0.10 (current) | 0.1667 | 0.2274 | +26.69% |
| 0.15 | 0.1668 | 0.2274 | +26.64% |

- λ=0.15 is worse by 0.0001 RPS points (noise-level); **λ=0.10 retained unchanged**

### Next steps
- MVP complete. Post-MVP items from REQUIREMENTS.md remain.

---

## Session 9 — UI polish (2026-06-07)

### Done
- Updated `app/templates/index.html` with four visual improvements:
  1. **Font size** bumped from 14px to 16px throughout; header and standings scaled proportionally
  2. **Probability bar** replaces W%/D%/L% text columns in fixture rows:
     - Three-segment CSS flexbox bar (blue = home win, grey = draw, red = away win)
     - Segment widths set by inline `width: X%` — no JS
     - Labels shown inside segment only when >15% wide to avoid crowding
  3. **Outcome summary line** below each bar: natural-language text ("Mexico win most likely")
     with most likely scoreline demoted to small grey text at the end
  4. **Country flag emoji** added before every team name in both standings and fixture rows;
     displayed in a circular container matching font height; mapping for all 48 WC teams
     added to `app/app.py` and passed through to template context
  5. **Accordion** (`<details>`/`<summary>`) wraps each group's fixtures — collapsed by default,
     pure HTML with no JS; animated arrow indicator via CSS

### Next steps
- MVP complete. Post-MVP items from REQUIREMENTS.md remain:
  1. Knockout bracket simulator (best third-place rules)
  2. Scoreline distribution click-through

---

## Session 8 — Flask web app (2026-06-07)

### Done
- Wrote `app/app.py`:
  - Pre-computes all predictions at startup: data prep → model fit → 72 match predictions
    → 10,000-run group stage simulation; held in memory, not recomputed per request
  - Single `GET /` route renders `index.html` with all data as template context
  - Imports from `model/` via `sys.path` — no logic duplication
  - Runnable from project root: `python app/app.py`
- Wrote `app/templates/index.html`:
  - Two-column grid of group cards (Groups A–L)
  - Standings table per group: team / progression % (colour-coded) / mean pts
  - Qualification line drawn after row 2 in each standings table
  - Fixture rows per group with most likely score and W/D/L probabilities
  - No external CSS or JS dependencies
- Created `.claude/launch.json` for preview tool integration

### Next steps
1. UI polish (font size, probability bar, flags, accordion)

---

## Session 7 — Group stage simulator (2026-06-07)

### Done
- Wrote `model/simulator.py`:
  - Loads `data/worldcup_2026.json`, extracts 72 group stage matches across 12 groups
  - Fits Poisson model on full dataset (11,760 matches, all years — not the train/holdout split)
  - Pre-computes lambda_home/lambda_away for all 72 fixtures, then samples all 10,000 × 72
    scorelines in one vectorised numpy call — runs in 0.3s
  - Applies home advantage for USA/Canada/Mexico when listed as designated home team (team1)
    in the fixture data; all other matches treated as neutral
  - Standings per group: 3pts win / 1pt draw / 0 loss; tiebreakers GD then GF
  - Top 2 per group advance (best third-place rules deferred to post-MVP per D5)
  - Warns if any WC team is missing from training data (none missing in practice)
  - Prints progression probability and mean expected points per team, sorted by group
    then progression descending

### Results summary (seed=42, 10,000 simulations)
| Group | 1st (prob) | 2nd (prob) | Tightest contest |
|---|---|---|---|
| A | Mexico 77.8% | South Korea 50.4% | SKO vs CZE neck-and-neck (50.4/49.4%) |
| B | Switzerland 84.1% | Canada 74.8% | |
| C | Brazil 93.2% | Morocco 71.5% | |
| D | USA 61.4% | Australia 48.7% | Most open group — 4 teams within 18pp |
| E | Germany 87.2% | Ecuador 72.5% | |
| F | Netherlands 74.9% | Japan 56.2% | |
| G | Belgium 81.3% | Iran 49.5% | |
| H | Spain 94.1% | Uruguay 80.7% | |
| I | France 86.1% | Senegal 50.9% | |
| J | Argentina 93.2% | Austria 49.7% | Argentina highest mean pts (7.03) |
| K | Portugal 83.5% | Colombia 80.5% | Clearest two-horse race |
| L | England 91.5% | Croatia 75.1% | |

### Sanity checks passed
- Mean pts ↔ progression correlation holds in every group
- Host nations elevated by home advantage: Mexico 77.8%, Canada 74.8%, USA 61.4%
- Minnow probabilities realistic and non-zero: Haiti 6.1%, Curaçao 6.0%, Cape Verde 9.5%
- Runtime: 0.3s for 10,000 simulations

### Next steps
1. Flask backend + frontend

---

## Session 6 — Host-nation home-win diagnostic (2026-06-07)

### Done
- Extended `model/validate.py` with a host-nation diagnostic section (all prior output untouched)
- Filtered gap-1 held-out matches by whether the home team is USA, Canada, or Mexico
- Compared mean predicted P(home win) vs actual home win rate for host nations vs all others

### Results
| Segment | n | Pred HW | Actual HW | Bias |
|---|---|---|---|---|
| USA / Canada / Mexico as home | 19 | 69.3% | 78.9% | −0.097 |
| All other gap-1 home teams | 805 | 46.1% | 48.4% | −0.023 |

- The overall gap-1 bias (−0.025) reported in Session 5 was almost entirely driven by the 19 host-nation matches
- The model under-predicts host-nation home wins by ~10 percentage points at gap 1
- The general (non-host) gap-1 bias (−0.023) is negligible noise

### Interpretation
The trained home advantage coefficient is not fully capturing how dominant USA/Canada/Mexico
are on their own turf in competitive fixtures. Small sample (n=19) so some variance expected,
but direction is consistent with prior expectations.

### Impact on WC predictions
For group stage fixtures where USA, Canada, or Mexico are the designated home team, the model
will likely under-price their win probability. Noted as a known limitation — no code change made.
Could be addressed post-MVP by applying a calibration adjustment to host-nation home advantage.

### Next steps
1. Group stage simulator (10,000 runs)
2. Flask backend + frontend

---

## Session 5 — Tier-bias analysis (2026-06-07)

### Done
- Extended `model/validate.py` with a tier-bias analysis section (existing output untouched):
  - Computes composite strength score per team: `attack - defence`
  - Quintile-ranks all 300 fitted teams into tiers Q1 (weakest) → Q5 (strongest)
  - Labels each held-out match by tier gap (0–4) and match type (6 categories)
  - Table 1: RPS by tier gap with home-win bias check
  - Table 2: RPS by match type sorted by model RPS
  - Overall and per-bucket home-win bias (predicted vs actual)

### Key findings
**RPS by tier gap**
- Model edge over baseline scales sharply with mismatch:
  gap 0 (evenly matched): +7.7% | gap 1: +25.0% | gap 2: +40.9% | gap 3: +61.3% | gap 4: +86.8%
- Evenly-matched fixtures are the hardest to beat the baseline on — football noise dominates

**RPS by match type**
- Elite vs minnow: model RPS 0.084 vs baseline 0.244 (+65.7%) — strongest edge
- Mid vs mid: model RPS 0.214 vs baseline 0.221 (+3.1%) — almost no edge over baseline
- Elite vs elite: +15.6% — decent but noisy

**Home-win bias**
- Overall bias: −0.012 (model very slightly under-predicts home wins — negligible)
- Largest bias: tier-gap-1 matches (−0.025, n=824): model under-estimates home-win
  probability when one team is marginally better. Relevant for USA/Canada/Mexico
  fixtures against mid-tier opponents — may slightly under-price the host advantage.
- No systematic over- or under-prediction of upsets

### No changes to model or data prep
Tier-bias section is a post-hoc analysis only — model parameters unchanged.

### Next steps
1. Group stage simulator (10,000 runs)
2. Flask backend + frontend

---

## Session 4 — RPS validation (2026-06-07)

### Done
- Wrote `model/validate.py`:
  - Splits data at 2024-01-01: 9,302 training / 2,458 held-out matches
  - Refits model on training set only; time-decay weights anchored to 2023-12-31
    to avoid leaking future recency into the evaluation
  - Computes RPS per match using exact formula from requirements
  - Reports naive baseline (historical H/D/A frequencies from training set)
  - Per-tournament breakdown for matches with n ≥ 5

### Validation results
- **Model RPS: 0.1668**
- **Baseline RPS: 0.2276**
- **Model beats baseline by 26.7%** across 2,456 held-out matches (2 skipped — unseen teams)
- Training baseline frequencies: H 47.7% / D 23.0% / A 29.3%
- Home advantage on training-only fit: +29.7% goals (consistent with full-data fit)

### Per-tournament findings
Model beats baseline on all major tournaments. Three minor exceptions:
- Gulf Cup (15 matches): model RPS 0.267 vs baseline 0.247 — small invitational, irrelevant to WC
- MSG Prime Minister's Cup (11 matches): similar — minor Pacific invitational
- King's Cup (8 matches): similar — Thai invitational
All three are low-weight, low-volume tournaments with no WC relevance.

### Strongest model gains
- UEFA Euro qualification: −40% vs baseline (best in show, small sample)
- Gold Cup: −36% vs baseline
- WC qualification: −37% vs baseline
- CONCACAF Nations League: −31% vs baseline

### No changes required to model or data prep
Validation run as a clean read-only check — `poisson_model.py` and `data_prep.py` untouched.

### Next steps
1. Group stage simulator (10,000 runs)
2. Flask backend + frontend

---

## Session 3 — Data prep + model fitting (2026-06-05)

### Done
- Wrote `model/data_prep.py`:
  - Loads `intl_results.csv`, filters to 2014+, drops NA scores
  - Applies name aliases (Bosnia & Herzegovina, USA)
  - Applies time-decay weight e^(-0.1 · age_in_years)
  - Assigns competition weights (see D6 below for tier structure)
  - Outputs clean dataframe with `match_weight` column ready for model fitting
- Wrote `model/poisson_model.py`:
  - Weighted Poisson MLE via L-BFGS-B (scipy)
  - Sum-to-zero constraint on attack/defence for identifiability
  - L2 regularisation scaled by 1/n_matches for sparse-nation shrinkage (D3)
  - Home advantage coefficient trained from data; WC predictions use it only
    for USA, Canada, Mexico in their territory (D2)
  - `predict()` returns win/draw/loss probs, expected goals, most likely score,
    and full scoreline matrix up to 10×10

### Key numbers (fitted on 11,760 matches)
- Home advantage: +28.9% goals (coefficient 0.254) — consistent with literature
- Global mean goals at neutral venue: 1.16 per team
- Teams fitted: 300

### Competition weight assignments (D6 resolved)
After inspecting `tournament` value_counts, final tiers:
- Tier 1 (1.00): FIFA World Cup, UEFA Euro, Copa América, African Cup of Nations,
  AFC Asian Cup, Gold Cup, Oceania Nations Cup, Confederations Cup
- Tier 2 (0.75): FIFA World Cup qualification (all confederations blended —
  source data has single label, confederation split not possible without lookup table)
- Tier 2/3 (0.50–0.65): Continental qualifiers, UEFA/CONCACAF Nations Leagues
- Tier 5 (0.20–0.25): Friendlies, FIFA Series, invitational cups
- Default (0.35): Regional/minor tournaments (COSAFA, Island Games, CONIFA, etc.)

### Known limitation logged
WCQ confederation weighting: `FIFA World Cup qualification` is a single label
covering all confederations. UEFA/CONMEBOL qualifiers are stronger than OFC/CONCACAF
but cannot be distinguished from the label alone. A team→confederation lookup would
be needed to split them. Deferred — treat as a single tier for now; revisit after
RPS validation if calibration per confederation looks poor.

### Next steps
1. ~~RPS validation on 2024+ held-out set~~ ✓
2. Group stage simulator (10,000 runs)
3. Flask backend + frontend

---

## Session 2 — Model design decisions (2026-06-05)

### Decisions made (pre-code)

**D1 — Training window**
Time-decay weighting from 2014 onward. Each match weighted by e^(-λ·age_in_years),
λ ≈ 0.1. Rationale: avoids arbitrary hard cutoff; gives sparse nations more data
while down-weighting older squads that bear little resemblance to today's teams.

**D2 — Home advantage**
Train with a home advantage coefficient as normal (historical data contains
home/away matches). For WC predictions: apply zero home advantage for all
teams *except* USA, Canada, and Mexico, who receive the trained home advantage
coefficient for fixtures played in their respective territory.
Requires cross-referencing venue/city in fixture data to determine host country.

**D3 — Sparse nation shrinkage**
Implement global mean shrinkage. Each team's attack and defence ratings are
blended toward the global mean, weighted by number of matches. The less data
a team has, the more they are pulled toward average. Protects predictions for
low-match-count nations (Curaçao ~60, New Zealand ~52, Haiti ~68, Cape Verde ~73)
from being driven by small-sample noise.

**D4 — Validation**
Quick Ranked Probability Score (RPS) check before shipping predictions.
Hold out matches from 2024 onward; train on everything prior; compute RPS
on held-out set. To be walked through during code session.

**D5 — Scope**
MVP covers group stage only. Knockout bracket (including best third-place
qualification rules) deferred to post-MVP.

**D6 — Competition weighting**
Weight each match by competitive importance as well as recency. Final weights
combined multiplicatively (competition weight × time-decay weight).
Exact tier weights to be determined after inspecting `tournament` column labels
in data-prep script. Guiding principle: weight by how much winning mattered
to both teams. Provisional tiers:
  - Tier 1 (1.0): World Cup finals, major continental championships
  - Tier 2 (0.85): WC qualification — competitive confederations (UEFA, CONMEBOL)
  - Tier 3 (0.6): WC qualification — less competitive confederations (CAF, CONCACAF, AFC, OFC)
  - Tier 4 (0.5): Continental qualification, Nations League
  - Tier 5 (0.2): Friendlies
Exact tier assignments confirmed once labels are inspected.

### Next steps
1. Data-prep script: load, inspect tournament labels, assign competition weights,
   apply time-decay, apply name aliases, drop NA scores.
2. Fit Poisson model with shrinkage and home advantage coefficient.
3. RPS validation on 2024+ held-out set.
4. Group stage simulator (10,000 runs).
5. Flask backend + frontend.

---

## Session 1 — Data acquisition (2026-06-05)

### Done
- Set up working project structure (data/, model/, app/templates/).
- Fetched 2026 fixture data: openfootball/worldcup.json → `data/worldcup_2026.json`
  - 104 matches, full expanded 48-team / 12-group format.
  - All 48 group-stage teams are named (draw fully populated).
  - Knockout matches (Round of 32 onward) use placeholder slots ("1A", "2B"
    etc.) — to be resolved by the bracket simulator later.
- Downloaded historical international results: martj42/international_results
  - `data/intl_results.csv` — 49,390 rows, 1872 → 2026.
  - `data/intl_shootouts.csv` — penalty shootout outcomes.
  - 49,318 rows have actual scores; ~8,000 matches since 2018-01-01.

### Data source note
- Requirements named football-data.co.uk for historical results, but that
  source is club/league-focused. Switched to martj42/international_results,
  the standard open dataset for international fixtures. REQUIREMENTS.md updated.

### Issues flagged (carried forward)
1. **Team-name reconciliation** — two aliases required:
     - "Bosnia & Herzegovina"  → "Bosnia and Herzegovina"
     - "USA"                   → "United States"
   All other 46 WC team names match exactly.
2. **Filter unplayed fixtures** — intl_results.csv contains future 2026 WC
   matches with score = NA. Must drop before fitting.
3. **Sparse data for smaller nations** — addressed by D3 (shrinkage) above.
4. **Provisional groups** — cross-check openfootball draw against official
   FIFA source before going live.

### Data sources (re-fetchable, key-free)
- Fixtures:  https://raw.githubusercontent.com/openfootball/worldcup.json/master/2026/worldcup.json
- Results:   https://raw.githubusercontent.com/martj42/international_results/master/results.csv
- Shootouts: https://raw.githubusercontent.com/martj42/international_results/master/shootouts.csv
