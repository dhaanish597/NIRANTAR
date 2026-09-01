# extension_v1 — P0: Smart India Hackathon Completion Build Plan

> **Project:** ICONIX / NIRANTAR — AI-Based Early Warning & Landslide Risk Monitoring System for the North Eastern Region  
> **Primary objective:** Make the existing project complete, credible, reliable, offline-capable, judge-ready, and submission-ready for Smart India Hackathon (SIH).  
> **Secondary objective:** Preserve a clean foundation so later `extension_v1` phases can add advanced innovations for other hackathons without destabilizing the SIH build.
>
> **This file is intended to be given directly to Codex.**
>
> **Important:** Do not assume that an item is implemented merely because it appears in an older BUILD_PLAN, README, PPT, or specification. The code and current tests are the source of truth. Inspect the repository before modifying anything.

---

# 0. Mission

Complete the SIH version of ICONIX from its current functional-prototype state into a **reliable competition build**.

The target is not merely "make tests pass."

The target is:

> **A judge can run the project end-to-end, offline, on the demo machine, using the Aizawl case study, see real model-driven risk escalation, real impact/isolation analysis, real routing, a real action card, human approval, dissemination, auditability, explainability, and a credible fallback path — without encountering fabricated judge-facing data, broken maps, dead network dependencies, or misleading claims.**

The latest project audit reports approximately **74/89 planned tasks complete**. Phases 0–4 are largely functionally complete, Phase 5 is partially complete, and Phase 6/rehearsal has not yet been completed. The current implementation already has a real demo spine:

`case study replay → XGBoost + rainfall-threshold fusion → SHAP → runout → road severance → RII → EPS → routing → Action Card → approval/dissemination → audit`

The remaining work must focus first on **correctness, credibility, offline reliability, integration, and demo readiness**.

---

# 1. Non-negotiable principles

## 1.1 Never fabricate

Do not create fake populations, road names, risk values, model outputs, confidence values, timestamps, event IDs, or infrastructure counts merely to make the UI look impressive.

If real data is unavailable:

1. use a clearly labelled deterministic fallback,
2. show that it is a fallback,
3. never present it as measured real-world data.

The current `frontend/src/lib/whatIfDemo.ts` is specifically flagged for fabricated judge-facing village populations and road names. Fix this before the final demo.

## 1.2 Replay is the reliable SIH demo path

The primary SIH demonstration must work from **reconstructed/replay data** without depending on internet access.

LIVE mode may remain available, but:

- it must not overwrite replay data with synthetic fallback data;
- it must not silently require the network during replay;
- it must not claim live data when it is using fallback/synthetic data.

## 1.3 Offline means physically offline

The project must work with networking disabled.

Do not claim "offline-first" merely because IndexedDB exists.

The final verification must physically disable networking on the actual demo machine and run the Aizawl replay.

## 1.4 Human-in-the-loop is mandatory

AI recommends.

Authorised human approves.

System disseminates.

System audits.

Never present the AI Commander as autonomous emergency authority.

## 1.5 Existing real pipeline must be preserved

Do not replace the real risk/impact/decision pipeline with hardcoded demo logic.

The real Aizawl pipeline currently includes:

- trained XGBoost model
- published rainfall threshold curves
- SHAP
- DEM-based runout
- OSM road graph
- road severance
- Road/Village Isolation Index
- Evacuation Priority Score
- escalation state machine
- safe evacuation window
- risk-aware routing
- Action Cards
- audit trail

These are the core of the SIH build.

## 1.6 Do not expand scope prematurely

For this P0:

### Required now
- SIH-critical correctness
- offline demo
- map
- real data integrity
- What-if integration
- live/replay correctness
- alert/action flow
- audit chain
- case studies
- demo-check
- documentation
- final rehearsal infrastructure

### Optional but strongly encouraged if low-risk
- pre-generated Mizo voice alerts
- visual polish

### Explicitly defer to later extension phases unless already safe
- full Sentinel-1 InSAR processing
- Sikkim GLOF
- crowdsourced image CV
- broad multi-hazard engine
- advanced multimodal AI

Do not let future features destabilize the SIH submission.

---

# 2. Current-state risks to resolve first

The latest audit identified these important issues. Verify each against the current repository before changing it.

## P0-A — Test-suite failure / encoding problem

`backend/app/api/whatif.py` has a UTF-8 BOM and mojibake character issue that causes `tests/test_no_wallclock.py` to fail before its AST checks execute.

That means a real wall-clock violation can remain hidden.

The audit identified a violation around:

`backend/app/commander/store.py:20`

and a nondeterministic UUID/event ID issue in:

`backend/app/api/whatif.py`

Fix the parser/encoding problem first, then fix every violation the test reveals.

### Acceptance

- `pytest` no longer fails because of the BOM.
- `tests/test_no_wallclock.py` actually executes its AST scan.
- No forbidden wall-clock calls remain outside the allowed clock abstraction.
- Deterministic replay behavior remains intact.

---

# 3. P0-A — Repository reconnaissance before edits

Before changing code, Codex MUST inspect:

```text
git status
git log --oneline -20
docs/BUILD_PLAN.md
PROJECT_STATUS.md (if present)
CLAUDE.md
docs/ARCHITECTURE.md (if present)
backend/
frontend/
tests/
data/
Makefile
docker-compose.yml
```

Also search for:

```text
TODO
NotBuilt
fallback
demo
whatIfDemo
uuid.uuid4
datetime.now
datetime.utcnow
time.time
LIVE
REPLAY
pmtiles
audio
IndexedDB
offline
scenario
Aizawl
Wayanad
Tupul
```

Do not overwrite local user work.

Before each meaningful edit, inspect the relevant current implementation.

---

# 4. P0-1 — Restore a fully green automated test baseline

## 4.1 Fix `whatif.py` encoding

Remove the UTF-8 BOM and repair mojibake without changing behavior.

Confirm the file is valid UTF-8.

## 4.2 Fix deterministic clock violations

Where an event ID or timestamp is generated during replay:

- inject/use the project clock abstraction;
- never call `datetime.now()`, `datetime.utcnow()`, `time.time()`, etc. in replay-sensitive code;
- use deterministic IDs derived from stable inputs where the architecture requires deterministic replay.

Example principle:

```python
event_id = f"event-{aoi_id}-{tick_time.isoformat()}"
```

Use the repository's established ID conventions if they already exist. Do not introduce a second ID system unnecessarily.

## 4.3 Fix nondeterministic UUID generation

If `uuid.uuid4()` is used in replay/demo paths, replace it with deterministic identifiers.

Do not remove UUID support globally if UUIDs are legitimately required for real live transactions. Scope the change to deterministic/replay paths.

## 4.4 Run the complete backend suite

Run:

```bash
pytest -q
```

Expected:

- zero failures;
- skips only where explicitly justified;
- no hidden failure caused by a parser error.

If a test exposes a real defect, fix the defect rather than weakening the test.

---

# 5. P0-2 — Remove fabricated What-If judge-facing data

## Problem

The current What-If demo layer has been identified as containing fabricated village populations and road names.

This is a major credibility risk.

A judge must never see a fabricated number presented as real.

## Required behavior

The What-If simulator must use the actual backend simulation result.

The intended flow is:

```text
UI input
  ↓
POST /api/whatif/simulate
  ↓
synthetic observation frame
  ↓
real Pipeline()
  ↓
real XGBoost + threshold fusion
  ↓
real runout
  ↓
real road severance
  ↓
real isolation
  ↓
real priority
  ↓
real response
```

The What-If result must NOT be generated by a separate fake frontend dataset.

## Important existing issue

The current `simulate_whatif()` implementation was audited as not actually invoking the same real `Pipeline.process()` path used by replay.

Fix this.

### Acceptance

Changing rainfall from e.g.:

```text
100 mm
→
250 mm
→
400 mm
```

must produce deterministic, model/physics-derived changes in:

- cell failure probabilities;
- risk tier distribution;
- runout;
- road severance;
- isolation;
- priority;
- routing where applicable.

The UI must display assumptions clearly.

Example:

```text
WHAT-IF — SIMULATED SCENARIO

Rainfall: 250 mm
Duration: 12 h

Assumptions:
• Rainfall applied uniformly across the AOI grid
• Constant storm intensity over the simulated duration
• Road severance calculated from runout/road intersection
• This is a counterfactual simulation, not a forecast
```

Never call a counterfactual output "predicted reality."

---

# 6. P0-3 — Fix LIVE/REPLAY state integrity

## Problem

The audit identified two hardcoded LIVE badges and a modified tick store that can allow synthetic forecast/fallback data to overwrite the real model output.

Also, the live stub source still uses an old fake cell-ID convention:

```text
aizawl_{row}{col}
```

while real `cells.gpkg` uses real cell IDs.

## Required work

### 6.1 Mode state

All UI mode labels must come from the canonical application state.

Never hardcode:

```text
LIVE
```

in a component.

Use the existing mode store/state.

### 6.2 Replay isolation

When the application is in replay mode:

- replay frames are authoritative;
- forecast fallback cannot overwrite the map;
- external network fetches must not be required;
- synthetic forecast data cannot silently replace model output.

### 6.3 LIVE cell mapping

If LIVE mode is retained:

- map incoming/live observations onto real cell IDs;
- do not invent IDs that cannot join with the real grid.

If full LIVE integration cannot be made reliable without network credentials, keep the live stub explicitly labelled and do not let it contaminate replay.

### Acceptance

- REPLAY remains deterministic.
- LIVE and REPLAY badges are correct.
- Switching modes does not leak state.
- A replay run produces identical outputs for identical scenario/tick inputs.
- No synthetic forecast overwrites replay/model data.

---

# 7. P0-4 — Complete the real static data required for SIH scenarios

The final demo should have working data for the scenarios that are presented.

The audit identified missing artifacts including:

```text
data/static/wayanad/
data/static/tupul/
data/osm/wayanad_graph.pkl
data/osm/tupul_graph.pkl
data/tiles/aizawl.pmtiles
data/audio/
```

Regenerate only through the repository's existing scripts and documented pipeline.

## 7.1 Wayanad

Generate/verify:

```text
DEM
cells
exposure
road graph
scenario references
```

Use the repository's established commands, e.g.:

```bash
python scripts/fetch_dem.py --aoi wayanad
python scripts/build_grid.py --aoi wayanad
python scripts/fetch_exposure.py --aoi wayanad
python scripts/build_road_graph.py --aoi wayanad
```

If exact CLI signatures differ, inspect the scripts and use the actual supported interface.

