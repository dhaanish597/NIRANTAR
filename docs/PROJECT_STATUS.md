# PROJECT_STATUS.md — full state audit, NIRANTAR / SIH26001

**Audit date:** 2026-08-30
**Audited against:** `main` @ `ab785e5` (94 commits total), plus 7 modified + 6 untracked files in the working tree.
**Method:** direct file reading, `git log`/`git status`, byte-level encoding scans, and a full run of both test suites on this machine. Every number in this document was measured today or read out of a committed artifact. Nothing here is estimated. Where a claim could not be verified, it says so.

> **Read §0 first.** It is the whole document in one screen. Everything after it is the detail.

---

## 0. Executive summary

| Question you asked | Short answer |
|---|---|
| **What stage are we at?** | **74 of 89 planned tasks done (83%).** Phases 0–4 are functionally complete. Phase 5 is 9/12. **Phase 6 (rehearsal → freeze → submit) is 0/7 and has not been started.** |
| **What works?** | The full demo spine works for real, end to end, on real data: **Run Case Study → real trained model + real published rainfall thresholds → real runout → real road severance → real RII → real EPS → real routing → real Action Card → real hash-chained audit trail**, rendered on the map. 5 officer workspaces + a citizen PWA. **1,038 tests pass.** |
| **What's hard-coded?** | Concentrated in **4 files** and it is not evenly bad. One file (`frontend/src/lib/whatIfDemo.ts`) contains **fabricated village populations and road names on a judge-facing screen** — that is the single biggest credibility risk in the repo. Two forecast files duplicate ~10 uncited constants in two languages. `config.py` itself is exemplary. Full inventory in §3 and Appendix A. |
| **What's missing?** | **1 red test** (a one-line encoding fix that currently leaves rule 14 unenforced), **6 missing data artifacts** (incl. the offline basemap and both non-Aizawl road graphs), **no `docs/DEMO_SCRIPT.md`**, **no `make demo-check`**, **no aeroplane-mode rehearsal**. |
| **What's needed from you?** | 3 external credentials (all optional — none blocks the demo), 4 decisions, and 5 things only a human at the physical demo laptop can do. §5. |

### The three things that matter most, in order

1. **`backend/app/api/whatif.py` starts with a UTF-8 BOM and contains a mojibake em-dash.** This makes `tests/test_no_wallclock.py` die with `SyntaxError` before its AST walk scans anything — so **CLAUDE.md rule 14 is currently unenforced**, and it is hiding a real live violation at `backend/app/commander/store.py:20`. One-line fix, ~2 minutes, unblocks a green suite. (§3.5.1)
2. **`frontend/src/lib/whatIfDemo.ts` fabricates 6 village populations (Durtlang 6,400; Hunthar 3,100; …) and 7 road names**, and it renders on `/console/whatif` where a judge can click it. The real WorldPop-derived populations for those same villages are under 100 each. A geologist or a district officer on the panel will catch this. (§3.1.1)
3. **Phase 6 is entirely unstarted and it is 100% yours.** Deadline is **20 Sep 2026** — 21 days. No demo script, no frozen tag, no video fallback, no rehearsed answers to the 10 hard judge questions. This is now the critical path, not code. (§5.1)

---

# 1. Where we are

## 1.1 Headline

`docs/BUILD_PLAN.md` is the authoritative checklist and its own checkboxes say:

```
checked:   74
unchecked: 15
total:     89
```

**Note on stale documentation:** `CLAUDE.md` §11 ("Current State") and §12 ("Session Log") were last updated for **Session 4, 2026-08-26**. There have been **25 commits since then**, none of which are recorded. Five entire subsystems built in those 25 commits are absent from CLAUDE.md. Per CLAUDE.md's own instruction ("If anything in this file contradicts what you find in the code, the code is wrong or this file is stale — say so explicitly"): **CLAUDE.md §11 is stale, the code is right.** Full list of contradictions in §4.5.

## 1.2 Per-phase state

| Phase | Title | Done | State |
|---|---|---|---|
| **0** | Vertical slice (stub end-to-end) | 16/16 | ✅ Complete. Superseded — every Phase-0 stub has been replaced by a real module. |
| **1** | Real data + real risk model | 17/19 | ✅ P0 critical path complete. Open: **1.4** (lithology, P1, deliberately deferred), **1.9** (InSAR, P2, cut-first candidate). |
| **2** | Impact layer (runout / RII / EPS) | 6/6 | ✅ Complete. This is the signature differentiator and it is real. |
| **3** | Decision + dissemination | 9/11 | ✅ P0 complete. Open: **3.9** (TTS/voice, P1 — nothing built), **3.11** (crowdsourced photo CV, P2 — explicit cut-first). |
| **4** | Replay engine + case studies | 6/7 | ✅ Complete for Aizawl / Wayanad / Tupul. Open: **4.6** (Sikkim GLOF, P2, stretch — its own text says "only attempt if Phases 0–4 are green"). |
| **5** | Offline, polish, credibility | 9/12 | 🟡 Open: **5.4 (P0)** aeroplane-mode rehearsal, **5.9 (P1)** visual design pass, **5.11 (P0)** `make demo-check`. |
| **6** | Rehearsal → freeze → submit | **0/7** | ❌ **Not started.** All 7 tasks. 5 of them are P0. |

## 1.3 The 15 unchecked tasks, with an honest read on each

| # | P | Task | Honest read |
|---|---|---|---|
| 1.4 | P1 | Lithology / geology layer from GSI Bhukosh | **Deliberately deferred, not forgotten.** `cells.gpkg` already has `lithology_class` as an explicit null; the eval report lists it as one of 4 features that are 100% missing. Documented `coarse_fallback` path exists. Needs your Bhukosh access (§5.3). |
| 1.9 | P2 | Sentinel-1 InSAR displacement | **Not attempted.** #1 on the plan's own cut list. Safe to drop; say so on screen rather than fake it. |
| 3.9 | P1 | IndicTrans2 + Indic-Parler-TTS voice alerts | **Nothing built.** `data/audio/` does not exist. The citizen app already handles this honestly — a disabled button reading *"Voice alert not available yet"*. This is the largest remaining judge-visible feature gap. |
| 3.11 | P2 | Crowdsourced photo + spam classifier | **Not attempted.** The plan says "cut this before cutting anything above it." The citizen app has a disabled *"Add photo · camera integration pending"* button. Answers problem-statement clause (e), so worth a sentence in the pitch even unbuilt. |
| 4.6 | P2 | `sikkim-glof-2023` scenario | **Not attempted, correctly.** Different hazard physics. Its own instruction gates it behind green Phases 0–4. |
| **5.4** | **P0** | **Aeroplane-mode rehearsal on the real demo machine** | **Not done. Requires you** — physically disable networking and run the full Aizawl replay. This is the single highest-value untested assumption in the project. See §5.1. |
| 5.9 | P1 | Visual design pass | **Not done as a dedicated pass.** A lot of styling exists (5 workspaces, dark console aesthetic, `dashboard-workspace.css`), but no one has done the deliberate typography/whitespace/hierarchy sweep the task describes. |
| **5.11** | **P0** | **`make demo-check`** | **Not built.** `Makefile` has no `demo-check` target. This is the preflight that is supposed to run before every rehearsal. Also see §4.4 — `make data` and `make graph` are still `@echo "TODO"` placeholders. |
| 6.1 | P0 | `docs/DEMO_SCRIPT.md` | **File does not exist.** Confirmed by directory listing. |
| 6.2 | P0 | Freeze the build, tag it | Not done. No tags. |
| 6.3 | P0 | 3-minute screen capture fallback | Not done. |
| 6.4 | P0 | Rehearse the 10 hard judge questions | Not done. **This one is pure human work and it is where the pitch is won or lost.** |
| 6.5 | P1 | One-page architecture handout | Not done. |
| 6.6 | P0 | Final demo-check, 5 clean runs, 2 operators | Not done. |
| 6.7 | P0 | Submit | Not done. |

