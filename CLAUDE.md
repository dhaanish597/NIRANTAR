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

- **Phase:** 1 — in progress. Tasks 1.1, 1.2, 1.3, 1.5, 1.6, and 1.11 done and verified against
  real output (not just "ran without error"). Task 1.4 deliberately deferred to run last in
  Phase 1 (see BUILD_PLAN.md) — it blocks nothing until task 1.15. Phase 0 is complete (all 16
  tasks done and verified).
- **Working end-to-end?** Yes, with entirely fabricated numbers, per Phase 0's DoD. Verified live
  in a real browser (not just tests): click **Run Case Study** → pick `_smoke` → mode banner
  flips to REPLAY, the 3×3 cell block escalates Green→Yellow→Orange→Red on the MapLibre map, the
  priority list moves P3→P1, an action card ("Evacuate Now" / RED) appears with shelter + roads
  to avoid, one `AI_FLAGGED` audit event is written per tick.
- **Backend:** scaffolded and real for Phase 0's scope — `core/{clock,mode,bus}.py`,
  `schemas/` (all Appendix A models), `ingest/{base,factory}.py` + `live/stub_source.py` +
  `replay/scenario_source.py`, `pipeline.py` + stub `risk/impact/decision/dissemination`,
  `audit/` (real in-memory hash chain), `api/` (`AppState`, REST routes), `ws/hub.py`, `main.py`.
  `ingest/live/imerg.py` (task 1.6, real but not yet wired into `factory.py` — see below).
  202 backend tests passing (`backend/tests/`).
- **Frontend:** scaffolded and real for Phase 0's scope — Vite + React 19 + TS + Tailwind v4 +
  MapLibre GL v6 + Zustand. `ModeBanner`, `MapView` (self-contained style, no external tile
  requests — see note below), `RightRail`, `ScenarioPickerModal`. 11 frontend tests passing
  (`frontend/src/**/*.test.ts(x)`).
- **Risk model:** not trained — Phase 0's `risk/stub.py` is still what the live pipeline uses.
  `risk/thresholds.py` (the real I-D/E-D threshold engine, task 1.11) exists and is tested but is
  **not wired into the pipeline yet** — that's task 1.17/1.19, once `risk/model.py` also exists,
  so both halves of the fusion rule are available at once.
- **Static data:** `data/static/aizawl/dem.tif` (real Copernicus DEM GLO-30),
  `data/static/aizawl/cells.gpkg` (2,912-cell 500m grid: elevation, slope, aspect, relief, TWI,
  distance-to-road, land-cover; 212 of 2,912 cells legitimately null on terrain stats — edge
  cells with no valid DEM pixel, inherited from task 1.2, not a new bug), and
  `data/static/aizawl/exposure.gpkg` (task 1.3: 11 villages, 7 shelters, 19 hospitals, 0 bridges
  — `man_made=bridge` is a rare OSM tag, documented, not a bug) all exist, all real, all
  sanity-checked against actual values (not just "no exception raised") — see session log.
  `cells.gpkg` has four intentionally-null columns (see task 1.2's note in BUILD_PLAN.md):
  `plan_curvature`, `profile_curvature`, `dist_to_fault_km`, `lithology_class`. Villages carry
  `population_worldpop_est`, a WorldPop-density-based estimate, not a Census figure — named
  distinctly so it's never mistaken for ground truth.
- **Database:** Docker Desktop is now running (was blocked, now fixed — see Required_by_me.md).
  `docker-compose`'s `postgis` container is up and healthy. `scripts/load_db.py` (task 1.5) has
  loaded Aizawl's cells + all four exposure layers into it for real — verified via direct `psql`
  queries (row counts, `ST_SRID`), and confirmed idempotent by re-running the script and checking
  counts didn't double. PostGIS only this pass — no SQLite/SpatiaLite fallback yet, a documented
  scope cut (Docker being fixed removes the urgency).
- **NASA COOLR:** `data/static/COOLR_Reports_Points.csv` obtained (14,963 rows, global scope, not
  yet filtered to India/NER — that filtering is task 1.12's job, not done yet). Gitignored for
  now pending a decision on committing a filtered subset (see Required_by_me.md).
- **Scenarios ready:** `_smoke` only (fabricated, 10 frames, `data/scenarios/_smoke.json`). No
  real-event scenarios yet — those are Phase 4.
- **Known gaps / deliberate deferrals (not blockers, but worth knowing about):**
  - `RunoutEnvelope` is computed by `impact/stub.py` but has no field on `TickResult`
    (Appendix A) — not broadcast to the frontend yet. Phase 2 needs to decide how runout geometry
    reaches the UI (a schema addition vs. a separate endpoint).
  - `MapView` renders a **self-contained MapLibre style with no basemap imagery** — a solid
    background plus our own risk-cell layer, no external tile requests at all. This was a
    deliberate choice so CLAUDE.md rule 10 ("demo runs with the network cable unplugged") holds
    from Phase 0 on rather than being deferred to Phase 5's PMTiles work (task 5.2). Phase 5 adds
    a real offline basemap *underneath* the existing layer, it doesn't replace this setup.
  - Cell geometry in the **live pipeline is still synthetic** (`frontend/src/lib/grid.ts`'s 3×3
    square layout) even though real cell geometry now exists in `data/static/aizawl/cells.gpkg`.
    Nothing has wired the real grid into `ingest`/`risk`/the API yet — that's a Phase 1C/2 task
    (real cell_ids need to replace the `aizawl_{row}{col}` stub convention everywhere: stub_source,
    _smoke.json, grid.ts). Don't assume this is done just because the grid file exists.
  - `ingest/factory.py` (new, not in the original file list) is the one place outside `core/`
    that branches on mode — consistent with CLAUDE.md §2 naming `ingest/` as an allowed
    mode-aware location, but flagging the addition since it wasn't literally named before.
  - `backend/app/config.py` now exists (Phase 1 needed it for AOI bounding boxes — see session
    log). `api/routes.py`'s `/api/aoi/{id}` now reads from it instead of its own duplicate dict.
- **External access still needed** (see `Required_by_me.md`): the Earthdata *account* exists but
  its **GES DISC application isn't authorized yet** — a real, confirmed blocker for task 1.6's
  live-download path (see task 1.6 note above), fixed by one click in the Earthdata profile UI,
  likely needed again for task 1.7 (SMAP). IMD API access not yet requested (blocks 1.8, P1,
  circuit-broken so not critical path). GSI Bhukosh (task 1.4) deliberately deprioritized — see
  BUILD_PLAN.md, it now blocks nothing until task 1.15. Docker Desktop is running.
- **Known blockers:** task 1.6's real-download verification is blocked on the GES DISC
  authorization above — everything else about the adapter (URL construction, parsing logic,
  cell-to-pixel mapping) is written and tested. Nothing else blocks Phase 1's P0 critical path.
- **Next action:** once GES DISC is authorized, re-run
  `python -m app.ingest.live.imerg --aoi aizawl --backfill-hours 6` (from `backend/`) to verify
  the real HDF5 parsing against genuine bytes for the first time — fix `_read_granule_precip` if
  the real structure differs from the documented spec it was written against. Otherwise, task 1.7
  (`ingest/live/smap.py`) or task 1.12 (`ml/build_inventory.py`, COOLR CSV already exists) are the
  natural next tasks not blocked by that.

---

## 12. Session Log

> Newest entry at the top. One entry per session. Keep each to ~5 lines.

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
