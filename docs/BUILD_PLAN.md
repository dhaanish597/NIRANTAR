# BUILD PLAN — NER Landslide Early Warning & Risk Monitoring System (SIH26001)

**Window:** 24 August 2026 → 20 September 2026 (27 days)
**Demo freeze:** 17 September. Nothing but bug fixes after that.
**Read `CLAUDE.md` first.** This file tracks *what* to build and in *what order*. `CLAUDE.md` holds the rules that never change.

---

## How to read this plan

Each phase has a hard **Definition of Done** and a **Demo Value** line. If a phase's DoD is not met, do not advance. Tasks are marked:

- **P0** — the demo dies without it
- **P1** — the demo is visibly weaker without it
- **P2** — nice, cut it without hesitation if behind

**Cut order if behind schedule:** InSAR module → BLE mesh simulation → Sikkim GLOF scenario → live TTS (use pre-generated audio) → what-if simulator → crowdsourced photo CV.
**Never cut:** the replay engine, RII, action cards, the audit trail, the offline PWA.

---

## Phase timeline at a glance

| Phase | Days | Dates | Theme |
|---|---|---|---|
| 0 | 2 | Aug 24–25 | Skeleton + contracts + fake vertical slice |
| 1 | 5 | Aug 26–30 | Real data + risk engine |
| 2 | 5 | Aug 31–Sep 4 | Impact layer — runout, RII, EPS |
| 3 | 5 | Sep 5–9 | Decision + dissemination |
| 4 | 4 | Sep 10–13 | Replay engine + case-study scenarios |
| 5 | 4 | Sep 14–17 | Offline PWA, explainability, polish |
| 6 | 3 | Sep 18–20 | Rehearsal, freeze, submission |

Parallelization note: if you have ≥3 people, one owns `frontend/`, one owns `backend/risk` + `ml/`, one owns `backend/impact` + `backend/decision`. The schemas in Phase 0 are what let this work — get them right on day one.

---

## Phase 0 — Skeleton and contracts (Aug 24–25)

**Demo Value:** none directly. This is the phase that protects every other phase.
**Definition of Done:** `make dev` starts the stack; pressing "Run Case Study" in the browser plays a *fake* 10-frame scenario; a stub risk value renders as coloured cells on a MapLibre map of Aizawl; a stub action card appears; an audit entry is written. All with fabricated numbers. The pipe is real; the water is fake.

- [x] **0.1 (P0)** Repo scaffold: `backend/`, `frontend/`, `data/`, `scripts/`, `docs/`, `Makefile`, `docker-compose.yml` (postgis + backend), `.env.example`, `.gitignore` (ignore `data/static`, `data/osm`, `data/models`, `data/tiles`; **commit `data/scenarios`**).
- [x] **0.2 (P0)** Copy the team research documents into `docs/reference/` and add a README there stating they are read-only source of truth for all domain facts.
- [x] **0.3 (P0)** Write `docs/ARCHITECTURE.md` from **Appendix A** of this file. This is the module-boundary contract.
- [x] **0.4 (P0)** Implement every Pydantic schema in Appendix A under `backend/app/schemas/`. Nothing else gets written until these exist.
- [x] **0.5 (P0)** `core/clock.py`: `Clock` protocol with `now()`, `advance()`, `is_live`. Implement `LiveClock` and `ScenarioClock(start, end, speed_factor)`. **This is the only file in the repo allowed to call `datetime.now()`.**
- [x] **0.6 (P0)** `tests/test_no_wallclock.py` — an AST walk over `backend/app/` that fails if `datetime.now()`, `datetime.utcnow()`, or `time.time()` appears outside `core/clock.py`. Do not delete this test.
- [x] **0.7 (P0)** `core/mode.py`: state machine `LIVE ⇄ REPLAY(scenario_id)`. Transitions: `start_replay(id)`, `pause()`, `resume()`, `set_speed(x)`, `stop_replay()` → returns to LIVE. Emits mode-change events on the bus.
- [x] **0.8 (P0)** `core/bus.py`: minimal in-process async pub/sub. One topic per pipeline stage.
- [x] **0.9 (P0)** `ingest/base.py`: `DataSource` protocol — `async def frames() -> AsyncIterator[ObservationFrame]`. Two implementations: `live/` (stubbed) and `replay/scenario_source.py` (reads a scenario JSON).
- [x] **0.10 (P0)** Pipeline orchestrator `app/pipeline.py`: `frame → risk → impact → decision → dissemination → audit`, each stage a pure function over schemas. Stub every stage with a deterministic fake.
- [x] **0.11 (P0)** FastAPI app + `/ws/ticks` WebSocket that broadcasts `TickResult` objects. REST: `GET /api/aoi/{id}`, `GET /api/scenarios`, `POST /api/replay/start`, `POST /api/replay/stop`, `GET /api/state`.
- [x] **0.12 (P0)** Frontend scaffold: Vite + React + TS + Tailwind + MapLibre. One page: full-bleed map, a mode banner across the top, a right-hand rail, a **"Run Case Study"** button that opens a scenario picker modal.
- [x] **0.13 (P0)** Frontend WebSocket client + Zustand store. Cells render as coloured polygons keyed off `p_fail`.
- [x] **0.14 (P0)** Fake scenario `data/scenarios/_smoke.json` — 10 frames, rising fake rainfall over a 3×3 cell block. Used forever as the CI smoke test.
- [x] **0.15 (P1)** `make demo-check` skeleton — currently just asserts the smoke scenario completes end to end.
- [x] **0.16 (P0)** Update `CLAUDE.md` §11 and §12.