## 1.4 Test suite state — measured on this machine today

### Backend — `pytest` (full suite)

```
1 failed, 771 passed, 12 skipped, 3 warnings in 1578.26s (0:26:18)
FAILED tests/test_no_wallclock.py::test_no_wallclock_calls_outside_core_clock
```

- **771 passing.** One failure. Twelve skips.
- The **single failure is not a logic bug** — it is the `whatif.py` encoding corruption in §3.5.1. The test's AST walk crashes on `SyntaxError: invalid non-printable character U+FEFF` at `whatif.py` line 1 before it inspects a single file.
- The **12 skips are legitimate**: they are real-data-dependent tests that skip when a `data/` artifact is absent. They will run once the missing artifacts in §4.2 are regenerated.
- Suite takes **26 minutes** — worth knowing before you run it.

### Frontend — `vitest`

```
Test Files  44 passed (44)
     Tests  267 passed (267)
  Duration  167.12s
```

Genuinely green. **Important caveat for whoever runs this next:** the default parallel run on this machine produces `Errors 11` — `[vitest-pool]: Failed to start threads worker` — and still exits 0, leaving ~10 files silently unrun. That is a machine/parallelism artifact, not a code failure. Run it serially to get a trustworthy result:

```bash
cd frontend && npx vitest run --no-file-parallelism --testTimeout=30000
```

### Combined: **1,038 tests pass, 1 fails, 12 skip.**

## 1.5 Uncommitted work in the tree right now

**7 modified files** (+119 insertions, −5 deletions) and **6 untracked files** — together they are one coherent, unfinished feature: a **5-day risk forecast strip** on the dashboard.

| File | State | What it is |
|---|---|---|
| `backend/app/schemas/forecast.py` | untracked | Clean Pydantic contract. `source: Literal["LIVE","MODEL","FALLBACK"]`, exactly 5 days enforced. Good. |
| `backend/app/risk/forecast.py` | untracked | The adapter. Honest docstring, correctly stamps `source="FALLBACK"`, routes time through `LiveClock()`. **But it is the most magic-number-dense backend module in the repo** — see §3.2.1. |
| `backend/tests/test_forecast.py` | untracked | Tests for the above. |
| `frontend/src/lib/forecast.ts` | untracked | **Duplicates every one of those constants in TypeScript.** §3.2.2. |
| `frontend/src/lib/forecast.test.ts` | untracked | Tests for the above. |
| `ml_model_metrics.ipynb` | untracked, 93 KB | A notebook. Not referenced by any build step. Decide whether it is committed or gitignored (rule 15 is about *large* binaries; 93 KB is fine either way, but it should be a decision, not a leftover). |
| `backend/app/api/routes.py` | modified +17 | Adds `GET /api/risk/forecast`. Docstring is honest: *"no forward weather feed, so the adapter is explicitly FALLBACK."* |
| `frontend/src/types/schemas.ts` | modified +35 | Mirrors the forecast types. Fine. |
| `frontend/src/lib/api.ts` | modified +2 | `getRiskForecast()`. Fine. |
| `frontend/src/components/DashboardWorkspace.tsx` | modified +42 | `ForecastStrip`. 8-second timeout racing the API, honest `FALLBACK`/`LOADING`/`UNAVAILABLE` source badge. Good behaviour. |
| `frontend/src/components/RightRail.tsx` | modified +7 | `selected-forecast-summary`. Fine. |
| `frontend/src/components/dashboard-workspace.css` | modified +2 | Two very long minified lines. Cosmetic. |
| **`frontend/src/store/useTickStore.ts`** | **modified +19/−5** | **⚠ This one needs a decision before it is committed. See §3.1.2 — it lets synthetic forecast data overwrite the live map.** |

---

# 2. What is working

Everything in this section was verified by reading the code path, not by trusting a status file.

## 2.1 The demo spine — real, end to end

Click **Run Case Study** → pick `aizawl-2024` → the mode banner flips to `REPLAY · RECONSTRUCTED` → and then, per tick:

| Stage | Module | Is it real? |
|---|---|---|
| Scenario frames on an accelerated clock | `ingest/replay/scenario_source.py` + `core/clock.py` `ScenarioClock` | ✅ Real. 4 committed scenarios validate and dry-run. |
| `p_fail` per cell | `risk/model.py` (XGBoost) **fused with** `risk/thresholds.py` | ✅ Real. Trained artifact `data/models/xgb_terrain_v1.json`. Fusion rule is `max(ml_p_fail, min(1.0, threshold_exceedance))` — "whichever method is more concerned wins." |
| Rainfall thresholds | `risk/thresholds.py` | ✅ Real **published** NE-Himalaya curves: I–D `I = 5.8294·D^-0.4141`, E–D `E = -11.10 + 0.62·D`. This is the credible primary signal and the eval report says so. |
| SHAP explanations | `risk/explain.py` | ✅ Real SHAP attributions with plain-language strings. |
| Runout envelopes | `impact/runout.py` | ✅ Real, from real terrain, using cited empirical relations (Heim 1932, Corominas 1996, Rickenmann 2005, Jaboyedoff & Labiouse 2011). |
| Road severance | `impact/road_graph.py` | ✅ Real OSM graph — `data/osm/aizawl_graph.pkl`, 3,622 nodes / 8,808 edges, real Overpass pull. `p_blocked` from real runout-geometry intersection. |
| **RII (Road Isolation Index)** | `impact/isolation.py` | ✅ Real NetworkX connectivity on the real graph. **The signature differentiator is genuinely implemented.** |
| **EPS (Evacuation Priority Score)** | `impact/priority.py` | ✅ Real, with the documented weights and P1/P2/P3 bucketing. |
| Escalation state machine | `decision/escalation.py` | ✅ Real Green→Yellow→Orange→Red with hysteresis (0.1) to prevent flapping. |
| Safe evacuation window | `decision/window.py` | ✅ Real. Correctly emits a **range**, never a point estimate. UI wording is right. |
| Evacuation routing | `decision/routing.py` | ✅ Real Dijkstra on the risk-weighted graph, `C_edge = L_edge × (1 + α·P_fail + β·S_slope)`, severed edges removed. |
| Action Card | `decision/action_card.py` | ✅ Real, to a real nearest shelter from real `exposure.gpkg`. |
| CAP 1.2 XML | `dissemination/cap.py` | ✅ Real, spec-conformant. |
| 4 simulated channels | `dissemination/channels.py` | ✅ Real (Cell Broadcast / SMS / Push / Mesh), deterministic, parameterised. |
| Hash-chained audit trail | `audit/` | ✅ Real. `AI_FLAGGED` → `ESCALATED` → `DDMA_APPROVED` → `DISSEMINATED` → `VILLAGE_ACKNOWLEDGED`. Append-only, `prev_hash` chained. |
| WebSocket broadcast | `ws/` + `/ws/ticks` | ✅ Real. Now multiplexes announcements over the same channel. |

## 2.2 The central architectural invariant **holds**

Verified by grep: nothing in `risk/`, `impact/`, `decision/`, `dissemination/`, or `audit/` branches on LIVE vs REPLAY. `pipeline.py` receives a timestamp and a set of observations and does not know where they came from. The only mode-aware places are the four CLAUDE.md permits: `core/mode.py`, `core/clock.py`, `ingest/factory.py`, and the UI mode banner.

**This is the thing a sharp judge will probe, and it will survive the probe.**

## 2.3 Frontend — 18 API routes, 5 officer workspaces, 1 citizen PWA

Two-persona shell (`ConsoleShell.tsx` for officers, `CitizenApp.tsx` for villagers):

