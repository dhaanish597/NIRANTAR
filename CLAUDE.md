# CLAUDE.md — NER Landslide Early Warning & Risk Monitoring System

> **Read this file in full at the start of every session, before touching any code.**
> **Update the `Session Log` and `Current State` sections at the end of every session.**
> If anything in this file contradicts what you find in the code, the code is wrong or this file is stale — say so explicitly and ask before proceeding.

---

## 1. What this project is

We are building **SIH26001** for Smart India Hackathon 2026.

| | |
|---|---|
| Problem statement | SIH26001 — AI-Based Early Warning and Landslide Risk Monitoring System in NER |
| Ministry | MDoNER (Ministry of Development of North Eastern Region) |
| Category | **Software** (no custom hardware may be part of the solution) |
| Theme | Disaster Management |
| Internal round deadline | **20 September 2026** |
| Primary success metric | **Judge perception.** A feature that judges cannot see, understand, or believe is worth zero regardless of technical merit. |

### The thesis (memorize this — every design decision descends from it)

India is not short of landslide *prediction*. GSI's National Landslide Forecasting Centre, NESAC's FLEWS, ISRO's Bhuvan and NDMA's SACHET all exist. People die anyway, because:

1. Warnings are **regional, not slope-specific** (taluk/district colour codes).
2. Warnings **do not reach the last village** (~1,841 NER villages have no mobile coverage).
3. There is **no accountable chain** from a bulletin to an actual evacuation.
4. Nobody predicts **which road will be cut and which village will be isolated** — the thing MDoNER actually cares about.

So: **we are not building "another prediction model." We are building the decision-and-dissemination layer that sits on top of existing public feeds and closes those four gaps.**

One-line pitch:
> *"We don't just predict landslides — we make sure the warning reaches the last village and tells them exactly where to go, before the road is gone."*

---

## 2. The demo (this drives the entire architecture)

The product runs in **two modes** and the mode is a first-class concept in the codebase.

- **LIVE mode** — real feeds (IMD / IMERG / SMAP / Sentinel-1), wall-clock time. This is the default state of the dashboard.
- **REPLAY mode** — a judge presses **"Run Case Study"**, picks a real historical disaster (Aizawl 2024, Tupul 2022, Wayanad 2024, Sikkim GLOF 2023), and the system's live inputs are **swapped for that event's reconstructed data**, played back on an accelerated clock. Every downstream component behaves *identically*. The map lights up, the risk engine escalates, roads get flagged, villages get ranked, action cards fire, the audit trail fills — in front of the judges, in ~90 seconds.

At the end of a replay, the system shows a **Counterfactual Lead-Time Scorecard**: what our system would have issued, at what hour, versus what actually happened.

### THE CENTRAL ARCHITECTURAL INVARIANT

> **REPLAY must not be a separate code path. It is a different `Clock` and a different `DataSource` feeding the exact same pipeline.**

If you ever find yourself writing `if mode == REPLAY:` anywhere *below* the ingest layer, stop — you are building a fake demo and it will fall apart under a judge's question. The only places allowed to know about mode are:

- `core/mode.py` (the state machine)
- `core/clock.py` (which clock is instantiated)
- `ingest/` (which source is instantiated)
- The UI mode banner

Everything else — risk, impact, decision, dissemination, audit — receives a timestamp and a set of observations and does not know or care where they came from.

---

## 3. Non-negotiable rules

### Honesty rules (these win or lose the pitch)
1. **Never state a prediction accuracy number that we have not measured** with spatial cross-validation on held-out data. No "99% accurate." A GSI/NESAC geologist on the panel will destroy it.
2. **Any scenario replay event must be excluded from model training data.** Held-out status must be displayed on screen during the replay ("Aizawl 2024 — held out of training"). This is a credibility multiplier; treat leakage as a P0 bug.
3. **All reconstructed scenario data must be labelled as reconstructed**, with its published source, in the UI and in the scenario file's `provenance` block. Never present reconstructed rainfall as if it were archived observation.
4. **InSAR is scoped to slow / deep-seated deformation only.** It does not catch sudden shallow rainfall-triggered debris flows. Say so in the UI. Do not overclaim "weeks of lead time" universally.
5. **Satellite soil moisture (SMAP/ESA CCI) is a topsoil proxy**, not pore-water pressure. Frame it as NASA LHASA v2 does — a surrogate, fused with antecedent rainfall.
6. Show **confidence, provenance, and "not detected" caveats** in the product rather than hiding them.

### Scope rules
7. **No custom hardware.** Category is Software. We may *ingest* from hypothetical state sensor networks via an open REST endpoint, but we deploy nothing physical.
8. **Integrate, don't rebuild.** We consume GSI / IMD / NESAC / Bhuvan data and we emit **CAP 1.2** into SACHET's rails. We are a partner to the national system, never a replacement. Say this in code comments and in the UI.
9. **NER-first.** No generic pan-India model. Wayanad is used as the opening emotional hook only; all other scenarios and the primary AOI are North East.
10. **The demo must run with the network cable unplugged.** All data required for a scenario replay is pre-baked into `data/`. No live API call may be on the demo critical path.