## 7.2 Tupul

Repeat for:

```text
aoi=tupul
```

## 7.3 Do not download blindly

If a dataset requires credentials or external access:

- detect the failure;
- preserve the documented offline fallback;
- do not hardcode credentials;
- do not commit secrets;
- document exactly what is unavailable.

## Acceptance

Each intended replay scenario must:

1. load;
2. validate;
3. run;
4. produce impact results;
5. render map layers;
6. generate action/decision outputs;
7. complete without uncaught exceptions.

---

# 8. P0-5 — Fix the offline basemap

This is one of the most visible remaining demo problems.

Current failure mode:

> MapLibre loads, overlays render, but the basemap is absent.

The Aizawl terrain must be visible offline.

## Preferred solution

Use the existing PMTiles architecture if the repository supports it.

Verify:

```text
data/tiles/aizawl.pmtiles
```

exists and is non-empty.

Verify the MapLibre PMTiles protocol is registered BEFORE map construction.

Expected architecture:

```javascript
maplibregl.addProtocol(...)
```

before:

```javascript
new maplibregl.Map(...)
```

## Debug sequence

1. Check file existence.
2. Check file size.
3. Check browser network requests.
4. Verify HTTP Range requests.
5. Verify protocol registration order.
6. Verify MapLibre style sources/layers.
7. Add persistent map error logging.
8. Test with networking disabled.

## Offline fallback

If a PMTiles extract cannot be generated quickly, use an offline terrain/hillshade raster generated from the repository's DEM.

Conceptually:

```bash
gdaldem hillshade <aoi_dem>.tif hillshade.tif -z 2 -az 315 -alt 45
gdal2tiles.py --xyz -z 8-14 hillshade.tif data/tiles/hillshade/
```

Then serve it locally and render it as a MapLibre raster layer.

The fallback MUST remain fully offline.

## Forbidden

Do not use:

```text
OSM raster tile servers
external MapLibre styles
demotiles.maplibre.org
Google Maps network tiles
any external basemap dependency
```

for the offline replay.

## Acceptance

With Wi-Fi/network disabled:

- map loads;
- terrain/basemap is visible;
- risk cells render;
- roads render;
- affected roads are distinguishable;
- map interactions still work.

---

# 9. P0-6 — Make offline data complete

The citizen application must have local access to everything necessary for the SIH demo.

Store/cache locally:

- last action card;
- route geometry;
- shelter list;
- emergency contacts;
- relevant map assets;
- current watch/risk state;
- queued acknowledgements;
- queued reports if reporting is enabled.

Use the repository's existing IndexedDB/offline storage abstraction.

## Offline state indicator

Keep a persistent indicator with three states:

```text
ONLINE · SYNCED
OFFLINE · N ITEMS QUEUED
SYNCING
```

Show last successful sync time.

Do not create fake synchronization timestamps.

## Reconnect behavior

When connectivity returns:

1. detect reconnection;
2. upload queued items;
3. mark successful items synced;
4. preserve failed items for retry;
5. update last sync time;
6. never duplicate an event.

## Acceptance

Test:

```text
online
→ receive action card
→ disable network
→ reload
→ action card remains
→ route remains
→ shelter data remains
→ offline state is visible
→ queue an action/report
→ reconnect
→ queue synchronizes once
```

---

# 10. P0-7 — Aeroplane-mode rehearsal support

This is a mandatory final validation.

Codex should provide all software support needed, but the actual physical network-disable step must be performed by the human operator on the real demo machine.

Before that human test, create an automated check that identifies network dependencies in replay.

## Replay network contract

Replay must NOT require:

- IMD API
- NASA Earthdata
- external tile servers
- external geocoding
- external LLM
- external TTS
- external routing API

All replay-critical inputs must be local.

## Network audit

Search the replay code path for:

```text
fetch(
axios
requests
httpx
urllib
external URLs
MapLibre external styles
external tile URLs
NVIDIA live call
```

Any network call must be:

- removed from replay;
- guarded behind LIVE mode;
- or replaced with deterministic local fallback.

## Acceptance

Run the Aizawl replay with network disabled on the actual demo machine.

The full flow must complete.

---

# 11. P0-8 — Complete the Action Card → Approval → Dissemination → Audit chain

The intended chain is:

```text
Risk escalation
  ↓
Action Card
  ↓
DDMA review
  ↓
Human approval
  ↓
Dissemination
  ↓
Acknowledgement
  ↓
Audit trail
```

## Unified alert identity

The audit found that:

```text
AI_FLAGGED
```

and:

```text
ActionCard / DDMA_APPROVED / DISSEMINATED
```

currently use different ID conventions.

Unify them where practical.

One logical alert should have one stable:

```text
alert_id
```

The ID must survive:

- risk flag;
- action card;
- approval;
- dissemination;
- acknowledgement;
- audit entries.

For replay, the ID must be deterministic.

## Audit entry requirements

Each event should contain enough information to answer:

```text
What happened?
When?
Where?
Why?
Which scenario/tick?
Which model version?
Who approved it?
Which channel was used?
Was it acknowledged?
```

Do not store unnecessary personal information.

## Acceptance

A judge can open Audit and trace one alert from:

```text
AI_FLAGGED
→ ACTION_CARD
→ DDMA_APPROVED
→ DISSEMINATED
→ ACKNOWLEDGED
```

