"""Multiplex Knowledge Graph, Neuro-Symbolic GraphRAG Copilot, Sarvam AI & CoE-AWRDS API Router."""
from __future__ import annotations

import base64
from pathlib import Path
from typing import Any, Literal

try:
    from fastapi import APIRouter, HTTPException
    from pydantic import BaseModel
except ImportError:  # pragma: no cover - stdlib fallback when FastAPI/Pydantic are absent
    class APIRouter:  # type: ignore[no-redef]
        def __init__(self, **kwargs: Any) -> None:
            self.routes: list[Any] = []

        def get(self, *_args: Any, **_kwargs: Any):
            return lambda fn: fn

        def post(self, *_args: Any, **_kwargs: Any):
            return lambda fn: fn

    class HTTPException(Exception):  # type: ignore[no-redef]
        def __init__(self, status_code: int, detail: str) -> None:
            super().__init__(detail)
            self.status_code = status_code
            self.detail = detail

    from app.config import BaseModel  # type: ignore[assignment]

from app.agents.orchestrator import OrchestratorAgent
from app.config import AOIS
from app.graph.cascade_engine import compute_cascading_blast_radius
from app.graph.gds_chokepoints import compute_risk_budgeted_astar_route, discover_top_chokepoints
from app.graph.neo4j_client import GraphStoreManager
from app.robotics.coe_awrds import CoeAwrdsRoboticsCoordinator
from app.sarvam.stt_saaras import SarvamSaarasSttService
from app.sarvam.tts_bulbul import SarvamBulbulTtsService
from app.sarvam.vision_ocr import SarvamVisionOcrService


REPO_ROOT = Path(__file__).resolve().parents[3]
router = APIRouter(prefix="/api")

_GRAPH_STORE: GraphStoreManager | None = None


def get_multiplex_store() -> GraphStoreManager:
    global _GRAPH_STORE
    if _GRAPH_STORE is None:
        _GRAPH_STORE = GraphStoreManager.from_seed_bundle(REPO_ROOT / "data" / "seed_bundle")
    return _GRAPH_STORE


class CascadeRequest(BaseModel):
    trigger_node_id: str = "FZ-CHENNAI-01"
    max_hops: int = 3


class CopilotQueryRequest(BaseModel):
    aoi_id: str = "chennai"
    query: str
    trigger_node_id: str = "FZ-CHENNAI-01"


class SarvamSttRequest(BaseModel):
    aoi_id: str = "chennai"
    language_hint: str = "ta-IN"
    audio_base64: str = ""
    fixture_id: str | None = None
    prefer_live_api: bool = True


class SarvamVisionRequest(BaseModel):
    shelter_node_id: str = "SHEL-CHENNAI-01"
    image_base64: str = ""
    fixture_id: str | None = None
    prefer_live_api: bool = True


class SarvamTtsRequest(BaseModel):
    text: str
    language_code: str = "ta-IN"
    prefer_live_api: bool = True


class RoboticsMissionRequest(BaseModel):
    aoi_id: str = "chennai"
    target_node_id: str = "CUL-CHENNAI-01"
    platform_type: Literal["UAV_DRONE", "USV_SONAR"] = "USV_SONAR"


class RoboticsSdgRequest(BaseModel):
    aoi_id: str = "chennai"
    trigger_node_id: str = "FZ-CHENNAI-01"
    mitigated_node_ids: list[str] = []


@router.get("/aoi/{aoi_id}/grid")
async def get_aoi_dynamic_grid(aoi_id: str) -> dict[str, Any]:
    """Returns dynamic spatial grid cells & multiplex node positions for an AOI (no hardcoded frontend lookup table)."""
    if aoi_id not in AOIS:
        raise HTTPException(status_code=404, detail=f"Unknown AOI {aoi_id!r}")
    store = get_multiplex_store()
    nodes = store.all_nodes(aoi_id=aoi_id)
    cells = [
        {
            "cell_id": n["id"],
            "label": n.get("label", "Node"),
            "name": n.get("name", n["id"]),
            "lat": float(n.get("lat", AOIS[aoi_id].center_lat)),
            "lon": float(n.get("lon", AOIS[aoi_id].center_lon)),
            "elev_m": float(n.get("elev_m", 10.0)),
        }
        for n in nodes
        if "lat" in n and "lon" in n
    ]
    return {"aoi_id": aoi_id, "cell_count": len(cells), "cells": cells}


