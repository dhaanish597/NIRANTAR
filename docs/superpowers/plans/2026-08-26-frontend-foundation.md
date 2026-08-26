# Frontend Rebuild — Sub-project 1: Foundation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the shared state architecture and the 5-item Government / 4-item Citizen navigation
shell the rest of the SIH26001 frontend rebuild depends on, fixing the regression already sitting
in the working tree (orphaned `DdmaConsole`/`VillageView`/`VillageDetailDrawer`/
`CounterfactualScorecard`/`AuditTrailView`/`OnboardingOverlay`/`InstallPrompt`) and closing the
real, documented backend gap: nothing currently chains a DDMA approval to an actual dissemination
send.

**Architecture:** One extended Zustand store (`useTickStore`) consumed identically by the
Government shell and `CitizenApp` — no per-app duplicate state. A new `POST /api/announcements`
endpoint reuses the existing (already-built, already-tested, never-called) `dissemination/
channels.py` + `dissemination/cap.py` + `audit/producers.py` machinery to perform a real approve
→ send → audit chain, broadcasting the result over the existing single `/ws/ticks` WebSocket
connection as a second discriminated message shape. Village demographics are a small deterministic
function attached to the existing `VillageIsolation` schema, not a new endpoint.

**Tech Stack:** Python 3.11 / FastAPI / Pydantic v2 (backend); React 18 / TypeScript / Zustand /
Vite / vitest (frontend). No new dependencies.

**Spec:** `docs/superpowers/specs/2026-08-26-frontend-foundation-design.md`

## Global Constraints

- `datetime.now()` is banned outside `core/clock.py` — every backend timestamp in this plan uses
  `LiveClock().now()`, matching `ddma_decide`'s existing precedent (a human action happens at real
  wall-clock time even during an accelerated replay).
- Every simulated value must be seeded/deterministic, never `random`/`Math.random()` — village
  demographics use a fixed ratio table, not randomness.
- No fabricated data presented as real: village demographics carry `source: "simulated"` at the
  schema level.
- One WebSocket channel only (`/ws/ticks`) — announcements are multiplexed onto it, not a second
  endpoint.
- Follow existing file-organization convention: request/response DTOs and business logic for one
  endpoint live together in `api/<feature>.py` (see `api/whatif.py`); `routes.py` holds only thin
  route handlers that call into it; cross-module wire contracts live in `schemas/`.
- `frontend/src/types/schemas.ts` is a hand-maintained mirror of the backend Pydantic schemas —
  update it whenever a schema changes, matching field names/optionality exactly.

---

### Task 1: Backend — simulated village demographics

**Files:**
- Modify: `backend/app/schemas/impact.py`
- Create: `backend/app/impact/demographics.py`
- Modify: `backend/app/impact/isolation.py:244` (the real `VillageIsolation(...)` construction)
- Modify: `backend/app/impact/stub.py:62` (the Phase-0 stub `VillageIsolation(...)` construction)
- Modify: `backend/tests/test_schemas.py:132` (existing `VillageIsolation(...)` construction)
- Modify: `backend/tests/test_priority.py:22` (existing `VillageIsolation(...)` construction)
- Test: `backend/tests/test_demographics.py`

**Interfaces:**
- Produces: `Demographics` (Pydantic model, `backend/app/schemas/impact.py`) with fields
  `children: int`, `seniors: int`, `adults: int`, `high_risk_households: int`,
  `source: Literal["simulated"] = "simulated"`. `VillageIsolation.demographics: Demographics`
  (new required field). `simulate_demographics(population: int) -> Demographics`
  (`backend/app/impact/demographics.py`).

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/test_demographics.py
from __future__ import annotations

from app.impact.demographics import simulate_demographics


def test_simulate_demographics_sums_to_population():
    d = simulate_demographics(1000)
    assert d.children + d.seniors + d.adults == 1000


def test_simulate_demographics_is_deterministic():
    assert simulate_demographics(2840) == simulate_demographics(2840)


def test_simulate_demographics_labels_source_simulated():
    assert simulate_demographics(500).source == "simulated"


def test_simulate_demographics_zero_population():
    d = simulate_demographics(0)
    assert d.children == 0
    assert d.seniors == 0
    assert d.adults == 0
    assert d.high_risk_households == 0
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && pytest tests/test_demographics.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'app.impact.demographics'`

- [ ] **Step 3: Add `Demographics` to the schema, then write `simulate_demographics`**

In `backend/app/schemas/impact.py`, insert immediately before `class VillageIsolation(BaseModel):`:

```python
class Demographics(BaseModel):
    """Simulated household/census-level breakdown — no such dataset exists for the NER pilot
    AOIs. Derived deterministically from each village's real WorldPop-based `population` figure
    (see impact/demographics.py). Never presented as Census/ground-truth data."""

    children: int = Field(ge=0)
    seniors: int = Field(ge=0)
    adults: int = Field(ge=0)
    high_risk_households: int = Field(ge=0)
    source: Literal["simulated"] = "simulated"
```

Then add the field to `VillageIsolation`:

```python
class VillageIsolation(BaseModel):
    village_id: str
    name: str
    population: int = Field(ge=0)
    demographics: Demographics
    p_isolated: float = Field(ge=0.0, le=1.0)
    isolated_now: bool
    alternate_route_exists: bool
    est_duration_hours: float | None = None  # ALWAYS labelled "estimate" in UI
    severed_links: list[str] = Field(default_factory=list)
```

Create `backend/app/impact/demographics.py`:

```python
"""impact/demographics.py — simulated household/census-level demographics per village.

No such dataset exists for the NER pilot AOIs (CLAUDE.md's honesty rules — this is SIMULATED,
never presented as Census/ground-truth data). Derived from each village's real WorldPop-based
`population` figure (scripts/fetch_exposure.py) via a fixed ratio table, not randomness — same
population always produces the same breakdown (CLAUDE.md rule 13), so no seed is needed at all.

Ratios are an engineering judgment call (rural NER's younger-skewing population pyramid), not a
cited statistic — documented as such, same spirit as ml/negative_sampling.py's buffer distances.
"""
from __future__ import annotations

from app.schemas.impact import Demographics

CHILDREN_RATIO = 0.30
SENIOR_RATIO = 0.08
AVERAGE_HOUSEHOLD_SIZE = 4.8
HIGH_RISK_HOUSEHOLD_RATIO = 0.05  # of estimated households, not population


def simulate_demographics(population: int) -> Demographics:
    children = round(population * CHILDREN_RATIO)
    seniors = round(population * SENIOR_RATIO)
    adults = population - children - seniors
    households = population / AVERAGE_HOUSEHOLD_SIZE
    high_risk_households = round(households * HIGH_RISK_HOUSEHOLD_RATIO)
    return Demographics(
        children=children,
        seniors=seniors,
        adults=adults,
        high_risk_households=high_risk_households,
        source="simulated",
    )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && pytest tests/test_demographics.py -v`
Expected: PASS (4 tests)

- [ ] **Step 5: Wire `simulate_demographics` into both `VillageIsolation` construction sites**

In `backend/app/impact/isolation.py`, add to the imports:

```python
from app.impact.demographics import simulate_demographics
```

Then change (around line 244):

```python
    return VillageIsolation(
        village_id=village.village_id,
        name=village.name,
        population=village.population,
        demographics=simulate_demographics(village.population),
        p_isolated=p_isolated,
        isolated_now=isolated_now,
        alternate_route_exists=alternate_route_exists,
        est_duration_hours=est_duration_hours,
        severed_links=severed_links,
    )
```

In `backend/app/impact/stub.py`, add to the imports:

```python
from app.impact.demographics import simulate_demographics
```

Then change (around line 62):

```python
    village = VillageIsolation(
        village_id=STUB_VILLAGE_ID,
        name="Hunthar (stub)",
        population=1200,  # fabricated — Phase 1 exposure data (scripts/fetch_exposure.py) replaces this
        demographics=simulate_demographics(1200),
        p_isolated=avg,
        isolated_now=road.severed,
        alternate_route_exists=not road.severed,
        est_duration_hours=None,
        severed_links=[STUB_ROAD_EDGE_ID] if road.severed else [],
    )
```

- [ ] **Step 6: Fix the two existing tests that construct `VillageIsolation` directly**

In `backend/tests/test_schemas.py`, add the import `from app.impact.demographics import
simulate_demographics` near the top, then change (around line 132):

```python
        village = VillageIsolation(
            village_id="v_hunthar",
            name="Hunthar",
            population=1200,
            demographics=simulate_demographics(1200),
            p_isolated=0.55,
            isolated_now=False,
            alternate_route_exists=True,
            est_duration_hours=None,
            severed_links=[],
```

(keep whatever closing `)` / trailing lines already follow — only the body above changes).

In `backend/tests/test_priority.py`, add the same import near the top, then change (around line
22):

```python
    return VillageIsolation(
        village_id=village_id, name="Test Village", population=population,
        demographics=simulate_demographics(population),
        p_isolated=p_isolated, isolated_now=isolated_now, alternate_route_exists=not isolated_now,
        est_duration_hours=None, severed_links=[],
    )
```

- [ ] **Step 7: Run the full backend test suite to check for regressions**

Run: `cd backend && pytest -v`
Expected: PASS, no failures introduced by the new required field

- [ ] **Step 8: Commit**

```bash
git add backend/app/schemas/impact.py backend/app/impact/demographics.py backend/app/impact/isolation.py backend/app/impact/stub.py backend/tests/test_demographics.py backend/tests/test_schemas.py backend/tests/test_priority.py
git commit -m "Add simulated village demographics (children/seniors/adults/high-risk households)"
```

---

### Task 2: Backend — Announcement wire schema

**Files:**
- Create: `backend/app/schemas/announcement.py`
- Test: `backend/tests/test_announcement_schema.py`

**Interfaces:**
- Produces: `ChannelResultSummary` (`channel: str`, `recipient_count: int`, `delivered_count:
  int`, `acknowledged_count: int`) and `Announcement` (`id: str`, `alert_id: str`, `village_id:
  str`, `stage: Literal["GREEN","YELLOW","ORANGE","RED"]`, `message: str`, `language: str = "en"`,
  `issued_by: str`, `issued_at: datetime`, `channel_results: list[ChannelResultSummary]`,
  `cap_xml: str`), both in `backend/app/schemas/announcement.py`.

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/test_announcement_schema.py
from __future__ import annotations

from app.schemas.announcement import Announcement, ChannelResultSummary


def test_announcement_round_trips_through_json():
    announcement = Announcement(
        id="ann-1",
        alert_id="alert-1",
        village_id="v1",
        stage="RED",
        message="Evacuate now",
        language="en",
        issued_by="officer-1",
        issued_at="2026-01-01T00:00:00+05:30",
        channel_results=[
            ChannelResultSummary(
                channel="sms", recipient_count=100, delivered_count=90, acknowledged_count=40
            )
        ],
        cap_xml="<alert></alert>",
    )
    restored = Announcement.model_validate_json(announcement.model_dump_json())
    assert restored == announcement
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && pytest tests/test_announcement_schema.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'app.schemas.announcement'`

- [ ] **Step 3: Write the schema**

```python
# backend/app/schemas/announcement.py
"""Announcement contract — the wire shape CLAUDE.md's own Known Gaps section names: "nothing yet
chains an approval to an actual channel send." `POST /api/announcements` (api/announcements.py)
is that chain; this is what it returns, consumed identically by the Government Announce workspace
and the Citizen Announcement tab, and mirrored by hand in frontend/src/types/schemas.ts.
"""
from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel


class ChannelResultSummary(BaseModel):
    channel: str
    recipient_count: int
    delivered_count: int
    acknowledged_count: int


class Announcement(BaseModel):
    id: str
    alert_id: str
    village_id: str
    stage: Literal["GREEN", "YELLOW", "ORANGE", "RED"]
    message: str
    language: str = "en"
    issued_by: str
    issued_at: datetime
    channel_results: list[ChannelResultSummary]
    cap_xml: str
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && pytest tests/test_announcement_schema.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add backend/app/schemas/announcement.py backend/tests/test_announcement_schema.py
git commit -m "Add Announcement wire schema"
```

---

### Task 3: Backend — the real announce/dispatch logic

**Files:**
- Create: `backend/app/api/announcements.py`
- Test: `backend/tests/test_announcements.py`

**Interfaces:**
- Consumes: `Announcement`, `ChannelResultSummary` (Task 2); `record_ddma_decision`,
  `record_dissemination` (`app/audit/producers.py`, existing); `CellBroadcastChannel`,
  `SmsChannel`, `PushChannel`, `MeshChannel` (`app/dissemination/channels.py`, existing);
  `build_cap_alert` (`app/dissemination/cap.py`, existing); `LiveClock`
  (`app/core/clock.py`, existing); `AuditLog` (`app/audit/log.py`, existing).
- Produces: `AnnouncementRequest` (Pydantic: `action_card: ActionCard`, `officer_id: str`,
  `recipient_count: int`, `message: str | None = None`, `language: str = "en"`);
  `create_announcement(body: AnnouncementRequest, *, audit_log: AuditLog, announcements:
  list[Announcement]) -> Announcement`; `list_announcements(announcements: list[Announcement]) ->
  list[Announcement]` (newest first) — all in `backend/app/api/announcements.py`.

- [ ] **Step 1: Write the failing tests**