under one alert identity.

---

# 12. P0-9 — Dissemination must be honest and demo-safe

The system may expose multiple channels, but the SIH demo must clearly distinguish:

### Real implementation
from

### Simulated/demo channel

For example:

```text
CAP export — generated locally
SMS — simulated gateway
Cell Broadcast — simulated integration
IVRS — simulated/pre-generated demo
```

Never imply that the demo laptop actually sent a national cell broadcast unless it truly did.

The current CAP 1.2 generation should remain standards-oriented.

## Acceptance

Approval causes:

1. alert state transition;
2. channel preparation;
3. dissemination record;
4. acknowledgement state;
5. audit entry.

All steps must be deterministic in replay.

---

# 13. P0-10 — Voice alert / Mizo audio

This is technically P1 in the older plan but is a **high-value SIH feature** and should be built if it can be completed without destabilizing the system.

The citizen problem is last-mile warning in remote communities.

## Preferred SIH implementation

Pre-generate a small, deterministic set of voice clips for the demo action cards.

Do NOT make live external TTS a dependency of the offline demo.

Suggested structure:

```text
data/audio/
  mizo/
    red_alert.wav
    evacuation_now.wav
    shelter_route.wav
    avoid_road.wav
  en/
    red_alert.wav
    evacuation_now.wav
    shelter_route.wav
    avoid_road.wav
```

Use the repository's intended TTS/translation stack if available.

If a full IndicTrans2/Indic-Parler-TTS pipeline is too heavy, a clearly documented pre-generated demo asset is acceptable for SIH.

## UI behavior

The audio button must:

- play the selected language;
- work offline;
- indicate playback;
- fail gracefully if an asset is missing.

Never show:

```text
Voice available
```

if the file is missing.

## Acceptance

In airplane mode:

```text
open citizen alert
→ choose Mizo
→ press audio
→ voice plays
```

---

# 14. P0-11 — Explainability and trust surface

The project already has real SHAP support.

The final UI must make it understandable to a judge without requiring ML knowledge.

Show:

```text
RISK: HIGH
Probability: 0.xx
Confidence: [level]

WHY?

↑ Rainfall intensity
↑ Slope
↑ Antecedent rainfall
↓/neutral [feature]
```

Also show data provenance:

```text
Source
Timestamp
Spatial resolution
Feature status
```

If soil moisture is a software-derived surface proxy, label it exactly and honestly:

```text
Surface proxy (top 5 cm)
```

Do not call it measured deep soil moisture.

## False-alarm-cost slider

If the feature already exists, verify it uses the real evaluation numbers.

Changing the slider must show the tradeoff between:

- alarms;
- events caught;
- false alarms.

Do not invent percentages.

If the evaluation report does not support a number, say:

```text
Not measured
```

rather than estimating.

---

# 15. P0-12 — Model credibility

The current model is not allowed to be marketed with a fake single "accuracy" headline.

The latest evaluation should be treated as the authoritative source.

Known evaluation context includes:

- ROC-AUC around 0.696;
- PR-AUC around 0.500;
- threshold-specific metrics.

Use the actual current evaluation artifact in the repository as the source of truth.

## UI/presentation language

Prefer:

```text
ROC-AUC
PR-AUC
recall at operating threshold
precision at operating threshold
false-alarm tradeoff
spatial/temporal validation
```

Avoid:

```text
95% accurate
99% accurate
AI guarantees landslide
```

## Model limitations

Document:

- small training dataset limitations;
- missing lithology if still unavailable;
- missing InSAR if still unavailable;
- resolution mismatch where applicable;
- replay versus live data distinctions.

A judge should leave believing:

> "They understand what their model can and cannot claim."

---

# 16. P0-13 — Lithology decision

Lithology is a useful enhancement but must not block the SIH demo.

Current project state has `lithology_class` represented as missing/null in the grid/evaluation.

If GSI Bhukosh access becomes available without delaying the submission:

1. acquire the permitted dataset;
2. document provenance;
3. map it to the grid;
4. test missing values;
5. add it to the model only if the trained artifact/evaluation is updated consistently.

If access is unavailable:

- keep the documented coarse fallback;
- label lithology as unavailable;
- do NOT fabricate geology.

Do not retrain casually on a different feature schema immediately before the demo.

---

# 17. P0-14 — Road isolation must remain the flagship USP

The final UI must make the following chain obvious:

```text
LANDSLIDE RISK
      ↓
RUNOUT
      ↓
ROAD SEVERANCE
      ↓
NETWORK ISOLATION
      ↓
POPULATION / CRITICAL SERVICES AT RISK
      ↓
EVACUATION PRIORITY
      ↓
SAFE ROUTE
```

A judge should be able to understand this in less than 30 seconds.

## Road presentation

Show:

- road name;
- blockage probability;
- whether severed;
- affected villages;
- alternative route if available.

Do not use fake road names.

## Routing

The route must come from the real risk-aware routing engine.

Do not draw a straight line as if it were a safe route.

---

# 18. P0-15 — Safe evacuation window

Keep the existing design principle:

> Output a **time range**, not a fake point prediction.

Example:

```text
SAFE EVACUATION WINDOW
Approximately 2–5 hours
```

Explain that the window is model/threshold/scenario dependent.

Never show:

```text
Evacuation must begin at exactly 14:37
```

