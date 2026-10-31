"""End-to-End Verification of All NIRANTAR 2.0 Features, Multi-AOI Graph Resolution & Live API Keys (`NVIDIA_API_KEY` & `SARVAM_API_KEY`).

Run from `/Users/dhaanish/Documents/NIRANTAR`:
    PYTHONPATH=.:backend /usr/bin/python3 scripts/verify_live_apis.py
"""
from __future__ import annotations

import asyncio
import json
from typing import Any

from app.api.multiplex import (
    CascadeRequest,
    CopilotQueryRequest,
    RoboticsMissionRequest,
    RoboticsSdgRequest,
    SarvamSttRequest,
    SarvamTtsRequest,
    SarvamVisionRequest,
    get_aoi_dynamic_grid,
    get_multiplex_chokepoints,
    get_multiplex_route,
    post_multiplex_cascade,
    post_multiplex_copilot,
    post_robotics_mission,
    post_robotics_sdg,
    post_sarvam_stt,
    post_sarvam_tts,
    post_sarvam_vision,
)
from app.config import NVIDIA_API_KEY, SARVAM_API_KEY


async def verify_all_features_and_aois() -> dict[str, Any]:
    results: dict[str, Any] = {
        "env_keys_loaded": {
            "NVIDIA_API_KEY_present": bool(NVIDIA_API_KEY and NVIDIA_API_KEY.startswith("nvapi-")),
            "SARVAM_API_KEY_present": bool(SARVAM_API_KEY and SARVAM_API_KEY.startswith("sk_")),
        },
        "aois_verified": {},
    }

    for aoi_id, trigger_id in (("chennai", "FZ-CHENNAI-01"), ("wayanad", "FZ-WAYANAD-01"), ("aizawl", "FZ-AIZAWL-01")):
        grid = await get_aoi_dynamic_grid(aoi_id)
        cascade = await post_multiplex_cascade(CascadeRequest(trigger_node_id=trigger_id, max_hops=3))
        chokepoints = await get_multiplex_chokepoints(aoi_id, top_k=3)
        route = await get_multiplex_route(
            source_osmid=f"OSM-{aoi_id.upper()}-001",
            target_osmid=f"OSM-{aoi_id.upper()}-017",
            vehicle_clearance_m=0.45,
        )
        copilot = await post_multiplex_copilot(
            CopilotQueryRequest(
                aoi_id=aoi_id,
                query=f"Analyze 3-hop cascading infrastructure failure in {aoi_id} and recommend actions.",
                trigger_node_id=trigger_id,
            )
        )
        top_cp_id = chokepoints["chokepoints"][0]["node_id"]
        mission = await post_robotics_mission(
            RoboticsMissionRequest(aoi_id=aoi_id, target_node_id=top_cp_id, platform_type="USV_SONAR")
        )
        sdg = await post_robotics_sdg(
            RoboticsSdgRequest(aoi_id=aoi_id, trigger_node_id=trigger_id, mitigated_node_ids=[top_cp_id])
        )
        results["aois_verified"][aoi_id] = {
            "dynamic_grid_cells": grid["cell_count"],
            "cascade_impacted_assets": len(cascade["impacted_assets"]),
            "cascade_human_exposure": cascade["total_critical_human_exposure"],
            "top_chokepoint": top_cp_id,
            "route_reachable": route["reachable"],
            "copilot_status": copilot["status"],
            "copilot_turns": len(copilot["agent_traces"]),
            "copilot_llm_source": copilot["agent_traces"][-1]["tool_args"].get("llm_source"),
            "copilot_blocked_hallucinations": copilot["unverified_citations_blocked"],
            "robotics_mission_id": mission["mission_id"],
            "sdg6_person_hours_saved": sdg["sdg6_potable_water_person_hours_saved"],
        }

    stt_res = await post_sarvam_stt(
        SarvamSttRequest(aoi_id="chennai", language_hint="ta-IN", prefer_live_api=True)
    )
    vision_res = await post_sarvam_vision(
        SarvamVisionRequest(shelter_node_id="SHEL-CHENNAI-01", prefer_live_api=True)
    )
    tts_ta = await post_sarvam_tts(
        SarvamTtsRequest(
            text="வேளச்சேரி துணை மின்நிலையம் அருகே வெள்ள அபாயம். பாதுகாப்பான இடத்திற்கு செல்லவும்.",
            language_code="ta-IN",
            prefer_live_api=True,
        )
    )
    tts_ml = await post_sarvam_tts(
        SarvamTtsRequest(
            text="വയനാട് ചൂരൽമല പാലം അപകടത്തിലാണ്, സുരക്ഷിത സ്ഥാനത്തേക്ക് മാറുക.",
            language_code="ml-IN",
            prefer_live_api=True,
        )
    )
    results["sarvam_multimodal"] = {
        "stt_model": stt_res["model"],
        "stt_source": stt_res["source_mode"],
        "stt_keyterms_count": len(stt_res["keyterms_applied"]),
        "vision_model": vision_res["model"],
        "vision_shelter_headcount": vision_res["total_headcount"],
        "tts_ta_model": tts_ta["model_used"],
        "tts_ta_source": tts_ta["source_mode"],
        "tts_ml_model": tts_ml["model_used"],
        "tts_ml_fallback_triggered": tts_ml["fallback_triggered"],
    }
    return results


if __name__ == "__main__":
    summary = asyncio.run(verify_all_features_and_aois())
    print(json.dumps(summary, indent=2))
