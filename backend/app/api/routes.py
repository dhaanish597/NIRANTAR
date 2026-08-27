"""REST routers (BUILD_PLAN.md task 0.11): GET /api/aoi/{id}, GET /api/scenarios,
POST /api/replay/start, POST /api/replay/stop, GET /api/state.

BUILD_PLAN.md task 3.6(b) adds GET /api/audit/{alert_id}. This session's "small connected gap"
adds POST /api/replay/pause|resume|speed — the REST wiring `core/mode.py`'s already-real
pause()/resume()/set_speed() and `ingest/replay/scenario_source.py`'s already-real
ScenarioSource.pause()/resume()/set_speed() (task 4.7) were left waiting for, per task 4.9's own
frontend `ReplayControlBar.tsx` code-comment note (its Play/Pause and speed controls render real
backend state but stay `disabled` until this exists).

BUILD_PLAN.md tasks 3.7/3.10 add POST /api/ddma/decide and POST /api/village/acknowledge — see
each route's own docstring below for the scope ruling (option (a) from each task's own choice:
real backend wiring over `audit/producers.py`'s already-real, already-tested producer functions,
rather than an honestly-disabled frontend stub).

BUILD_PLAN.md task 5.8 adds POST /api/whatif/simulate — see that route's own docstring and
`api/whatif.py`'s module docstring for the throwaway-Pipeline isolation and synthetic-frame
rulings (real cell_ids, uniform rainfall, no fabricated antecedent wetness).
"""
from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

from app.api.announcements import AnnouncementRequest, create_announcement, list_announcements
from app.api.whatif import WhatIfRequest, WhatIfResult, simulate_whatif
from app.audit.producers import record_ddma_decision, record_village_acknowledged
from app.config import AOIS
from app.config import get_aoi as get_aoi_config  # aliased: this module's OWN `/api/aoi/{id}`
# route below is itself named `get_aoi` — importing app.config's function under its real name
# would silently shadow that route function at module scope.
from app.core.bus import Topic
from app.core.clock import LiveClock
from app.core.mode import ModeError
from app.ingest.factory import SCENARIOS_DIR, UnknownScenarioError, load_scenario_or_raise
from app.pipeline import Pipeline
from app.schemas.announcement import Announcement
from app.schemas.audit import AuditEvent
from app.schemas.decision import ActionCard
from app.schemas.mode import ModeState, RunMode

router = APIRouter(prefix="/api")


def _app_state(request: Request):
    return request.app.state.app_state


@router.get("/state")
async def get_state(request: Request) -> ModeState:
    return _app_state(request).mode.state


@router.get("/aoi/{aoi_id}")
async def get_aoi(aoi_id: str) -> dict:
    aoi = AOIS.get(aoi_id)
    if aoi is None:
        raise HTTPException(status_code=404, detail=f"unknown AOI {aoi_id!r}")
    return {
        "id": aoi.id,
        "name": aoi.name,
        "center": {"lat": aoi.center_lat, "lon": aoi.center_lon},
        "bbox": list(aoi.bbox),
    }


@router.get("/scenarios")
async def list_scenarios() -> list[dict]:
    scenarios = []
    for path in sorted(SCENARIOS_DIR.glob("*.json")):
        scenario = load_scenario_or_raise(path.stem)
        scenarios.append(
            {
                "id": scenario.id,
                "aoi_id": scenario.aoi_id,
                "held_out_of_training": scenario.held_out_of_training,
                "frame_count": len(scenario.frames),
                "start": scenario.clock.start,
                "end": scenario.clock.end,
                "provenance": scenario.provenance,
            }
        )
    return scenarios


class ReplayStartRequest(BaseModel):
    scenario_id: str


@router.post("/replay/start")
async def start_replay(body: ReplayStartRequest, request: Request) -> ModeState:
    app_state = _app_state(request)
    try:
        await app_state.start_replay(body.scenario_id)
    except UnknownScenarioError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return app_state.mode.state