### Engineering rules
11. **Vertical slice first, depth second.** A stubbed end-to-end pipeline that renders on the map beats a brilliant risk model with no UI. Phase 0 exists for this reason.
12. **Schemas are the spine.** Every inter-module boundary is a Pydantic model in `backend/app/schemas/`. Change the schema first, then the producers, then the consumers.
13. **Determinism.** Given the same scenario file and the same model artifact, a replay must produce byte-identical output. Seed everything. No `random` without a seed, no `datetime.now()` outside `core/clock.py`.
14. **`datetime.now()` is banned outside `core/clock.py`.** Everything else calls `clock.now()`. There is a test that enforces this — do not delete it.
15. Never commit large binaries. `data/` derived artifacts are produced by `scripts/` and gitignored except for scenario JSON and small vector files.

---

## 4. Domain glossary (use these exact terms in code and UI)

| Term | Meaning |
|---|---|
| **AOI** | Area of Interest — a pilot district we have pre-baked data for. |
| **Cell** | 500 m analysis unit inside an AOI. Carries static terrain features + dynamic observations. Primary key `cell_id`. |
| **P_fail** | Probability of slope failure for a cell at a tick, ∈ [0,1]. Output of the risk engine. |
| **Runout envelope** | Predicted downslope debris travel polygon from a failing cell. |
| **RII — Road Isolation Index** | Per-village score for likelihood + duration of being cut off, computed on the OSM road graph. **Our signature differentiator.** |
| **EPS — Evacuation Priority Score** | Per-settlement rank fusing P_fail, population, RII, shelter accessibility. Bucketed P1 / P2 / P3. |
| **P1 / P2 / P3** | Immediate Mandatory Evacuation / Evacuation Ready / Watch. |
| **Action Card** | The village-facing artifact: where to go, which road to avoid, nearest usable shelter, what to do now — in local language + voice. |
| **Escalation stage** | Green Watch → Yellow Pre-Alert → Orange Evacuation Ready → Red Evacuate Now. |
| **Audit trail** | Timestamped chain: AI Flagged → DDMA Approved → Disseminated → Village Acknowledged. |
| **Tick** | One step of the pipeline for one timestamp. LIVE = every N minutes; REPLAY = every scenario frame. |
| **Frame** | One timestamped bundle of observations in a scenario file. |
| **DDMA** | District Disaster Management Authority — our primary institutional user. |
| **Safe evacuation window** | Estimated time until critical risk. **Never** call this "time to landslide" — we do not predict exact timing. |

### Reference formulae (NE Himalaya — cite these, they impress geologist judges)
- Intensity–Duration threshold: `I = 5.8294 × D^(-0.4141)` (I in mm/h, D in hours)
- Event–Duration threshold: `E = -11.10 + 0.62 × D` (E in mm, valid 24 < D < 1440 h)
- Dynamic routing cost: `C_edge = L_edge × (1 + α·P_fail + β·S_slope)`; edge severed if `P_fail > P_crit`
- Evacuation priority: `EPS = w1·P_fail + w2·E_pop + w3·RII + w4·(1 − A_shelter)`

Weights and constants live in `backend/app/config.py` and **must be tunable from the UI** (the false-alarm-cost slider is a demo feature, not a hidden constant).

---

## 5. Repository layout

```
.
├── CLAUDE.md                  <- this file
├── docs/
│   ├── BUILD_PLAN.md          <- phased plan; check off tasks here
│   ├── ARCHITECTURE.md        <- data contracts + module responsibilities
│   ├── DEMO_SCRIPT.md         <- the 8-minute pitch, beat by beat
│   └── reference/             <- team research docs (READ-ONLY source of truth)
├── docker-compose.yml
├── Makefile
├── .env.example
├── backend/
│   ├── app/
│   │   ├── main.py
│   │   ├── config.py          <- all tunable constants, no magic numbers elsewhere
│   │   ├── core/
│   │   │   ├── clock.py       <- LiveClock | ScenarioClock  (ONLY datetime.now() here)
│   │   │   ├── mode.py        <- LIVE/REPLAY state machine
│   │   │   └── bus.py         <- in-process pub/sub for tick events
│   │   ├── schemas/           <- Pydantic contracts (the spine)
│   │   ├── ingest/
│   │   │   ├── base.py        <- DataSource protocol
│   │   │   ├── live/          <- imd.py, imerg.py, smap.py, insar.py
│   │   │   └── replay/        <- scenario_source.py
│   │   ├── risk/              <- features, thresholds, model (XGBoost), explain (SHAP)
│   │   ├── impact/            <- runout, road_graph, isolation (RII), priority (EPS)
│   │   ├── decision/          <- routing, action_card, escalation, window
│   │   ├── dissemination/     <- cap.py (CAP 1.2), channels.py, tts.py
│   │   ├── audit/             <- append-only hash-chained event log
│   │   ├── api/                <- FastAPI routers
│   │   └── ws/                <- websocket hub pushing ticks to the UI
│   ├── ml/                    <- training scripts, spatial CV, evaluation reports
│   └── tests/
├── frontend/                  <- React + Vite + TS + MapLibre + Tailwind, PWA
├── data/
│   ├── static/                <- DEM derivatives, lithology, admin, villages, shelters
│   ├── osm/                   <- pre-baked road graphs per AOI
│   ├── scenarios/             <- case study fixtures (COMMITTED)
│   ├── models/                <- trained artifacts + eval reports
│   └── tiles/                 <- PMTiles for offline map
└── scripts/                   <- one-shot data build scripts (idempotent, re-runnable)
```