```python
# backend/tests/test_announcements.py
from __future__ import annotations

from app.api.announcements import AnnouncementRequest, create_announcement, list_announcements
from app.audit.log import AuditLog
from app.schemas.decision import ActionCard


def _sample_card(alert_id: str = "alert-1") -> ActionCard:
    return ActionCard(
        alert_id=alert_id,
        village_id="v1",
        stage="RED",
        headline="Evacuate now",
        reason_plain="Heavy rainfall and slope movement",
        shelter_name="Community Hall",
        route=None,
        roads_to_avoid=[],
        what_to_carry=[],
        contact="108",
        issued_at="2026-01-01T00:00:00+05:30",
        valid_until="2026-01-02T00:00:00+05:30",
        safe_window_hours=None,
        translations={},
        audio_urls={},
    )


def test_create_announcement_sends_through_all_four_channels():
    audit_log = AuditLog()
    body = AnnouncementRequest(action_card=_sample_card(), officer_id="officer-1", recipient_count=1000)
    announcement = create_announcement(body, audit_log=audit_log, announcements=[])
    assert {r.channel for r in announcement.channel_results} == {
        "cell_broadcast",
        "sms",
        "push",
        "mesh",
    }
    assert len(announcement.cap_xml) > 0


def test_create_announcement_records_real_audit_events():
    audit_log = AuditLog()
    body = AnnouncementRequest(action_card=_sample_card(), officer_id="officer-1", recipient_count=10)
    announcement = create_announcement(body, audit_log=audit_log, announcements=[])
    kinds = [e.kind for e in audit_log.for_alert(announcement.alert_id)]
    assert "DDMA_APPROVED" in kinds
    assert "DISSEMINATED" in kinds


def test_create_announcement_does_not_double_approve():
    audit_log = AuditLog()
    card = _sample_card()
    create_announcement(
        AnnouncementRequest(action_card=card, officer_id="o", recipient_count=1),
        audit_log=audit_log,
        announcements=[],
    )
    create_announcement(
        AnnouncementRequest(action_card=card, officer_id="o", recipient_count=1),
        audit_log=audit_log,
        announcements=[],
    )
    approved = [e for e in audit_log.for_alert(card.alert_id) if e.kind == "DDMA_APPROVED"]
    assert len(approved) == 1


def test_create_announcement_defaults_message_to_reason_plain():
    audit_log = AuditLog()
    announcement = create_announcement(
        AnnouncementRequest(action_card=_sample_card(), officer_id="o", recipient_count=1),
        audit_log=audit_log,
        announcements=[],
    )
    assert announcement.message == "Heavy rainfall and slope movement"


def test_list_announcements_returns_newest_first():
    announcements: list = []
    audit_log = AuditLog()
    create_announcement(
        AnnouncementRequest(action_card=_sample_card("a1"), officer_id="o", recipient_count=1),
        audit_log=audit_log,
        announcements=announcements,
    )
    create_announcement(
        AnnouncementRequest(action_card=_sample_card("a2"), officer_id="o", recipient_count=1),
        audit_log=audit_log,
        announcements=announcements,
    )
    result = list_announcements(announcements)
    assert [a.alert_id for a in result] == ["a2", "a1"]
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && pytest tests/test_announcements.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'app.api.announcements'`

- [ ] **Step 3: Write the implementation**

```python
# backend/app/api/announcements.py
"""api/announcements.py — the real dissemination trigger CLAUDE.md's Known Gaps section names:
"nothing yet chains an approval to an actual channel send." `create_announcement()` is that
chain: approve (if not already decided), send through every real simulated channel, record the
real DISSEMINATED audit event, build the real CAP 1.2 XML, and return the result.
`backend/app/api/routes.py` wires the two thin REST handlers that call into this module — the
same split `api/whatif.py`/`routes.py` already establish.
"""
from __future__ import annotations

from pydantic import BaseModel, Field

from app.audit.log import AuditLog
from app.audit.producers import record_ddma_decision, record_dissemination
from app.core.clock import LiveClock
from app.dissemination.cap import build_cap_alert
from app.dissemination.channels import CellBroadcastChannel, Channel, MeshChannel, PushChannel, SmsChannel
from app.schemas.announcement import Announcement, ChannelResultSummary
from app.schemas.decision import ActionCard

CHANNELS: list[Channel] = [CellBroadcastChannel(), SmsChannel(), PushChannel(), MeshChannel()]


class AnnouncementRequest(BaseModel):
    action_card: ActionCard
    officer_id: str
    recipient_count: int = Field(ge=0)
    message: str | None = None
    language: str = "en"


def create_announcement(
    body: AnnouncementRequest, *, audit_log: AuditLog, announcements: list[Announcement]
) -> Announcement:
    t = LiveClock().now()
    card = body.action_card

    already_decided = any(
        event.kind in ("DDMA_APPROVED", "STOOD_DOWN")
        for event in audit_log.for_alert(card.alert_id)
    )
    if not already_decided:
        record_ddma_decision(
            audit_log,
            action_card=card,
            officer_id=body.officer_id,
            t=t,
            decision="approved",
            notes="Approved via Announce workspace",
        )

    channel_results = [
        channel.send(card, recipient_count=body.recipient_count) for channel in CHANNELS
    ]
    record_dissemination(audit_log, action_card=card, channel_results=channel_results, t=t)
    cap_xml = build_cap_alert(card)

    announcement = Announcement(
        id=f"ann-{card.alert_id}-{t.isoformat()}",
        alert_id=card.alert_id,
        village_id=card.village_id,
        stage=card.stage,
        message=body.message or card.reason_plain,
        language=body.language,
        issued_by=body.officer_id,
        issued_at=t,
        channel_results=[
            ChannelResultSummary(
                channel=result.channel,
                recipient_count=result.recipient_count,
                delivered_count=result.delivered_count,
                acknowledged_count=result.acknowledged_count,
            )
            for result in channel_results
        ],
        cap_xml=cap_xml.decode("utf-8"),
    )
    announcements.append(announcement)
    return announcement


def list_announcements(announcements: list[Announcement]) -> list[Announcement]:
    return list(reversed(announcements))
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd backend && pytest tests/test_announcements.py -v`
Expected: PASS (5 tests)

- [ ] **Step 5: Commit**

```bash
git add backend/app/api/announcements.py backend/tests/test_announcements.py
git commit -m "Add the real announce/dispatch logic: approve, send, audit, CAP 1.2"
```

---

### Task 4: Backend — wire the endpoints and multiplex the WebSocket

**Files:**
- Modify: `backend/app/api/state.py` (add `self.announcements` to `AppState`)
- Modify: `backend/app/api/routes.py` (add the two REST handlers)
- Modify: `backend/app/ws/hub.py` (multiplex `Topic.TICK` + `Topic.DISSEMINATION`)
- Test: additions to `backend/tests/test_api_http.py`

**Interfaces:**
- Consumes: `AnnouncementRequest`, `create_announcement`, `list_announcements` (Task 3);
  `Announcement` (Task 2); `Topic` (`app/core/bus.py`, existing — `Topic.DISSEMINATION` already
  defined, previously unused).
- Produces: `POST /api/announcements` (body: `AnnouncementRequest` JSON, returns `Announcement`
  JSON); `GET /api/announcements` (returns `list[Announcement]` JSON, newest first). A connected
  `/ws/ticks` client receives `{"type": "announcement", "data": {...}}` whenever one is created,
  interleaved with ordinary bare-`TickResult` tick messages on the same connection.

- [ ] **Step 1: Write the failing tests**

Append to `backend/tests/test_api_http.py`:

