"""Typed schemas for the 4-Layer Multiplex Knowledge Graph, GDS Choke-Point & DEM Physics Engine."""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Literal


@dataclass
class SeedSummary:
    status: Literal["SEEDED", "FAILED"]
    elapsed_seconds: float
    nodes_seeded: int
    edges_seeded: int
    backend_mode: Literal["auradb_live", "local_mirror"]

    def model_dump(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class ImpactedAssetNode:
    asset_type: str
    asset_id: str
    asset_name: str
    blast_radius_hop: int
    cascade_probability: float
    primary_cascade_path: list[str]
    primary_edge_types: list[str]
    survival_window_hrs: float
    critical_human_exposure: int
    lat: float
    lon: float

    def model_dump(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class CascadeBlastRadiusResult:
    trigger_node_id: str
    max_hops: int
    impacted_assets: list[ImpactedAssetNode]
    total_critical_human_exposure: int
    traversal_latency_ms: float

    def model_dump(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class ChokePointNode:
    node_type: str
    node_id: str
    choke_point_name: str
    is_spof_articulation: bool
    split_components_if_lost: int
    downstream_critical_facilities: int
    betweenness_centrality: float
    pagerank_centrality: float
    criticality_index: float
    elevation_m: float
    current_water_depth_m: float
    lat: float
    lon: float

    def model_dump(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class RiskBudgetedRouteResult:
    source_osmid: str
    target_osmid: str
    reachable: bool
    risk_adjusted_eta_seconds: float
    route_junction_osmids: list[str]
    route_geojson_coords: list[list[float]]
    avoided_flooded_nodes: list[str] = field(default_factory=list)

    def model_dump(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class PlausibilityGateVerdict:
    report_id: str
    snapped_junction_osmid: str
    dem_elev_m: float
    claimed_depth_m: float
    verification_state: Literal["VERIFIED", "PENDING", "PLAUSIBILITY_REJECTED", "SUPERSEDED"]
    confidence_score: float
    physics_audit_note: str
    superseded_report_ids: list[str] = field(default_factory=list)

    def model_dump(self) -> dict[str, Any]:
        return asdict(self)
