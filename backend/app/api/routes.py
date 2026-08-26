"""REST routers (BUILD_PLAN.md task 0.11): GET /api/aoi/{id}, GET /api/scenarios,
POST /api/replay/start, POST /api/replay/stop, GET /api/state.

BUILD_PLAN.md task 3.6(b) adds GET /api/audit/{alert_id}. This session's "small connected gap"
adds POST /api/replay/pause|resume|speed — the REST wiring `core/mode.py`'s already-real
pause()/resume()/set_speed() and `ingest/replay/scenario_source.py`'s already-real
ScenarioSource.pause()/resume()/set_speed() (task 4.7) were left waiting for, per task 4.9's own
frontend `ReplayControlBar.tsx` code-comment note (its Play/Pause and speed controls render real
backend state but stay `disabled` until this exists).
"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

from app.config import AOIS
from app.core.mode import ModeError
from app.ingest.factory import SCENARIOS_DIR, UnknownScenarioError, load_scenario_or_raise
from app.schemas.audit import AuditEvent
from app.schemas.mode import ModeState

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