@router.post("/replay/stop")
async def stop_replay(request: Request) -> ModeState:
    app_state = _app_state(request)
    await app_state.stop_replay()
    return app_state.mode.state


@router.post("/replay/pause")
async def pause_replay(request: Request) -> ModeState:
    app_state = _app_state(request)
    try:
        await app_state.pause_replay()
    except ModeError as exc:
        # Not currently in REPLAY — a client-side state error (there is nothing to pause), not a
        # server error. 409 Conflict: the request is well-formed but conflicts with current state.
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return app_state.mode.state


@router.post("/replay/resume")
async def resume_replay(request: Request) -> ModeState:
    app_state = _app_state(request)
    try:
        await app_state.resume_replay()
    except ModeError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return app_state.mode.state


class ReplaySpeedRequest(BaseModel):
    speed_factor: float


@router.post("/replay/speed")
async def set_replay_speed(body: ReplaySpeedRequest, request: Request) -> ModeState:
    app_state = _app_state(request)
    try:
        await app_state.set_replay_speed(body.speed_factor)
    except ModeError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except ValueError as exc:
        # speed_factor <= 0 — a malformed request body value, not a state conflict.
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return app_state.mode.state


@router.get("/audit/{alert_id}")
async def get_audit_trail(alert_id: str, request: Request) -> list[AuditEvent]:
    """The full hash-chained event history for one `alert_id` (BUILD_PLAN.md task 3.6(b)) —
    whatever `AuditEvent`s the currently-running `Pipeline`'s `AuditLog` has actually recorded
    under that id, in append order (`AuditLog.for_alert`, already real — audit/log.py).

    Returns an empty list (200), not a 404, for an `alert_id` with no matching events: unlike
    `/api/aoi/{id}`, `alert_id` is not drawn from a fixed, enumerable registry (`AOIS`) — it is a
    freely-formed string produced by whichever pipeline stage issued it (`pipeline.py`'s own
    `tick-{aoi}-{t}`, `decision/escalation.py`'s `esc-{entity_id}`, `decision/action_card.py`'s
    `card-{village}-{t}`, ...), so "no events yet" (e.g. a DDMA console polling an alert the
    instant after it was issued) is a legitimate, non-error state to return, not a client mistake.

    Note (documented rather than silently implied): `decision/escalation.py`'s `ESCALATED`
    producer and `audit/producers.py`'s `DDMA_APPROVED`/`DISSEMINATED` producers (BUILD_PLAN.md
    task 3.6(a), this session) are real and independently tested, but are not yet CALLED from
    `pipeline.py` — wiring producers into the live pipeline is a separate, later task (this
    session's brief is explicit that it is out of scope). Until that wiring lands, this endpoint
    will only ever show `AI_FLAGGED` events for a live tick's own alert id
    (`tick-{aoi_id}-{t.isoformat()}`) — a real, honest reflection of what the running pipeline
    actually produces today, not a stubbed/fabricated fuller chain.
    """
    app_state = _app_state(request)
    return app_state.pipeline.audit_log.for_alert(alert_id)


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


class DdmaDecisionRequest(BaseModel):
    action_card: ActionCard
    officer_id: str
    decision: Literal["approved", "modified", "rejected"] = "approved"
    notes: str = ""