@router.post("/multiplex/cascade")
async def post_multiplex_cascade(body: CascadeRequest) -> dict[str, Any]:
    store = get_multiplex_store()
    res = compute_cascading_blast_radius(store, trigger_node_id=body.trigger_node_id, max_hops=body.max_hops)
    return res.model_dump()


@router.get("/multiplex/chokepoints/{aoi_id}")
async def get_multiplex_chokepoints(aoi_id: str, top_k: int = 5) -> dict[str, Any]:
    store = get_multiplex_store()
    chokepoints = discover_top_chokepoints(store, aoi_id=aoi_id, top_k=top_k)
    return {
        "aoi_id": aoi_id,
        "chokepoints": [cp.model_dump() for cp in chokepoints],
    }


@router.get("/multiplex/route")
async def get_multiplex_route(
    source_osmid: str = "OSM-CHENNAI-001",
    target_osmid: str = "OSM-CHENNAI-017",
    vehicle_clearance_m: float = 0.45,
) -> dict[str, Any]:
    store = get_multiplex_store()
    route = compute_risk_budgeted_astar_route(
        store,
        source_osmid=source_osmid,
        target_osmid=target_osmid,
        vehicle_clearance_m=vehicle_clearance_m,
    )
    return route.model_dump()


@router.post("/multiplex/copilot")
async def post_multiplex_copilot(body: CopilotQueryRequest) -> dict[str, Any]:
    store = get_multiplex_store()
    agent = OrchestratorAgent(store)
    result = await agent.run_commander_investigation(
        query=body.query,
        aoi_id=body.aoi_id,
    )
    return result.model_dump()


@router.post("/multiplex/sarvam/stt")
async def post_sarvam_stt(body: SarvamSttRequest) -> dict[str, Any]:
    stt = SarvamSaarasSttService()
    wav_path = REPO_ROOT / "data" / "seed_bundle" / "fixtures" / "velachery_substation_spark.wav"
    raw_bytes = base64.b64decode(body.audio_base64) if body.audio_base64 else wav_path.read_bytes()
    res = stt.transcribe_distress_audio(
        audio_bytes=raw_bytes,
        aoi_id=body.aoi_id,
        language_hint=body.language_hint,
        fixture_id=body.fixture_id,
        prefer_live_api=body.prefer_live_api,
    )
    return res.model_dump()


@router.post("/multiplex/sarvam/vision")
async def post_sarvam_vision(body: SarvamVisionRequest) -> dict[str, Any]:
    store = get_multiplex_store()
    vision = SarvamVisionOcrService(store)
    raw_bytes = base64.b64decode(body.image_base64) if body.image_base64 else b"JPEG_FIXTURE_BYTES"
    res = vision.extract_shelter_register(
        image_bytes=raw_bytes,
        shelter_node_id=body.shelter_node_id,
        fixture_id=body.fixture_id,
        prefer_live_api=body.prefer_live_api,
    )
    return res.model_dump()


@router.post("/multiplex/sarvam/tts")
async def post_sarvam_tts(body: SarvamTtsRequest) -> dict[str, Any]:
    tts = SarvamBulbulTtsService()
    res = tts.synthesize_alert(
        text=body.text,
        language_code=body.language_code,
        prefer_live_api=body.prefer_live_api,
    )
    return res.model_dump()


@router.post("/multiplex/robotics/mission")
async def post_robotics_mission(body: RoboticsMissionRequest) -> dict[str, Any]:
    store = get_multiplex_store()
    coord = CoeAwrdsRoboticsCoordinator(store)
    mission = coord.generate_uav_usv_mission_order(
        aoi_id=body.aoi_id,
        target_node_id=body.target_node_id,
        platform_type=body.platform_type,
    )
    return mission.model_dump()


@router.post("/multiplex/robotics/sdg")
async def post_robotics_sdg(body: RoboticsSdgRequest) -> dict[str, Any]:
    store = get_multiplex_store()
    coord = CoeAwrdsRoboticsCoordinator(store)
    scorecard = coord.compute_sdg_resilience_metrics(
        aoi_id=body.aoi_id,
        trigger_node_id=body.trigger_node_id,
        mitigated_node_ids=body.mitigated_node_ids,
    )
    return scorecard.model_dump()