| Screen | Route | State |
|---|---|---|
| Dashboard | `/console/dashboard` | ✅ Real map, mode banner, right rail, scenario picker, counterfactual scorecard. 🟡 New uncommitted `ForecastStrip` — see §3.1.2. |
| Commander | `/console/commander` | 🟡 Real, but it is an LLM chat — see §3.5.3 for the rule-10 / §9 tension. Honest fallback exists. |
| What-If | `/console/whatif` | ⚠ **Real backend, fabricated frontend fallback.** §3.1.1. |
| Audit | `/console/audit` | ✅ Real. Reuses the real `AuditTrailView`. Honest `NotBuilt` empty state. |
| Announce | `/console/announce` | ✅ **Real, and it closes a gap CLAUDE.md still lists as open** — a DDMA approval now genuinely chains to a channel send + CAP XML + audit event. |
| Citizen PWA | `/` | ✅ Honest throughout: real offline ack queueing, real IndexedDB shelter/contact cache, correct "safe evacuation window … estimate, not a prediction of exact timing" wording, disabled buttons for unbuilt features. One defect: §3.4.1. |

**API surface:** 18 routes (15 under `/api`, 3 under `/api/commander`). `ARCHITECTURE.md` documents 5 of them — see §4.5.

## 2.4 Honesty features that are genuinely wired (do not let these go unmentioned in the pitch)

These are the credibility multipliers CLAUDE.md asks for, and they are real:

- **`frontend/src/lib/evalReport.ts` — exemplary.** It parses the real committed `data/models/eval_report.md` at build time, asserts the exact table headers, and **throws a descriptive error rather than returning a wrong number**. Task 5.6's false-alarm-cost slider is wired to genuinely measured numbers. No fabrication anywhere in this file.
- **`frontend/src/lib/scenarioDetails.ts` — exemplary.** Reads committed scenario JSON offline-safely. `deathTollInfo()` **returns `null` rather than fabricating**. `whatWentWrongLine()` derives only from the ground-truth block.
- **`data/models/eval_report.md`** publishes the model's modest numbers honestly and states in §7 that the threshold engine "should be treated as the load-bearing half of that `max`."
- **`MeshPropagationVisual.tsx`** carries a **"SIMULATION PREVIEW"** badge and says "animation compressed for display."
- **`ConsoleShell.tsx`** shows a real provenance footer reading `model_version` and `is_reconstructed` off the tick.
- **`NotBuilt.tsx`** — a reusable honest empty state naming the blocking task. Used consistently.
- Every scenario file carries a `provenance` block; the replay UI shows `REPLAY · RECONSTRUCTED`.
- `config.py` labels its own engineering defaults as *"ENGINEERING DEFAULT, not measured"* where they are not citable.

## 2.5 The only measured ML numbers — use exactly these, never round them up

From `data/models/eval_report.md`:

| Metric | Value |
|---|---|
| AUC-ROC | **0.696** |
| PR-AUC | **0.500** (random baseline 0.250) |
| n | **56** cells (14 positive / 42 negative) |
| Spatial CV | **leave-one-quadrant-out**, Aizawl only. Folds are 12–16 cells. |
| Confusion @ 0.70 | TP=0, FP=0, FN=14, TN=42 |

Data funnel: COOLR 14,753 global → 1,741 India → 504 NER → 19 in the Aizawl bbox → 17 trusted. Grid 2,912 cells → 56 labelled.

**Four features are 100% missing by design** (ready for real values with no retrain-time schema change): `lithology_class`, `plan_curvature`, `profile_curvature`, `dist_to_fault_km`.

**Say the number is modest and explain why the threshold engine carries the load.** The report already frames it that way. Do not let anyone in the team round 0.696 upward or describe it as "~70% accurate" — the eval report's own §2 says every fold is tiny and the estimate is "illustrative, not stable."

## 2.6 Data artifacts that are present and real

- `data/models/` — `xgb_terrain_v1.json`, `model_metadata.json`, `eval_report.md`, `cv_predictions.csv`
- `data/static/aizawl/` — `dem.tif`, `cells.gpkg` (2,912 cells), `exposure.gpkg` (11 villages, 7 shelters, 19 hospitals, 0 bridges), `imerg_pixel_timeseries.csv`
- `data/static/` — `ner_inventory.csv` (504 NER rows, committed), `COOLR_Reports_Points.csv`
- `data/osm/` — `aizawl_graph.pkl`, `aizawl_graph.geojson`
- `data/scenarios/` — `_smoke.json`, `aizawl-2024.json`, `wayanad-2024.json`, `tupul-2022.json` (all committed)
- 3 real NASA IMERG HDF5 granules (verified authenticated download, real 8.08 MB files)

---

# 3. What is hard-coded, fabricated, or placeholder

This is the section you asked about as "hot-coded." It is tiered by **how much damage it does if a judge finds it**, not by how much code it is. Most of the codebase is clean; the problems are concentrated.

## 3.1 TIER 0 — fabricated data on a judge-facing screen

### 3.1.1 ⚠ `frontend/src/lib/whatIfDemo.ts` — the single worst file in the repo

25 dense lines. It is the client-side fallback for the What-If simulator, and it **invents data that contradicts our own real data**:

| What it fabricates | Value | Reality |
|---|---|---|
| Village populations | Durtlang **6,400**; Hunthar **3,100**; Aizawl outskirts **4,700**; Reiek Ridge **2,200**; Tuirial **1,800**; Tuirini **1,200** | `config.py`'s own comment says real Aizawl villages "top out well under 100 people within their 500m sampling buffer." **These are off by ~2 orders of magnitude.** |
| Road names | "NH-6 — Hunthar Chasm", "NH-306 — Section 4", "Durtlang East Link", "Reiek Ridge Road", "Tuirial Bridge Approach", "Tuirini Village Link", "North Valley Connector" | Invented. Some are plausible-sounding, which makes it worse. |
| Terrain | 9 synthetic cells with invented slope / fault distance / lithology / wetness | Real values exist in `cells.gpkg`. |
| Timestamp | `const now = '2026-08-27T14:45:00+05:30'` | Hard-frozen. |
| `model_version` | `'demo_spatial_twin_v2'` | Not a real model. |

**Why it is Tier 0:** it is reachable at `/console/whatif` (`WhatIfSimulator.tsx:5` → `WhatIfWorkspace.tsx:8` → `App.tsx`), it fires whenever the backend call fails, and **populations are exactly the kind of number a district officer on the panel knows by heart.** It does carry an honest `assumptions` array and the UI shows a `DEMO SIMULATION DATA` badge — but a fabricated population under a badge is still a fabricated population.

**Recommended fix (cheap):** delete the fabricated village/road/terrain arrays and make the fallback either (a) read the same real `exposure.gpkg`-derived data the rest of the frontend already has in the tick store, or (b) refuse to render and show `NotBuilt` ("What-If requires the backend; it is unavailable"). Option (b) is 10 minutes and strictly more honest than what is there now.

Also in this file's component: **`WhatIfSimulator.tsx:2` is `// @ts-nocheck`** — the only TypeScript suppression in the entire frontend (the one other suppression, at `CitizenApp.tsx:146`, is a legitimate `jsx-a11y/media-has-caption`). Type checking is off for the largest single component in the app.

### 3.1.2 ⚠ `frontend/src/store/useTickStore.ts` (uncommitted) — synthetic forecast data overwrites the live map

The new `setForecast` action **overwrites `cellRisks` / `roadRisks` / `isolations` / `priorities`** with day-0 copies from the forecast, and `applyTick` was changed to *conditionally skip* updating them:

```ts
...(state.forecast && state.selectedForecastDate !== state.forecast.forecast[0]?.date
  ? {}
  : { cellRisks: tick.cell_risks, roadRisks: tick.road_risks, isolations: tick.isolations, priorities: tick.priorities }),
```

Two consequences:

