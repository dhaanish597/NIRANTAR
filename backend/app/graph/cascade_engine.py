"""1-to-3 Hop Heterogeneous Cascading Blast Radius & ICU Survival Window Engine.

Implements:
1. Hospital ICU Diesel Generator (DG) survival window formula:
   tau_rem(h, t) = F_res(h, t0) / (gamma_DG * P_ICU(h)) - (t - t_trip(i))
2. Telecom Base Transceiver Station (BTS) battery depletion horizon:
   tau_batt(c, t) = (V_nom * Q_Ah * eta_DOD) / (1000 * P_BTS_kW) - (t - t_trip(i))
3. Breadth-first 1-to-3 hop heterogeneous cascade traversal across INUNDATES, POWERS,
   SUPPLIES_WATER_TO, COVERS_COMMS, CARRIES_CORRIDOR, and EVACUATES_TO edges.
"""
from __future__ import annotations

from collections import deque
import time
from typing import Any

from app.graph.models import CascadeBlastRadiusResult, ImpactedAssetNode
from app.graph.neo4j_client import GraphStoreManager

CASCADE_REL_TYPES: set[str] = {
    "INUNDATES",
    "POWERS",
    "SUPPLIES_WATER_TO",
    "COVERS_COMMS",
    "CARRIES_CORRIDOR",
    "EVACUATES_TO",
}

CYPHER_THREE_HOP_BLAST_RADIUS = """
MATCH (trigger {id: $trigger_id})
MATCH path = (trigger)-[rels:INUNDATES|POWERS|SUPPLIES_WATER_TO|COVERS_COMMS|CARRIES_CORRIDOR|EVACUATES_TO*1..3]->(downstream)
WHERE NONE(n IN nodes(path)[1..-1] WHERE n = trigger)
RETURN downstream, length(path) AS hop_distance, relationships(path) AS rels
"""


def compute_hospital_dg_survival_hours(
    fuel_liters: float,
    icu_load_kw: float,
    elapsed_trip_hours: float = 0.0,
    specific_consumption: float = 0.28,
) -> float:
    if icu_load_kw <= 0.0 or specific_consumption <= 0.0:
        return 0.0
    burn_rate_lph = specific_consumption * icu_load_kw
    initial_hours = fuel_liters / burn_rate_lph
    return round(max(0.0, initial_hours - max(0.0, elapsed_trip_hours)), 2)


def compute_telecom_battery_survival_hours(
    battery_capacity_ah: float,
    nominal_voltage_v: float = 48.0,
    depth_of_discharge: float = 0.80,
    load_kw: float = 2.75,
    elapsed_trip_hours: float = 0.0,
) -> float:
    if load_kw <= 0.0:
        return 0.0
    usable_kwh = (nominal_voltage_v * battery_capacity_ah * depth_of_discharge) / 1000.0
    initial_hours = usable_kwh / load_kw
    return round(max(0.0, initial_hours - max(0.0, elapsed_trip_hours)), 2)


def _asset_survival_window(node: dict[str, Any], elapsed_trip_hours: float = 0.0) -> float:
    label = str(node.get("label", ""))
    if label == "Hospital":
        fuel_l = float(node.get("dg_fuel_rem_l", node.get("dg_fuel_cap_l", 0.0) * 0.367))
        icu_kw = float(node.get("icu_load_kw", 185.0))
        if fuel_l > 0 and icu_kw > 0:
            return compute_hospital_dg_survival_hours(fuel_l, icu_kw, elapsed_trip_hours)
        return float(node.get("dg_fuel_rem_hrs", 0.0))
    if label == "TelecomTower":
        cap_ah = float(node.get("battery_capacity_ah", 0.0))
        if cap_ah > 0:
            return compute_telecom_battery_survival_hours(cap_ah, elapsed_trip_hours=elapsed_trip_hours)
        return float(node.get("battery_rem_hrs", 0.0))
    return float(node.get("backup_power_hrs", 0.0))


def compute_cascading_blast_radius(
    graph_store: GraphStoreManager,
    trigger_node_id: str,
    max_hops: int = 3,
    elapsed_trip_hours: float = 0.0,
) -> CascadeBlastRadiusResult:
    t_start = time.perf_counter()
    trigger = graph_store.get_node(trigger_node_id)
    if trigger is None:
        return CascadeBlastRadiusResult(
            trigger_node_id=trigger_node_id,
            max_hops=max_hops,
            impacted_assets=[],
            total_critical_human_exposure=0,
            traversal_latency_ms=0.1,
        )

    best_by_node: dict[str, dict[str, Any]] = {}
    queue: deque[tuple[str, int, float, list[str], list[str]]] = deque([
        (trigger_node_id, 0, 1.0, [trigger_node_id], [])
    ])

    while queue:
        curr_id, hop, prob, chain, edge_types = queue.popleft()
        if hop >= max_hops:
            continue

        for edge in graph_store.outgoing_edges(curr_id, CASCADE_REL_TYPES):
            nxt_id = str(edge["dst_id"])
            if nxt_id in chain:
                continue
            nxt_node = graph_store.get_node(nxt_id)
            if nxt_node is None:
                continue

            weight = float(
                edge.get("inundation_prob")
                or edge.get("cascade_weight")
                or 0.95
            )
            nxt_hop = hop + 1
            nxt_prob = prob * weight
            nxt_chain = [*chain, nxt_id]
            nxt_edges = [*edge_types, str(edge["rel_type"])]

            existing = best_by_node.get(nxt_id)
            if existing is None or (
                nxt_hop < existing["hop"]
                or (nxt_hop == existing["hop"] and nxt_prob > existing["prob"])
            ):
                best_by_node[nxt_id] = {
                    "node": nxt_node,
                    "hop": nxt_hop,
                    "prob": nxt_prob,
                    "chain": nxt_chain,
                    "edges": nxt_edges,
                }
            queue.append((nxt_id, nxt_hop, nxt_prob, nxt_chain, nxt_edges))

    impacted: list[ImpactedAssetNode] = []
    for asset_id, entry in best_by_node.items():
        node = entry["node"]
        survival_hrs = _asset_survival_window(node, elapsed_trip_hours=elapsed_trip_hours)
        human_exp = int(node.get("icu_beds") or node.get("current_occupancy") or 0)
        impacted.append(
            ImpactedAssetNode(
                asset_type=str(node.get("label", "Asset")),
                asset_id=asset_id,
                asset_name=str(node.get("name", asset_id)),
                blast_radius_hop=int(entry["hop"]),
                cascade_probability=round(float(entry["prob"]), 3),
                primary_cascade_path=list(entry["chain"]),
                primary_edge_types=list(entry["edges"]),
                survival_window_hrs=survival_hrs,
                critical_human_exposure=human_exp,
                lat=float(node.get("lat", 0.0)),
                lon=float(node.get("lon", 0.0)),
            )
        )

    impacted.sort(
        key=lambda x: (x.blast_radius_hop, x.survival_window_hrs, -x.critical_human_exposure)
    )
    total_exposure = sum(item.critical_human_exposure for item in impacted)
    elapsed_ms = (time.perf_counter() - t_start) * 1000.0
    return CascadeBlastRadiusResult(
        trigger_node_id=trigger_node_id,
        max_hops=max_hops,
        impacted_assets=impacted,
        total_critical_human_exposure=total_exposure,
        traversal_latency_ms=round(max(0.05, elapsed_ms), 2),
    )
