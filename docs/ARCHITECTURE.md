# ARCHITECTURE.md — module boundaries and data contracts

This file is the module-boundary contract. The Pydantic models below (extracted from
`BUILD_PLAN.md` Appendix A) are implemented verbatim in `backend/app/schemas/` — that is the
single source of truth for the actual code; this file explains what owns what and why the
boundaries sit where they do. If this file and the schema code ever disagree, the code wins and
this file is stale — fix it.

---

## 1. The invariant this whole layout exists to protect

> **REPLAY is not a separate code path. It is a different `Clock` and a different `DataSource`
> feeding the exact same pipeline.**

Concretely: everything from `risk/` onward consumes an `ObservationFrame` and a `datetime` and
produces schema objects. It never asks "am I live or replaying." Only four places are allowed to
know the mode exists:

- `core/mode.py` — the `LIVE ⇄ REPLAY` state machine
- `core/clock.py` — decides whether `now()` reads the wall clock or a scenario's virtual clock
- `ingest/` — decides whether frames come from a live adapter or `replay/scenario_source.py`
- the frontend mode banner

The pipeline stages (`risk/`, `impact/`, `decision/`, `dissemination/`, `audit/`) are pure
functions over the schemas below: `ObservationFrame` (+ prior state) in, a typed result out. A
mode check inside any of them is a design failure, not a shortcut — see CLAUDE.md §2.

---

## 2. Pipeline shape

One **tick** = one timestamp processed end to end:

```
DataSource.frames()  →  ObservationFrame
        │
        ▼
    risk/            →  list[CellRisk]            (per cell: p_fail, confidence, attributions)
        │
        ▼
    impact/           →  list[RunoutEnvelope]       (Phase 2)
                          list[RoadSegmentRisk]      (Phase 2)
                          list[VillageIsolation]     (Phase 2)
                          list[SettlementPriority]   (Phase 2)
        │
        ▼
    decision/          →  list[ActionCard]           (Phase 3, stubbed Phase 0)
                          escalation stage changes
        │
        ▼
    dissemination/     →  simulated channel sends     (Phase 3)
        │
        ▼
    audit/              →  list[AuditEvent]           (hash-chained)
        │
        ▼
    TickResult          →  broadcast on /ws/ticks
```

In Phase 0 every stage above `risk/` is a deterministic stub that still returns schema-valid
objects — the pipe is real, the water is fake. `LIVE = "live"` values on `CellObservation.source`
and `is_reconstructed=False`; a scenario source sets `source="scenario:<id>"` and
`is_reconstructed=True`. Nothing downstream branches on either.

---

## 3. Module responsibilities

| Module | Owns | Consumes | Produces | Notes |
|---|---|---|---|---|
| `core/clock.py` | wall-clock vs. scenario time | — | `datetime` via `.now()` | **Only file allowed to call `datetime.now()`.** Enforced by `tests/test_no_wallclock.py`. |
| `core/mode.py` | `LIVE ⇄ REPLAY` transitions | replay control calls | `ModeState`, mode-change bus events | `start_replay`, `pause`, `resume`, `set_speed`, `stop_replay`. |
| `core/bus.py` | in-process pub/sub | — | topic subscriptions | One topic per pipeline stage; used to fan out tick progress to the WS hub. |
| `ingest/base.py` | the `DataSource` protocol | — | `AsyncIterator[ObservationFrame]` | Contract only; no logic. |
| `ingest/live/` | real feed adapters (Phase 1+) | external APIs | `ObservationFrame` | Stubbed with fabricated values in Phase 0. |
| `ingest/replay/scenario_source.py` | reading a scenario JSON on the `ScenarioClock`'s schedule | `data/scenarios/<id>.json` | `ObservationFrame` (`is_reconstructed=True`) | Drives the "Run Case Study" demo. |
| `risk/` | turning observations into `p_fail` | `ObservationFrame` | `list[CellRisk]` | Phase 0: deterministic fake function of rainfall. Phase 1: threshold engine + XGBoost. |
| `impact/` | runout, road isolation, settlement priority | `list[CellRisk]` | `RunoutEnvelope`, `RoadSegmentRisk`, `VillageIsolation`, `SettlementPriority` | Phase 2. Phase 0 stubs return a fixed small set. |
| `decision/` | routing, escalation stage, action cards | impact outputs | `EvacuationRoute`, `ActionCard`, escalation transitions | Phase 3. Phase 0 stubs one fixed `ActionCard`. |
| `dissemination/` | CAP 1.2 XML, simulated channel sends, TTS | `ActionCard` | channel send records | Phase 3. Not wired in Phase 0. |
| `audit/` | append-only hash-chained event log | events from every stage above | `list[AuditEvent]` | Phase 0 writes one `AI_FLAGGED` event per tick so the audit trail is real from day one. |
| `api/` | FastAPI REST routers | schema objects from all of the above | HTTP responses | `GET /api/aoi/{id}`, `GET /api/scenarios`, `POST /api/replay/start`, `POST /api/replay/stop`, `GET /api/state`. |
| `ws/` | the `/ws/ticks` hub | bus events | `TickResult` broadcast | One channel; every connected client gets every tick. |