unless a real deterministic rule explicitly produces that time.

---

# 19. P0-16 — What-If simulator final contract

The What-If screen must clearly distinguish:

```text
OBSERVED / REPLAY
```

from:

```text
COUNTERFACTUAL SIMULATION
```

## Inputs

At minimum:

- rainfall;
- duration.

If existing inputs are supported, retain:

- slope modifier;
- antecedent rainfall;
- soil moisture;
- lithology;
- fault distance;
- other documented factors.

## Outputs

Show:

- hazard level;
- failure distribution;
- road severance;
- isolated villages;
- population at risk;
- priority changes;
- route changes where supported.

## Test cases

Run at least:

```text
Scenario A: low rainfall
Scenario B: moderate rainfall
Scenario C: severe rainfall
```

Verify monotonic/physically plausible behavior where expected.

Do not assert that every metric must monotonically increase if the actual model/graph can legitimately produce non-monotonic local behavior.

---

# 20. P0-17 — Case-study validation

The final SIH build should validate:

## Aizawl 2024

Primary demo.

Must show:

```text
rainfall buildup
→ risk escalation
→ NH-6 / relevant road impact
→ isolation
→ priority
→ action card
→ routing
→ approval
→ dissemination
→ audit
```

## Wayanad 2024

Use as an accountability / warning-gap case study.

Do not imply that the project "predicted Wayanad live" unless it actually did.

Use language such as:

```text
Historical replay / reconstructed scenario
```

## Tupul 2022

Use as a second historical replay demonstrating that static susceptibility alone is insufficient and that impact/connectivity matters.

## Scenario validation command

Use the project's actual scenario validation tooling.

If no such tool exists, create a deterministic script that:

1. loads each scenario;
2. checks schema;
3. checks required files;
4. runs the pipeline;
5. records completion;
6. exits non-zero on failure.

---

# 21. P0-18 — Build `make demo-check`

This is mandatory.

Create a single preflight command:

```bash
make demo-check
```

It must verify, at minimum:

## Models

- trained XGBoost artifact exists;
- model can load;
- feature schema matches expected schema.

## Scenarios

- Aizawl exists;
- Wayanad exists;
- Tupul exists;
- all scenario files validate.

## Geographic data

- required DEM/cells/exposure artifacts exist;
- required road graphs exist.

## Map

- offline basemap/terrain asset exists;
- file is non-empty;
- required style/source configuration exists.

## Audio

If voice is part of the final SIH build:

- expected audio files exist.

If voice is intentionally cut:

- check that UI correctly reports unavailable voice.

## Determinism

Run a small replay determinism check:

```text
same scenario + same tick
→ same key output hash
```

## No-network replay

Static scan/config check that the replay path does not require external URLs.

Do not attempt to prove all network independence with a fragile regex alone; combine static checks with a documented runtime check where practical.

## Full scenario smoke test

Run the complete Aizawl replay.

Run abbreviated smoke tests for Wayanad and Tupul if full execution is too expensive, but the final preflight should be able to run all scenarios before submission.

## Test suite

Run:

```bash
pytest -q
```

and frontend tests/type checks according to the actual repository scripts.

## Output

Use readable output:

```text
ICONIX DEMO CHECK
────────────────────────────
[PASS] model
[PASS] scenarios
[PASS] geographic data
[PASS] offline map
[PASS] audio
[PASS] deterministic replay
[PASS] no replay network dependency
[PASS] Aizawl smoke
[PASS] Wayanad smoke
[PASS] Tupul smoke
[PASS] backend tests
[PASS] frontend checks

RESULT: READY
```

If anything fails:

```text
RESULT: NOT READY
```

with a concise reason.

Never make `demo-check` pass by ignoring a real failure.

---

# 22. P0-19 — Replace Makefile placeholders

The audit identified `make data` and `make graph` as possible TODO/echo placeholders.

Inspect the actual Makefile.

Replace placeholder targets with the repository's real scripts.

Examples:

```make
data:
	python scripts/fetch_dem.py ...
	python scripts/build_grid.py ...
	python scripts/fetch_exposure.py ...

graph:
	python scripts/build_road_graph.py ...
```

Do not invent CLI arguments. Read the scripts first.

The commands must fail loudly if required data cannot be generated.

---

# 23. P0-20 — Configuration and constants cleanup

The audit found duplicated/uncited constants in forecast/What-If-related files.

Move genuine configuration values into the canonical configuration layer where appropriate.

Keep:

- scientific constants;
- thresholds;
- routing weights;
- forecast assumptions

centralized and documented.

Do not move every UI string into config.

## Rules

Every scientific number should have one of:

1. source citation;
2. explicit "not measured";
3. documented demo assumption.

Avoid duplicate constants in Python and TypeScript.

---

# 24. P0-21 — Commander AI reliability

If the NVIDIA-powered Commander exists:

## Demo requirement

The SIH demo must never hang waiting for an external LLM.

Recommended behavior:

```text
Commander request
    ↓
deterministic local response first for known demo questions
    ↓
optional live model only when explicitly enabled
```

or:

```text
hard-disable external call in replay/demo mode
```

The fallback must be generated from actual project data, not fake data.

Set a short timeout if live calls are retained.

The Commander must be clearly labelled:

```text
AI ADVISORY
Human approval required
```

Never claim autonomous decision-making.

---

# 25. P0-22 — Frontend visual completion