```python
import json


def _sample_action_card(alert_id: str = "alert-1") -> dict:
    return {
        "alert_id": alert_id,
        "village_id": "v1",
        "stage": "RED",
        "headline": "Evacuate now",
        "reason_plain": "Heavy rainfall and slope movement",
        "shelter_name": "Community Hall",
        "route": None,
        "roads_to_avoid": [],
        "what_to_carry": [],
        "contact": "108",
        "issued_at": "2026-01-01T00:00:00+05:30",
        "valid_until": "2026-01-02T00:00:00+05:30",
        "safe_window_hours": None,
        "translations": {},
        "audio_urls": {},
    }


def test_post_announcement_dispatches_and_records_audit():
    with make_client() as client:
        card = _sample_action_card()
        response = client.post(
            "/api/announcements",
            json={"action_card": card, "officer_id": "officer-1", "recipient_count": 500},
        )
        assert response.status_code == 200
        body = response.json()
        assert {r["channel"] for r in body["channel_results"]} == {
            "cell_broadcast",
            "sms",
            "push",
            "mesh",
        }

        audit_response = client.get(f"/api/audit/{card['alert_id']}")
        kinds = [e["kind"] for e in audit_response.json()]
        assert "DDMA_APPROVED" in kinds
        assert "DISSEMINATED" in kinds


def test_get_announcements_lists_newest_first():
    with make_client() as client:
        client.post(
            "/api/announcements",
            json={"action_card": _sample_action_card("a1"), "officer_id": "o", "recipient_count": 1},
        )
        client.post(
            "/api/announcements",
            json={"action_card": _sample_action_card("a2"), "officer_id": "o", "recipient_count": 1},
        )
        response = client.get("/api/announcements")
        ids = [a["alert_id"] for a in response.json()]
    assert ids == ["a2", "a1"]


def test_announcement_is_broadcast_over_ws_ticks():
    with make_client() as client:
        card = _sample_action_card()
        with client.websocket_connect("/ws/ticks") as ws:
            client.post(
                "/api/announcements",
                json={"action_card": card, "officer_id": "o", "recipient_count": 1},
            )
            for _ in range(20):
                message = json.loads(ws.receive_text())
                if message.get("type") == "announcement":
                    assert message["data"]["alert_id"] == card["alert_id"]
                    break
            else:
                pytest.fail("no announcement message received over /ws/ticks")
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && pytest tests/test_api_http.py -k announcement -v`
Expected: FAIL — `POST /api/announcements` returns 404 (route doesn't exist yet)

- [ ] **Step 3: Add `announcements` to `AppState`**

In `backend/app/api/state.py`, add to the imports:

```python
from app.schemas.announcement import Announcement
```

Then add to `AppState.__init__` (after `self.pipeline = Pipeline()`):

```python
        # Real Announcements this session has dispatched (Task 3/4, Foundation sub-project).
        # Independent of replay state — an announcement made in LIVE mode stays visible even if a
        # replay starts afterwards, unlike self.pipeline (which IS reassigned on start_replay()).
        self.announcements: list[Announcement] = []
```

- [ ] **Step 4: Add the two REST handlers to `routes.py`**

Add to `backend/app/api/routes.py`'s imports:

```python
from app.api.announcements import AnnouncementRequest, create_announcement, list_announcements
from app.core.bus import Topic
from app.schemas.announcement import Announcement
```

Add the handlers (near the other POST handlers):

```python
@router.post("/announcements")
async def post_announcement(body: AnnouncementRequest, request: Request) -> Announcement:
    """Closes the gap CLAUDE.md's own Known Gaps section names: real approve -> real simulated
    channel send -> real DISSEMINATED audit event -> broadcast to any connected client."""
    app_state = _app_state(request)
    announcement = create_announcement(
        body, audit_log=app_state.pipeline.audit_log, announcements=app_state.announcements
    )
    await app_state.bus.publish(Topic.DISSEMINATION, announcement)
    return announcement


@router.get("/announcements")
async def get_announcements(request: Request) -> list[Announcement]:
    app_state = _app_state(request)
    return list_announcements(app_state.announcements)
```

- [ ] **Step 5: Multiplex the WebSocket hub**

Replace the full contents of `backend/app/ws/hub.py`:

```python
"""The /ws/ticks WebSocket hub (BUILD_PLAN.md task 0.11). Every connected client receives every
TickResult broadcast on Topic.TICK, and every Announcement broadcast on Topic.DISSEMINATION —
still ONE WebSocket endpoint (the stack table's "one channel, /ws/ticks"), multiplexed by message
shape on the wire: a bare TickResult JSON object for a tick, `{"type": "announcement", "data":
{...}}` for an announcement. TickResult has no `type` field, so this is an unambiguous
discriminator — see frontend/src/lib/ws.ts's matching parse.
"""
from __future__ import annotations

import asyncio
import json
import logging

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from app.core.bus import Topic
from app.schemas.tick import TickResult

logger = logging.getLogger(__name__)

router = APIRouter()


@router.websocket("/ws/ticks")
async def ws_ticks(websocket: WebSocket) -> None:
    await websocket.accept()
    app_state = websocket.app.state.app_state
    try:
        async with (
            app_state.bus.subscribe(Topic.TICK) as tick_queue,
            app_state.bus.subscribe(Topic.DISSEMINATION) as announcement_queue,
        ):
            pending = {
                asyncio.ensure_future(tick_queue.get()): tick_queue,
                asyncio.ensure_future(announcement_queue.get()): announcement_queue,
            }
            while True:
                done, _ = await asyncio.wait(pending, return_when=asyncio.FIRST_COMPLETED)
                for task in done:
                    queue = pending.pop(task)
                    message = task.result()
                    if isinstance(message, TickResult):
                        await websocket.send_text(message.model_dump_json())
                    else:
                        await websocket.send_text(
                            json.dumps(
                                {"type": "announcement", "data": message.model_dump(mode="json")}
                            )
                        )
                    pending[asyncio.ensure_future(queue.get())] = queue
    except WebSocketDisconnect:
        logger.info("client disconnected from /ws/ticks")
```

- [ ] **Step 6: Run tests to verify they pass**

Run: `cd backend && pytest tests/test_api_http.py -v`
Expected: PASS, including the 3 new tests. Also re-run `pytest -v` (full suite) to confirm the
hub rewrite didn't break the existing tick-broadcast tests (`test_replay_start_switches_mode_to_replay`-adjacent WS tests already in this file).

- [ ] **Step 7: Commit**

```bash
git add backend/app/api/state.py backend/app/api/routes.py backend/app/ws/hub.py backend/tests/test_api_http.py
git commit -m "Wire POST/GET /api/announcements and multiplex announcements onto /ws/ticks"
```

---

### Task 5: Frontend — mirror the new/changed types

**Files:**
- Modify: `frontend/src/types/schemas.ts`

**Interfaces:**
- Produces: `Demographics` interface; `VillageIsolation.demographics?: Demographics` (optional on
  the frontend — see note below); `ChannelResultSummary`, `Announcement` interfaces;
  `VerificationRecord` interface (frontend-only for now — no backend schema until sub-project 3,
  but Dashboard/sub-project 2 needs the shape to exist).

Note on optionality: the Python `VillageIsolation.demographics` field is *required* (Task 1) — 13
existing frontend test files construct `VillageIsolation`-shaped fixtures with fields that predate
this change, and none of them are otherwise touched by this sub-project. Making the TS field
`demographics?: Demographics` (optional) avoids an unrelated 13-file ripple edit while the backend
contract still guarantees it's always present in real data.

- [ ] **Step 1: Edit `types/schemas.ts`**

Change the `VillageIsolation` interface:

```ts
export interface Demographics {
  children: number
  seniors: number
  adults: number
  high_risk_households: number
  source: 'simulated'
}

export interface VillageIsolation {
  village_id: string
  name: string
  population: number
  demographics?: Demographics
  p_isolated: number
  isolated_now: boolean
  alternate_route_exists: boolean
  est_duration_hours: number | null
  severed_links: string[]
}
```

Add near the end of the file (after `WhatIfResult`):

```ts
export interface ChannelResultSummary {
  channel: string
  recipient_count: number
  delivered_count: number
  acknowledged_count: number
}

/** POST/GET /api/announcements' wire shape (backend/app/schemas/announcement.py::Announcement).
 * The real dissemination trigger: this is what a DDMA officer's Approve/Modify action in the
 * Announce workspace actually produces, and what the Citizen Announcement tab reads. */
export interface Announcement {
  id: string
  alert_id: string
  village_id: string
  stage: EscalationStage
  message: string
  language: string
  issued_by: string
  issued_at: string // ISO 8601
  channel_results: ChannelResultSummary[]
  cap_xml: string
}

/** Frontend-only for now (no backend schema until sub-project 3's verification workflow) — the
 * shape Dashboard (sub-project 2) needs to exist so it can badge a route "Verified Safe" without
 * a later schema change. */
export interface VerificationRecord {
  status: 'pending' | 'verified' | 'rejected'
  verifiedBy?: string
  verifiedAt?: string // ISO 8601
}
```

- [ ] **Step 2: Type-check**

Run: `cd frontend && npx tsc --noEmit`
Expected: no new errors (the `VillageIsolation.demographics` field is optional, so nothing
downstream that omits it in a test fixture breaks)

- [ ] **Step 3: Commit**

```bash
git add frontend/src/types/schemas.ts
git commit -m "Mirror Demographics/Announcement/ChannelResultSummary/VerificationRecord types"
```

---

### Task 6: Frontend — API client + WebSocket multiplexing

**Files:**
- Modify: `frontend/src/lib/api.ts`
- Modify: `frontend/src/lib/ws.ts`
- Test: `frontend/src/lib/ws.test.ts` (new)

**Interfaces:**
- Consumes: `Announcement`, `TickResult` (Task 5).
- Produces: `api.sendAnnouncement(payload)`, `api.listAnnouncements()` (`lib/api.ts`);
  `TickSocketHandlers.onAnnouncement?: (announcement: Announcement) => void` (`lib/ws.ts`) — the
  handler `connectTickSocket()` calls when a `{"type":"announcement",...}` message arrives,
  instead of `onTick`.

- [ ] **Step 1: Write the failing test**

```ts
// frontend/src/lib/ws.test.ts
import { describe, expect, it, vi } from 'vitest'
import { connectTickSocket } from './ws'

class FakeWebSocket {
  static instances: FakeWebSocket[] = []
  onopen: (() => void) | null = null
  onmessage: ((event: { data: string }) => void) | null = null
  onclose: (() => void) | null = null
  onerror: (() => void) | null = null
  close = vi.fn()
  constructor() {
    FakeWebSocket.instances.push(this)
  }
  emitMessage(data: unknown) {
    this.onmessage?.({ data: JSON.stringify(data) })
  }
}

describe('connectTickSocket', () => {
  it('routes a bare TickResult message to onTick', () => {
    vi.stubGlobal('WebSocket', FakeWebSocket)
    const onTick = vi.fn()
    const onAnnouncement = vi.fn()
    connectTickSocket({ onTick, onAnnouncement })
    const socket = FakeWebSocket.instances[FakeWebSocket.instances.length - 1]
    socket.emitMessage({ t: '2026-01-01T00:00:00+05:30', mode: 'live', aoi_id: 'aizawl', cell_risks: [] })
    expect(onTick).toHaveBeenCalledTimes(1)
    expect(onAnnouncement).not.toHaveBeenCalled()
  })

  it('routes a {type: "announcement"} message to onAnnouncement, not onTick', () => {
    vi.stubGlobal('WebSocket', FakeWebSocket)
    const onTick = vi.fn()
    const onAnnouncement = vi.fn()
    connectTickSocket({ onTick, onAnnouncement })
    const socket = FakeWebSocket.instances[FakeWebSocket.instances.length - 1]
    socket.emitMessage({ type: 'announcement', data: { id: 'ann-1', alert_id: 'a1' } })
    expect(onAnnouncement).toHaveBeenCalledWith({ id: 'ann-1', alert_id: 'a1' })
    expect(onTick).not.toHaveBeenCalled()
  })
})
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd frontend && npx vitest run src/lib/ws.test.ts`
Expected: FAIL — `onAnnouncement` doesn't exist on `TickSocketHandlers` yet / second test's
assertion fails because everything currently routes to `onTick`

- [ ] **Step 3: Update `ws.ts`**

```ts
// frontend/src/lib/ws.ts
import type { Announcement, TickResult } from '../types/schemas'

const WS_URL = import.meta.env.VITE_WS_URL ?? 'ws://localhost:8000/ws/ticks'

export type WsStatus = 'connecting' | 'open' | 'closed'

export interface TickSocketHandlers {
  onTick: (tick: TickResult) => void
  onAnnouncement?: (announcement: Announcement) => void
  onStatusChange?: (status: WsStatus) => void
}

const RECONNECT_DELAYS_MS = [500, 1000, 2000, 5000] // capped backoff; demo shouldn't die on a blip

/** Connects to /ws/ticks and auto-reconnects on close. Multiplexes two message shapes off the
 * same connection: a bare TickResult (no `type` field), or `{type: "announcement", data:
 * Announcement}` — see backend/app/ws/hub.py's matching wrapper. */
export function connectTickSocket({
  onTick,
  onAnnouncement,
  onStatusChange,
}: TickSocketHandlers): () => void {
  let socket: WebSocket | null = null
  let attempt = 0
  let stopped = false
  let reconnectTimer: ReturnType<typeof setTimeout> | null = null

  const connect = () => {
    if (stopped) return
    onStatusChange?.('connecting')
    socket = new WebSocket(WS_URL)

    socket.onopen = () => {
      attempt = 0
      onStatusChange?.('open')
    }

    socket.onmessage = (event: MessageEvent<string>) => {
      const parsed = JSON.parse(event.data) as TickResult | { type: 'announcement'; data: Announcement }
      if ('type' in parsed && parsed.type === 'announcement') {
        onAnnouncement?.(parsed.data)
      } else {
        onTick(parsed as TickResult)
      }
    }

    socket.onclose = () => {
      onStatusChange?.('closed')
      if (stopped) return
      const delay = RECONNECT_DELAYS_MS[Math.min(attempt, RECONNECT_DELAYS_MS.length - 1)]
      attempt += 1
      reconnectTimer = setTimeout(connect, delay)
    }

    socket.onerror = () => {
      socket?.close()
    }
  }

  connect()

  return () => {
    stopped = true
    if (reconnectTimer) clearTimeout(reconnectTimer)
    socket?.close()
  }
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd frontend && npx vitest run src/lib/ws.test.ts`
Expected: PASS (2 tests)

- [ ] **Step 5: Add the two API functions**

In `frontend/src/lib/api.ts`, add `Announcement` to the type import:

```ts
import type {
  ActionCard,
  Announcement,
  AoiInfo,
  AuditEvent,
  ModeState,
  ScenarioSummary,
  WhatIfRequest,
  WhatIfResult,
} from '../types/schemas'
```

Add to the `api` object:

```ts
  // Sub-project 1 (Foundation): the real dissemination trigger — approves (if not already),
  // sends through every real simulated channel, records a real DISSEMINATED audit event.
  sendAnnouncement: (payload: {
    action_card: ActionCard
    officer_id: string
    recipient_count: number
    message?: string
    language?: string
  }) =>
    request<Announcement>('/api/announcements', {
      method: 'POST',
      body: JSON.stringify(payload),
    }),
  listAnnouncements: () => request<Announcement[]>('/api/announcements'),
```

- [ ] **Step 6: Run the full frontend test suite to check for regressions**

Run: `cd frontend && npx vitest run`
Expected: PASS, no failures introduced

- [ ] **Step 7: Commit**

```bash
git add frontend/src/lib/api.ts frontend/src/lib/ws.ts frontend/src/lib/ws.test.ts
git commit -m "Add sendAnnouncement/listAnnouncements and multiplex announcements over the WS client"
```

---

### Task 7: Frontend — shared store slices for announcements, verification, citizen reports

**Files:**
- Modify: `frontend/src/lib/citizenReports.ts`
- Create: `frontend/src/lib/citizenReports.test.ts`
- Modify: `frontend/src/store/useTickStore.ts`
- Modify: `frontend/src/store/useTickStore.test.ts`

**Interfaces:**
- Consumes: `Announcement`, `VerificationRecord` (Task 5); `connectTickSocket` with
  `onAnnouncement` (Task 6).
- Produces on `useTickStore`: state `announcements: Announcement[]`, `verificationByAlertId:
  Record<string, VerificationRecord>`, `citizenReports: CitizenReport[]`; actions
  `hydrateCitizenReports(): void`, `queueCitizenReport(input: Pick<CitizenReport,
  'category'|'note'>): void`, `applyAnnouncement(a: Announcement): void`, `setVerification(alertId:
  string, record: VerificationRecord): void`.

- [ ] **Step 1: Add `source` to `CitizenReport` and write its test**

```ts
// frontend/src/lib/citizenReports.test.ts
import { beforeEach, describe, expect, it } from 'vitest'
import { getCitizenReports, queueCitizenReport } from './citizenReports'

beforeEach(() => localStorage.clear())

describe('citizenReports', () => {
  it('queues a report tagged as simulated and persists it to localStorage', () => {
    const report = queueCitizenReport({ category: 'Crack', note: 'Wall crack near the school' })
    expect(report.source).toBe('simulated')
    expect(report.status).toBe('queued')
    expect(getCitizenReports()).toHaveLength(1)
    expect(getCitizenReports()[0].id).toBe(report.id)
  })
})
```

Run: `cd frontend && npx vitest run src/lib/citizenReports.test.ts` — expect FAIL (`source` not
yet on the returned object, so `report.source` is `undefined`, not `'simulated'`).

Update `frontend/src/lib/citizenReports.ts`:

```ts
export type CitizenReportCategory = 'Crack' | 'Blocked road' | 'Water seepage'
export interface CitizenReport {
  id: string
  category: CitizenReportCategory
  note: string
  createdAt: string
  status: 'queued' | 'sent'
  source: 'simulated'
}
const STORAGE_KEY = 'nirantar-citizen-reports-v1'
export function getCitizenReports(): CitizenReport[] {
  try {
    return JSON.parse(localStorage.getItem(STORAGE_KEY) ?? '[]') as CitizenReport[]
  } catch {
    return []
  }
}
export function queueCitizenReport(input: Pick<CitizenReport, 'category' | 'note'>): CitizenReport {
  const report: CitizenReport = {
    ...input,
    id: crypto.randomUUID(),
    createdAt: new Date().toISOString(),
    status: 'queued',
    source: 'simulated',
  }
  const reports = [...getCitizenReports(), report]
  localStorage.setItem(STORAGE_KEY, JSON.stringify(reports))
  return report
}
```

Run: `cd frontend && npx vitest run src/lib/citizenReports.test.ts` — expect PASS.

- [ ] **Step 2: Write the failing store tests**

Add to `frontend/src/store/useTickStore.test.ts` (new `describe` block; keep the existing ones
as-is):

```ts
import { queueCitizenReport } from '../lib/citizenReports'
import type { Announcement } from '../types/schemas'

function makeAnnouncement(overrides: Partial<Announcement> = {}): Announcement {
  return {
    id: 'ann-1',
    alert_id: 'a1',
    village_id: 'v1',
    stage: 'RED',
    message: 'Evacuate now',
    language: 'en',
    issued_by: 'officer-1',
    issued_at: '2026-01-01T00:00:00+05:30',
    channel_results: [],
    cap_xml: '<alert></alert>',
    ...overrides,
  }
}

describe('announcements / verification / citizen reports', () => {
  beforeEach(() => {
    localStorage.clear()
    useTickStore.setState({ announcements: [], verificationByAlertId: {}, citizenReports: [] })
  })

  it('applyAnnouncement prepends newest-first', () => {
    useTickStore.getState().applyAnnouncement(makeAnnouncement({ id: 'ann-1' }))
    useTickStore.getState().applyAnnouncement(makeAnnouncement({ id: 'ann-2' }))
    expect(useTickStore.getState().announcements.map((a) => a.id)).toEqual(['ann-2', 'ann-1'])
  })

  it('setVerification stores a record keyed by alert_id', () => {
    useTickStore.getState().setVerification('a1', { status: 'verified', verifiedBy: 'officer-1' })
    expect(useTickStore.getState().verificationByAlertId['a1']).toEqual({
      status: 'verified',
      verifiedBy: 'officer-1',
    })
  })

  it('queueCitizenReport updates the store and localStorage together', () => {
    useTickStore.getState().queueCitizenReport({ category: 'Crack', note: 'test' })
    expect(useTickStore.getState().citizenReports).toHaveLength(1)
    expect(useTickStore.getState().citizenReports[0].source).toBe('simulated')
  })

  it('hydrateCitizenReports reads whatever is already in localStorage', () => {
    queueCitizenReport({ category: 'Blocked road', note: 'pre-existing' })
    useTickStore.getState().hydrateCitizenReports()
    expect(useTickStore.getState().citizenReports).toHaveLength(1)
    expect(useTickStore.getState().citizenReports[0].note).toBe('pre-existing')
  })
})
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `cd frontend && npx vitest run src/store/useTickStore.test.ts`
Expected: FAIL — `applyAnnouncement`/`setVerification`/`queueCitizenReport`/`hydrateCitizenReports`
don't exist on the store yet

- [ ] **Step 4: Add the new slices to `useTickStore.ts`**

Add to the imports:

```ts
import { getCitizenReports, queueCitizenReport as persistCitizenReport, type CitizenReport } from '../lib/citizenReports'
import type { Announcement, VerificationRecord } from '../types/schemas'
```

Add a constant near `MAX_AUDIT_EVENTS`:

```ts
const MAX_ANNOUNCEMENTS = 50
```

Add to the `TickStoreState` interface:

```ts
  announcements: Announcement[]
  verificationByAlertId: Record<string, VerificationRecord>
  citizenReports: CitizenReport[]

  hydrateCitizenReports: () => void
  queueCitizenReport: (input: Pick<CitizenReport, 'category' | 'note'>) => void
  applyAnnouncement: (announcement: Announcement) => void
  setVerification: (alertId: string, record: VerificationRecord) => void
```

Add to the store's initial state and actions:

```ts
  announcements: [],
  verificationByAlertId: {},
  citizenReports: [],
```

```ts
  hydrateCitizenReports: () => set({ citizenReports: getCitizenReports() }),

  queueCitizenReport: (input) => {
    const report = persistCitizenReport(input)
    set((state) => ({ citizenReports: [...state.citizenReports, report] }))
  },

  applyAnnouncement: (announcement) =>
    set((state) => ({
      announcements: [announcement, ...state.announcements].slice(0, MAX_ANNOUNCEMENTS),
    })),

  setVerification: (alertId, record) =>
    set((state) => ({
      verificationByAlertId: { ...state.verificationByAlertId, [alertId]: record },
    })),
```

Update `connect()` to wire `onAnnouncement`:

```ts
  connect: () => {
    if (disconnectSocket) return // already connected
    disconnectSocket = connectTickSocket({
      onTick: (tick) => get().applyTick(tick),
      onAnnouncement: (announcement) => get().applyAnnouncement(announcement),
      onStatusChange: (wsStatus) => set({ wsStatus }),
    })
  },
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `cd frontend && npx vitest run src/store/useTickStore.test.ts`
Expected: PASS (all tests, existing + 4 new)

- [ ] **Step 6: Run the full frontend suite**

Run: `cd frontend && npx vitest run`
Expected: PASS

- [ ] **Step 7: Commit**

```bash
git add frontend/src/lib/citizenReports.ts frontend/src/lib/citizenReports.test.ts frontend/src/store/useTickStore.ts frontend/src/store/useTickStore.test.ts
git commit -m "Add shared announcements/verification/citizenReports store slices"
```

---

### Task 8: Frontend — DashboardWorkspace (restores MapView + RightRail)

**Files:**
- Create: `frontend/src/components/DashboardWorkspace.tsx`
- Test: `frontend/src/components/DashboardWorkspace.test.tsx`

**Interfaces:**
- Consumes: `MapView`, `RightRail`, `ReplayControlBar`, `ScenarioPickerModal` (all existing,
  untouched); `useTickStore` (`wsStatus`, `error`, existing fields).
- Produces: `DashboardWorkspace()` — a component with no props, self-contained (owns its own
  `pickerOpen` state for the Run Case Study modal, matching the pre-rewrite `App.tsx`'s
  behavior).

- [ ] **Step 1: Write the failing test**

```tsx
// frontend/src/components/DashboardWorkspace.test.tsx
import { render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'

// MapView needs MapLibre GL, which needs a real WebGL canvas jsdom doesn't provide — same
// tradeoff VillageView.test.tsx already documents and mocks.
vi.mock('maplibre-gl', () => {
  class FakeMap {
    constructor(_opts: unknown) {}
    on(event: string, arg2: unknown, arg3?: unknown) {
      if (event === 'load' && typeof arg2 === 'function' && arg3 === undefined) arg2()
      return this
    }
    once(event: string, cb: () => void) {
      if (event === 'load') cb()
      return this
    }
    addSource() {
      return this
    }
    addLayer() {
      return this
    }
    getSource() {
      return { setData: vi.fn() }
    }
    getCanvas() {
      return { style: {} }
    }
    isStyleLoaded() {
      return true
    }
    setCenter() {
      return this
    }
    remove() {}
  }
  return { MapLibreMap: FakeMap }
})

import { DashboardWorkspace } from './DashboardWorkspace'

describe('DashboardWorkspace', () => {
  it('renders a Run Case Study trigger', () => {
    render(<DashboardWorkspace />)
    expect(screen.getByText('Run Case Study')).toBeInTheDocument()
  })
})
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd frontend && npx vitest run src/components/DashboardWorkspace.test.tsx`
Expected: FAIL — module doesn't exist

- [ ] **Step 3: Write the implementation**

```tsx
// frontend/src/components/DashboardWorkspace.tsx
import { useState } from 'react'
import { useTickStore } from '../store/useTickStore'
import { MapView } from './MapView'
import { ReplayControlBar } from './ReplayControlBar'
import { RightRail } from './RightRail'
import { ScenarioPickerModal } from './ScenarioPickerModal'

/** The Government "Dashboard" workspace (sub-project 1: restores the map/right-rail/replay-bar
 * that pre-existed the in-flight ConsoleShell rewrite, which had dropped them from App.tsx
 * entirely). Sub-project 2 adds the heatmap, working layer toggles, and the Risk Intelligence
 * Panel on top of this — this is the minimal, real, functional slice. */
export function DashboardWorkspace() {
  const [pickerOpen, setPickerOpen] = useState(false)
  const wsStatus = useTickStore((s) => s.wsStatus)
  const error = useTickStore((s) => s.error)

  return (
    <>
      <div className="relative flex flex-1 overflow-hidden">
        <div className="relative flex-1">
          <MapView />
          <div className="absolute top-4 left-4 flex gap-2">
            <button
              type="button"
              onClick={() => setPickerOpen(true)}
              className="rounded bg-emerald-600 px-4 py-2 text-sm font-semibold shadow-lg hover:bg-emerald-500"
            >
              Run Case Study
            </button>
          </div>
          {wsStatus !== 'open' && (
            <div className="absolute bottom-4 left-4 rounded bg-black/60 px-3 py-1.5 text-xs text-slate-300">
              WebSocket: {wsStatus}
            </div>
          )}
          {error && (
            <div className="absolute right-4 bottom-4 rounded bg-red-900/80 px-3 py-1.5 text-xs text-red-100">
              {error}
            </div>
          )}
        </div>
        <RightRail />
      </div>
      <ReplayControlBar />
      <ScenarioPickerModal open={pickerOpen} onClose={() => setPickerOpen(false)} />
    </>
  )
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd frontend && npx vitest run src/components/DashboardWorkspace.test.tsx`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add frontend/src/components/DashboardWorkspace.tsx frontend/src/components/DashboardWorkspace.test.tsx
git commit -m "Add DashboardWorkspace: restores MapView/RightRail/ReplayControlBar"
```

---

### Task 9: Frontend — WhatIfWorkspace (wraps the existing real simulator)

**Files:**
- Create: `frontend/src/components/WhatIfWorkspace.tsx`
- Test: `frontend/src/components/WhatIfWorkspace.test.tsx`

**Interfaces:**
- Consumes: `WhatIfSimulator` (existing, untouched, already real).
- Produces: `WhatIfWorkspace()` — no props.

- [ ] **Step 1: Write the failing test**

```tsx
// frontend/src/components/WhatIfWorkspace.test.tsx
import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import { WhatIfWorkspace } from './WhatIfWorkspace'

describe('WhatIfWorkspace', () => {
  it('renders the What-if Simulator heading and its rainfall control', () => {
    render(<WhatIfWorkspace />)
    expect(screen.getByText('What-if Simulator')).toBeInTheDocument()
    expect(screen.getByLabelText('Total rainfall in millimetres')).toBeInTheDocument()
  })
})
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd frontend && npx vitest run src/components/WhatIfWorkspace.test.tsx`
Expected: FAIL — module doesn't exist

- [ ] **Step 3: Write the implementation**

```tsx
// frontend/src/components/WhatIfWorkspace.tsx
import { WhatIfSimulator } from './WhatIfSimulator'

/** The Government "What-if Simulator" top-level workspace (new 5-item IA — previously nested
 * under a "Commander" sub-nav that no longer exists). Thin wrapper: WhatIfSimulator itself is
 * already real (BUILD_PLAN.md task 5.8) and untouched by this sub-project; sub-project 7
 * reorganizes its parameters and gives it a dedicated predictive map. */
export function WhatIfWorkspace() {
  return (
    <div className="flex-1 overflow-y-auto bg-slate-950 p-6">
      <h1 className="mb-1 text-xl font-bold">What-if Simulator</h1>
      <p className="mb-4 text-sm text-slate-400">
        DDMA pre-positioning support — re-runs the real risk/impact/decision pipeline on
        hypothetical rainfall. Results never touch live map state or the audit trail.
      </p>
      <WhatIfSimulator />
    </div>
  )
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd frontend && npx vitest run src/components/WhatIfWorkspace.test.tsx`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add frontend/src/components/WhatIfWorkspace.tsx frontend/src/components/WhatIfWorkspace.test.tsx
git commit -m "Add WhatIfWorkspace: wraps the existing real WhatIfSimulator"
```

---

### Task 10: Frontend — AnnounceWorkspace (real approve/modify/reject + dispatch)

**Files:**
- Create: `frontend/src/components/AnnounceWorkspace.tsx`
- Test: `frontend/src/components/AnnounceWorkspace.test.tsx`

**Interfaces:**
- Consumes: `api.sendAnnouncement`, `api.submitDdmaDecision` (existing + Task 6);
  `DDMA_OFFICER_ID_PLACEHOLDER`, `recommendationContext`, `DdmaDecisionKind` (`lib/ddma.ts`,
  existing, untouched); `MeshPropagationVisual` (existing, untouched); `useTickStore`
  (`actionCards`, `priorities`, `isolations`, `openAuditTrail`, all existing).
- Produces: `AnnounceWorkspace()` — no props. This absorbs the real Approve/Modify/Reject flow
  `DdmaConsole.tsx` currently implements (which Task 14 retires).

- [ ] **Step 1: Write the failing test**

```tsx
// frontend/src/components/AnnounceWorkspace.test.tsx
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { api } from '../lib/api'
import { useTickStore } from '../store/useTickStore'
import type { ActionCard, Announcement } from '../types/schemas'
import { AnnounceWorkspace } from './AnnounceWorkspace'

vi.mock('../lib/api', () => ({
  api: {
    sendAnnouncement: vi.fn(),
    submitDdmaDecision: vi.fn(),
  },
}))

const CARD: ActionCard = {
  alert_id: 'alert-1',
  village_id: 'v1',
  stage: 'RED',
  headline: 'Evacuate now',
  reason_plain: 'Heavy rainfall and slope movement',
  shelter_name: 'Community Hall',
  route: null,
  roads_to_avoid: [],
  what_to_carry: [],
  contact: '108',
  issued_at: '2026-01-01T00:00:00+05:30',
  valid_until: '2026-01-02T00:00:00+05:30',
  safe_window_hours: null,
  translations: {},
  audio_urls: {},
}

beforeEach(() => {
  vi.clearAllMocks()
  useTickStore.setState({
    actionCards: [CARD],
    priorities: [{ village_id: 'v1', eps: 0.8, tier: 'P1', components: {} }],
    isolations: [
      {
        village_id: 'v1',
        name: 'Test Village',
        population: 2840,
        p_isolated: 0.5,
        isolated_now: true,
        alternate_route_exists: false,
        est_duration_hours: null,
        severed_links: [],
      },
    ],
  })
})

describe('AnnounceWorkspace', () => {
  it('Approve & Dispatch calls sendAnnouncement with the village population as recipient_count', async () => {
    const announcement: Announcement = {
      id: 'ann-1',
      alert_id: 'alert-1',
      village_id: 'v1',
      stage: 'RED',
      message: 'Heavy rainfall and slope movement',
      language: 'en',
      issued_by: 'ddma-officer-placeholder (no real DDMA login system — type any identifier)',
      issued_at: '2026-01-01T00:00:00+05:30',
      channel_results: [
        { channel: 'sms', recipient_count: 2840, delivered_count: 2500, acknowledged_count: 900 },
      ],
      cap_xml: '<alert></alert>',
    }
    vi.mocked(api.sendAnnouncement).mockResolvedValue(announcement)

    render(<AnnounceWorkspace />)
    fireEvent.click(screen.getByText('Approve & Dispatch'))

    await waitFor(() => expect(api.sendAnnouncement).toHaveBeenCalledTimes(1))
    expect(api.sendAnnouncement).toHaveBeenCalledWith(
      expect.objectContaining({ action_card: CARD, recipient_count: 2840 }),
    )
    expect(await screen.findByText(/Dispatched for real/)).toBeInTheDocument()
    expect(screen.getByText(/2500\/2840 delivered/)).toBeInTheDocument()
  })

  it('Reject calls submitDdmaDecision, not sendAnnouncement', async () => {
    vi.mocked(api.submitDdmaDecision).mockResolvedValue({
      event_id: 'evt-1',
      alert_id: 'alert-1',
      kind: 'STOOD_DOWN',
      actor: 'ddma:officer',
      t: '2026-01-01T00:00:00+05:30',
      payload: {},
      input_hash: 'x',
      prev_hash: 'x',
      hash: 'x',
    })

    render(<AnnounceWorkspace />)
    fireEvent.click(screen.getByText('Reject'))

    await waitFor(() => expect(api.submitDdmaDecision).toHaveBeenCalledTimes(1))
    expect(api.sendAnnouncement).not.toHaveBeenCalled()
  })
})
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd frontend && npx vitest run src/components/AnnounceWorkspace.test.tsx`
Expected: FAIL — module doesn't exist

- [ ] **Step 3: Write the implementation**

```tsx
// frontend/src/components/AnnounceWorkspace.tsx
import { useState } from 'react'
import { api } from '../lib/api'
import { DDMA_OFFICER_ID_PLACEHOLDER, recommendationContext, type DdmaDecisionKind } from '../lib/ddma'
import { useTickStore } from '../store/useTickStore'
import type { ActionCard, Announcement, AuditEvent, EscalationStage } from '../types/schemas'
import { MeshPropagationVisual } from './MeshPropagationVisual'

interface DecisionState {
  status: 'submitting' | 'done' | 'error'
  kind?: DdmaDecisionKind
  event?: AuditEvent
  announcement?: Announcement
  error?: string
}

/** The Government "Announce" workspace (new 5-item IA). Absorbs DdmaConsole.tsx's real
 * Approve/Modify/Reject flow (Task 14 retires that file): Approve/Modify now call the real
 * POST /api/announcements (Task 3/4) — approve + send through every simulated channel + record a
 * real DISSEMINATED audit event, all in one action, matching how the new IA collapses "approve"
 * and "disseminate" into a single Announce step. Reject still calls the existing
 * POST /api/ddma/decide (nothing to disseminate for a rejected card). */
export function AnnounceWorkspace() {
  const actionCards = useTickStore((s) => s.actionCards)
  const priorities = useTickStore((s) => s.priorities)
  const isolations = useTickStore((s) => s.isolations)
  const openAuditTrail = useTickStore((s) => s.openAuditTrail)

  const [officerId, setOfficerId] = useState(DDMA_OFFICER_ID_PLACEHOLDER)
  const [decisions, setDecisions] = useState<Record<string, DecisionState>>({})
  const [notesDraft, setNotesDraft] = useState<Record<string, string>>({})

  const decide = async (card: ActionCard, kind: DdmaDecisionKind) => {
    setDecisions((prev) => ({ ...prev, [card.alert_id]: { status: 'submitting' } }))
    const context = recommendationContext(card, priorities, isolations)
    const resolvedOfficerId = officerId.trim() || DDMA_OFFICER_ID_PLACEHOLDER
    try {
      if (kind === 'rejected') {
        const event = await api.submitDdmaDecision({
          action_card: card,
          officer_id: resolvedOfficerId,
          decision: 'rejected',
          notes: notesDraft[card.alert_id] ?? '',
        })
        setDecisions((prev) => ({ ...prev, [card.alert_id]: { status: 'done', kind, event } }))
      } else {
        const announcement = await api.sendAnnouncement({
          action_card: card,
          officer_id: resolvedOfficerId,
          recipient_count: context.population ?? 0,
          message: notesDraft[card.alert_id] || undefined,
        })
        setDecisions((prev) => ({ ...prev, [card.alert_id]: { status: 'done', kind, announcement } }))
      }
    } catch (err) {
      setDecisions((prev) => ({
        ...prev,
        [card.alert_id]: { status: 'error', error: err instanceof Error ? err.message : String(err) },
      }))
    }
  }

  return (
    <div className="flex-1 overflow-y-auto bg-slate-950 p-6">
      <div className="mb-4">
        <h1 className="text-xl font-bold">Announce</h1>
        <p className="text-sm text-slate-400">
          Approve or modify a recommendation to dispatch it for real over every simulated channel;
          reject to stand it down.
        </p>
      </div>

      <div className="mb-4 rounded border border-amber-500/40 bg-amber-500/10 px-4 py-3 text-sm text-amber-200">
        <span className="font-bold">No machine issues an evacuation order.</span> Every
        recommendation below was generated by the AI risk pipeline and requires a human DDMA
        officer to Approve, Modify, or Reject it before anything is disseminated.
      </div>

      <div className="mb-6 flex items-center gap-2 text-sm">
        <label htmlFor="announce-officer-id" className="text-slate-400">
          Officer ID
        </label>
        <input
          id="announce-officer-id"
          type="text"
          value={officerId}
          onChange={(event) => setOfficerId(event.target.value)}
          className="max-w-md flex-1 rounded border border-white/10 bg-white/5 px-2 py-1.5 font-mono text-xs text-slate-200"
        />
      </div>

      <div className="mb-6 rounded border border-white/10 bg-white/5 p-4">
        <MeshPropagationVisual />
      </div>

      <h2 className="mb-2 text-xs font-semibold uppercase tracking-wide text-slate-400">
        Pending recommendations ({actionCards.length})
      </h2>

      {actionCards.length === 0 && (
        <p className="text-sm text-slate-500">No AI recommendations issued yet.</p>
      )}

      <ul className="space-y-3">
        {actionCards.map((card) => (
          <RecommendationRow
            key={card.alert_id}
            card={card}
            context={recommendationContext(card, priorities, isolations)}
            decision={decisions[card.alert_id]}
            notes={notesDraft[card.alert_id] ?? ''}
            onNotesChange={(value) => setNotesDraft((prev) => ({ ...prev, [card.alert_id]: value }))}
            onDecide={(kind) => void decide(card, kind)}
            onViewAuditTrail={() => openAuditTrail(card.alert_id)}
          />
        ))}
      </ul>
    </div>
  )
}

function RecommendationRow({
  card,
  context,
  decision,
  notes,
  onNotesChange,
  onDecide,
  onViewAuditTrail,
}: {
  card: ActionCard
  context: ReturnType<typeof recommendationContext>
  decision: DecisionState | undefined
  notes: string
  onNotesChange: (value: string) => void
  onDecide: (kind: DdmaDecisionKind) => void
  onViewAuditTrail: () => void
}) {
  const busy = decision?.status === 'submitting'
  const done = decision?.status === 'done'

  return (
    <li className="rounded border border-white/10 bg-white/5 p-4">
      <div className="mb-2 flex items-start justify-between gap-2">
        <div>
          <div className="flex items-center gap-2">
            <span className={`rounded px-2 py-0.5 text-xs font-bold ${stageBadgeClass(card.stage)}`}>
              {card.stage}
            </span>
            <span className="font-semibold">{card.headline}</span>
          </div>
          <p className="mt-0.5 text-xs text-slate-400">
            {card.village_id}
            {context.population !== null && ` · pop. ${context.population.toLocaleString()}`}
          </p>
        </div>
      </div>

      <p className="mb-2 text-sm text-slate-300">
        <span className="text-slate-500">AI rationale: </span>
        {card.reason_plain}
      </p>

      {!done && (
        <div className="mb-2">
          <textarea
            value={notes}
            onChange={(event) => onNotesChange(event.target.value)}
            placeholder="Message to send (defaults to the AI-generated rationale)"
            rows={2}
            className="w-full rounded border border-white/10 bg-white/5 px-2 py-1 text-xs text-slate-200"
          />
        </div>
      )}

      {!done && (
        <div className="flex items-center gap-2">
          <button
            type="button"
            disabled={busy}
            onClick={() => onDecide('approved')}
            className="rounded bg-emerald-600 px-3 py-1.5 text-sm font-semibold hover:bg-emerald-500 disabled:opacity-50"
          >
            Approve & Dispatch
          </button>
          <button
            type="button"
            disabled={busy}
            onClick={() => onDecide('modified')}
            className="rounded bg-amber-600 px-3 py-1.5 text-sm font-semibold text-black hover:bg-amber-500 disabled:opacity-50"
          >
            Modify & Dispatch
          </button>
          <button
            type="button"
            disabled={busy}
            onClick={() => onDecide('rejected')}
            className="rounded bg-red-700 px-3 py-1.5 text-sm font-semibold hover:bg-red-600 disabled:opacity-50"
          >
            Reject
          </button>
          {busy && <span className="text-xs text-slate-500">Submitting…</span>}
        </div>
      )}

      {decision?.status === 'error' && (
        <p className="mt-2 text-xs text-red-300">Could not submit decision: {decision.error}</p>
      )}

      {done && decision.announcement && (
        <div className="mt-2 rounded bg-black/20 px-3 py-2 text-xs">
          <p className="mb-1 font-semibold text-emerald-300">Dispatched for real.</p>
          {decision.announcement.channel_results.map((r) => (
            <p key={r.channel} className="text-slate-400">
              {r.channel}: {r.delivered_count}/{r.recipient_count} delivered, {r.acknowledged_count}{' '}
              acknowledged
            </p>
          ))}
          <button
            type="button"
            onClick={onViewAuditTrail}
            className="mt-1 rounded bg-white/10 px-2 py-1 font-semibold hover:bg-white/20"
          >
            View audit trail
          </button>
        </div>
      )}

      {done && decision.event && (
        <div className="mt-2 rounded bg-black/20 px-3 py-2 text-xs">
          <p className="text-slate-400">
            Rejected — stood down at {new Date(decision.event.t).toLocaleString()}
          </p>
          <button
            type="button"
            onClick={onViewAuditTrail}
            className="mt-1 rounded bg-white/10 px-2 py-1 font-semibold hover:bg-white/20"
          >
            View audit trail
          </button>
        </div>
      )}
    </li>
  )
}

function stageBadgeClass(stage: EscalationStage): string {
  switch (stage) {
    case 'RED':
      return 'bg-red-600'
    case 'ORANGE':
      return 'bg-orange-500'
    case 'YELLOW':
      return 'bg-yellow-500 text-black'
    default:
      return 'bg-emerald-600'
  }
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd frontend && npx vitest run src/components/AnnounceWorkspace.test.tsx`
Expected: PASS (2 tests)

- [ ] **Step 5: Commit**

```bash
git add frontend/src/components/AnnounceWorkspace.tsx frontend/src/components/AnnounceWorkspace.test.tsx
git commit -m "Add AnnounceWorkspace: real approve/modify -> dispatch, reject -> stand down"
```

---

### Task 11: Frontend — CommanderWorkspace (ports the existing real recommendation logic)

**Files:**
- Create: `frontend/src/components/CommanderWorkspace.tsx`
- Test: `frontend/src/components/CommanderWorkspace.test.tsx`

**Interfaces:**
- Consumes: `useTickStore` (`priorities`, `roadRisks`, existing); `NotBuilt` (existing).
- Produces: `CommanderWorkspace({ onAnnounce, onWhatIf }: { onAnnounce: () => void; onWhatIf: ()
  => void })`.

- [ ] **Step 1: Write the failing test**

```tsx
// frontend/src/components/CommanderWorkspace.test.tsx
import { fireEvent, render, screen } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { useTickStore } from '../store/useTickStore'
import { CommanderWorkspace } from './CommanderWorkspace'

beforeEach(() => {
  useTickStore.setState({ priorities: [], roadRisks: [] })
})

describe('CommanderWorkspace', () => {
  it('shows a NotBuilt fallback when there is no priority feed yet', () => {
    render(<CommanderWorkspace onAnnounce={vi.fn()} onWhatIf={vi.fn()} />)
    expect(screen.getByText(/No recommendation is shown/)).toBeInTheDocument()
  })

  it('recommends the top-ranked village and links to Announce', () => {
    useTickStore.setState({
      priorities: [{ village_id: 'v1', eps: 0.91, tier: 'P1', components: { rainfall: 0.4 } }],
      roadRisks: [],
    })
    const onAnnounce = vi.fn()
    render(<CommanderWorkspace onAnnounce={onAnnounce} onWhatIf={vi.fn()} />)
    expect(screen.getByText(/v1/)).toBeInTheDocument()
    fireEvent.click(screen.getByText('Open Announce'))
    expect(onAnnounce).toHaveBeenCalledTimes(1)
  })
})
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd frontend && npx vitest run src/components/CommanderWorkspace.test.tsx`
Expected: FAIL — module doesn't exist

- [ ] **Step 3: Write the implementation**

```tsx
// frontend/src/components/CommanderWorkspace.tsx
import { useTickStore } from '../store/useTickStore'
import { NotBuilt } from './NotBuilt'

/** The Government "AI Emergency Commander" top-level workspace (new 5-item IA). Ports the real,
 * data-driven recommendation logic the in-flight ConsoleWorkspaces.tsx rewrite already built
 * (Task 14 retires that file) — unchanged behavior, just remounted at its own route instead of
 * nested under a "Commander" sub-nav that no longer exists. Sub-project 6 replaces this with the
 * full conversational chat interface; this is the real, functional slice Foundation ships. */
export function CommanderWorkspace({
  onAnnounce,
  onWhatIf,
}: {
  onAnnounce: () => void
  onWhatIf: () => void
}) {
  const priorities = useTickStore((s) => s.priorities)
  const roads = useTickStore((s) => s.roadRisks)
  const top = priorities[0]

  return (
    <div className="flex-1 overflow-y-auto bg-slate-950 p-6">
      <p className="text-xs uppercase tracking-wide text-slate-500">AI Emergency Commander</p>
      <h1 className="mb-4 text-xl font-bold">Decision support, not autonomous response.</h1>
      <div className="mb-6 grid gap-4 md:grid-cols-2">
        <article className="rounded border border-white/10 bg-white/5 p-4">
          <h2 className="mb-2 text-sm font-semibold text-slate-200">Situation summary</h2>
          <p className="text-sm text-slate-400">
            {priorities.length
              ? `${priorities.filter((x) => x.tier === 'P1').length} P1 villages are currently in the received priority feed.`
              : 'Awaiting a verified priority feed.'}
          </p>
          <p className="text-sm text-slate-400">
            {roads.length
              ? `${roads.filter((x) => x.severed).length} road segments are marked severed in the current impact feed.`
              : 'Awaiting road impact feed.'}
          </p>
        </article>
        <article className="rounded border border-white/10 bg-white/5 p-4">
          <h2 className="mb-2 text-sm font-semibold text-slate-200">Recommendation</h2>
          {top ? (
            <>
              <p className="text-sm text-slate-300">
                Consider preparing an announcement for <strong>{top.village_id}</strong>; it is
                ranked {top.tier} with EPS {top.eps.toFixed(2)}.
              </p>
              <h3 className="mt-2 text-xs font-semibold uppercase text-slate-500">Why</h3>
              <ul className="text-xs text-slate-400">
                {Object.keys(top.components)
                  .slice(0, 3)
                  .map((x) => (
                    <li key={x}>{x} contributes to the current EPS</li>
                  ))}
              </ul>
            </>
          ) : (
            <NotBuilt
              task="TASK-AI-COMMANDER"
              what="No recommendation is shown without a current decision-pipeline context."
              blocks="AI recommendation backend and risk/priority tick"
            />
          )}
        </article>
      </div>
      <div className="rounded border border-amber-500/40 bg-amber-500/10 px-4 py-3 text-sm text-amber-200">
        <strong>HUMAN-IN-THE-LOOP</strong> — this system proposes. An authorised officer decides.
        <div className="mt-2 flex gap-2">
          <button
            type="button"
            onClick={onAnnounce}
            className="rounded bg-white/10 px-3 py-1.5 text-xs font-semibold hover:bg-white/20"
          >
            Open Announce
          </button>
          <button
            type="button"
            onClick={onWhatIf}
            className="rounded bg-white/10 px-3 py-1.5 text-xs font-semibold hover:bg-white/20"
          >
            Run What-if
          </button>
        </div>
      </div>
    </div>
  )
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd frontend && npx vitest run src/components/CommanderWorkspace.test.tsx`
Expected: PASS (2 tests)

- [ ] **Step 5: Commit**

```bash
git add frontend/src/components/CommanderWorkspace.tsx frontend/src/components/CommanderWorkspace.test.tsx
git commit -m "Add CommanderWorkspace: ports the real recommendation logic to its own route"
```

---

### Task 12: Frontend — AuditWorkspace (alert list, opens the existing real modal)

**Files:**
- Create: `frontend/src/components/AuditWorkspace.tsx`
- Test: `frontend/src/components/AuditWorkspace.test.tsx`

**Interfaces:**
- Consumes: `useTickStore` (`auditEvents`, `openAuditTrail`, existing); `NotBuilt` (existing).
- Produces: `AuditWorkspace()` — no props.

- [ ] **Step 1: Write the failing test**

```tsx
// frontend/src/components/AuditWorkspace.test.tsx
import { fireEvent, render, screen } from '@testing-library/react'
import { beforeEach, describe, expect, it } from 'vitest'
import { useTickStore } from '../store/useTickStore'
import { AuditWorkspace } from './AuditWorkspace'

beforeEach(() => {
  useTickStore.setState({ auditEvents: [], auditTrailAlertId: null })
})

describe('AuditWorkspace', () => {
  it('shows a NotBuilt fallback when no audit events exist', () => {
    render(<AuditWorkspace />)
    expect(screen.getByText(/No audit events have been received/)).toBeInTheDocument()
  })

  it('lists distinct alert_ids and opens the trail modal on click', () => {
    useTickStore.setState({
      auditEvents: [
        {
          event_id: 'e1',
          alert_id: 'alert-1',
          kind: 'AI_FLAGGED',
          actor: 'system',
          t: '2026-01-01T00:00:00+05:30',
          payload: {},
          input_hash: 'x',
          prev_hash: 'x',
          hash: 'x',
        },
      ],
    })
    render(<AuditWorkspace />)
    expect(screen.getByText('alert-1')).toBeInTheDocument()
    fireEvent.click(screen.getByText('View trail'))
    expect(useTickStore.getState().auditTrailAlertId).toBe('alert-1')
  })
})
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd frontend && npx vitest run src/components/AuditWorkspace.test.tsx`
Expected: FAIL — module doesn't exist

- [ ] **Step 3: Write the implementation**

```tsx
// frontend/src/components/AuditWorkspace.tsx
import { useTickStore } from '../store/useTickStore'
import { NotBuilt } from './NotBuilt'

/** The Government "Audit" top-level workspace. A page-level list of alert_ids (real, from
 * `useTickStore.auditEvents`) that opens the existing, real, already-tested `AuditTrailView`
 * modal (App.tsx-mounted, Task 14) for the full hash-chained timeline — reused, not rebuilt. */
export function AuditWorkspace() {
  const events = useTickStore((s) => s.auditEvents)
  const openAuditTrail = useTickStore((s) => s.openAuditTrail)
  const alertIds = Array.from(new Set(events.map((e) => e.alert_id)))

  return (
    <div className="flex-1 overflow-y-auto bg-slate-950 p-6">
      <h1 className="mb-1 text-xl font-bold">Audit</h1>
      <p className="mb-4 text-sm text-slate-400">
        AI Flagged → DDMA Approved → Disseminated → Village Acknowledged
      </p>
      {alertIds.length === 0 ? (
        <NotBuilt
          task="TASK-AUDIT-FEED"
          what="No audit events have been received yet."
          blocks="A live or replay tick"
        />
      ) : (
        <table className="w-full text-sm">
          <thead>
            <tr className="text-left text-slate-500">
              <th className="pb-2">Alert</th>
              <th className="pb-2">Latest event</th>
              <th className="pb-2" />
            </tr>
          </thead>
          <tbody>
            {alertIds.map((alertId) => {
              const latest = events.find((e) => e.alert_id === alertId)
              return (
                <tr key={alertId} className="border-t border-white/10">
                  <td className="py-2 font-mono text-xs">{alertId}</td>
                  <td className="py-2">{latest?.kind}</td>
                  <td className="py-2 text-right">
                    <button
                      type="button"
                      onClick={() => openAuditTrail(alertId)}
                      className="rounded bg-white/10 px-2 py-1 text-xs font-semibold hover:bg-white/20"
                    >
                      View trail
                    </button>
                  </td>
                </tr>
              )
            })}
          </tbody>
        </table>
      )}
    </div>
  )
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd frontend && npx vitest run src/components/AuditWorkspace.test.tsx`
Expected: PASS (2 tests)

- [ ] **Step 5: Commit**

```bash
git add frontend/src/components/AuditWorkspace.tsx frontend/src/components/AuditWorkspace.test.tsx
git commit -m "Add AuditWorkspace: real alert list that opens the existing AuditTrailView modal"
```

---

### Task 13: Frontend — CitizenApp gains the Announcement tab, and absorbs VillageView's real Alert/Route content

**Files found during self-review, not in the original spec draft:** `VillageView.tsx` (BUILD_PLAN.md
task 3.10) is the real citizen-facing screen — stage-colour card, voice-alert playback, an offline
map with the real route drawn, and the actual "I have evacuated" acknowledge button wired to
`POST /api/village/acknowledge` with offline queueing (`lib/ackQueue.ts`) — but it has no route
anywhere in the pre-rewrite `App.tsx` OR the in-flight `ConsoleShell`/`CitizenApp` rewrite; it was
reachable only via a `screen === 'village'` DDMA-toolbar button that this sub-project's shell
replacement removes. Meanwhile `CitizenApp.tsx`'s existing `alert`/`route` sections are a much
thinner, independently-built duplicate (no voice alert, no acknowledge button, no offline
fallback, a static ASCII-art placeholder instead of a real map) covering the same two concepts.
Rather than leave `VillageView.tsx` orphaned (the exact regression class this sub-project exists
to fix) alongside a permanently-thinner `CitizenApp`, this task merges `VillageView`'s real content
into `CitizenApp`'s `alert` and `route` tabs and retires `VillageView.tsx` as a separate component
— the same absorb-not-orphan treatment Task 10 already gives `DdmaConsole.tsx`.

**Files:**
- Modify: `frontend/src/components/CitizenApp.tsx`
- Create: `frontend/src/components/CitizenApp.test.tsx`
- Delete (end of this task): `frontend/src/components/VillageView.tsx`,
  `frontend/src/components/VillageView.test.tsx`

**Interfaces:**
- Consumes: `useTickStore` (`announcements` new from Task 7; `actionCards`, `isolations`,
  `openAuditTrail`, existing); `queueAcknowledgement` (`lib/ackQueue.ts`, existing);
  `api.acknowledgeVillage` (existing); `STAGE_COLOR` (`lib/escalation.ts`, existing);
  `deriveCachedEmergencyContacts`, `deriveCachedShelters`, `getCachedActionCards`
  (`lib/offlineData.ts`, existing); `villagesWithActionCards`, `actionCardForVillage`
  (`lib/villageView.ts`, existing); `MapView` (existing, with its `routeGeometry` prop).
- Produces: `CitizenApp({ route, onNavigate })` where `route` now includes `'announcement'` (was
  `'alert' | 'route' | 'report'`, now `'alert' | 'route' | 'announcement' | 'report'`). The `alert`
  tab is now the full real stage card + voice alert + acknowledge flow (ported from `VillageView`);
  the `route` tab is now the full real offline map + shelter/distance detail (also ported from
  `VillageView`).

- [ ] **Step 1: Write the failing test**

```tsx
// frontend/src/components/CitizenApp.test.tsx
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { api } from '../lib/api'
import { useTickStore } from '../store/useTickStore'
import type { ActionCard, AuditEvent } from '../types/schemas'
import { CitizenApp } from './CitizenApp'

// The alert/route tabs render MapView (ported from VillageView.tsx) — same MapLibre GL /
// jsdom-WebGL tradeoff VillageView.test.tsx already documents and mocks.
vi.mock('maplibre-gl', () => {
  class FakeMap {
    constructor(_opts: unknown) {}
    on(event: string, arg2: unknown, arg3?: unknown) {
      if (event === 'load' && typeof arg2 === 'function' && arg3 === undefined) arg2()
      return this
    }
    once(event: string, cb: () => void) {
      if (event === 'load') cb()
      return this
    }
    addSource() {
      return this
    }
    addLayer() {
      return this
    }
    getSource() {
      return { setData: vi.fn() }
    }
    getCanvas() {
      return { style: {} }
    }
    isStyleLoaded() {
      return true
    }
    setCenter() {
      return this
    }
    remove() {}
  }
  return { MapLibreMap: FakeMap }
})

vi.mock('../lib/api', () => ({
  api: { acknowledgeVillage: vi.fn() },
}))

const CARD: ActionCard = {
  alert_id: 'alert-1',
  village_id: 'v1',
  stage: 'RED',
  headline: 'Evacuate now',
  reason_plain: 'Heavy rainfall and slope movement',
  shelter_name: 'Community Hall',
  route: {
    village_id: 'v1',
    shelter_id: 's1',
    shelter_name: 'Community Hall',
    geometry: { type: 'LineString', coordinates: [[0, 0], [1, 1]] },
    distance_m: 2400,
    est_walk_minutes: 18,
    avoided_roads: [],
    shelter_capacity_ok: true,
  },
  roads_to_avoid: ['NH-6'],
  what_to_carry: [],
  contact: '108',
  issued_at: '2026-01-01T00:00:00+05:30',
  valid_until: '2026-01-02T00:00:00+05:30',
  safe_window_hours: null,
  translations: {},
  audio_urls: {},
}

beforeEach(() => {
  vi.clearAllMocks()
  useTickStore.setState({ actionCards: [], isolations: [], announcements: [] })
})

describe('CitizenApp — alert tab (ported from VillageView)', () => {
  it('shows a fallback when there is no active alert for any village', () => {
    render(<CitizenApp route="alert" onNavigate={vi.fn()} />)
    expect(screen.getByText(/No active alert for any village right now/)).toBeInTheDocument()
  })

  it('renders the real stage card and acknowledges evacuation', async () => {
    useTickStore.setState({ actionCards: [CARD] })
    const event: AuditEvent = {
      event_id: 'evt-1',
      alert_id: 'alert-1',
      kind: 'VILLAGE_ACKNOWLEDGED',
      actor: 'village:v1',
      t: '2026-01-01T01:00:00+05:30',
      payload: {},
      input_hash: 'x',
      prev_hash: 'x',
      hash: 'x',
    }
    vi.mocked(api.acknowledgeVillage).mockResolvedValue(event)

    render(<CitizenApp route="alert" onNavigate={vi.fn()} />)
    expect(screen.getByText('RED')).toBeInTheDocument()
    expect(screen.getByText('Evacuate now')).toBeInTheDocument()

    fireEvent.click(screen.getByText('I have evacuated'))
    await waitFor(() =>
      expect(api.acknowledgeVillage).toHaveBeenCalledWith({ alert_id: 'alert-1', village_id: 'v1' }),
    )
    expect(await screen.findByText('✓ Evacuation acknowledged')).toBeInTheDocument()
  })
})

describe('CitizenApp — route tab (ported from VillageView)', () => {
  it('renders the real shelter/distance detail when a route exists', () => {
    useTickStore.setState({ actionCards: [CARD] })
    render(<CitizenApp route="route" onNavigate={vi.fn()} />)
    expect(screen.getByText('Community Hall')).toBeInTheDocument()
    expect(screen.getByText(/2\.4 km/)).toBeInTheDocument()
  })
})

describe('CitizenApp — announcement tab', () => {
  it('shows a NotBuilt fallback when no announcement has been sent', () => {
    render(<CitizenApp route="announcement" onNavigate={vi.fn()} />)
    expect(screen.getByText(/No announcement has been sent yet/)).toBeInTheDocument()
  })

  it('renders a real announcement from the shared store', () => {
    useTickStore.setState({
      announcements: [
        {
          id: 'ann-1',
          alert_id: 'a1',
          village_id: 'v1',
          stage: 'RED',
          message: 'Evacuate to the community hall',
          language: 'en',
          issued_by: 'officer-1',
          issued_at: '2026-01-01T00:00:00+05:30',
          channel_results: [],
          cap_xml: '<alert></alert>',
        },
      ],
    })
    render(<CitizenApp route="announcement" onNavigate={vi.fn()} />)
    expect(screen.getByText('Evacuate to the community hall')).toBeInTheDocument()
    expect(screen.getByText('v1')).toBeInTheDocument()
  })

  it('nav includes an Announcements tab', () => {
    render(<CitizenApp route="alert" onNavigate={vi.fn()} />)
    expect(screen.getByText(/Announcements/)).toBeInTheDocument()
  })
})
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd frontend && npx vitest run src/components/CitizenApp.test.tsx`
Expected: FAIL — `route="announcement"` isn't a valid prop value yet, and the current `alert`/
`route` tabs don't have any of `VillageView`'s real content

- [ ] **Step 3: Update the implementation**

Replace the full contents of `frontend/src/components/CitizenApp.tsx`:

```tsx
import { useEffect, useMemo, useState } from 'react'
import { queueAcknowledgement } from '../lib/ackQueue'
import { api } from '../lib/api'
import { getCitizenReports, queueCitizenReport, type CitizenReportCategory } from '../lib/citizenReports'
import { STAGE_COLOR } from '../lib/escalation'
import {
  deriveCachedEmergencyContacts,
  deriveCachedShelters,
  getCachedActionCards,
  type CachedShelter,
} from '../lib/offlineData'
import { actionCardForVillage, villagesWithActionCards } from '../lib/villageView'
import { useTickStore } from '../store/useTickStore'
import type { AuditEvent } from '../types/schemas'
import { MapView } from './MapView'
import { NotBuilt } from './NotBuilt'

export type CitizenRoute = 'alert' | 'route' | 'announcement' | 'report'

type AckState =
  | { status: 'idle' }
  | { status: 'submitting' }
  | { status: 'done'; event: AuditEvent }
  | { status: 'queued' }
  | { status: 'error'; error: string }

export function CitizenApp({
  route,
  onNavigate,
}: {
  route: CitizenRoute
  onNavigate: (route: CitizenRoute) => void
}) {
  const actionCards = useTickStore((s) => s.actionCards)
  const isolations = useTickStore((s) => s.isolations)
  const announcements = useTickStore((s) => s.announcements)
  const openAuditTrail = useTickStore((s) => s.openAuditTrail)

  // Ported from VillageView.tsx (BUILD_PLAN.md task 3.10): no village login/selection system
  // exists, so the viewer picks among whichever villages currently carry a pending action card.
  const villageIds = useMemo(() => villagesWithActionCards(actionCards), [actionCards])
  const [selectedVillageId, setSelectedVillageId] = useState<string | null>(null)
  const activeVillageId =
    selectedVillageId && villageIds.includes(selectedVillageId) ? selectedVillageId : villageIds[0] ?? null
  const card = actionCardForVillage(actionCards, activeVillageId)
  const villageName = isolations.find((v) => v.village_id === activeVillageId)?.name ?? activeVillageId

  const [ackState, setAckState] = useState<AckState>({ status: 'idle' })
  const [queued, setQueued] = useState(() => getCitizenReports().filter((r) => r.status === 'queued').length)
  const [offline, setOffline] = useState(!navigator.onLine)
  const [category, setCategory] = useState<CitizenReportCategory>('Blocked road')
  const [note, setNote] = useState('')

  useEffect(() => {
    const update = () => setOffline(!navigator.onLine)
    addEventListener('online', update)
    addEventListener('offline', update)
    return () => {
      removeEventListener('online', update)
      removeEventListener('offline', update)
    }
  }, [])

  const handleAcknowledge = async () => {
    if (!card) return
    setAckState({ status: 'submitting' })
    const payload = { alert_id: card.alert_id, village_id: card.village_id }
    if (typeof navigator !== 'undefined' && navigator.onLine === false) {
      await queueAcknowledgement(payload)
      setAckState({ status: 'queued' })
      return
    }
    try {
      const event = await api.acknowledgeVillage(payload)
      setAckState({ status: 'done', event })
    } catch {
      await queueAcknowledgement(payload)
      setAckState({ status: 'queued' })
    }
  }

  const saveReport = () => {
    queueCitizenReport({ category, note: note.trim() })
    setQueued(getCitizenReports().filter((r) => r.status === 'queued').length)
    setNote('')
  }

  return (
    <main className="citizen-app">
      <header className="citizen-head">
        <a href="/console/dashboard" className="citizen-brand">
          NIRANTAR
        </a>
        <a href="/console/dashboard" className="citizen-role">
          Officer view
        </a>
        <button>English ▾</button>
      </header>

      {route === 'alert' &&
        (card ? (
          <section className="citizen-screen" style={{ backgroundColor: STAGE_COLOR[card.stage] }}>
            {villageIds.length > 1 && (
              <select
                aria-label="Select village"
                value={activeVillageId ?? ''}
                onChange={(event) => setSelectedVillageId(event.target.value)}
              >
                {villageIds.map((id) => (
                  <option key={id} value={id}>
                    {isolations.find((v) => v.village_id === id)?.name ?? id}
                  </option>
                ))}
              </select>
            )}
            <div className="citizen-alert">
              <span>{card.stage}</span>
              <h1>{card.headline}</h1>
              <h2>{villageName}</h2>
              <p>{card.reason_plain}</p>
            </div>
            <div className="citizen-action">
              <h2>Voice alert</h2>
              {Object.entries(card.audio_urls).length > 0 ? (
                Object.entries(card.audio_urls).map(([lang, url]) => (
                  <div key={lang}>
                    <span>{lang}</span>
                    {/* eslint-disable-next-line jsx-a11y/media-has-caption */}
                    <audio controls src={url} />
                  </div>
                ))
              ) : (
                <button type="button" disabled title="Pre-generated multilingual audio is not built yet.">
                  ▶ Play voice alert — not yet available
                </button>
              )}
            </div>
            {card.roads_to_avoid.length > 0 && (
              <div className="citizen-action">
                <h2>Roads to avoid</h2>
                <p>{card.roads_to_avoid.join(', ')}</p>
              </div>
            )}
            {card.what_to_carry.length > 0 && (
              <div className="citizen-action">
                <h2>What to carry</h2>
                <ul>
                  {card.what_to_carry.map((item) => (
                    <li key={item}>{item}</li>
                  ))}
                </ul>
              </div>
            )}
            <div className="citizen-action">
              <span>Contact: {card.contact}</span>
            </div>
            <button className="button" onClick={() => onNavigate('route')}>
              Safe route
            </button>
            <div className="citizen-action">
              {ackState.status !== 'done' && ackState.status !== 'queued' && (
                <button
                  type="button"
                  disabled={ackState.status === 'submitting'}
                  onClick={() => void handleAcknowledge()}
                >
                  {ackState.status === 'submitting' ? 'Submitting…' : 'I have evacuated'}
                </button>
              )}
              {ackState.status === 'error' && <p>Could not submit: {ackState.error}</p>}
              {ackState.status === 'queued' && (
                <p>Saved — offline. This will be sent automatically once the device is back online.</p>
              )}
              {ackState.status === 'done' && (
                <div>
                  <p>✓ Evacuation acknowledged</p>
                  <p>
                    Recorded as {ackState.event.kind} at {new Date(ackState.event.t).toLocaleString()}
                  </p>
                  <button type="button" onClick={() => openAuditTrail(card.alert_id)}>
                    View audit trail
                  </button>
                </div>
              )}
            </div>
          </section>
        ) : (
          <NoActiveAlert />
        ))}

      {route === 'route' &&
        (card ? (
          <section className="citizen-screen">
            <h1>Safe route</h1>
            <div style={{ height: '16rem' }}>
              <MapView routeGeometry={card.route?.geometry ?? null} />
            </div>
            {card.route ? (
              <>
                <h2>{card.route.shelter_name}</h2>
                <p>
                  {(card.route.distance_m / 1000).toFixed(1)} km · approximately{' '}
                  {card.route.est_walk_minutes} min
                </p>
              </>
            ) : (
              <NotBuilt
                task="TASK-CIT-ROUTE"
                what="A verified route has not been supplied for this alert."
                blocks="Routing engine and action-card route geometry"
              />
            )}
          </section>
        ) : (
          <NoActiveAlert />
        ))}

      {route === 'announcement' && (
        <section className="citizen-screen">
          <h1>Announcements</h1>
          {announcements.length === 0 ? (
            <NotBuilt
              task="TASK-CIT-ANNOUNCEMENT-FEED"
              what="No announcement has been sent yet."
              blocks="A DDMA officer sending an announcement from the Announce workspace"
            />
          ) : (
            <ul>
              {announcements.map((a) => (
                <li key={a.id} className={`citizen-alert ${a.stage.toLowerCase()}`}>
                  <span>{a.stage}</span>
                  <h2>{a.village_id}</h2>
                  <p>{a.message}</p>
                  <small>{new Date(a.issued_at).toLocaleString()}</small>
                </li>
              ))}
            </ul>
          )}
        </section>
      )}

      {route === 'report' && (
        <section className="citizen-screen">
          <h1>Report an incident</h1>
          <p className="muted">
            Reports are saved in this device's durable prototype queue. They are not marked sent
            until a server accepts them.
          </p>
          <label>
            Category
            <select value={category} onChange={(e) => setCategory(e.target.value as CitizenReportCategory)}>
              <option>Crack</option>
              <option>Blocked road</option>
              <option>Water seepage</option>
            </select>
          </label>
          <label>
            Optional note
            <textarea value={note} onChange={(e) => setNote(e.target.value)} placeholder="Describe what you can see" />
          </label>
          <button className="button secondary" disabled>
            Add photo · camera integration pending
          </button>
          <button className="button" onClick={saveReport}>
            Save report locally
          </button>
          {queued > 0 && (
            <p className="muted">
              {queued} report{queued === 1 ? '' : 's'} safely queued on this device.
            </p>
          )}
        </section>
      )}

      <div className="offline-status">
        {offline
          ? `○ Offline · ${queued} item${queued === 1 ? '' : 's'} queued`
          : queued
            ? `↻ Syncing boundary · ${queued} item${queued === 1 ? '' : 's'} queued`
            : '● Online & synced'}
      </div>

      <nav className="citizen-nav">
        {(['alert', 'route', 'announcement', 'report'] as const).map((item) => (
          <button key={item} className={route === item ? 'active' : ''} onClick={() => onNavigate(item)}>
            {item === 'alert'
              ? '⚠ Alert'
              : item === 'route'
                ? '⌁ Route'
                : item === 'announcement'
                  ? '📢 Announcements'
                  : '＋ Report'}
          </button>
        ))}
      </nav>
    </main>
  )
}

/** Ported from VillageView.tsx: when there is no LIVE action card for any village (the store is
 * empty — e.g. opened with no connectivity before hydrateFromOfflineCache resolves, or genuinely
 * no alert is active), fall back to the real shelter/contact info the last known action cards
 * actually referenced, read straight from IndexedDB. */
function NoActiveAlert() {
  const [shelters, setShelters] = useState<CachedShelter[]>([])
  const [contacts, setContacts] = useState<string[]>([])

  useEffect(() => {
    let cancelled = false
    void getCachedActionCards().then((cards) => {
      if (cancelled) return
      setShelters(deriveCachedShelters(cards))
      setContacts(deriveCachedEmergencyContacts(cards))
    })
    return () => {
      cancelled = true
    }
  }, [])

  return (
    <section className="citizen-screen">
      <p>No active alert for any village right now</p>
      <p className="muted">
        This screen shows the citizen-facing alert for a settlement that currently has an AI
        recommendation issued (ORANGE/RED). None is issued at the moment.
      </p>
      {(shelters.length > 0 || contacts.length > 0) && (
        <div>
          <p className="muted">From the last known alert (saved on this device)</p>
          {shelters.length > 0 && (
            <ul>
              {shelters.map((s) => (
                <li key={s.shelterId}>{s.shelterName}</li>
              ))}
            </ul>
          )}
          {contacts.length > 0 && (
            <ul>
              {contacts.map((c) => (
                <li key={c}>{c}</li>
              ))}
            </ul>
          )}
        </div>
      )}
    </section>
  )
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd frontend && npx vitest run src/components/CitizenApp.test.tsx`
Expected: PASS (6 tests)

- [ ] **Step 5: Delete the now-superseded `VillageView`**

```bash
git rm frontend/src/components/VillageView.tsx frontend/src/components/VillageView.test.tsx
```

- [ ] **Step 6: Run the full frontend suite to check for regressions**

Run: `cd frontend && npx vitest run`
Expected: PASS — no leftover import of `VillageView` anywhere (it had no route mounting it in
`App.tsx` prior to this task, so removing it should not break any other file)

- [ ] **Step 7: Commit**

```bash
git add frontend/src/components/CitizenApp.tsx frontend/src/components/CitizenApp.test.tsx
git commit -m "Merge VillageView's real alert/acknowledge/route content into CitizenApp; add the Announcement tab

VillageView.tsx (stage card, voice alert, offline map+route, real 'I have evacuated'
acknowledgment) had no route anywhere in the new shell — same orphaning this sub-project exists
to fix. Merged into CitizenApp's alert/route tabs rather than left duplicated alongside the
thinner pre-existing versions; VillageView.tsx retired as a separate component."
```

---

### Task 14: Frontend — final shell wiring, remounting orphaned components, retiring superseded files

**Files:**
- Modify: `frontend/src/components/ConsoleShell.tsx` (rewrite to the 5 flat Government routes)
- Modify: `frontend/src/App.tsx` (full route table + root-level modal mounts)
- Delete: `frontend/src/components/ConsoleWorkspaces.tsx` (superseded — Situation/Impact/
  Priority/Trust logic either has no home in the new IA per the approved spec, or was already
  ported: its `AiCommander` → Task 11's `CommanderWorkspace`, its `ActionComposer` →
  Task 10's `AnnounceWorkspace` via `DdmaConsole.tsx`'s equivalent, more complete flow)
- Delete: `frontend/src/components/DdmaConsole.tsx` and `frontend/src/components/DdmaConsole.test.tsx`
  (superseded by Task 10's `AnnounceWorkspace`, which absorbs its real Approve/Modify/Reject logic)
- Test: `frontend/src/App.test.tsx` (new)

**Interfaces:**
- Consumes: every workspace component from Tasks 8–13; `VillageDetailDrawer`, `AuditTrailView`,
  `CounterfactualScorecard`, `OnboardingOverlay`, `InstallPrompt` (all existing, untouched).
- Produces: the final route table — Government `/console/{dashboard,commander,whatif,audit,announce}`,
  Citizen `/citizen/{alert,route,announcement,report}`, `/` → `/console/dashboard`.

- [ ] **Step 1: Confirm nothing unique is lost from the two files being deleted**

Read `frontend/src/components/DdmaConsole.tsx` once more against `AnnounceWorkspace.tsx` (Task
10): confirm every piece of real logic — `submit()`/`decide()`'s Approve/Modify/Reject calls,
`MeshPropagationVisual` mount, `recommendationContext` usage, the human-in-the-loop banner — has
an equivalent in `AnnounceWorkspace.tsx`. It does (Task 10 was written by porting this file
directly). Read `frontend/src/components/ConsoleWorkspaces.tsx` once more: confirm its
`SituationWorkspace`/`ImpactWorkspace`/`PriorityWorkspace`/`TrustWorkspace` exports have no
current consumer once this task's `App.tsx` rewrite lands (per the approved spec §6, their
content is deferred to sub-project 2's Dashboard redesign, not silently dropped — this is
tracked there, not invented here) and that `AiCommander`/`ActionComposer` are superseded as
described above. This is a read-only confirmation step — no code changes.

- [ ] **Step 2: Write the failing App-level test**

```tsx
// frontend/src/App.test.tsx
import { render, screen } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'

vi.mock('maplibre-gl', () => {
  class FakeMap {
    constructor(_opts: unknown) {}
    on(event: string, arg2: unknown, arg3?: unknown) {
      if (event === 'load' && typeof arg2 === 'function' && arg3 === undefined) arg2()
      return this
    }
    once(event: string, cb: () => void) {
      if (event === 'load') cb()
      return this
    }
    addSource() {
      return this
    }
    addLayer() {
      return this
    }
    getSource() {
      return { setData: vi.fn() }
    }
    getCanvas() {
      return { style: {} }
    }
    isStyleLoaded() {
      return true
    }
    setCenter() {
      return this
    }
    remove() {}
  }
  return { MapLibreMap: FakeMap }
})

vi.mock('./lib/ws', () => ({ connectTickSocket: () => () => {} }))
vi.mock('./lib/api', () => ({
  api: {
    getState: () => Promise.resolve({ mode: 'live', scenario_id: null, scenario_time: null, speed_factor: 1, paused: false }),
    getScenarios: () => Promise.resolve([]),
    getAoi: () => Promise.resolve({ id: 'aizawl', name: 'Aizawl', center: { lat: 0, lon: 0 } }),
  },
}))

import App from './App'

beforeEach(() => {
  history.pushState({}, '', '/')
})

describe('App routing', () => {
  it('redirects / to the Dashboard workspace', () => {
    render(<App />)
    expect(screen.getByText('Run Case Study')).toBeInTheDocument()
  })

  it('renders the 5 Government nav items', () => {
    render(<App />)
    for (const label of ['Dashboard', 'AI Emergency Commander', 'What-if Simulator', 'Audit', 'Announce']) {
      expect(screen.getByText(label)).toBeInTheDocument()
    }
  })

  it('navigates to the Announce workspace', () => {
    render(<App />)
    screen.getByText('Announce').click()
    expect(screen.getByText('Officer ID')).toBeInTheDocument()
  })

  it('renders the Citizen app on a /citizen path', () => {
    history.pushState({}, '', '/citizen/alert')
    render(<App />)
    expect(screen.getByText(/Announcements/)).toBeInTheDocument()
  })
})
```

- [ ] **Step 3: Run test to verify it fails**

Run: `cd frontend && npx vitest run src/App.test.tsx`
Expected: FAIL — current `App.tsx` still uses the old `ConsoleRoute` type/6-workspace nav

- [ ] **Step 4: Rewrite `ConsoleShell.tsx`**

Replace the full contents of `frontend/src/components/ConsoleShell.tsx`:

```tsx
import type { ReactNode } from 'react'
import { useTickStore } from '../store/useTickStore'

export type GovernmentRoute = 'dashboard' | 'commander' | 'whatif' | 'audit' | 'announce'

const NAV: Array<[GovernmentRoute, string]> = [
  ['dashboard', 'Dashboard'],
  ['commander', 'AI Emergency Commander'],
  ['whatif', 'What-if Simulator'],
  ['audit', 'Audit'],
  ['announce', 'Announce'],
]

/** The Government shell — 5 flat top-level workspaces (SIH26001 master frontend prompt §3),
 * replacing the prior 6-workspace Situation/Impact/Priority/Commander/Audit/Trust nav. The map
 * is NOT a shell-level singleton in this IA (only Dashboard renders MapView) — sub-project 2
 * decides whether that needs to change once the heatmap/layers work lands. */
export function ConsoleShell({
  route,
  onRoute,
  children,
}: {
  route: GovernmentRoute
  onRoute: (route: GovernmentRoute) => void
  children: ReactNode
}) {
  const aoi = useTickStore((s) => s.aoi)
  const modeState = useTickStore((s) => s.modeState)
  const latestTick = useTickStore((s) => s.latestTick)
  const mode = latestTick?.mode ?? modeState?.mode ?? 'live'
  const tick = latestTick?.t ?? modeState?.scenario_time

  return (
    <main className="console-shell">
      <header className="console-topbar">
        <button className="brand" onClick={() => onRoute('dashboard')} aria-label="NIRANTAR Dashboard">
          <span className="brand-mark">N</span>
          <span>
            NIRANTAR
            <small>Decision & Dissemination</small>
          </span>
        </button>
        <span className={`mode-chip ${mode}`}>{mode === 'replay' ? 'REPLAY · RECONSTRUCTED' : 'LIVE'}</span>
        <div className="top-meta">
          <span>AOI</span>
          <strong>{aoi?.name ?? 'Aizawl'}</strong>
        </div>
        <div className="top-meta">
          <span>Current tick</span>
          <strong>{tick ? new Date(tick).toLocaleString() : 'Awaiting feed'}</strong>
        </div>
        <a className="role-switch" href="/citizen/alert">
          Citizen demo ↗
        </a>
      </header>
      <nav className="primary-nav" aria-label="Government workspaces">
        {NAV.map(([key, label]) => (
          <button key={key} className={route === key ? 'active' : ''} onClick={() => onRoute(key)}>
            {label}
          </button>
        ))}
      </nav>
      {children}
      <footer className="provenance">
        MODE: {mode.toUpperCase()}
        <br />
        TICK: {tick ? new Date(tick).toLocaleTimeString() : '—'}
        <br />
        MODEL: {latestTick?.cell_risks[0]?.model_version ?? 'Awaiting model metadata'}
        <br />
        RECONSTRUCTED: {latestTick?.is_reconstructed ? 'YES' : 'NO'}
      </footer>
    </main>
  )
}
```

- [ ] **Step 5: Rewrite `App.tsx`**

Replace the full contents of `frontend/src/App.tsx`:

```tsx
import { useEffect, useState } from 'react'
import { AnnounceWorkspace } from './components/AnnounceWorkspace'
import { AuditTrailView } from './components/AuditTrailView'
import { AuditWorkspace } from './components/AuditWorkspace'
import { CitizenApp, type CitizenRoute } from './components/CitizenApp'
import { CommanderWorkspace } from './components/CommanderWorkspace'
import { ConsoleShell, type GovernmentRoute } from './components/ConsoleShell'
import { CounterfactualScorecard } from './components/CounterfactualScorecard'
import { DashboardWorkspace } from './components/DashboardWorkspace'
import { InstallPrompt } from './components/InstallPrompt'
import { OnboardingOverlay } from './components/OnboardingOverlay'
import { VillageDetailDrawer } from './components/VillageDetailDrawer'
import { WhatIfWorkspace } from './components/WhatIfWorkspace'
import { attachAckQueueAutoSync, syncQueuedAcknowledgements } from './lib/ackQueue'
import { useTickStore } from './store/useTickStore'

const AOI_ID = 'aizawl'

const GOVERNMENT_ROUTES: GovernmentRoute[] = ['dashboard', 'commander', 'whatif', 'audit', 'announce']
const CITIZEN_ROUTES: CitizenRoute[] = ['alert', 'route', 'announcement', 'report']

type Route = `/console/${GovernmentRoute}` | `/citizen/${CitizenRoute}`

function routeFromPath(path: string): Route {
  const citizenMatch = CITIZEN_ROUTES.find((r) => path.startsWith(`/citizen/${r}`))
  if (citizenMatch) return `/citizen/${citizenMatch}`
  const govMatch = GOVERNMENT_ROUTES.find((r) => path.startsWith(`/console/${r}`))
  return govMatch ? `/console/${govMatch}` : '/console/dashboard'
}

function App() {
  const [route, setRoute] = useState<Route>(() => routeFromPath(location.pathname))
  const loadInitial = useTickStore((s) => s.loadInitial)
  const connect = useTickStore((s) => s.connect)
  const disconnect = useTickStore((s) => s.disconnect)
  const hydrate = useTickStore((s) => s.hydrateFromOfflineCache)
  const hydrateCitizenReports = useTickStore((s) => s.hydrateCitizenReports)

  useEffect(() => {
    void hydrate()
    hydrateCitizenReports()
    void loadInitial(AOI_ID)
    connect()
    attachAckQueueAutoSync()
    void syncQueuedAcknowledgements()
    return () => disconnect()
  }, [hydrate, hydrateCitizenReports, loadInitial, connect, disconnect])

  useEffect(() => {
    const onPop = () => setRoute(routeFromPath(location.pathname))
    addEventListener('popstate', onPop)
    return () => removeEventListener('popstate', onPop)
  }, [])

  const navigate = (next: Route) => {
    if (location.pathname !== next) history.pushState({}, '', next)
    setRoute(next)
    window.scrollTo(0, 0)
  }

  if (route.startsWith('/citizen/')) {
    const citizenRoute = route.replace('/citizen/', '') as CitizenRoute
    return (
      <>
        <CitizenApp route={citizenRoute} onNavigate={(r) => navigate(`/citizen/${r}`)} />
        <OnboardingOverlay />
        <InstallPrompt />
      </>
    )
  }

  const govRoute = route.replace('/console/', '') as GovernmentRoute
  return (
    <>
      <ConsoleShell route={govRoute} onRoute={(r) => navigate(`/console/${r}`)}>
        {govRoute === 'dashboard' && <DashboardWorkspace />}
        {govRoute === 'commander' && (
          <CommanderWorkspace
            onAnnounce={() => navigate('/console/announce')}
            onWhatIf={() => navigate('/console/whatif')}
          />
        )}
        {govRoute === 'whatif' && <WhatIfWorkspace />}
        {govRoute === 'audit' && <AuditWorkspace />}
        {govRoute === 'announce' && <AnnounceWorkspace />}
      </ConsoleShell>
      <VillageDetailDrawer />
      <AuditTrailView />
      <CounterfactualScorecard />
      <OnboardingOverlay />
      <InstallPrompt />
    </>
  )
}

export default App
```

- [ ] **Step 6: Delete the superseded files**

```bash
git rm frontend/src/components/ConsoleWorkspaces.tsx
git rm frontend/src/components/DdmaConsole.tsx frontend/src/components/DdmaConsole.test.tsx
```

- [ ] **Step 7: Run test to verify it passes**

Run: `cd frontend && npx vitest run src/App.test.tsx`
Expected: PASS (4 tests)

- [ ] **Step 8: Run the full frontend test suite and type-check**

Run: `cd frontend && npx vitest run && npx tsc --noEmit`
Expected: PASS, no leftover references to the deleted files or the old `ConsoleRoute` type

- [ ] **Step 9: Commit**

```bash
git add frontend/src/components/ConsoleShell.tsx frontend/src/App.tsx frontend/src/App.test.tsx
git commit -m "Wire the final 5-item Government / 4-item Citizen shell; retire superseded workspaces

Deletes ConsoleWorkspaces.tsx (superseded by Dashboard/Commander/WhatIf/Audit/Announce
workspaces) and DdmaConsole.tsx (superseded by AnnounceWorkspace, which absorbs its real
Approve/Modify/Reject flow). Fixes the regression where VillageDetailDrawer/AuditTrailView/
CounterfactualScorecard/OnboardingOverlay/InstallPrompt had been dropped from App.tsx."
```

---

## Final verification (run after Task 14)

```bash
cd backend && pytest -v
cd ../frontend && npx vitest run && npx tsc --noEmit
```

Both must pass cleanly. This closes out Sub-project 1 (Foundation) of the 9-part frontend rebuild
— Sub-project 2 (Dashboard: heatmap, working layer toggles, Risk Intelligence Panel) is speced
and planned separately, next.