1. **Days 1–4 render a fabricated projection on the judge-facing risk map.** The forecast is stamped `FALLBACK` (honest) and the strip shows that badge — but the *map* does not distinguish "this is today's model output" from "this is a deterministic decay curve applied to today's model output."
2. **Even on day 0**, where the rainfall factor is 1.0 and `p_fail` is therefore identity, `confidence` is still replaced by the synthetic `1 - |p − 0.5| × 2`. **The real model's confidence is discarded on the default view.**

**Recommended fix before committing:** keep the forecast strip (it is a nice feature and its source badge is honest) but do not let it write into the live `cellRisks`. Give the forecast its own map layer or its own selection state, and never overwrite `confidence`.

## 3.2 TIER 1 — magic numbers that violate the `config.py` contract

`backend/app/config.py` line 1 says: *"All tunable constants live here — no magic numbers scattered elsewhere."* CLAUDE.md §4 additionally requires that weights and constants **"must be tunable from the UI."** These sites break that.

### 3.2.1 `backend/app/risk/forecast.py` (uncommitted) — ~10 uncited constants

```python
_RAINFALL_TREND = (1.0, 1.14, 0.96, 0.74, 0.56)   # where do these come from?
def _level(p):  # cut-points 0.75 / 0.5 / 0.25
def _base_rainfall(tick):  return 4.0  ... or mean(threshold_exceedance) * 24.0
probability = cell.p_fail * (0.72 + 0.28 * factor)
severed / isolated recomputed at >= 0.7
eps - components["p_fail"] * 0.35 + risk * 0.35
confidence = 1.0 - abs(probability - 0.5) * 2
default = min(0.85, 0.18 + 0.12 * factor)
```

None of these are in `config.py`. None has a citation. The module's docstring is honest about being a FALLBACK, which is good — but the numbers themselves are unexplained, and `_RAINFALL_TREND` in particular is a **five-day weather shape with no meteorological basis**, which is exactly the kind of thing that gets asked about.

One further issue: `ForecastArea(id=cell.cell_id, name=cell.cell_id, …)` — **the human-facing `name` is the raw cell id**, so the UI will show strings like `aizawl_040_026` where a village name belongs.

### 3.2.2 `frontend/src/lib/forecast.ts` (uncommitted) — the same constants, again, in TypeScript

```ts
const RAINFALL_TREND = [1, 1.14, 0.96, 0.74, 0.56]
// same 0.75 / 0.5 / 0.25 cut-points
// same (0.72 + 0.28 * factor)
// same * 24
// same Math.min(0.85, 0.18 + 0.12 * factor)
```

**Two copies of ten uncited constants in two languages.** If anyone tunes one, the other silently disagrees. If the forecast feature is kept, these must come from one source (an API-served config block, or a generated constants file).

### 3.2.3 `backend/app/api/whatif.py` — a hand-rolled hazard model with zero constants in config

```python
k_lith = {"weak": 1.35, "moderate": 1.0, "competent": 0.72}[lith]
geo_factor = k_lith * (1.0 + 1.8 / (1.0 + fault ** 0.8))
slope_factor = (sin(radians(slope)) / sin(radians(35.0))) ** 1.35
moisture_factor = 1.0 + 0.55 * (antecedent / 150.0) + 0.65 * (soil / 50.0 - 1.0)
wetness = max(0.7, min(1.35, 0.85 + 0.06 * (twi - 5.0)))
hazard = 0.02 * rainfall_ratio * slope_factor * geo_factor * max(0.2, moisture_factor) * wetness * snow_factor * exposure
probability = 1.0 - exp(-hazard)
```

Eleven tuning constants, none in `config.py`, none cited. **And it fabricates geology:**

```python
fault = 1.0 + ((abs(float(row.geometry.centroid.x)) % 7000.0) / 7000.0) * 10.0
```

That is **distance-to-fault derived from a coordinate modulo** — pseudo-geology. Lithology is likewise inferred from slope bands (`>=40° → weak`, `>=28° → moderate`, else `competent`). Both *are* disclosed in the response's `assumptions` array, which is the honest thing to do, but a geologist judge asking "where does your fault distance come from?" will not like the answer.

Two more problems in this file:

- **`"threshold_exceedance": round(probability, 4)`** — the exceedance field is **set equal to `p_fail`**, not to a real observed/threshold ratio. Anything downstream reading `threshold_exceedance` (including `risk/forecast.py`'s `_base_rainfall`!) gets a meaningless value from a what-if run.
- **`"confidence": 0.7`** hardcoded identically for every cell.

The **genuinely real** halves of this file, for balance: the published I–D curve (`i_crit = 5.8294 * duration_hours ** -0.4141`), real `cells.gpkg` geometry, a real STRtree spatial join against the real OSM graph, and real calls to `build_isolation_inputs` / `compute_all_village_isolations` / `resolve_priority_inputs` / `compute_settlement_priorities` with real `exposure.gpkg` village geometry. The impact half is real; the hazard half is invented.

### 3.2.4 `backend/app/impact/demographics.py` — 4 constants, honest but off-config

```python
CHILDREN_RATIO = 0.30
SENIOR_RATIO = 0.08
AVERAGE_HOUSEHOLD_SIZE = 4.8
HIGH_RISK_HOUSEHOLD_RATIO = 0.05
```

The module is **fully simulated and says so** — it stamps `source="simulated"` and is deterministic. That is the right pattern. But the four ratios belong in `config.py`, and ideally should carry a Census 2011 citation or a `TODO(verify)`.

### 3.2.5 `frontend/src/lib/commander.ts` — risk cut-points

`riskLevel` uses hardcoded `.8 / .6 / .35`. These differ from **both** `config.py`'s escalation thresholds (`0.25 / 0.5 / 0.75`) **and** `forecast.py`'s `_level` cut-points (`0.25 / 0.5 / 0.75`). Three different risk-banding schemes now exist in one product.

### 3.2.6 Duplicated strings and caps across the backend/frontend boundary

| Duplicated thing | Backend | Frontend |
|---|---|---|
| Route cap of 3 | `commander/service.py` → `if len(result) == 3: break` | `CommanderWorkspace.tsx` → `.slice(0, 3)` |
| Safety reason text | `commander/service.py` → `"Uses the current risk-filtered route and avoids affected roads."` | `CommanderWorkspace.tsx` → byte-identical string |

Both work today; both will drift.

## 3.3 TIER 2 — synthetic **by design**, honestly labelled (these are fine, do not "fix" them)

Listing these explicitly so nobody mistakes them for problems later:

| File | What is synthetic | Why it is acceptable |
|---|---|---|
| `frontend/src/lib/grid.ts` | 3×3 synthetic cell layout; `CELL_SIZE_DEG = 0.006`, `GRID_GAP_DEG = 0.001`; a hand-maintained `REMAPPED_REAL_CELL_POSITIONS` table | Docstring states plainly: *"fabricated positioning for visualization only in BOTH cases."* It is map *placement*, not risk data. |
| `frontend/src/lib/villages.ts` | Village pin positions via FNV-1a hash → ring, `RING_RADIUS_DEG = 0.012` | Docstring admits it. Placement only. |
| `frontend/src/lib/roads.ts` | Falls back to sketching through synthetic cell centres | **Prefers real `road.geometry` when present.** Correct precedence. |
| `frontend/src/lib/commander.ts` `demoResponse()` | Keyword-intent router with templated answers | **Every string is a template over real store data** (real `priorities`, `roadRisks`, `isolations`, `routes`, `shelters`). No fabricated villages or populations. Stamps `source: 'fallback'`. This is the *right* way to build a fallback — contrast with §3.1.1. |
| `backend/app/impact/demographics.py` | All of it | `source="simulated"`, deterministic. (Constants should move to config — §3.2.4 — but the approach is right.) |
| `dissemination/channels.py` | 4 simulated channels | Simulation is the correct scope; we deploy no hardware (rule 7). Parameters are real and cited. |
| `MeshPropagationVisual.tsx` | `NODE_COUNT = 16`, `DEMO_DURATION_MS = 4000` | Both self-labelled as demo choices, with a "SIMULATION PREVIEW" badge and "animation compressed for display." |
| `config.py` engineering defaults | `RUNOUT_TRIGGER_P_FAIL = 0.5`, `RUNOUT_ANGLE_OF_REACH_DEG = 25.0`, `P_CRIT_ROAD = 0.7`, `EPS_WEIGHTS`, etc. | Each carries **either a real citation** (Heim 1932; Corominas 1996; Rickenmann 2005; Jaboyedoff & Labiouse 2011) **or an explicit "ENGINEERING DEFAULT, not measured."** This is the standard the rest of the repo should meet. |

**One genuine no-op to know about:** `ROUTING_BETA_SLOPE = 1.0` is structurally present in the routing cost function but is **a no-op for every edge**, because no per-edge road-slope dataset exists. The `β·S_slope` term in `C_edge = L_edge × (1 + α·P_fail + β·S_slope)` currently contributes nothing. If a judge asks about the formula, do not claim the slope term is active.

## 3.4 TIER 3 — placeholders and cosmetic

### 3.4.1 Hardcoded `LIVE` badges that lie during a REPLAY

- **`frontend/src/components/CitizenApp.tsx:103`** — `<span className="citizen-live"><i /> LIVE</span>` is a literal. During a case-study replay the citizen app **claims to be LIVE**. This is a direct contradiction of the mode banner two clicks away and is a 5-minute fix (read `mode` off the tick store, as `ConsoleShell.tsx` already does correctly).
- **`frontend/src/components/CommanderWorkspace.tsx`** — same problem, plus a hardcoded `'NVIDIA · VERIFIED CONTEXT'` source badge.

### 3.4.2 Other placeholders

- `config.py` `ACTION_CARD_CONTACT_PLACEHOLDER` — a fake phone number, **self-labelled as fake**. Correct handling; just remember it is on screen.
- `CommanderWorkspace.tsx` — a hardcoded 6-prompt `suggestions` array.
- `frontend/src/components/WhatIfSimulator.tsx` — 5 hardcoded scenario presets ("Cyclone Remal Storm", "Seismic / Fault Shock", "Normal Baseline", "Flash Cloudburst", "Himalayan Spring Melt"). These are *inputs* a user could dial in by hand, so they are legitimate presets, not fabricated outputs. Note "Cyclone Remal" is a real 2024 cyclone — make sure the pitch does not imply we reconstructed it from data.
- `WhatIfSimulator.tsx` `Inspector` contains one hardcoded cell-id → name mapping: `selection.id === 'aizawl_040_026' ? 'Durtlang / Hunthar Escarpment' : selection.id`. Everything else shows a raw cell id.
- `Makefile` — `make data` and `make graph` are still `@echo "TODO(Phase 1)…"` / `@echo "TODO(Phase 2)…"` **despite the real `scripts/` implementations existing.** Anyone following the documented commands will think data-building is unimplemented. (`make tiles` is real.)

## 3.5 Rule violations

### 3.5.1 🔴 P0 — `backend/app/api/whatif.py` encoding corruption ⇒ **rule 14 is unenforced**

**The finding.** A byte scan of every file under `backend/app/**/*.py` found **exactly one** BOM-prefixed file and **exactly one** file containing the double-encoded sequence `C3 A2 E2 82 AC` (`â€`). Both are `api/whatif.py`. The mojibake is at byte offset 29, on line 1.

```
E   File "C:\Users\clash\Documents\NIRANTAR\backend\app\api\whatif.py", line 1
E     \ufeff"""BUILD_PLAN.md task 5.8 \xe2\u20ac\u201d the what-if rainfall simulator...
E     ^
E   SyntaxError: invalid non-printable character U+FEFF
```

**Why it matters more than it looks.** `import app.api.whatif` still *succeeds* — CPython treats a UTF-8 BOM as an encoding declaration — and `WHAT_IF_ASSUMPTIONS[0]` decodes to a clean em-dash at runtime. So **the app works fine.** But `tests/test_no_wallclock.py` walks the AST of every file under `backend/app/`, and `ast.parse` is stricter than the import machinery. It raises on this file and the test dies **before inspecting anything**.

**Net effect: CLAUDE.md rule 14 — the one rule the project explicitly says has a test that must never be deleted — has silently not been enforced for as long as this file has been corrupted.**

**And it is hiding a real violation:**

```python
# backend/app/commander/store.py:20
result = SavedRoutePlan(id=str(uuid.uuid4()), created_at=datetime.now(timezone.utc), **plan.model_dump())
```

That is **both** a rule-14 violation (`datetime.now()` outside `core/clock.py`) **and** a rule-13 violation (unseeded `uuid.uuid4()` breaks determinism). It is the **only** real rule-14 violation in `backend/app/` — I grepped; the three other hits are docstring text discussing the rule.

**Fix:** strip the BOM, repair the em-dash, re-run the test, then fix `store.py:20` to take a `Clock` and a deterministic id. Total ~20 minutes. **Do this first.**

### 3.5.2 🟠 Rule 13 (determinism) — `backend/app/api/whatif.py:323`

```python
event = audit.append(event_id=f"whatif-{uuid.uuid4()}", ...)
```

Unseeded randomness writing into the **hash-chained audit log**. Two identical what-if runs produce different audit hashes. Rule 13 requires byte-identical output for identical inputs. Session 1 already caught and fixed exactly this bug pattern in the audit event id — it has regressed here.

### 3.5.3 🟠 Rule 10 + §9 tension — the NVIDIA LLM on a demo path

`backend/app/commander/llm.py` (43 lines, undocumented in CLAUDE.md) makes a **live external network call**:

```
POST {NVIDIA_BASE_URL}/chat/completions
Authorization: Bearer {NVIDIA_API_KEY}
temperature=0.1, max_tokens=500, last 10 history messages + context
```

Against:
- **Rule 10:** *"The demo must run with the network cable unplugged. No live API call may be on the demo critical path."*
- **§9:** *"What we deliberately do NOT build: … LLM agent swarms … or anything else that adds demo risk without adding judge-legible value."*

**Mitigation that exists:** a deterministic `fallback_answer()` and an honest source badge (`source = "nvidia" if generated else "fallback"`, surfaced in the UI as *"Live AI unavailable — showing simulation scenario"*). The fallback (`lib/commander.ts::demoResponse`) is genuinely good — templated over real store data, no fabrication.

**Residual risks:**
1. A broad `except (httpx.HTTPError, ValueError, KeyError, IndexError, TypeError): return None` will swallow real bugs as "fallback."
2. **This is untested in aeroplane mode** (task 5.4). An unresolvable DNS lookup can hang differently from a refused connection; `NVIDIA_TIMEOUT_SECONDS = 12` means a **12-second dead air pause in front of judges** in the worst case.
3. The Commander is not in BUILD_PLAN.md at all, so it has no P-level and no cut-first position.

**Decision needed from you** — see §5.2.

### 3.5.4 🟡 `frontend/src/lib/forecast.ts` uses `new Date()` directly

Rule 14 is written for the backend and enforced only there, so this is not a literal violation — but the *spirit* (all time through one clock) is broken on the frontend. During a REPLAY the forecast strip will label days from **wall-clock today**, not from scenario time. A judge replaying Aizawl 2024 will see forecast dates in August 2026.

## 3.6 Full off-config constant inventory

| File | Count | In `config.py`? | Cited? |
|---|---|---|---|
| `backend/app/config.py` | ~35 | n/a | ✅ each has a citation or an explicit "not measured" |
| `backend/app/api/whatif.py` | ~11 | ❌ | ❌ (I–D curve only) |
| `backend/app/risk/forecast.py` | ~10 | ❌ | ❌ |
| `frontend/src/lib/forecast.ts` | ~10 (duplicates the above) | ❌ | ❌ |
| `backend/app/impact/demographics.py` | 4 | ❌ | ❌ (honestly `source="simulated"`) |
| `frontend/src/lib/commander.ts` | 3 | ❌ | ❌ |
| `frontend/src/lib/grid.ts` | 2 | ❌ | n/a — visualization only, disclosed |
| `frontend/src/lib/villages.ts` | 2 | ❌ | n/a — visualization only, disclosed |
| `frontend/src/components/MeshPropagationVisual.tsx` | 2 | ❌ | n/a — labelled demo choices |

---

# 4. What is missing

## 4.1 P0 — blocks the demo

| # | Missing | Effort | Notes |
|---|---|---|---|
| 1 | **Green test suite** — fix the `whatif.py` BOM | ~2 min | Then fix `store.py:20`'s rule-13/14 violation that it was hiding (~15 min). |
| 2 | **`make demo-check`** (task 5.11) | ~2–3 h | Must verify: models present, scenarios validate, tiles present, road graphs cached, no network on the replay path, all scenarios complete a full run. |
| 3 | **Aeroplane-mode rehearsal** (task 5.4) | ~1 h, **yours** | On the actual demo machine. This is where the NVIDIA-call risk (§3.5.3) and the missing PMTiles basemap (§4.2) will actually bite. |
| 4 | **`docs/DEMO_SCRIPT.md`** (task 6.1) | ~2–3 h, **yours** | Does not exist. 8-minute beat-by-beat + a 3-minute compressed version. |
| 5 | **Frozen tagged build** (task 6.2) | ~15 min, **yours** | |
| 6 | **3-minute screen capture fallback** (task 6.3) | ~1 h, **yours** | The insurance policy if the laptop dies. |
| 7 | **Rehearsed answers to the 10 hard judge questions** (task 6.4) | ~3 h, **whole team** | Especially Q1 (vs GSI's LEWS), Q2 (software-only soil moisture), Q3 (accuracy + false-alarm rate), Q7 (InSAR under NER vegetation). |
| 8 | **5 clean runs, 2 operators** (task 6.6) | ~2 h, **yours** | |

## 4.2 Missing data artifacts

All are gitignored-and-regenerable by design (rule 15), but **none is in this working tree right now**, so the features that depend on them cannot run today:

| Missing | Blocks | How to regenerate |
|---|---|---|
| `data/static/wayanad/` (dem, cells, exposure) | Wayanad replay with real impact | `scripts/fetch_dem.py` → `build_grid.py` → `fetch_exposure.py --aoi wayanad` |
| `data/static/tupul/` (dem, cells, exposure) | Tupul replay with real impact | same, `--aoi tupul` |
| `data/osm/wayanad_graph.pkl` | Wayanad RII / routing | `scripts/build_road_graph.py --aoi wayanad` |
| `data/osm/tupul_graph.pkl` | Tupul RII / routing | same, `--aoi tupul` |
| **`data/tiles/aizawl.pmtiles`** | **The offline basemap.** Only `.gitkeep` is present. Without it `MapView` renders a self-contained MapLibre style with **no basemap imagery** — cells and roads float on a blank background. | `make tiles` (this target is real) |
| `data/audio/` | Voice alerts (task 3.9) | Not built at all — see §4.3 |

**The PMTiles one is the demo-visible one.** A risk map with no terrain underneath it is a much weaker image than one over real hillshade, and Aizawl's topography *is* the story.

## 4.3 Missing features

**Deliberate cuts (leave them cut, but be ready to say so out loud):**
- InSAR (1.9) — #1 on the plan's own cut list.
- Sikkim GLOF scenario (4.6) — different hazard physics, correctly gated.
- Crowdsourced photo CV (3.11) — the plan says cut this before anything above it.

**Genuine gaps worth reconsidering:**
- **Voice alerts / TTS (3.9, P1).** Nothing built. `data/audio/` absent. For a problem statement about reaching villages with no mobile coverage, **a village-facing voice alert in Mizo is one of the most judge-legible features in the entire concept**, and pre-generating a handful of `.wav` files for the demo action cards is not a big task. The citizen app already handles the absence honestly, so this is a strict upgrade, not a bug fix. **This is the highest-value remaining feature build.**
- **Lithology (1.4, P1).** Blocked on your Bhukosh access. Four ML features stay 100% missing without it.
- **LIVE-mode cell ids.** `ingest/live/stub_source.py` still emits the Phase-0 fake `aizawl_{row}{col}` convention, which structurally never matches `cells.gpkg`. Only the 4 committed scenario files were migrated to real cell ids. **LIVE mode therefore cannot produce real village-level escalation.** Low priority because REPLAY is the demo — but if a judge asks to see LIVE mode, it is a visible hole.
- **Unified `alert_id`.** `AI_FLAGGED` is tick-scoped (`tick-{aoi}-{t}`) while `ActionCard` / `DDMA_APPROVED` / `DISSEMINATED` are village-scoped (`card-{village_id}-{t}`). The two audit chains do not merge under one alert id. The Audit Trail view surfaces this honestly as a "not yet reached" row rather than hiding it — which is the right call — but the chain is not end-to-end.
- **`ROUTING_BETA_SLOPE` is a no-op.** No per-edge road-slope dataset exists (§3.3).

## 4.4 Missing / broken documentation

| Item | State |
|---|---|
| `docs/DEMO_SCRIPT.md` | **Does not exist** (task 6.1). |
| One-page architecture handout | Does not exist (task 6.5). |
| `make data`, `make graph` | Still `@echo "TODO"` placeholders **despite real implementations in `scripts/`**. Anyone following the documented workflow will conclude data-building is unimplemented. |
| `CLAUDE.md` §11 / §12 | **25 commits stale.** See §4.5. |
| `docs/ARCHITECTURE.md` §3 | Documents **5 API routes**; there are **18**. Module table still describes `risk/`, `impact/`, `decision/` as "Phase 0 stubs." Missing entirely: `commander/`, `impact/demographics.py`, `risk/forecast.py`, `api/whatif.py`, `api/announcements.py`. The file's own header says "if this file and the schema code disagree, the code wins and this file is stale — fix it." |

## 4.5 Documentation that is present but **wrong** — 7 confirmed contradictions

I did not fix any of these; changing docs to match code is a decision, not a cleanup. Each is a real disagreement between a file and the code.

| # | Where | Claims | Reality |
|---|---|---|---|
| 1 | `CLAUDE.md` §11 / §12 | Last state = Session 4, 2026-08-26 | **25 commits since.** Five unrecorded subsystems: the NVIDIA Commander (`commander/`, `api/commander.py`), announcements + CAP dissemination (`api/announcements.py`), simulated demographics (`impact/demographics.py`), the 5-day forecast, and the two-persona officer/citizen shell. Also unrecorded: `VillageView.tsx` and `DdmaConsole.tsx` were **retired** (commits `a95aaf6`, `d6fb4c6`). |
| 2 | `CLAUDE.md` §11 "Known gaps" | *"nothing yet chains an approval to an actual channel send"* | **Closed.** `api/announcements.py` does exactly this — DDMA approval → 4 channels → `record_dissemination` → real CAP 1.2 XML → audit event. |
| 3 | `Required_by_me.md` "Resolved since" | wayanad / tupul have *"no registered `config.AOIS` entry"* | **`config.py` registers both** (wayanad 11.61/76.12 utm 32643; tupul 24.7667/93.75 utm 32646), each with `TODO(verify)` comments. |
| 4 | `api/whatif.py` docstring, rulings 1–4 | A what-if run is *"the first place… the REAL trained model + real SHAP + real terrain-driven runout actually fire end-to-end"* | **False.** Lines 188–191 of the same file say *"What-If has its own pure simulation path. It intentionally does not call `Pipeline.process`."* `simulate_whatif()` never touches `risk/model.py` or `risk/thresholds.py`. Additionally `build_synthetic_frame()` is **dead in production** — grep shows it is referenced only by `tests/test_whatif.py` (lines 17, 43, 52, 63, 70). **The what-if tests exercise a function the shipped endpoint does not call.** |
| 5 | `api/routes.py:287` | *"A brand-new, throwaway `Pipeline()` is constructed and discarded for this one call"* | Describes an implementation that no longer exists. |
| 6 | `api/routes.py` `/api/audit/{alert_id}` docstring | `ESCALATED` / `DDMA_APPROVED` / `DISSEMINATED` producers are *"not yet CALLED from `pipeline.py`"* | Stale — they are called now. |
| 7 | `MeshPropagationVisual.tsx` docstring | Says twice it is *"Placed in the DDMA Console (`DdmaConsole.tsx`)"* | `DdmaConsole.tsx` **was retired.** It now lives in `AnnounceWorkspace.tsx`. |

Minor: `lib/scenarioDetails.ts`'s docstring says *"Only `data/scenarios/_smoke.json` exists as of this writing"* — four scenarios now exist.

---

# 5. What is required from you

## 5.1 Things only you can do — no coding session can substitute

| # | Task | Why it must be you | Est. |
|---|---|---|---|
| 1 | **Aeroplane-mode rehearsal (5.4, P0)** | Requires physically disabling networking **on the actual demo machine**, not a dev box. This is where the live NVIDIA call (§3.5.3), the missing PMTiles basemap (§4.2), and any unnoticed CDN dependency will surface. | 1 h |
| 2 | **Write `docs/DEMO_SCRIPT.md` (6.1, P0)** | Only you know who is presenting, who clicks what, and how the room is arranged. 8-minute run + 3-minute compressed fallback. | 2–3 h |
| 3 | **Rehearse the 10 hard judge questions (6.4, P0)** | Whole team. **Every member** must be able to answer Q1 / Q2 / Q3 / Q7. §2.5 has the exact numbers for Q3 — do not let anyone improvise them. | 3 h |
| 4 | **Record the 3-minute fallback video (6.3, P0)** | Insurance if the laptop dies mid-pitch. | 1 h |
| 5 | **Five clean runs by two operators (6.6, P0)** + **freeze/tag (6.2)** + **submit (6.7)** | | 3 h |

**21 days to the 20 Sep deadline. Items 1–5 are now the critical path, not code.**

## 5.2 Decisions only you can make

| # | Decision | Options | My recommendation |
|---|---|---|---|
| 1 | **Keep the NVIDIA Commander?** (§3.5.3) | (a) Keep, but hard-disable the live call for the demo and run the deterministic fallback only. (b) Keep the live call and accept a possible 12-second dead-air pause. (c) Cut the workspace. | **(a).** You keep the visible feature and the judge-legible framing, and rule 10 is satisfied. The fallback (`demoResponse`) is genuinely good — templated over real data, honest badge. Also drop `NVIDIA_TIMEOUT_SECONDS` to ~3 s regardless. |
| 2 | **What to do with `lib/whatIfDemo.ts`?** (§3.1.1) | (a) Delete the fabricated arrays; fall back to real tick-store data. (b) Replace the fallback with `NotBuilt`. (c) Leave it. | **(b)** if time is short (10 min, strictly more honest), **(a)** if you have an hour. **Not (c)** — fabricated village populations on a judge-clickable screen is the biggest single credibility risk in the repo. |
| 3 | **Commit the forecast feature, or shelve it?** (§1.5, §3.1.2) | (a) Commit after fixing the map-hijack + the duplicated constants. (b) Shelve until after the demo. | **(a) with the §3.1.2 fix**, or **(b)**. Do not commit as-is — synthetic FALLBACK data currently overwrites the real model's output on the primary judge-facing map. |
| 4 | **Build voice alerts (3.9)?** (§4.3) | (a) Pre-generate audio for the demo action cards only. (b) Leave the honest disabled button. | **(a) if you can find 3–4 hours.** For a problem statement about reaching unreached villages, a Mizo voice alert is one of the most judge-legible features available, and pre-generated files carry zero demo risk. If you cannot, (b) is already handled honestly. |
| 5 | Git branching strategy (open in `Required_by_me.md`) | | Your call; nothing blocks on it. |
| 6 | `ml_model_metrics.ipynb` — commit or ignore? | | 93 KB, harmless either way. Just make it a decision. |

## 5.3 External access still needed — **none of these blocks the demo**

| What | For | Status |
|---|---|---|
| **IMD public API key** (`IMD_API_KEY`) | Task 1.8's real verification. Adapter code is written and tested. | Not obtained. **The env-var field name is the one unconfirmed guess in `build_auth_headers()`** — verify it against IMD's docs when the key arrives. |
| **GSI Bhukosh lithology export** | Task 1.4. Unblocks 4 currently-100%-missing ML features. | Not obtained. `bhukosh.gsi.gov.in/Bhukosh/Public` refused an automated connection; also try `bhusanket.gsi.gov.in`. Documented `coarse_fallback` path exists. |
| **SMAP / NSIDC Earthdata authorization** | Task 1.7. | **Genuinely unconfirmed** whether NSIDC needs its own app authorization separate from the GES DISC one you already completed. Worth 5 minutes to check. |

**All three are enhancements.** The demo runs on pre-baked scenario data (rule 10) and does not touch any of them.

## 5.4 Security / hygiene — please review

None of these is currently leaking, but two are worth your eyes:

| Item | State | Action |
|---|---|---|
| `~` (418 B) and `~.pub` (102 B) in the repo root, plus a `.ssh/` directory | **Gitignored** (`.gitignore:59-60`) and **not tracked** — verified. | These look like an SSH keypair sitting in a project directory. `.gitignore` protects `git`, but not a zipped folder, a `git add -f`, or a backup sync. **Recommend moving them out of the repo entirely.** Note commit `3a4b0a0` is literally titled *"Remove local artifacts and key material"* — this may be a remnant of that cleanup. |
| `.env` (1,231 B) | **Gitignored** (`.gitignore:22`), not tracked. `.env.example` (1,217 B) is tracked. | Fine as-is. But CLAUDE.md's Session-2 log records a **prior near-miss** where real NASA Earthdata credentials were pasted into the tracked `.env.example` and reverted before commit. Worth one glance to confirm `.env.example` still contains only placeholders. |
| `NVIDIA_API_KEY` | Read from env in `config.py`. | Must stay in `.env`, never in `.env.example` or any committed file. If the Commander ships, this key travels to the demo machine — decide how. |

---

# 6. Recommended order of work

## Immediately (under an hour, all mechanical)

1. **Fix the `whatif.py` BOM + mojibake.** Green suite, rule 14 enforced again. (~2 min)
2. **Fix `commander/store.py:20`** — take a `Clock`, use a deterministic id. Rules 13 + 14. (~15 min)
3. **Fix `api/whatif.py:323`** — deterministic `event_id`, not `uuid.uuid4()`. Rule 13. (~5 min)
4. **Fix the two hardcoded `LIVE` badges** (`CitizenApp.tsx:103`, `CommanderWorkspace.tsx`) — read mode off the store. (~10 min)
5. **Regenerate `data/tiles/aizawl.pmtiles`** via `make tiles`. The map has no basemap without it. (~15 min + download)

## This week (P0 code)

6. **Decide §5.2 items 1–3**, then act on them. The `whatIfDemo.ts` fabrication and the `useTickStore.ts` map-hijack should both be resolved **before** the visual design pass, not after.
7. **Build `make demo-check`** (5.11). Also replace the `make data` / `make graph` TODO echoes with the real script calls while you are in the Makefile.
8. **Regenerate the Wayanad + Tupul static data and road graphs** so all four scenarios run with real impact, not just Aizawl.
9. **Move the off-config constants into `config.py`** (§3.2), and wire the ones CLAUDE.md §4 requires to be UI-tunable. Start with the forecast constants if the forecast ships, since they are currently duplicated across two languages.

## Then (P1)

10. **Voice alerts (3.9)** if you take §5.2 item 4 — highest-value remaining feature.
11. **Visual design pass (5.9)** — read the `frontend-design` skill first, as the task instructs.
12. **Update `CLAUDE.md` §11/§12 and `docs/ARCHITECTURE.md`**, and fix the 7 contradictions in §4.5. Do this *before* Phase 6, so the freeze captures accurate docs.

## Finally — Phase 6, all yours

13. Tasks 6.1 → 6.7 in order. **This is 21 days out. Start 6.1 (the demo script) and 6.4 (the 10 questions) in parallel with the code work above — they do not depend on it.**

---

# Appendix A — every fabricated / hard-coded site, by file

| File | Line(s) | Kind | Tier |
|---|---|---|---|
| `frontend/src/lib/whatIfDemo.ts` | whole file (25 lines) | Fabricated village populations, road names, terrain, frozen timestamp | **T0** |
| `frontend/src/store/useTickStore.ts` | `setForecast`, `applyTick` (uncommitted) | Synthetic forecast overwrites live map + real confidence | **T0** |
| `backend/app/api/whatif.py` | 1 | UTF-8 BOM + mojibake ⇒ breaks rule-14 guard test | **T0** |
| `backend/app/api/whatif.py` | 323 | `uuid.uuid4()` in audit chain — rule 13 | T1 |
| `backend/app/api/whatif.py` | hazard model | ~11 off-config constants; coordinate-modulo fault distance; slope-band lithology; `threshold_exceedance = p_fail`; `confidence = 0.7` | T1 |
| `backend/app/commander/store.py` | 20 | `datetime.now()` (rule 14) + `uuid.uuid4()` (rule 13) | T1 |
| `backend/app/risk/forecast.py` | 20, 32-39, 42-47, 53-54, 62, 67, 77, 99, 103 | ~10 off-config uncited constants; `name = cell_id` | T1 |
| `frontend/src/lib/forecast.ts` | 3, 5-10, 17, 25-29 | Duplicates all of the above in TS | T1 |
| `backend/app/impact/demographics.py` | constants | 4 off-config ratios (honestly `source="simulated"`) | T1 |
| `frontend/src/lib/commander.ts` | `riskLevel` | Cut-points .8/.6/.35 — a third banding scheme | T1 |
| `backend/app/commander/service.py` + `CommanderWorkspace.tsx` | route cap, safety string | Duplicated across the language boundary | T1 |
| `frontend/src/components/WhatIfSimulator.tsx` | 2 | `// @ts-nocheck` — only TS suppression in the frontend | T1 |
| `frontend/src/lib/grid.ts` | `CELL_SIZE_DEG`, `GRID_GAP_DEG`, `REMAPPED_REAL_CELL_POSITIONS` | Synthetic map placement — **disclosed in docstring** | T2 ✅ |
| `frontend/src/lib/villages.ts` | `RING_RADIUS_DEG`, `TIER_COLOR` | Synthetic pin placement — **disclosed** | T2 ✅ |
| `frontend/src/components/MeshPropagationVisual.tsx` | `NODE_COUNT`, `DEMO_DURATION_MS` | **Labelled demo choices**, "SIMULATION PREVIEW" badge | T2 ✅ |
| `frontend/src/components/CitizenApp.tsx` | 103 | Hardcoded `LIVE` — lies during REPLAY | T3 |
| `frontend/src/components/CommanderWorkspace.tsx` | badges, suggestions | Hardcoded `LIVE`, `'NVIDIA · VERIFIED CONTEXT'`, 6 prompts | T3 |
| `backend/app/config.py` | `ACTION_CARD_CONTACT_PLACEHOLDER` | Fake phone number — **self-labelled** | T3 ✅ |
| `backend/app/config.py` | `ROUTING_BETA_SLOPE` | Present but a **no-op** — no per-edge slope data | T3 |
| `Makefile` | `data`, `graph` | `@echo "TODO"` despite real `scripts/` implementations | T3 |
| `frontend/src/components/WhatIfSimulator.tsx` | `Inspector` | One hardcoded cell-id → name mapping | T3 |

**Clean by contrast — no fabrication found:** `backend/app/config.py` (35 constants, each cited or explicitly labelled unmeasured), `frontend/src/lib/evalReport.ts`, `frontend/src/lib/scenarioDetails.ts`, `frontend/src/lib/commander.ts::demoResponse`, `frontend/src/lib/roads.ts`, `frontend/src/components/NotBuilt.tsx`, `frontend/src/components/AuditWorkspace.tsx`, `frontend/src/components/ConsoleShell.tsx`, `backend/app/schemas/forecast.py`, and the entire `risk/` `impact/` `decision/` `dissemination/` `audit/` chain.

---

# Appendix B — how this document was verified

Every claim above traces to one of these. Nothing was inferred from a status file.

```bash
# Phase / task state — read from BUILD_PLAN.md's own checkboxes, not CLAUDE.md
grep -cE '^\s*-\s*\[x\]' docs/BUILD_PLAN.md   # 74
grep -cE '^\s*-\s*\[ \]' docs/BUILD_PLAN.md   # 15

# Backend suite (26 minutes)
cd backend && .venv/Scripts/python.exe -m pytest tests/ -q
# → 1 failed, 771 passed, 12 skipped, 3 warnings in 1578.26s

# The single failure, isolated
cd backend && .venv/Scripts/python.exe -m pytest tests/test_no_wallclock.py
# → SyntaxError: invalid non-printable character U+FEFF, whatif.py line 1

# Frontend suite — MUST be serial on this machine, see §1.4
cd frontend && npx vitest run --no-file-parallelism --testTimeout=30000
# → Test Files 44 passed (44) | Tests 267 passed (267) | 167.12s

# Encoding corruption — byte scan of every backend module
#   → exactly one BOM-prefixed file, exactly one file with C3 A2 E2 82 AC: both api/whatif.py
# Runtime unaffected: `import app.api.whatif` succeeds, WHAT_IF_ASSUMPTIONS[0] decodes clean

# Real rule-14 violations, once the guard is discounted
grep -rn "datetime\.now()" backend/app --include=*.py | grep -v core/clock.py
# → commander/store.py:20 is the ONLY real one (3 other hits are docstrings about the rule)

# API surface
grep -rhoE '@router\.(get|post|put|delete)\("[^"]+"' backend/app/api/*.py | wc -l   # 18

# Doc staleness
git log --oneline --since=2026-08-26 | wc -l   # 25 commits unrecorded in CLAUDE.md
ls docs/DEMO_SCRIPT.md                          # absent

# Dead-but-tested code
grep -rn "build_synthetic_frame" backend/
# → defined in api/whatif.py; referenced ONLY by tests/test_whatif.py (17,43,52,63,70)

# Secret hygiene
git ls-files --error-unmatch .env "~" "~.pub"   # none tracked
git check-ignore -v "~" "~.pub" .env            # .gitignore:59, :60, :22
```

Two prior claims in this session were wrong and are corrected here for the record: an early "frontend tests are green" reading came from a vitest **startup** failure that still exited 0 (a bad `--reporter=basic` flag), and a subsequent parallel run reported `Errors 11` with ~10 files silently unrun while also exiting 0. Only the serial run in Appendix B is trustworthy. **Do not trust a vitest exit code on this machine without reading the file/test counts.**