Do a deliberate final visual pass after correctness is stable.

Priority order:

1. map;
2. risk hierarchy;
3. action card;
4. isolation visualization;
5. route;
6. commander;
7. audit;
8. secondary chrome.

## Design target

Operational emergency console:

- dark console aesthetic;
- strong hierarchy;
- generous whitespace;
- restrained accent color;
- readable typography;
- map as the hero.

Avoid:

- excessive cards;
- excessive glowing effects;
- fake KPI numbers;
- clutter;
- generic SaaS dashboard appearance.

## Important

Do not redesign functional components just for aesthetics if doing so risks breaking the demo.

---

# 26. P0-23 — Citizen application completion

The citizen PWA must have three clear primary surfaces:

## Alert

Show:

- current alert;
- what is happening;
- what to do;
- shelter;
- distance;
- voice button;
- language selector.

If there is no active alert:

```text
No active emergency alert.
Current watch: [real state]
```

Do not show a broken-looking empty state.

## Route

Show:

- current location if available;
- shelter;
- safe route;
- blocked roads marked as avoid;
- turn list if implemented.

Route must use the risk-aware routing engine.

## Report

If reporting remains enabled:

- capture/queue report;
- category;
- optional note;
- geolocation;
- offline queue;
- sync state.

If camera integration is not built for SIH, keep the UI honest.

---

# 27. P0-24 — Role/mode clarity

The system should make it obvious whether the user is:

```text
DDMA / Officer
```

or:

```text
Citizen
```

and whether the system is:

```text
LIVE
```

or:

```text
REPLAY MODE — RECONSTRUCTED DATA
```

Aizawl replay should visibly show the reconstructed/held-out nature.

Do not hide that the scenario is replayed.

This is a credibility feature.

---

# 28. P0-25 — Documentation synchronization

Update stale documentation after code completion.

At minimum inspect/update:

```text
CLAUDE.md
docs/BUILD_PLAN.md
docs/ARCHITECTURE.md
README.md
```

Document:

- what is actually implemented;
- what is replay-only;
- what is live;
- what requires credentials;
- what is simulated;
- what is future scope;
- model limitations;
- offline guarantees;
- scenario provenance.

Do not leave old statements contradicting the code.

---

# 29. P0-26 — Create `docs/DEMO_SCRIPT.md`

Create a complete SIH demo script.

## Required length

### Full version
Approximately 8 minutes.

### Compressed version
Approximately 3 minutes.

## Full demo arc

Use this as the target sequence:

### 0:00 — Problem

Explain:

> The problem is not only predicting landslides. The harder problem is knowing who will be isolated, which road will fail, what action should be taken, and whether the warning reaches the community.

### 0:45 — System

Show the operational dashboard.

### 1:15 — Aizawl replay

Select:

```text
Aizawl 2024
```

Point out:

```text
REPLAY / RECONSTRUCTED
HELD-OUT CASE STUDY
```

### 1:30–3:30 — Escalation

Show:

```text
rainfall
→ risk
→ runout
→ road severance
→ isolation
→ priority
```

### 3:30 — Action Card

Show a P1 action card.

Play Mizo voice if implemented.

### 4:30 — DDMA approval

Approve the alert.

Show dissemination.

### 5:30 — Offline

Disable network.

Show citizen alert and route still working.

### 6:15 — Trust

Show:

- SHAP;
- data provenance;
- false-alarm tradeoff.

### 7:00 — What-If

Change rainfall and show impact cascade.

### 7:45 — Closing

Use the message:

> Prediction is only the first step. ICONIX connects prediction to impact, decision, communication, and accountability.

---

# 30. P0-27 — Hard judge questions

Create a question/answer document or section in `docs/DEMO_SCRIPT.md`.

At minimum prepare the team for:

1. How is ICONIX different from GSI's existing landslide early-warning system?
2. How can soil moisture be estimated without dedicated sensors?
3. What is the model accuracy?
4. What is the false-alarm rate?
5. Why XGBoost?
6. Why FastAPI?
7. Why offline-first?
8. Why is phone-to-phone/mesh useful if government broadcasts already exist?
9. What happens if the network comes back?
10. What happens if your AI is wrong?

Every answer must use actual project evidence.

Never invent metrics.

---

# 31. P0-28 — Final fallback strategy

The demo must have a deterministic fallback.

If a non-essential live service fails:

```text
service unavailable
→ local deterministic fallback
→ clearly labelled
→ demo continues
```

The fallback must still use real project data where possible.

For example:

- local scenario frames;
- local model;
- local map;
- local action cards;
- local audio;
- local CAP generation.

The fallback must not be a second fake application.

---

# 32. P0-29 — Security and secrets

Before freeze:

Search for accidental secrets:

```bash
git grep -n "API_KEY"
git grep -n "SECRET"
git grep -n "TOKEN"
git grep -n "PASSWORD"
```

Check:

```text
.env
.env.example
git history
```

Rules:

- `.env` remains untracked;
- `.env.example` contains placeholders only;
- no NASA credentials;
- no NVIDIA API key;
- no cloud secrets;
- no personal tokens.

Do not commit credentials to make the demo work.

---

# 33. P0-30 — Performance and startup reliability

The final demo must have a predictable startup.

Document the exact commands.

Example structure:

```bash
docker compose up -d
# start backend
# start frontend
# run make demo-check
# open application
```