---

## 6. Stack

| Layer | Choice | Notes |
|---|---|---|
| Backend | Python 3.11, FastAPI, Pydantic v2, Uvicorn | |
| DB | PostgreSQL 16 + PostGIS 3.4 (Docker) | SQLite fallback must exist for laptop-only demo |
| ML | XGBoost, scikit-learn, SHAP | LHASA v2 is the reference architecture |
| Geo | GeoPandas, Rasterio, Shapely, NetworkX, OSMnx | OSMnx only in `scripts/`, never at runtime |
| Realtime | FastAPI WebSocket | one channel, `/ws/ticks` |
| Frontend | React 18 + Vite + TypeScript | |
| Map | MapLibre GL JS + PMTiles | vector tiles for low bandwidth + offline |
| Styling | Tailwind CSS | |
| Offline | vite-plugin-pwa, IndexedDB (`idb`) | |
| Language | AI4Bharat IndicTrans2 + Indic-Parler-TTS | pre-generate audio for demo; live call is a stretch |

---

## 7. Pilot AOIs and scenarios

| AOI | Why | Priority |
|---|---|---|
| **Aizawl, Mizoram** | NH-6 severed at Hunthar in 2024, Aizawl isolated from the country. Perfect RII demo. | **Primary** |
| **Noney/Tupul, Manipur** | 2022 railway site failure, 61 dead, Ijai river dammed. Site was mapped low-moderate susceptibility. | Secondary |
| **Wayanad, Kerala** | Opening hook only: a warning existed ~16 h ahead, 200–400+ dead. Accountability failure. | Hook |
| **Mangan / South Lhonak, Sikkim** | GLOF cascade. **Different hazard physics** — stretch goal, do not attempt before Phase 5. | Stretch |

Scenario files live in `data/scenarios/<id>.json`. Schema is in `docs/ARCHITECTURE.md`. Every scenario carries a `provenance` block with published sources and a `ground_truth` block used to build the counterfactual scorecard.

---

## 8. Common commands

```bash
make up             # start postgres/postgis
make dev            # backend (:8000) + frontend (:5173) with hot reload
make data AOI=aizawl        # build derived static data for an AOI
make graph AOI=aizawl       # build + cache the OSM road graph
make train                  # train risk model with spatial CV, write eval report
make scenario ID=aizawl-2024   # validate + dry-run a scenario file
make test                   # pytest + vitest
make demo-check             # PREFLIGHT: verifies offline demo readiness. Run before every rehearsal.
make freeze                 # tag a known-good demo build
```

`make demo-check` must verify: models present, scenarios validate, tiles present, road graphs cached, no network calls in the replay path, all four scenarios complete a full run.

---

## 9. What we deliberately do NOT build