---

## Phase 1 — Real data and the risk engine (Aug 26–30)

**Demo Value:** the map becomes truthful. Real terrain, real rainfall, a real probability.
**Definition of Done:** for the Aizawl AOI, a real rainfall time series drives a trained XGBoost model producing per-cell `p_fail` with SHAP attributions, and the eval report in `data/models/eval_report.md` states AUC under *spatial* block cross-validation.

### 1A. Static data (Aug 26–27)
- [x] **1.1 (P0)** `scripts/fetch_dem.py` — Copernicus DEM 30 m (or ALOS PALSAR 12.5 m if bandwidth allows) for each AOI bounding box. Cache to `data/static/<aoi>/dem.tif`.
- [x] **1.2 (P0)** `scripts/build_grid.py` — 500 m analysis grid clipped to AOI. For each cell compute: mean/max slope, aspect, plan & profile curvature, elevation, relief, TWI, distance to nearest fault/lineament, distance to nearest road, land-cover class, lithology class. Write `data/static/<aoi>/cells.gpkg`. *(Scope cut, documented in the script: plan/profile curvature, distance-to-fault, and lithology_class are written as explicit null columns, not computed — see CLAUDE.md §11/§12. Everything else is real and verified against the actual Aizawl output.)*
- [x] **1.3 (P0)** `scripts/fetch_exposure.py` — village points + population (Census 2011 village directory or OSM `place=village` + WorldPop raster), shelters (OSM `amenity=school|hospital|community_centre` + state DM plan lists), bridges (`man_made=bridge`), hospitals. Write `data/static/<aoi>/exposure.gpkg`. *(Real run against Aizawl, verified against actual values, not just "no exception": 11 villages incl. real named places like Durtlang/Reiek, 7 shelters, 19 hospitals incl. real named ones like Aizawl Civil Hospital, 0 bridges. Scope cuts, documented in the script: Census 2011 and state DM plan lists have no scriptable API, so OSM is the only automated source for now; population is a WorldPop 1km-density-based estimate, not a Census figure — column named `population_worldpop_est`, not `population`, so it can't be mistaken for ground truth; bridges came back empty because `man_made=bridge` is a rare OSM tag — `bridge=yes` on highway ways is a documented, not-yet-implemented fallback.)*
- [ ] **1.4 (P1) — DEFERRED, not skipped.** Lithology / geology layer. If GSI Bhukosh export is not obtainable, fall back to a coarse published geological map and mark the field `source: "coarse_fallback"` in the cell record. Do not silently pretend it is high resolution. *(User decision 2026-08-25: GSI Bhukosh registration is slow and this task blocks nothing yet — `cells.gpkg`'s `lithology_class` column already exists as an explicit null (task 1.2), and nothing reads it until task 1.15's LHASA-v2 feature set (`slope, distance to faults, lithologic strength, ...`) needs it. Deliberately reordered to run last in Phase 1, immediately before 1.15, instead of here in 1A — re-attempt GSI Bhukosh access then, or take the documented `coarse_fallback` at that point if it still hasn't come through. Not a scope cut, just a scheduling one.)*
- [x] **1.5 (P0)** Load everything into PostGIS via `scripts/load_db.py`. Idempotent — re-running must not duplicate. *(Real run against the live docker-compose `postgis` container: 2,912 cells + 11 villages + 7 shelters + 19 hospitals + 0 bridges loaded, SRID confirmed 4326, re-ran the script and confirmed row counts stayed identical — not doubled. Scope cut, documented in the script: PostGIS only, no SQLite/SpatiaLite fallback this pass — Docker is confirmed working now so the fallback isn't blocking anything.)*

### 1B. Dynamic data adapters (Aug 27–28)
- [x] **1.6 (P0)** `ingest/live/imerg.py` — NASA GPM IMERG rainfall via Earthdata. Compute derived features: rain_1h, rain_6h, rain_24h, rain_72h, antecedent_7d, antecedent_15d, antecedent_30d. *(Written and unit-tested (18 tests, synthetic HDF5 fixtures for the parsing logic), but the real-download path is NOT yet verified against a real granule — blocked on a one-time GES DISC app-authorization step on the Earthdata account, confirmed via an actual request that hit exactly this documented NASA symptom, not assumed. See Required_by_me.md. Real, verified this session: the granule URL/naming pattern (confirmed against a real GES DISC directory listing), the cross-host-redirect auth-stripping fix, and the cell-to-pixel mapping against the real Aizawl grid (2,912 cells map onto just 16 unique IMERG pixels — the 10 km-vs-500 m resolution mismatch is real, not a design guess). NOT wired into `ingest/factory.py`'s LIVE branch — CLAUDE.md's Current State already flags that as a separate Phase 1C/2 integration step, not a per-adapter one.)*
- [ ] **1.7 (P0)** `ingest/live/smap.py` — NASA SMAP surface soil moisture. **Every UI surface that shows this must label it "surface proxy (top 5 cm)".**
- [ ] **1.8 (P1)** `ingest/live/imd.py` — IMD public API (`api.imd.gov.in`) district nowcast + warnings. Expect IP-whitelisting friction; wrap in a circuit breaker so a failure degrades gracefully instead of stalling the pipeline.
- [ ] **1.9 (P2)** `ingest/live/insar.py` — Sentinel-1 derived displacement. **Do not attempt full PSI/SBAS processing.** Use pre-processed ground-motion products or a GEE-computed coherence/displacement stack, cached to `data/static/<aoi>/insar_velocity.tif`. If this is not working by Sep 8, cut it to a static pre-computed layer and present it as such.
- [ ] **1.10 (P0)** Every adapter must have an offline cache and a recorded fixture in `tests/fixtures/`.

### 1C. The risk engine (Aug 28–30)
- [x] **1.11 (P0)** `risk/thresholds.py` — implement the NE Himalaya I–D curve `I = 5.8294·D^-0.4141` and E–D curve `E = -11.10 + 0.62·D`. Output a **threshold exceedance ratio** per cell (observed / threshold), not a boolean. This is the physically-grounded baseline and the fallback if ML underperforms. *(Implemented and tested; not yet wired into the pipeline — that's task 1.17/1.19, once risk/model.py exists too.)*
- [ ] **1.12 (P0)** Training inventory: NASA **COOLR / Global Landslide Catalog** filtered to India + NER, joined with GSI Bhukosh points if obtainable. Write `ml/build_inventory.py`. Record source counts in the eval report.
- [ ] **1.13 (P0)** **Hold out every replay-scenario event** (Aizawl May 2024, Tupul Jun 2022, Wayanad Jul 2024, Sikkim Oct 2023) plus a spatial buffer around them. `ml/holdout.py` must assert this and fail the training run if violated. This is a P0 correctness requirement, not a nicety.
- [ ] **1.14 (P0)** Negative sampling strategy — spatially stratified, matched on terrain, drawn from cell-days with no recorded failure. Document the choice in the eval report; a judge may ask.
- [ ] **1.15 (P0)** `ml/train.py` — XGBoost binary classifier, LHASA v2 feature set (slope, distance to faults, lithologic strength, antecedent + current rainfall, soil moisture) plus our terrain extras. **Spatial block cross-validation by district** — never a random split.
- [ ] **1.16 (P0)** `ml/evaluate.py` → `data/models/eval_report.md`: AUC-ROC, PR-AUC, calibration curve, confusion matrix at three operating thresholds, and a **false-alarm-cost table** (alarms/season vs. missed events). This document is what you hand a geologist judge.
- [ ] **1.17 (P0)** `risk/model.py` — inference wrapper, batched per-AOI, returns `CellRisk` with `p_fail`, `confidence`, `threshold_exceedance`, `model_version`.
- [ ] **1.18 (P0)** `risk/explain.py` — SHAP values per cell, top-4 contributing features returned in plain language ("72-hour rainfall: +38%", "slope 41°: +21%").
- [ ] **1.19 (P1)** Fusion rule between ML `p_fail` and threshold exceedance. Keep it simple and explainable (e.g. `max` with a documented rationale, or a calibrated weighted blend). Judges will ask why; have a one-sentence answer.
- [ ] **1.20 (P0)** Update `CLAUDE.md` §11/§12.

---

## Phase 2 — Impact layer: runout, RII, EPS (Aug 31 – Sep 4)

**Demo Value:** this is where we stop looking like everyone else. Nobody in India ships village isolation prediction.
**Definition of Done:** raising rainfall on the Aizawl AOI causes NH-6 to be flagged, causes specific villages to be marked isolated with an estimated duration, and produces a ranked P1/P2/P3 settlement list on screen.

- [ ] **2.1 (P0)** `scripts/build_road_graph.py` — OSMnx extract per AOI → NetworkX graph → serialize to `data/osm/<aoi>_graph.pkl` + a GeoJSON for rendering. **OSMnx runs only here, never at request time.** Preserve `highway` class, bridge flags, and NH/SH refs.
- [ ] **2.2 (P0)** `impact/runout.py` — for cells above a probability threshold, project a runout envelope using DEM flow direction plus an empirical angle-of-reach relationship. Document the empirical relation used. Output a polygon per source cell.
- [ ] **2.3 (P0)** `impact/road_graph.py` — spatial join of runout envelopes onto road edges. Each edge gets `p_blocked`, derived from the max/aggregated `p_fail` of intersecting envelopes. Bridges get a separate, higher-severity treatment (the Punapuzha bridge at Mundakkai is the case study; cite it in the code comment).
- [ ] **2.4 (P0)** `impact/isolation.py` — **RII**. For each village node: remove edges where `p_blocked > P_crit`, test connectivity to the district HQ / nearest hospital / nearest shelter. Output: `isolated: bool`, `p_isolated`, `alternate_route_exists`, `estimated_duration_hours` (heuristic from road class + blockage severity — **label it an estimate in the UI**).
- [ ] **2.5 (P0)** `impact/priority.py` — **EPS** per settlement: `w1·P_fail + w2·E_pop_norm + w3·RII + w4·(1 − A_shelter)`. Bucket into P1/P2/P3 with thresholds in `config.py`. Return the component breakdown so the UI can show *why* a village ranked where it did.
- [ ] **2.6 (P1)** `decision/window.py` — **safe evacuation window**: time until projected threshold crossing from the rainfall forecast trajectory. Emit as a range with confidence. **Never label it "time to landslide."**
- [ ] **2.7 (P0)** Frontend: road layer coloured by `p_blocked`; villages as ranked pins; a **Priority List panel** in the right rail showing P1/P2/P3 with population and isolation status.
- [ ] **2.8 (P1)** Frontend: click a village → drawer with EPS breakdown, RII detail, and the SHAP explanation of the driving slope's risk.
- [ ] **2.9 (P0)** Update `CLAUDE.md` §11/§12.

---

## Phase 3 — Decision and dissemination (Sep 5–9)

**Demo Value:** the "so what." A probability becomes an instruction that reaches a person.
**Definition of Done:** a P1 village generates a multilingual action card with a shelter route that avoids flagged roads; a DDMA officer approves it in a console; a CAP 1.2 XML is emitted; the audit trail shows the full chain with timestamps.

- [ ] **3.1 (P0)** `decision/routing.py` — Dijkstra/A* over the road graph with `C_edge = L_edge × (1 + α·P_fail + β·S_slope)`; edges with `p_blocked > P_crit` severed entirely. Route from village → nearest **usable** shelter (capacity-aware, not merely nearest). Return the route geometry + the roads explicitly avoided.
- [ ] **3.2 (P0)** `decision/escalation.py` — Green Watch → Yellow Pre-Alert → Orange Evacuation Ready → Red Evacuate Now. Hysteresis on downgrade so the UI does not flicker. Each transition is an audit event.
- [ ] **3.3 (P0)** `decision/action_card.py` — the village-facing artifact. Fields: village, stage, plain-language reason, shelter name + walking time, route summary, **roads to avoid by name**, what to carry, who to call, issued-at, valid-until, alert ID.
- [ ] **3.4 (P0)** `dissemination/cap.py` — valid **CAP 1.2** XML. Validate against the schema in a test. This is what proves "we integrate with SACHET, we don't replace it."
- [ ] **3.5 (P0)** `dissemination/channels.py` — channel adapters with a common interface: `CellBroadcastChannel`, `SmsChannel`, `PushChannel`, `MeshChannel`. **For the demo these are simulated** with realistic latency and a delivery/ack rate; label them "simulated channel" in the UI. Never imply we have live telecom integration.
- [ ] **3.6 (P0)** `audit/` — append-only, hash-chained event log. Event types: `AI_FLAGGED`, `DDMA_APPROVED`, `DISSEMINATED`, `DELIVERED`, `VILLAGE_ACKNOWLEDGED`, `ESCALATED`, `STOOD_DOWN`. Each carries alert ID, actor, timestamp, and the input data hash. Expose `GET /api/audit/{alert_id}`.
- [ ] **3.7 (P0)** Frontend **DDMA Console**: pending recommendations queue, each showing the AI rationale, EPS breakdown, affected population, and **Approve / Modify / Reject** buttons. Human-in-the-loop must be visually obvious — a judge should see that no machine ordered an evacuation.
- [ ] **3.8 (P0)** Frontend **Audit Trail view**: a vertical timeline per alert. AI flagged 03:14 → approved by DDMA 03:19 → disseminated 03:20 → 847/1,020 handsets acknowledged 03:26. This slide sells the whole product.
- [ ] **3.9 (P1)** `dissemination/tts.py` — multilingual text via IndicTrans2 (Mizo, Meitei, Assamese, Khasi, Garo, Bodo, Nepali, Nagamese, Hindi, English) + Indic-Parler-TTS audio. **Pre-generate audio for all demo action cards into `data/audio/` and commit it.** Live synthesis at demo time is a needless risk.
- [ ] **3.10 (P1)** Frontend **Village View** — the citizen-facing screen: big stage colour, the action card, a play button for the voice alert, an offline map with the route drawn, an **"I have evacuated"** acknowledge button that writes back into the audit trail.
- [ ] **3.11 (P2)** Crowdsourced report upload — geotagged crack/blocked-road photo, with an on-device or server-side classifier scoring quality/relevance to suppress spam. Answers problem-statement clause (e). Cut this before cutting anything above it.
- [ ] **3.12 (P0)** Update `CLAUDE.md` §11/§12.

---

## Phase 4 — The replay engine and case studies (Sep 10–13)

**Demo Value:** this *is* the demo.
**Definition of Done:** a judge picks "Aizawl, 28 May 2024" from a modal; the mode banner switches to REPLAY with a held-out-from-training badge; 60 hours of the disaster play back in ~90 seconds; the counterfactual scorecard appears at the end. Repeatable ten times without a restart.

- [ ] **4.1 (P0)** Finalize the scenario schema (Appendix B) and write `scripts/validate_scenario.py`. Every scenario must validate in CI.
- [ ] **4.2 (P0)** `scripts/build_scenario.py` — helper that turns published rainfall figures into a frame series with a documented interpolation method, and writes the `provenance` block automatically.
- [ ] **4.3 (P0)** **Scenario: `aizawl-2024`** — the primary. Cyclone Remal, 28 May 2024. Anchors: ~253.7 mm over 3 days in Aizawl; ~6 AM quarry collapse at Melthum–Hlimen; NH-6 severed at Hunthar isolating Aizawl; 27–34 deaths. Ground truth must include the NH-6 severance event so the RII counterfactual lands.
- [ ] **4.4 (P0)** **Scenario: `wayanad-2024`** — the accountability hook. 30 July 2024, ~572 mm/48 h at Puthumala, night-time initiation 02:00–04:30, failure on a pre-existing 2020 crack, Punapuzha bridge collapse isolating Mundakkai. Ground truth includes the Hume Centre alert at ~09:00 on 29 July, ~16 h prior. Death toll must be shown as a **range (200–400+)** with a source note — not a single fabricated number.
- [ ] **4.5 (P1)** **Scenario: `tupul-2022`** — 30 June 2022, Noney, Manipur. 705.5 mm May–Jun (130% above decadal average), two-phase failure ~00:30 and ~06:00, 61 dead, Ijai river dammed. The point this scenario proves: **the site was mapped low-to-moderate susceptibility** — static maps miss things, dynamic risk does not.
- [ ] **4.6 (P2)** **Scenario: `sikkim-glof-2023`** — stretch. Different hazard physics (moraine collapse → GLOF cascade). Only attempt if Phases 0–4 are green. If included, be explicit in the UI that this is a *cascading* hazard and that our InSAR layer is the relevant precursor signal (>15 m/yr moraine displacement 2016–2023).
- [ ] **4.7 (P0)** `ingest/replay/scenario_source.py` — reads frames, respects `ScenarioClock`, supports pause / resume / speed / **scrub to timestamp** / restart. Restart must fully reset downstream state — no residue from the previous run.
- [ ] **4.8 (P0)** Frontend **scenario picker modal**: cards with event name, date, location, death toll (with source), a one-line "what went wrong," and a **"Held out of training"** badge. The badge is not decoration — it is the answer to the sharpest question a judge will ask.
- [ ] **4.9 (P0)** Frontend **replay control bar**: play/pause, speed (1×/10×/60×/360×), a timeline scrubber showing scenario time, and a persistent **REPLAY MODE — reconstructed data** banner so nobody can accuse us of passing simulation off as live.
- [ ] **4.10 (P0)** **Counterfactual Lead-Time Scorecard** — the closing artifact of every replay. Two columns:
  - *What actually happened*: official warning level, when, at what spatial scale, the outcome.
  - *What our system produced*: first Yellow at T−h, first Orange at T−h, P1 evacuation list at T−h, N villages flagged, M km of road flagged, NH-6 severance predicted at T−h.
  Plus one honest line: **what we would have missed**. Include it. A team that names its own limitation is the team judges believe.
- [ ] **4.11 (P0)** Determinism test: run each scenario twice, assert identical `TickResult` hashes.
- [ ] **4.12 (P0)** Update `CLAUDE.md` §11/§12.

---

## Phase 5 — Offline, explainability, polish (Sep 14–17)

**Demo Value:** answers "will it work in a village with no signal?" and "why should I trust your number?"
**Definition of Done:** aeroplane mode on the demo laptop still renders the map, the cached action card, and the route. The false-alarm slider visibly changes the alert set. Nothing on screen looks like a default template.

- [ ] **5.1 (P0)** PWA: service worker via `vite-plugin-pwa`, app shell cached, install prompt working.
- [ ] **5.2 (P0)** Offline map: PMTiles for each AOI in `data/tiles/`, served locally, cached in IndexedDB. Must render with the network disabled.
- [ ] **5.3 (P0)** Offline data: last action card, route geometry, shelter list, emergency contacts in IndexedDB. Queue acknowledgements and sync on reconnect.
- [ ] **5.4 (P0)** **Aeroplane-mode rehearsal** — physically disable networking and run the full Aizawl replay. Fix whatever breaks. Do this on the actual demo machine, not a dev box.
- [ ] **5.5 (P1)** `MeshChannel` simulation: a small visual of phone-to-phone store-and-forward propagation through a village with no tower coverage. Cite the real number — ~1,841 NER villages without mobile coverage. Label it clearly as a simulation.
- [ ] **5.6 (P0)** **False-alarm-cost slider** in the DDMA console. Moving it re-thresholds live and shows the tradeoff: "at this setting, ~N alarms/season, ~M% of historical events caught." Wire it to the real eval numbers from `eval_report.md`. This single control pre-empts the most common geologist objection.
- [ ] **5.7 (P0)** Explainability panel: SHAP bars in plain language, data provenance per input (source, timestamp, resolution, "surface proxy" labels), and confidence.
- [ ] **5.8 (P1)** **What-if simulator**: a rainfall slider ("simulate 250 mm over 12 h") that re-runs the pipeline on synthetic input and shows the resulting failure distribution, road severance and isolation cascade. Position as DDMA pre-positioning support.
- [ ] **5.9 (P1)** Visual design pass. Dark operational-console aesthetic, one strong accent, generous whitespace, real typography. Read `/mnt/skills/public/frontend-design/SKILL.md` before this task. The map is the hero; chrome recedes.
- [ ] **5.10 (P1)** Onboarding: a 20-second first-run overlay so a judge who touches the laptop is never lost.
- [ ] **5.11 (P0)** `make demo-check` completed properly — verifies models, scenarios, tiles, graphs, audio, no network on the replay path, and a clean run of all scenarios.
- [ ] **5.12 (P0)** Update `CLAUDE.md` §11/§12.

---

## Phase 6 — Rehearsal, freeze, submit (Sep 18–20)

**Definition of Done:** the demo has been run start-to-finish five times without intervention, on the demo hardware, offline, by two different people.

- [ ] **6.1 (P0)** Write `docs/DEMO_SCRIPT.md` — the 8-minute run, beat by beat, with who says what and who clicks what. Include a 3-minute compressed version in case the panel cuts you short.
- [ ] **6.2 (P0)** **Freeze the build.** Tag it. Bug fixes only from here.
- [ ] **6.3 (P0)** Record a 3-minute screen capture as the fallback if the laptop dies.
- [ ] **6.4 (P0)** Rehearse the **10 hard judge questions** from the strategic reference doc. Every team member must be able to answer Q1 (how is this different from GSI's LEWS?), Q2 (software-only soil moisture?), Q3 (accuracy and false-alarm rate?) and Q7 (InSAR in vegetated NER?).
- [ ] **6.5 (P1)** One-page architecture handout for the panel.
- [ ] **6.6 (P0)** Final `make demo-check`, five clean runs, two operators.
- [ ] **6.7 (P0)** Submit.

---

## The 8-minute demo arc (build toward this)

1. **0:00** — Wayanad. One slide, one number: a warning existed ~16 hours ahead; 200–400+ people died anyway. *The gap is not prediction.*
2. **0:45** — Live dashboard, NER map. "This is what we run every day."
3. **1:15** — Press **Run Case Study** → pick **Aizawl, 28 May 2024**. Point at the "held out of training" badge and say it out loud.
4. **1:30 – 3:30** — Replay. Rain builds, cells escalate, **NH-6 at Hunthar goes red**, Aizawl's isolation risk climbs, the priority list orders itself P1/P2/P3.
5. **3:30** — A P1 village action card fires. Play the **Mizo voice alert**. Show the shelter route bending around the flagged road.
6. **4:30** — DDMA console: a human approves. Audit trail fills in with timestamps and acknowledgement percentage.
7. **5:30** — Aeroplane mode. The village screen still works. Cite ~1,841 uncovered villages.
8. **6:15** — Honesty beat: SHAP explanation, the false-alarm slider, and what the system would have missed.
9. **7:00** — **Counterfactual scorecard**: our first Orange at T−h vs. what was actually issued.
10. **7:30** — Close: CAP 1.2 into SACHET, ₹378 crore already earmarked for NE states under NLRMP, open data only, NESAC as the hosting partner. *We are a partner to the national system, not a replacement.*

---

## Risk register

| Risk | Likelihood | Mitigation |
|---|---|---|
| Landslide inventory too sparse to train a credible model | High | Threshold-exceedance engine (§1.11) is the fallback and is what GSI itself uses. Ship it as the primary if ML underperforms; present ML as an enhancement layer with measured numbers. |
| InSAR processing eats a week | High | Hard-cut date Sep 8. Fall back to a pre-computed static velocity layer, presented honestly as such. |
| IMD API IP-whitelisting blocks access | Medium | IMERG is the primary rainfall source; IMD is supplementary and circuit-broken. |
| Demo laptop has no network at the venue | Medium | Everything pre-baked. §5.4 aeroplane-mode rehearsal is mandatory. |
| Judge asks about training leakage on replayed events | **Certain** | §1.13 hard assertion + the on-screen badge. Volunteer this before they ask — it converts a threat into a credibility win. |
| Frontend polish consumes the last week | Medium | Phase 5 visual pass is timeboxed to one day. Function over finish. |
| Scope creep into a fifth scenario | Medium | Two scenarios done well beat four done badly. Aizawl + Wayanad is a sufficient demo. |

---

# Appendix A — Data contracts

These become `backend/app/schemas/`. Every module boundary crosses one of these. Extract this appendix into `docs/ARCHITECTURE.md` in task 0.3.

```python
# ---- Mode & time -------------------------------------------------------
class RunMode(str, Enum):
    LIVE = "live"
    REPLAY = "replay"

class ModeState(BaseModel):
    mode: RunMode
    scenario_id: str | None
    scenario_time: datetime | None
    speed_factor: float = 1.0
    paused: bool = False

# ---- Ingest ------------------------------------------------------------
class CellObservation(BaseModel):
    cell_id: str
    rain_1h: float; rain_6h: float; rain_24h: float; rain_72h: float
    antecedent_7d: float; antecedent_15d: float; antecedent_30d: float
    soil_moisture: float | None            # surface proxy, 0-1
    insar_velocity_mm_yr: float | None
    source: str                            # "imerg" | "scenario:aizawl-2024" | ...
    is_reconstructed: bool = False

class ObservationFrame(BaseModel):
    t: datetime
    aoi_id: str
    cells: list[CellObservation]
    provenance: dict[str, str]

# ---- Risk --------------------------------------------------------------
class Attribution(BaseModel):
    feature: str
    plain_language: str                    # "72-hour rainfall"
    contribution: float                    # signed SHAP value
    display_pct: float

class CellRisk(BaseModel):
    cell_id: str
    p_fail: float                          # [0,1]
    threshold_exceedance: float            # observed / ID-curve threshold
    confidence: float
    attributions: list[Attribution]
    model_version: str

# ---- Impact ------------------------------------------------------------
class RunoutEnvelope(BaseModel):
    source_cell_id: str
    geometry: dict                         # GeoJSON Polygon
    p_fail: float
    method: str                            # empirical relation used

class RoadSegmentRisk(BaseModel):
    edge_id: str
    name: str | None                       # "NH-6"
    highway_class: str
    is_bridge: bool
    p_blocked: float
    severed: bool
    contributing_cells: list[str]

class VillageIsolation(BaseModel):
    village_id: str
    name: str
    population: int
    p_isolated: float
    isolated_now: bool
    alternate_route_exists: bool
    est_duration_hours: float | None       # ALWAYS labelled "estimate" in UI
    severed_links: list[str]

class SettlementPriority(BaseModel):
    village_id: str
    eps: float
    tier: Literal["P1", "P2", "P3"]
    components: dict[str, float]           # {"p_fail":.., "pop":.., "rii":.., "shelter":..}

# ---- Decision ----------------------------------------------------------
class EvacuationRoute(BaseModel):
    village_id: str
    shelter_id: str
    shelter_name: str
    geometry: dict                         # GeoJSON LineString
    distance_m: float
    est_walk_minutes: int
    avoided_roads: list[str]
    shelter_capacity_ok: bool

class ActionCard(BaseModel):
    alert_id: str
    village_id: str
    stage: Literal["GREEN", "YELLOW", "ORANGE", "RED"]
    headline: str
    reason_plain: str
    shelter_name: str
    route: EvacuationRoute | None
    roads_to_avoid: list[str]
    what_to_carry: list[str]
    contact: str
    issued_at: datetime
    valid_until: datetime
    safe_window_hours: tuple[float, float] | None   # range, never a point estimate
    translations: dict[str, str]           # lang code -> text
    audio_urls: dict[str, str]

# ---- Audit -------------------------------------------------------------
class AuditEvent(BaseModel):
    event_id: str
    alert_id: str
    kind: Literal["AI_FLAGGED","DDMA_APPROVED","DISSEMINATED",
                  "DELIVERED","VILLAGE_ACKNOWLEDGED","ESCALATED","STOOD_DOWN"]
    actor: str                             # "system" | "ddma:officer_id" | "village:id"
    t: datetime
    payload: dict
    input_hash: str
    prev_hash: str                         # hash chain
    hash: str

# ---- Tick (the websocket payload) --------------------------------------
class TickResult(BaseModel):
    t: datetime
    mode: RunMode
    scenario_id: str | None
    aoi_id: str
    cell_risks: list[CellRisk]
    road_risks: list[RoadSegmentRisk]
    isolations: list[VillageIsolation]
    priorities: list[SettlementPriority]
    new_action_cards: list[ActionCard]
    new_audit_events: list[AuditEvent]
    is_reconstructed: bool
```

---

# Appendix B — Scenario file schema

`data/scenarios/<id>.json`. These files are **committed to git** and validated in CI.

```jsonc
{
  "id": "aizawl-2024",
  "name": "Aizawl multi-slope failures, Mizoram",
  "event_date": "2024-05-28",
  "aoi_id": "aizawl",
  "hazard_type": "rainfall_triggered_shallow",
  "trigger": "Cyclone Remal",

  "held_out_of_training": true,
  "provenance": {
    "confidence": "reconstructed",
    "method": "Published 3-day and daily totals disaggregated to hourly using a documented storm profile; see scripts/build_scenario.py",
    "sources": [
      "IMD daily rainfall bulletins, May 2024",
      "Peer-reviewed post-event study (see docs/reference/)",
      "Mizoram SDMA situation reports"
    ],
    "disclaimer": "Rainfall series is reconstructed from published aggregate figures, not archived gauge observation."
  },

  "clock": {
    "start": "2024-05-26T00:00:00+05:30",
    "end":   "2024-05-28T18:00:00+05:30",
    "frame_interval_minutes": 60,
    "default_speed_factor": 3600
  },

  "frames": [
    {
      "t": "2024-05-26T00:00:00+05:30",
      "cells": [
        { "cell_id": "aizawl_0412", "rain_1h": 2.1, "soil_moisture": 0.31 }
      ],
      "defaults": { "rain_1h": 0.4, "soil_moisture": 0.28 }
    }
  ],

  "ground_truth": {
    "failures": [
      { "t": "2024-05-28T06:00:00+05:30", "lat": 23.70, "lon": 92.71,
        "note": "Stone quarry collapse, Melthum–Hlimen", "deaths_attributed": "multiple" }
    ],
    "road_events": [
      { "t": "2024-05-28T07:00:00+05:30", "road": "NH-6", "location": "Hunthar",
        "effect": "severed", "consequence": "Aizawl isolated from the rest of the country" }
    ],
    "official_warnings": [
      { "t": "2024-05-27T08:00:00+05:30", "issuer": "IMD", "level": "red",
        "spatial_scale": "district", "note": "No slope-specific warning issued" }
    ],
    "outcome": {
      "deaths": "27–34 (state total; 33 bodies recovered per academic study)",
      "source_note": "Report as a range with source; do not assert a single figure."
    }
  },

  "narration": [
    { "t": "2024-05-28T04:00:00+05:30",
      "text": "Antecedent rainfall from Cyclone Remal has saturated the Aizawl slopes. Our engine escalates 14 cells to Orange — two hours before the quarry collapse." }
  ]
}
```

The `narration` array drives optional on-screen captions during replay so the presenter does not have to narrate every beat from memory.
