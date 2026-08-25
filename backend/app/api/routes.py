"""REST routers (BUILD_PLAN.md task 0.11): GET /api/aoi/{id}, GET /api/scenarios,
POST /api/replay/start, POST /api/replay/stop, GET /api/state.
"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

from app.ingest.factory import SCENARIOS_DIR, UnknownScenarioError, load_scenario_or_raise
from app.schemas.mode import ModeState

router = APIRouter(prefix="/api")

# Phase 0 stub AOI registry. Coordinates are Aizawl's public city-center lat/lon — not a claimed
# analysis-grid boundary. Real AOI boundaries come from scripts/build_grid.py (BUILD_PLAN.md
# task 1.2) in Phase 1.
_STUB_AOIS: dict[str, dict] = {
    "aizawl": {
        "id": "aizawl",
        "name": "Aizawl, Mizoram",
        "center": {"lat": 23.7307, "lon": 92.7173},
        "note": "Phase 0 stub — approximate city center, not a real analysis-grid boundary.",
    }
}


def _app_state(request: Request):
    return request.app.state.app_state


@router.get("/state")
async def get_state(request: Request) -> ModeState:
    return _app_state(request).mode.state


@router.get("/aoi/{aoi_id}")
async def get_aoi(aoi_id: str) -> dict:
    aoi = _STUB_AOIS.get(aoi_id)
    if aoi is None:
        raise HTTPException(status_code=404, detail=f"unknown AOI {aoi_id!r}")
    return aoi


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