- Custom IoT / soil-moisture sensors (violates Software category).
- A from-scratch alerting pipe (we emit CAP 1.2 into SACHET's rails).
- A generic pan-India model.
- Autonomous evacuation orders. **Human-in-the-loop always** — the AI recommends, a DDMA officer approves. Say this out loud in the UI.
- Any headline accuracy claim we have not measured.
- Reinforcement learning, LLM agent swarms, blockchain, or anything else that adds demo risk without adding judge-legible value.

---

## 10. Working protocol for Claude Code

**At session start:**
1. Read this file.
2. Read `docs/BUILD_PLAN.md` and identify the current phase and the next unchecked task.
3. Read `docs/ARCHITECTURE.md` if you will touch a module boundary.
4. State in one short paragraph: what phase we are in, what you are about to do, and what you will *not* do this session.

**During:**
- Work on **one task at a time**. Do not start Phase N+1 work while Phase N has unchecked P0 items.
- Write the Pydantic schema before the implementation.
- Write at least one test per module that proves the contract holds.
- If a task turns out to be bigger than the plan assumed, say so and propose a cut rather than silently expanding scope.
- If you need a fact about the disasters, the government systems, the thresholds, or the data sources, read `docs/reference/`. **Do not invent facts, figures, death tolls, or accuracy numbers.** If it is not in the reference docs, mark it `TODO(verify)` and move on.

**At session end (mandatory):**
1. Check off completed items in `docs/BUILD_PLAN.md`.
2. Update `## 11. Current State` below.
3. Append a dated entry to `## 12. Session Log` below: what was done, what broke, what the next session should do first.
4. Run `make test` and report the result honestly, including failures.

---

## 11. Current State

> **Update this section every session. Keep it short and true.**

- **Phase:** 1 done for its P0 critical path (only 1.4 lithology deliberately deferred, 1.9 InSAR
  cut-first, real IMD/SMAP live-download verification blocked on external auth). Phase 2 (impact
  layer) done. Phase 3 (decision/dissemination) done except 3.9 (TTS, not attempted) and 3.11 (P2
  crowdsourced photo, cut-first). Phase 4 (replay engine) done for Aizawl/Wayanad/Tupul; 4.6
  (Sikkim GLOF) explicitly not attempted per its own "only if Phases 0-4 are green" instruction.
  Phase 5 in progress (5.1 PWA done; 5.2/5.3/5.5/5.8 dispatched, not yet verified in this file —
  check BUILD_PLAN.md's own checkboxes for the authoritative state; 5.4 aeroplane-mode rehearsal
  and 5.9 visual design pass are still open and need a human/dedicated pass respectively). Phase 6
  untouched — it's explicitly the user's (rehearsal, freeze, submission).
- **Working end-to-end, for real now, not fabricated numbers:** click **Run Case Study** → pick
  `aizawl-2024` (or `_smoke`) → mode banner flips to REPLAY → real villages (Durtlang, Reiek,
  Tuirini, etc. — genuinely named places in `exposure.gpkg`) escalate Green→Yellow→Orange→Red
  driven by the REAL trained XGBoost model + the real NE-Himalaya I-D/E-D threshold engine
  (whichever is more concerned wins, task 1.19's fusion rule) → real road segments get `p_blocked`
  from real runout-envelope geometry → real RII isolation + real EPS priority ranking → real
  per-village escalation state machine → real routed `EvacuationRoute` to a real nearest shelter →
  a real `ActionCard` fires → a real, hash-chained `AI_FLAGGED`/`ESCALATED` audit trail is written.
  DDMA Console, Audit Trail view, and Village View (tasks 3.7/3.8/3.10) are real, not stubs —
  Approve/Modify/Reject and "I have evacuated" write real audit events over real new endpoints.
  Dissemination (CAP 1.2 + the 4 simulated channels) is built and tested but deliberately NOT
  auto-fired from the pipeline — human-in-the-loop, see below.
- **The central architectural invariant still holds**: nothing below `risk/`/`impact/`/
  `decision/`/`dissemination/` branches on LIVE vs REPLAY. `pipeline.py` (see next bullet) takes a
  timestamp and a set of observations and does not know or care where they came from.
- **`pipeline.py` is wired to every real module** (this was the single biggest outstanding gap —
  it was 100% Phase-0 stubs through Sessions 1-3 despite the real modules existing). Real risk
  (ML + threshold fallback for any cell_id with no terrain match — see the module's own docstring,
  rulings 1-2), real impact chain, real per-village escalation → routing → action cards. Caught
  and fixed a real, 100%-reproducible (not a race) audit-hash-chain ordering bug in the process:
  `AI_FLAGGED` must be appended before any same-tick `ESCALATED` event or its own `prev_hash`
  silently chains from the wrong event — moved earlier in `process()`.
- **The cell-id mismatch is mostly closed, not just documented.** LIVE mode's stub source and
  every scenario file used to share one fake `aizawl_{row}{col}` 3×3 convention with no
  relationship to `cells.gpkg`'s real grid — meaning real villages could never actually escalate
  from a replay. `_smoke.json` and `aizawl-2024.json` (which share the same 9-cell layout) are now
  remapped onto 9 real cells.gpkg cells, each a real named village's genuine nearest analysis
  cell — `frontend/src/lib/grid.ts`'s `REMAPPED_REAL_CELL_POSITIONS` keeps the map rendering them.
  `_smoke.json`'s rainfall values were also redesigned (a synthetic fixture, free to) — the
  original ramp saturated the real multi-window threshold engine from frame 0. `wayanad-2024.json`
  and `tupul-2022.json` are ALSO now remapped the same way, onto real Wayanad/Tupul cells (see
  next bullet) — so all four scenarios should now produce real village-level escalation, not just
  `_smoke`/Aizawl. LIVE mode's `ingest/live/stub_source.py` itself still emits the old fake
  convention — nobody has migrated that yet; not urgent since LIVE mode isn't the demo's focus.
- **Wayanad and Tupul are now real AOIs**, not just scenario files with nowhere to run. Both
  registered in `config.AOIS` (town-center coordinates, `TODO(verify)`-flagged per this project's
  own honesty convention — see the config comments). Real static data built for both: DEM, 500m
  grid, exposure (villages/shelters/hospitals — Wayanad's genuinely includes Chooralmala,
  Mundakkai, Puthumala, Meppadi, Vythiri; Tupul's genuinely includes a village literally named
  "Tupul"), and a real OSM road graph. **No ML model was trained for either** — Wayanad
  deliberately (CLAUDE.md rule 9, NER-first — it's the hook only), Tupul because its NER-inventory
  coverage is too sparse (3-4 trusted points) to be defensible; both rely on the real
  threshold-engine fallback, which is the documented credible-primary signal anyway.
- **Risk model: trained, real, honestly modest.** `data/models/xgb_terrain_v1.json` +
  `eval_report.md`: **AUC-ROC 0.696, PR-AUC 0.500, n=56** (14 positive / 42 negative, Aizawl-only,
  leave-one-quadrant-out spatial CV — NOT "by district," there's only one district's worth of
  terrain grid built). Explicitly not a headline number — the report says so, and the threshold
  engine remains the credible primary per the risk register's own anticipation. Terrain-only (no
  rainfall features — IMERG/SMAP real-download verification is still blocked on external auth, see
  below), so `lithology_class`/`plan_curvature`/`profile_curvature`/`dist_to_fault_km` are 100%
  missing features on purpose, ready for task 1.4/1.2's real values the moment they land with no
  retrain-time schema change needed.
- **Static data (Aizawl):** `dem.tif`, `cells.gpkg` (2,912 cells), `exposure.gpkg` (11 villages, 7
  shelters, 19 hospitals, 0 bridges) — unchanged since Session 2, still real, still sanity-checked.
  `data/osm/aizawl_graph.pkl` (3,622 nodes, 8,808 edges, real OSM Overpass pull) is new this
  session. All of these are gitignored (rule 15) and were NOT present in `main`'s own working
  directory at the start of this session (only in individual agents' now-deleted worktrees) — they
  were regenerated directly in `main` specifically so the pipeline-integration work could be
  tested against real data. If you're starting a fresh checkout, you need to regenerate them
  (`scripts/fetch_dem.py`, `build_grid.py`, `fetch_exposure.py`, `build_road_graph.py`,
  `python -m ml.train --aoi aizawl`) before real-data-dependent tests will run instead of skip.
- **NASA COOLR:** `data/static/ner_inventory.csv` (committed, small, task 1.12 done) — 14,753
  global rows filtered to 504 NER rows across all 8 states.
- **Scenarios ready:** all 4 — `_smoke`, `aizawl-2024`, `wayanad-2024`, `tupul-2022` — validate and
  dry-run through the real pipeline. `sikkim-glof-2023` not attempted (task 4.6, stretch-only).
- **Known gaps / deliberate deferrals (not blockers, but worth knowing about):**
  - Dissemination (CAP 1.2, the 4 simulated channels, `record_dissemination`) is real and tested
    but **not auto-fired from `pipeline.py`** — CLAUDE.md rule 9's human-in-the-loop principle
    means only a DDMA-approval action should trigger it. `POST /api/ddma/decide` exists and calls
    `record_ddma_decision`; nothing yet chains an approval to an actual channel send. That's the
    next real integration gap in the decision/dissemination stack, not this session's pipeline
    wiring (which deliberately stopped at generating the recommendation).
  - `AI_FLAGGED`'s `alert_id` is tick-scoped (`tick-{aoi}-{t}`) while `ActionCard`/`DDMA_APPROVED`/
    `DISSEMINATED` events are village-scoped (`card-{village_id}-{t}`) — the two audit chains
    don't merge under one alert_id yet. The Audit Trail view surfaces this honestly (a "not yet
    reached" row) rather than hiding it. Unifying alert_id schemes is a real follow-up, not
    attempted this session.
  - LIVE mode (`ingest/live/stub_source.py`) still emits the Phase-0 fake `aizawl_401`-style cell
    convention — the cell-id migration only touched the 4 committed scenario files, not the LIVE
    path. LIVE mode isn't the demo's focus (REPLAY is), so this is low-priority but real.
  - `impact/priority.py`'s `resolve_priority_inputs()` re-reads `cells.gpkg`/`exposure.gpkg` from
    disk every tick (it takes the tick's dynamic p_fail dict as an argument, so it can't share the
    same process-wide cache the other static loaders in `pipeline.py` use). Fine for a demo's tick
    cadence, a real perf pass would split it into a cached-static + cheap-dynamic half.
  - `MapView` still renders a **self-contained MapLibre style with no basemap imagery** (Phase 0's
    choice, rule 10). Task 5.2 (PMTiles) adds a real offline basemap *underneath* it — check
    BUILD_PLAN.md's own checkbox for whether that's landed since this was last updated.
  - `ingest/factory.py` is the one place outside `core/` that branches on mode (consistent with
    CLAUDE.md §2's allowance for `ingest/`).
- **External access still needed** (see `Required_by_me.md`, kept current): IMD API key (task
  1.8's real verification; the adapter code itself is written/tested). GSI Bhukosh (task 1.4,
  still deliberately deferred, has a documented fallback). SMAP (task 1.7) may need its OWN
  separate NSIDC Earthdata authorization, not automatically covered by GES DISC's — genuinely
  unconfirmed, flagged for the user to check.
- **Known blockers:** None for Phase 1-5's P0 critical path. Phase 6 is entirely the user's.
- **Next action:** verify Phase 5's dispatched-but-not-yet-confirmed tasks (5.2/5.3/5.5/5.8) landed
  cleanly, then 5.9 (visual design pass) and 5.11 (`make demo-check`) are the natural remaining
  P0/P1 work before Phase 6 (rehearsal/freeze/submit) can start for real.

---

## 12. Session Log

> Newest entry at the top. One entry per session. Keep each to ~5 lines.

### 2026-08-26 — Session 4 (autonomous multi-wave, controller + parallel worktree-isolated agents)

- **Did:** A long autonomous session, dispatched across several waves of parallel worktree-isolated
  subagents (each reviewed, independently re-verified — not just trusted — before merging). Wave 1:
  ML pipeline (tasks 1.12-1.19, real trained model + eval report), impact layer (2.1-2.5, real road
  graph + runout + RII + EPS, `RunoutEnvelope` schema gap closed), decision/dissemination
  groundwork (3.2/3.4/3.5), scenario engine (4.1-4.5/4.7, 3 real case-study scenarios), frontend
  Phase-2/4 UI. Wave 2: SMAP/IMD adapters (1.7/1.8), decision layer completion (2.6/3.1/3.3/3.6 +
  replay pause/resume/speed routes), frontend Phase-5 polish + counterfactual scorecard. Then the
  controller directly wired `pipeline.py` to every real module (it had stayed 100% Phase-0 stubs
  through Sessions 1-3 despite the modules existing) — regenerated Aizawl's road graph + trained
  model directly in `main` to have real data to test against, fixed a real deterministic
  audit-hash-chain ordering bug this exposed, and did the cell-id migration for `_smoke`/
  `aizawl-2024` (redesigned `_smoke.json`'s rainfall values too, computed against the real
  threshold engine, not hand-guessed). Wave 3: DDMA Console/Audit Trail/Village View
  (3.7/3.8/3.10, with real new backend routes), Wayanad+Tupul AOI static-data build + their own
  cell-id migration (closing the AOI-config gap those scenarios' own commits had flagged). Wave 4
  (Phase 5 offline/polish) dispatched, not yet verified as of this entry — check BUILD_PLAN.md.
  ~975 backend + ~200 frontend tests passing by the end of this entry's writing.
- **Broke / discovered:**
  1. A previous session's Session-3 work (GES DISC authorization completed, real IMERG download
     verified) was sitting uncommitted in `main`'s working tree the entire time — found via `git
     status`, committed as-is, credited to when it was actually done, not silently absorbed.
  2. The impact-layer wave-1 agent's session transcript was lost before it could report back
     (harness-side, not the agent's fault) — its real, working, tested code (278 passing tests) was
     still sitting uncommitted in its worktree. Reviewed directly (citations, honesty-rule
     compliance, a real independent test run) and committed by the controller instead of a
     self-report, rather than re-dispatching and losing real completed work.
  3. Wiring the real risk/impact/decision modules into `pipeline.py` surfaced that EVERY cell_id
     in LIVE mode and every scenario file used the Phase-0 stub `aizawl_{row}{col}` convention,
     which structurally never matches `cells.gpkg`'s real grid — meaning real villages could never
     actually escalate from a replay despite all the real modules existing and being individually
     correct. This was the session's most consequential finding; fixed for `_smoke`/`aizawl-2024`/
     `wayanad-2024`/`tupul-2022` (9 real cells each, real nearest-village resolution), not fixed
     for LIVE mode's stub source (lower priority, not the demo's focus).
  4. The audit-hash-chain ordering bug (#1 above) was caught by a 100%-reproducible test failure —
     confirmed deterministic (identical failing hash on 3 repeat runs) before spending time on an
     asyncio-race theory that turned out to be a red herring.
  5. Multiple frontend agents independently built a `REMAPPED_REAL_CELL_POSITIONS` table in
     `grid.ts` for their own AOI's cells (Aizawl vs. Wayanad+Tupul) — same name, different value
     shape — a real, expected merge conflict from genuinely parallel work, resolved by hand into
     one combined table.
  6. `test_smoke_scenario.py`'s own rewritten escalation-arc assertion initially failed because
     `EscalationStateMachine.current_stage()` returns LIVE state — reading it in a loop AFTER all
     ticks had already run (rather than inside the tick-processing loop) silently returned the same
     final stage 10 times over, not a real per-tick history. A real test bug, not a pipeline bug.
- **Next:** confirm wave 4 (5.2/5.3/5.5/5.8) landed cleanly, then 5.9 (visual design pass, read the
  frontend-design skill first) and 5.11 (`make demo-check`, wire the false-alarm slider's real
  numbers in if not already) are the natural remaining work before Phase 6 (entirely the user's —
  rehearsal, freeze, submission) can start for real.

### 2026-08-25 — Session 3

- **Did:** Verified user authorized `NASA GESDISC DATA ARCHIVE` in Earthdata. Identified that
  `imerg.py` was raising 404 on the most recent 1-hour backfill because NASA IMERG Early has a real-world
  ~4-hour publication delay. Added graceful 404 handling for unreleased near-realtime granules in
  `backfill_history()`. Verified real authenticated download of genuine 8.08 MB NASA HDF5 granules
  (`3B-HHR-E.MS.MRG.3IMERG...V07C.HDF5`), HDF5 grid precipitation extraction, and rolling feature calculation
  for Aizawl. All 365 backend tests passing. Checked off task 1.6 and GES DISC in `Required_by_me.md`.
- **Broke / discovered:** NASA IMERG Early run publishes every 30m but with ~4h latency; requesting
  granules within the last 4 hours returns HTTP 404 as expected. Gracefully skipping unreleased granules
  allows backfill to succeed cleanly up to the latest available satellite pass.
- **Next:** Proceed with task 1.7 (`ingest/live/smap.py`) or task 1.12 (`ml/build_inventory.py`).

### 2026-08-25 — Session 2

- **Did:** Verified Docker Desktop is now running (was blocked last session) and confirmed
  `docker compose up -d postgis` brings up a healthy container. Investigated GSI Bhukosh and
  NASA COOLR access in detail (portal structures, registration flows, an actual authenticated
  test request against the COOLR ArcGIS endpoint that confirmed HTTP Basic Auth is the wrong
  credential mechanism for it) — recorded findings in `Required_by_me.md` rather than leaving it
  as an open question. User manually exported `COOLR_Reports_Points.csv` (14,963 rows, global
  scope) via the NASA Earthdata GIS portal. Then did task 1.3: `scripts/fetch_exposure.py` —
  villages/shelters/hospitals/bridges via OSM Overpass + a WorldPop-density-based population
  estimate per village, run for real against Aizawl (11 villages, 7 shelters, 19 hospitals, 0
  bridges — sanity-checked against real named places, not just "ran without error"). Then task
  1.5: `scripts/load_db.py` — idempotent PostGIS loader (delete-then-insert per AOI), run for
  real against the live `postgis` container and verified via direct `psql` queries (row counts,
  `ST_SRID`), idempotency confirmed by re-running and checking counts didn't double. At user's
  request, deferred task 1.4 (GSI lithology) to run last in Phase 1 rather than in 1A — it blocks
  nothing until task 1.15 needs `lithology_class`, documented in BUILD_PLAN.md rather than just
  silently reordered. Then task 1.6: `ingest/live/imerg.py` — real granule URL construction
  (confirmed against an actual GES DISC directory listing), a `requests.Session` subclass fixing
  the cross-host Authorization-header-stripping redirect issue, HDF5 parsing against the publicly
  documented IMERG spec (not yet verified against real bytes — see below), a persistent per-pixel
  rolling-window rainfall cache, and cell-to-pixel mapping verified against the real Aizawl grid
  (2,912 cells map onto just 16 unique 0.1deg IMERG pixels — confirmed the resolution-mismatch
  claim for real, not asserted). 18 new tests using synthetic HDF5 fixtures.
- **Broke / discovered:**
  1. The public Overpass API rate-limited `fetch_exposure.py` (HTTP 429) after just 2 queries at
     a 2s gap, then also returned transient 502/503/504s — added a retry-with-backoff wrapper
     (respecting `Retry-After` when present) rather than a single fixed delay.
  2. WorldPop's 100m population-COUNT raster advertises `Accept-Ranges: bytes` but a real GDAL
     `/vsicurl/` windowed read against it failed ("Range downloading not supported by this
     server!"), and a raw `curl -H "Range: ..."` against it hung rather than returning partial
     content — confirmed by actually trying both, not assumed. Switched to the much smaller
     (~18 MB) 1km population-DENSITY product, downloaded whole and cached, with population
     estimated as `mean(density) * buffer_area_km2` per village — coarser, documented as such.
  3. Found the user had briefly pasted real NASA Earthdata credentials into `.env.example` (a
     tracked file) instead of `.env` — caught and reverted before it was committed, no leak
     reached git history.
  4. Real IMERG granule downloads return NASA's generic GES DISC web-app HTML shell (HTTP 200)
     instead of file bytes — confirmed via the Earthdata Forum that this is the account not
     having authorized the "GES DISC" application yet (a one-time step separate from just having
     an Earthdata login), not a code bug. Added a magic-byte check so this fails loudly with an
     actionable message instead of silently caching garbage as a "successful" download.
  5. Caught (via `test_no_wallclock.py`, not by luck) that `imerg.py`'s CLI entry point called
     `datetime.now()` directly — a real rule-14 violation. Fixed to go through `LiveClock()`.
  6. Caught (by actually running the script, not trusting the unit tests) an off-by-one in
     `REPO_ROOT`'s `.parents[N]` index — `imerg.py` sits one directory deeper than `scripts/`'s
     top-level modules, so the constant copied from a shallower file was wrong by one level.
- **Next:** once the GES DISC authorization above is done, re-run `imerg.py`'s backfill against
  real data and fix the HDF5 parsing if the real structure differs from the documented spec it
  was written against (see the module's own docstring). Otherwise task 1.7 (`smap.py`) or task
  1.12 (`ml/build_inventory.py`, COOLR CSV already exists) are next, and task 1.4 (lithology) is
  now deliberately scheduled last in Phase 1, right before task 1.15.

### 2026-08-25 — Session 1

- **Did:** All of Phase 0 (tasks 0.1–0.16). Repo scaffold, `docs/ARCHITECTURE.md`, every Appendix A
  schema, `Clock`/`ModeMachine`/`Bus`, ingest (live stub + scenario replay), the stub pipeline,
  the real hash-chained audit log, FastAPI + `/ws/ticks`, and the full frontend (MapLibre, mode
  banner, right rail, scenario picker). Verified live in a browser end to end, not just in tests.
  Then started Phase 1: `backend/app/config.py` (AOI registry, replaces `api/routes.py`'s
  duplicate dict), `risk/thresholds.py` (task 1.11, the real I-D/E-D curves, tested — not yet
  wired into the pipeline), and `scripts/fetch_dem.py` (task 1.1, Copernicus DEM GLO-30 via
  the public no-auth AWS Open Data bucket) — actually run against the real Aizawl AOI, not just
  written. Committed Phase 0 (`288967f`), `Required_by_me.md` (`f84319a`). Checked what's
  genuinely blocked before starting Phase 1: Docker Desktop's engine isn't running (confirmed,
  not assumed) and NASA Earthdata/IMD access hasn't been requested yet — both recorded in
  `Required_by_me.md` rather than worked around. Then `scripts/build_grid.py` (task 1.2): DEM
  reprojected to UTM 46N, slope/aspect (Horn's method, sign convention hand-derived and
  verified), D8 flow accumulation + TWI, a 500m grid (2,912 cells), distance-to-road (OSM
  Overpass), land-cover majority (ESA WorldCover) — all run against the real Aizawl AOI and
  sanity-checked (elevation/slope/land-cover distribution all geomorphologically plausible for
  Mizoram, not just "no exception"). Explicitly cut plan/profile curvature, distance-to-fault,
  and lithology_class rather than fabricate or silently skip them — written as null columns,
  flagged in the script docstring and BUILD_PLAN.md. Investigated task 1.12 (NASA COOLR): my
  earlier claim that it's public/no-auth was wrong — its ArcGIS services live under
  `gis.earthdata.nasa.gov` and return 503/499 errors consistent with needing the same Earthdata
  login as IMERG/SMAP. Corrected in `Required_by_me.md` rather than left standing.
- **Broke / discovered:**
  1. Caught (via the determinism test) that the audit event's `event_id` used `uuid.uuid4()` —
     unseeded randomness, violates rule 13. Fixed to a deterministic id.
  2. Caught a real concurrency bug in `api/state.py`: the background task read
     `self.mode.state` inside its own body instead of at the moment `_restart_tick_task()` was
     called. Since `asyncio.create_task` only schedules (doesn't run immediately), a task could
     start after a later transition had already mutated mode state, reading the wrong mode. Fixed
     by capturing mode/scenario_id/clock/source synchronously at transition time.
  3. Vite's esbuild dependency pre-bundler doesn't emit MapLibre's worker chunk, so the map
     silently never finished loading (no error — cells just never painted). Fixed with
     `optimizeDeps: { exclude: ['maplibre-gl'] }`.
  4. The Makefile's `python`/`uvicorn` calls resolved to an unrelated global Python install, not
     `backend/.venv` — `make test` was silently not testing what `requirements.txt` describes.
     Fixed with a `VENV_PY` variable resolved by testing which venv layout actually exists.
  5. `rasterio.mask()` silently 0-fills edge pixels when the source raster declares no nodata
     value — caught by actually inspecting the fetched DEM's min/max instead of trusting "no
     exception raised", since Aizawl has no business having a real 0.0 m elevation pixel. Fixed
     by passing an explicit `nodata=-9999.0` sentinel and setting it on the output file's metadata.
  6. OSM Overpass rejected `requests`' default User-Agent with a flat 406 (curl worked fine on
     the identical query) — Overpass's usage policy wants a descriptive client identifier. Fixed
     by setting an explicit `User-Agent` header.
- **Next:** task 1.3 (`scripts/fetch_exposure.py`) is the natural next static-data task and looks
  unblocked (OSM + WorldPop + Census 2011). Read `Required_by_me.md` first — it now also covers
  the 1.12/Earthdata correction — before assuming any task proceeds the same easy way 1.1/1.2/1.11
  did.