Use the repository's actual startup process.

Avoid requiring the presenter to troubleshoot:

- Python environments;
- missing node modules;
- missing containers;
- database migrations;
- external APIs.

Create a concise `docs/DEMO_SETUP.md` if needed.

---

# 34. P0-31 — Browser/UI failure handling

The UI must not become a blank screen if:

- backend is unavailable;
- a scenario fails;
- audio is missing;
- map asset is missing;
- live service is unavailable.

Show a useful state:

```text
Replay service unavailable.
Run local demo-check.
```

or:

```text
Voice alert unavailable offline.
Text alert remains active.
```

Never render an empty card that looks like a bug.

---

# 35. P0-32 — Automated frontend validation

Inspect `package.json` and use the repository's actual scripts.

Run all available relevant checks:

```text
lint
typecheck
unit tests
build
```

At minimum ensure:

- TypeScript errors = 0;
- build succeeds;
- no missing imports;
- no broken routes;
- no console errors during the main demo flow.

Do not weaken lint/type rules just to make the build green.

---

# 36. P0-33 — End-to-end smoke test

Create a deterministic smoke test for the core flow:

```text
start services
→ load Aizawl replay
→ tick 1
→ tick N
→ observe escalation
→ road becomes affected
→ isolation calculated
→ EPS calculated
→ route generated
→ Action Card generated
→ DDMA approval
→ dissemination
→ audit entry
```

The test should verify data contracts, not pixel-perfect screenshots.

---

# 37. P0-34 — Determinism

Replay must be deterministic.

Given:

```text
same scenario
same starting tick
same configuration
same model artifact
```

the key outputs should match.

Do not allow:

- current wall clock;
- random UUID;
- random simulation;
- external live weather;
- external routing;
- LLM randomness

to alter replay results.

If random sampling is scientifically required, seed it deterministically in replay.

---

# 38. P0-35 — Do not fake "real-time"

The SIH build may simulate accelerated time.

Call it:

```text
REPLAY
ACCELERATED REPLAY
RECONSTRUCTED CASE STUDY
```

not:

```text
LIVE REAL-TIME PREDICTION
```

unless the actual live path is running.

This distinction must be consistent in:

- UI;
- demo script;
- documentation;
- judge answers.

---

# 39. P0-36 — Completion gates

Codex must not declare the P0 complete until all software gates below are satisfied.

## Gate A — Tests

```text
Backend: PASS
Frontend: PASS
Build: PASS
```

## Gate B — Data

```text
Aizawl: PASS
Wayanad: PASS
Tupul: PASS
```

## Gate C — Map

```text
offline basemap/terrain: PASS
risk overlays: PASS
roads: PASS
```

## Gate D — Core pipeline

```text
model: PASS
threshold: PASS
SHAP: PASS
runout: PASS
road severance: PASS
RII: PASS
EPS: PASS
routing: PASS
Action Card: PASS
```

## Gate E — Decision/dissemination

```text
approval: PASS
dissemination: PASS
audit: PASS
alert_id continuity: PASS
```

## Gate F — Offline

```text
network disabled replay: PASS
citizen alert: PASS
route: PASS
map: PASS
voice if included: PASS
```

## Gate G — Credibility

```text
no fabricated judge-facing data: PASS
no fake metrics: PASS
no hidden external dependency: PASS
no secrets: PASS
replay clearly labelled: PASS
```

## Gate H — Demo

```text
make demo-check: PASS
```

---

# 40. Phase ordering for Codex

Do NOT implement everything simultaneously.

Use this order.

## Phase A — Integrity blockers

1. Repository reconnaissance.
2. Fix `whatif.py` BOM/mojibake.
3. Fix wall-clock violations.
4. Fix nondeterministic IDs.
5. Green backend tests.
6. Remove/fix fabricated What-If data.
7. Connect What-If to the real pipeline.
8. Fix LIVE/REPLAY state contamination.

## Phase B — Data and map

9. Restore Aizawl offline map.
10. Regenerate/verify Wayanad static data.
11. Regenerate/verify Tupul static data.
12. Regenerate/verify road graphs.
13. Validate all scenarios.

## Phase C — Offline

14. Complete IndexedDB/offline assets.
15. Remove replay network dependencies.
16. Add offline state handling.
17. Add/finalize offline audio if selected.

## Phase D — Decision/audit

18. Unify `alert_id`.
19. Verify Action Card → approval → dissemination → audit.
20. Verify CAP generation.
21. Verify acknowledgement tracking.

## Phase E — Trust/UI

22. Verify SHAP.
23. Verify false-alarm slider.
24. Verify provenance.
25. Fix model metrics display.
26. Final map/UI polish.

## Phase F — Automation

27. Implement `make demo-check`.
28. Replace Makefile placeholders.
29. Add end-to-end smoke tests.
30. Add determinism checks.

## Phase G — Documentation

31. Update CLAUDE.md.
32. Update architecture docs.
33. Create `docs/DEMO_SCRIPT.md`.
34. Create `docs/DEMO_SETUP.md` if needed.
35. Document limitations and future scope.

## Phase H — Human-only rehearsal

Codex cannot physically perform these:

36. Run airplane-mode test on actual demo machine.
37. Record fallback video.
38. Rehearse 10 judge questions.
39. Run five clean demos.
40. Freeze/tag final build.
41. Submit.