@router.post("/ddma/decide")
async def ddma_decide(body: DdmaDecisionRequest, request: Request) -> AuditEvent:
    """BUILD_PLAN.md task 3.7's DDMA Console: the human-in-the-loop Approve/Modify/Reject action.

    **Scope ruling (task 3.7 offered two honest choices; this is choice (a)):**
    `audit/producers.py::record_ddma_decision` (task 3.6(a)) already did the real work of
    building a correctly-typed, correctly-chained `DDMA_APPROVED`/`STOOD_DOWN` `AuditEvent` — it
    was callable but not yet called from anywhere. This route is the small, well-scoped REST
    wiring task 3.7 anticipated ("check `api/routes.py`'s existing patterns for how routes reach
    `AppState`/`audit_log`"), not a reimplementation.

    The full `ActionCard` being decided is accepted IN THE REQUEST BODY rather than looked up
    server-side by `alert_id`: this codebase has no server-side `ActionCard` store keyed by
    `alert_id` anywhere (`TickResult.new_action_cards` is a broadcast-only, fire-and-forget
    WebSocket payload — `pipeline.py` does not retain past ticks' cards). The frontend already
    holds the real `ActionCard` it received over `/ws/ticks` (`useTickStore.actionCards`), so
    round-tripping it here is the honest option — the alternative (inventing a server-side lookup
    against data that isn't persisted) would be worse, not simpler.

    `t=LiveClock().now()` (not `clock.now()` off whichever `Clock` is driving the current tick
    loop): a DDMA officer's approval is a genuine real-world action happening at real wall-clock
    time, in BOTH LIVE and REPLAY mode — a human clicking "Approve" while watching an accelerated
    replay did not act at 60x speed. `LiveClock` is CLAUDE.md rule 14's one designated escape
    hatch (`core/clock.py`), the same pattern `ingest/live/imerg.py`'s CLI entry point already
    uses for an out-of-pipeline, real-time action.
    """
    app_state = _app_state(request)
    return record_ddma_decision(
        app_state.pipeline.audit_log,
        action_card=body.action_card,
        officer_id=body.officer_id,
        t=LiveClock().now(),
        decision=body.decision,
        notes=body.notes,
    )


class VillageAcknowledgeRequest(BaseModel):
    alert_id: str
    village_id: str


@router.post("/village/acknowledge")
async def village_acknowledge(body: VillageAcknowledgeRequest, request: Request) -> AuditEvent:
    """BUILD_PLAN.md task 3.10's Village View "I have evacuated" button.

    **Scope ruling (task 3.10 offered the same two honest choices as 3.7; this is choice (a)):**
    `audit/producers.py::record_village_acknowledged` (added this session) does the real work;
    this route is the REST wiring, following the exact same shape as `ddma_decide` above.
    `t=LiveClock().now()` for the same reason: a citizen tapping "I have evacuated" is a genuine
    real-world action at real wall-clock time, not scenario time.
    """
    app_state = _app_state(request)
    return record_village_acknowledged(
        app_state.pipeline.audit_log,
        alert_id=body.alert_id,
        village_id=body.village_id,
        t=LiveClock().now(),
    )


@router.post("/whatif/simulate", response_model_exclude_none=True)
async def whatif_simulate(body: WhatIfRequest) -> WhatIfResult:
    """BUILD_PLAN.md task 5.8 — the what-if rainfall simulator: DDMA PRE-POSITIONING SUPPORT, not
    a real alert. "A rainfall slider ('simulate 250 mm over 12 h') that re-runs the pipeline on
    synthetic input and shows the resulting failure distribution, road severance and isolation
    cascade."

    Deliberately takes NO `Request`/`AppState` parameter — unlike `ddma_decide`/
    `village_acknowledge` above, this must NOT touch `app_state.pipeline` (the real, live audit
    hash chain) or `app_state.bus` (which would otherwise push a synthetic tick out over
    `/ws/ticks` as if it were real). A brand-new, throwaway `Pipeline()` is constructed and
    discarded for this one call — its own throwaway `AuditLog`/`EscalationStateMachine` are never
    referenced again once the response is returned, so nothing this produces is ever visible via
    `GET /api/audit/{alert_id}` or any live tick stream. See `api/whatif.py`'s own module
    docstring for the synthetic-frame construction rulings (real cell_ids, uniform rainfall, no
    fabricated antecedent wetness).

    `aoi_id` not registered / no static terrain grid built for it yet -> 404 (not a silent
    risk-only degrade, unlike `pipeline.py`'s own ruling 7 for a live/replay tick — a DDMA officer
    staring at an empty what-if result for an AOI that simply has no data would be misleading;
    failing loudly here is the honest choice for an on-demand exploratory tool).
    """
    try:
        get_aoi_config(body.aoi_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    t = LiveClock().now()
    try:
        return simulate_whatif(body, t=t)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