---

## 4. Data contracts

These are implemented in `backend/app/schemas/` — one module per section below, matching file
names. Field-for-field identical to `BUILD_PLAN.md` Appendix A.

### 4.1 Mode & time — `schemas/mode.py`

```python
class RunMode(str, Enum):
    LIVE = "live"
    REPLAY = "replay"

class ModeState(BaseModel):
    mode: RunMode
    scenario_id: str | None
    scenario_time: datetime | None
    speed_factor: float = 1.0
    paused: bool = False
```

### 4.2 Ingest — `schemas/ingest.py`

```python
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
```

### 4.3 Risk — `schemas/risk.py`

```python
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
```

### 4.4 Impact — `schemas/impact.py`

```python
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
```

### 4.5 Decision — `schemas/decision.py`

```python
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
```

### 4.6 Audit — `schemas/audit.py`

```python
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
```

### 4.7 Tick — `schemas/tick.py` (the WebSocket payload)

```python
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

`TickResult` is the one object the frontend ever receives over the WebSocket. It re-exports
(not duplicates) the types above — every field is a list of already-defined schema objects.

---

## 5. Scenario file contract (feeds `ingest/replay/`)

The full scenario file schema is **Appendix B of `BUILD_PLAN.md`** and is formally finalized with
a validator script in task 4.1. Phase 0 needs the shape early because
`ingest/replay/scenario_source.py` (task 0.9) and the smoke fixture `data/scenarios/_smoke.json`
(task 0.14) both read it. The fields Phase 0 actually relies on:

```jsonc
{
  "id": "string",
  "aoi_id": "string",
  "held_out_of_training": true,
  "provenance": { "confidence": "reconstructed | fabricated", "sources": ["..."], "disclaimer": "..." },
  "clock": { "start": "ISO8601", "end": "ISO8601", "frame_interval_minutes": 60, "default_speed_factor": 3600 },
  "frames": [
    { "t": "ISO8601", "cells": [ { "cell_id": "...", "rain_1h": 0.0, "...": "..." } ], "defaults": { "...": "..." } }
  ]
}
```

`ground_truth` and `narration` (used by the Counterfactual Scorecard, Phase 4) are part of the
full Appendix B schema but are not required for `_smoke.json`, which has no real-world referent.

---

## 6. Why the boundaries sit here

- **Schemas, not shared mutable state.** Every arrow in the pipeline diagram above is a Pydantic
  model, not a shared object or ORM row. A module can be rewritten completely (stub → real) with
  zero changes to its neighbours as long as the schema doesn't change — this is what lets three
  people work Phase 1–3 in parallel without merge hell.
- **`ingest/` is the only place allowed to know about data provenance.** `is_reconstructed` and
  `source` are set once, at the boundary, and carried through as data — nothing downstream needs
  a special case for replay data because the flag travels with the observation, not with a global.
- **`audit/` consumes from every stage but is written to by none of them directly** — each stage
  emits events onto the bus; `audit/` is the only writer of the hash chain. This keeps the audit
  log a single append-only sequence instead of N modules racing to write it.