---

# 41. Human-only actions

When Codex reaches these steps, it must STOP and tell the user exactly what to do.

## Human Action 1 — Network-off test

On the real demo machine:

```text
1. Start the application normally.
2. Confirm Aizawl replay works.
3. Disable Wi-Fi/Ethernet.
4. Reload/restart as required.
5. Run the complete replay.
6. Open citizen alert.
7. Open route.
8. Play voice.
9. Open audit.
10. Run What-If.
```

Record every failure.

## Human Action 2 — External credentials

If optional external services are tested:

- provide credentials locally;
- never paste them into source;
- never commit them.

## Human Action 3 — Presentation rehearsal

Each team member must know:

- system architecture;
- data sources;
- model limitations;
- offline design;
- RII;
- EPS;
- routing;
- What-If;
- alert chain;
- GSI differentiation.

---

# 42. Definition of Done

`extension_v1 P0` is complete only when:

### Product

- [ ] The application starts reliably.
- [ ] The Aizawl SIH demo works end-to-end.
- [ ] Wayanad and Tupul replay paths validate.
- [ ] The map looks like a real operational terrain map.
- [ ] What-If uses the real pipeline.
- [ ] No fabricated judge-facing values remain.
- [ ] Action Card → approval → dissemination → audit is traceable.
- [ ] Offline citizen experience works.
- [ ] Voice works offline if included.
- [ ] LIVE/REPLAY labels are truthful.
- [ ] Commander cannot stall the demo.

### Engineering

- [ ] Backend tests green.
- [ ] Frontend tests/typecheck/build green.
- [ ] Replay deterministic.
- [ ] `make demo-check` passes.
- [ ] No secrets committed.
- [ ] No replay network dependency.
- [ ] Required static artifacts exist.
- [ ] Documentation matches implementation.

### SIH demo

- [ ] Full 8-minute demo script exists.
- [ ] 3-minute compressed script exists.
- [ ] Fallback video exists.
- [ ] 10 judge questions have prepared answers.
- [ ] Demo has been run five clean times.
- [ ] Two people can operate it.
- [ ] Final build is tagged/frozen.

---

# 43. Future extension boundary

Do not implement the following as part of this P0 unless they are trivial and risk-free:

```text
Sentinel-1 InSAR
Sikkim GLOF
crowdsourced image CV
full multimodal foundation model
multi-hazard engine
advanced cascading disaster simulation
large-scale cloud deployment
internationalization beyond SIH needs
```

These belong to later `extension_v1` phases.

The architecture must remain extensible so those features can be added later.

---

# 44. Final SIH positioning

The completed SIH version should be able to truthfully demonstrate:

> **ICONIX does not stop at predicting landslide risk. It connects hazard prediction to terrain-aware impact analysis, road-network isolation, evacuation priority, risk-aware routing, actionable alerts, human approval, offline last-mile access, and an auditable response chain.**

The central story is:

```text
PREDICT
   ↓
UNDERSTAND IMPACT
   ↓
IDENTIFY WHO/WHAT IS ISOLATED
   ↓
PRIORITIZE
   ↓
ROUTE
   ↓
ALERT
   ↓
GET HUMAN APPROVAL
   ↓
DISSEMINATE
   ↓
AUDIT
```

That is the SIH completion target.

---

# 45. Codex operating instructions

When implementing this plan:

1. Inspect before editing.
2. Preserve existing working functionality.
3. Make one coherent change at a time.
4. Add/update tests with every behavior change.
5. Run the narrowest relevant test first.
6. Then run the full suite at milestone boundaries.
7. Never weaken tests to hide failures.
8. Never replace real pipeline logic with hardcoded demo values.
9. Never introduce secrets.
10. Never introduce a network dependency into replay.
11. Never claim a feature is complete without verification.
12. If a requirement cannot be completed because external credentials/data are unavailable, implement the strongest honest offline fallback and document the limitation.
13. If you discover that this plan contradicts the current code, inspect the code and current tests first; update the implementation based on the actual repository state rather than blindly following stale documentation.
14. Keep the SIH critical path ahead of future innovation.
15. At each major milestone, report:
   - files changed;
   - tests run;
   - results;
   - remaining blockers;
   - whether the next phase is safe to start.

---

# 46. Final implementation report required from Codex

When all software work is complete, produce a final report containing:

```text
ICONIX extension_v1 P0 COMPLETION REPORT

1. Starting state
2. Files changed
3. Features completed
4. Bugs fixed
5. Data artifacts restored
6. Tests:
   backend
   frontend
   integration
   demo-check
7. Offline verification status
8. What remains human-only
9. Known limitations
10. Exact commands to run the final demo
11. Recommended final demo sequence
12. Final readiness:
    READY / NOT READY
```

Do not write `READY` unless the acceptance criteria are actually verified.

---

# 47. Final priority rule

If time becomes limited, prioritize in this exact order:

```text
1. Green tests
2. No fabricated data
3. Real What-If pipeline
4. Offline map
5. Offline replay
6. Action/approval/dissemination/audit chain
7. Aizawl end-to-end demo
8. Wayanad/Tupul validation
9. demo-check
10. voice
11. visual polish
12. documentation/rehearsal support
```

The goal is not to have the largest feature list.

The goal is to have the **most credible, reliable, judge-proof SIH demonstration**.

