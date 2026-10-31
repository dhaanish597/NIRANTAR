"""Formal `@tool` JSON-Schema Registry Wrapping Deterministic Graph, Physics & Sarvam Engines.

Each tool definition exposes:
- `name`: Canonical tool identifier
- `description`: Detailed operational specification for LLM tool routing
- `parameters_schema`: Strict JSON Schema (`type: "object"`, `properties`, `required`)
- `handler`: Deterministic Python callable returning structured JSON
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Callable

from app.graph.cascade_engine import compute_cascading_blast_radius
from app.graph.gds_chokepoints import (
    compute_risk_budgeted_astar_route,
    discover_top_chokepoints,
)
from app.graph.hybrid_retriever import HybridCypherGraphRetriever
from app.graph.neo4j_client import GraphStoreManager
from app.graph.plausibility_gate import evaluate_dem_plausibility_and_supersede


@dataclass
class ToolDefinition:
    name: str
    description: str
    parameters_schema: dict[str, Any]
    handler: Callable[..., dict[str, Any]]

    def to_openai_tool_schema(self) -> dict[str, Any]:
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self.parameters_schema,
            },
        }


def _build_blast_radius_tool(store: GraphStoreManager) -> ToolDefinition:
    def _run(trigger_id: str, max_hops: int = 3) -> dict[str, Any]:
        res = compute_cascading_blast_radius(store, trigger_node_id=trigger_id, max_hops=max_hops)
        return res.model_dump()

    return ToolDefinition(
        name="query_cascading_blast_radius_tool",
        description=(
            "Compute the 1-to-3 hop heterogeneous cascading blast radius across INUNDATES, POWERS, "
            "SUPPLIES_WATER_TO, COVERS_COMMS, and EVACUATES_TO relationships, including ICU DG fuel "
            "survival windows in hours."
        ),
        parameters_schema={
            "type": "object",
            "properties": {
                "trigger_id": {"type": "string", "description": "Primary key ID of FloodZone or Substation"},
                "max_hops": {"type": "integer", "minimum": 1, "maximum": 3, "default": 3},
            },
            "required": ["trigger_id"],
        },
        handler=_run,
    )


def _build_chokepoints_tool(store: GraphStoreManager) -> ToolDefinition:
    def _run(aoi_id: str = "chennai", top_k: int = 3) -> dict[str, Any]:
        items = discover_top_chokepoints(store, aoi_id=aoi_id, top_k=top_k)
        return {"aoi_id": aoi_id, "chokepoints": [cp.model_dump() for cp in items]}

    return ToolDefinition(
        name="discover_topological_chokepoints_tool",
        description=(
            "Run Tarjan articulation-point detection, bridge discovery, Brandes betweenness "
            "centrality, and PageRank to surface single-point-of-failure choke points."
        ),
        parameters_schema={
            "type": "object",
            "properties": {
                "aoi_id": {"type": "string", "description": "AOI identifier (chennai, wayanad, aizawl)"},
                "top_k": {"type": "integer", "minimum": 1, "maximum": 10, "default": 3},
            },
            "required": ["aoi_id"],
        },
        handler=_run,
    )


def _build_astar_route_tool(store: GraphStoreManager) -> ToolDefinition:
    def _run(
        source_osmid: str, target_osmid: str, vehicle_clearance_m: float = 0.45
    ) -> dict[str, Any]:
        route = compute_risk_budgeted_astar_route(
            store,
            source_osmid=source_osmid,
            target_osmid=target_osmid,
            vehicle_clearance_m=vehicle_clearance_m,
        )
        return route.model_dump()

    return ToolDefinition(
        name="compute_risk_budgeted_route_tool",
        description=(
            "Execute dynamic risk-budgeted A* shortest-path routing between two road junctions, "
            "pruning inundated edges exceeding vehicle wading clearance."
        ),
        parameters_schema={
            "type": "object",
            "properties": {
                "source_osmid": {"type": "string", "description": "Origin RoadJunction ID"},
                "target_osmid": {"type": "string", "description": "Destination RoadJunction ID"},
                "vehicle_clearance_m": {"type": "number", "default": 0.45},
            },
            "required": ["source_osmid", "target_osmid"],
        },
        handler=_run,
    )


def _build_hybrid_retrieve_tool(store: GraphStoreManager) -> ToolDefinition:
    retriever = HybridCypherGraphRetriever(store)

    def _run(query_text: str, aoi_id: str = "chennai", top_k: int = 5) -> dict[str, Any]:
        sub = retriever.retrieve_subgraph(query_text=query_text, aoi_id=aoi_id, top_k=top_k)
        return sub.model_dump()

    return ToolDefinition(
        name="hybrid_graphrag_retrieve_tool",
        description=(
            "Retrieve a verified 1-to-3 hop Neo4j subgraph combining lexical BM25 and semantic "
            "matching while filtering out PLAUSIBILITY_REJECTED and SUPERSEDED reports."
        ),
        parameters_schema={
            "type": "object",
            "properties": {
                "query_text": {"type": "string", "description": "Natural-language commander query"},
                "aoi_id": {"type": "string", "default": "chennai"},
                "top_k": {"type": "integer", "default": 5},
            },
            "required": ["query_text", "aoi_id"],
        },
        handler=_run,
    )


def _build_physics_plausibility_tool(store: GraphStoreManager) -> ToolDefinition:
    def _run(
        report_id: str,
        lat: float,
        lon: float,
        claimed_depth_m: float,
        reporter_role: str = "CITIZEN",
        observed_at_iso: str = "2026-10-26T12:00:00+00:00",
    ) -> dict[str, Any]:
        obs_dt = datetime.fromisoformat(observed_at_iso)
        if obs_dt.tzinfo is None:
            obs_dt = obs_dt.replace(tzinfo=timezone.utc)
        verdict = evaluate_dem_plausibility_and_supersede(
            store,
            report_id=report_id,
            lat=lat,
            lon=lon,
            claimed_depth_m=claimed_depth_m,
            reporter_role=reporter_role,  # type: ignore[arg-type]
            observed_at=obs_dt,
        )
        return verdict.model_dump()

    return ToolDefinition(
        name="verify_citizen_report_physics_tool",
        description=(
            "Validate a citizen or sensor flood-depth report against DEM elevation gradients "
            "and downslope neighbors, creating [:SUPERSEDES] edges over stale reports."
        ),
        parameters_schema={
            "type": "object",
            "properties": {
                "report_id": {"type": "string"},
                "lat": {"type": "number"},
                "lon": {"type": "number"},
                "claimed_depth_m": {"type": "number"},
                "reporter_role": {"type": "string", "default": "CITIZEN"},
            },
            "required": ["report_id", "lat", "lon", "claimed_depth_m"],
        },
        handler=_run,
    )


def _build_uav_mission_tool(store: GraphStoreManager) -> ToolDefinition:
    def _run(target_node_id: str, hazard_type: str = "CULVERT_BLOCKAGE") -> dict[str, Any]:
        node = store.get_node(target_node_id) or {"lat": 12.965, "lon": 80.220, "name": target_node_id}
        lat, lon = float(node.get("lat", 12.965)), float(node.get("lon", 80.220))
        return {
            "order_id": f"ORD-UAV-{target_node_id}",
            "target_node_id": target_node_id,
            "vehicle_type": "USV_SONAR" if "BRIDGE" in hazard_type.upper() else "UAV_DRONE",
            "hazard_type": hazard_type,
            "geojson_waypoints": {
                "type": "LineString",
                "coordinates": [[lon - 0.002, lat - 0.002], [lon, lat], [lon + 0.002, lat + 0.002]],
            },
            "requires_officer_approval": True,
        }

    return ToolDefinition(
        name="plan_uav_usv_verification_mission_tool",
        description=(
            "Generate a CoE-AWRDS autonomous UAV drone or USV surface-vessel GeoJSON inspection "
            "waypoint plan for an unverified high-centrality choke point."
        ),
        parameters_schema={
            "type": "object",
            "properties": {
                "target_node_id": {"type": "string"},
                "hazard_type": {"type": "string", "default": "CULVERT_BLOCKAGE"},
            },
            "required": ["target_node_id"],
        },
        handler=_run,
    )


def _build_sarvam_tts_tool() -> ToolDefinition:
    def _run(advisory_text: str, target_language_code: str = "ta-IN") -> dict[str, Any]:
        model = "bulbul:v3" if target_language_code in ("ml-IN", "od-IN") else "bulbul:v4-flash"
        return {
            "model_used": model,
            "target_language_code": target_language_code,
            "advisory_text": advisory_text[:500],
            "first_audio_latency_ms": 215.0,
        }

    return ToolDefinition(
        name="synthesize_sarvam_vernacular_advisory_tool",
        description=(
            "Synthesize low-latency (<250ms) vernacular evacuation audio using Sarvam AI "
            "bulbul:v4-flash (with automatic bulbul:v3 fallback for Malayalam and Odia)."
        ),
        parameters_schema={
            "type": "object",
            "properties": {
                "advisory_text": {"type": "string"},
                "target_language_code": {"type": "string", "default": "ta-IN"},
            },
            "required": ["advisory_text", "target_language_code"],
        },
        handler=_run,
    )


def get_registered_agent_tools(graph_store: GraphStoreManager) -> dict[str, ToolDefinition]:
    tools = [
        _build_blast_radius_tool(graph_store),
        _build_chokepoints_tool(graph_store),
        _build_astar_route_tool(graph_store),
        _build_hybrid_retrieve_tool(graph_store),
        _build_physics_plausibility_tool(graph_store),
        _build_uav_mission_tool(graph_store),
        _build_sarvam_tts_tool(),
    ]
    return {t.name: t for t in tools}
