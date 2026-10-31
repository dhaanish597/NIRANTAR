"""Topographic DEM Hydrostatic Plausibility Gate & Temporal `[:SUPERSEDES]` Lineage Engine.

Enforces two physical and epistemic invariants on every incoming CitizenReport:
1. Topographic & Hydrostatic Conservation Gate:
   Because surface runoff flows downslope under gravity (q = -K * grad(H)), a claim of deep
   standing floodwater (claimed_depth_m >= 0.5m) at a local topographic ridge/peak node u
   with elevation z(u) is physically implausible if >= 2 connected downslope neighbors v
   (within 1..2 hops satisfying z(v) <= z(u) - 1.5m) are verified dry (flood_depth_m <= 0.05m).
2. Temporal & Authority Supersession:
   When a newer verified observation or responder report arrives at the same topological
   junction, it creates a directed `[:SUPERSEDES]` edge and transitions stale reports to
   `verification_state = 'SUPERSEDED'`.
"""
from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from app.graph.models import PlausibilityGateVerdict
from app.graph.neo4j_client import GraphStoreManager


def _collect_two_hop_downslope_neighbors(
    graph_store: GraphStoreManager, junction_id: str, max_elev_m: float
) -> list[dict[str, Any]]:
    visited: set[str] = {junction_id}
    frontier: set[str] = {junction_id}
    downslope: list[dict[str, Any]] = []

    for _ in range(2):
        next_frontier: set[str] = set()
        for curr_id in frontier:
            for edge in graph_store.outgoing_edges(curr_id, {"CONNECTS_TO", "DRAINS_INTO"}):
                nbr_id = str(edge["dst_id"])
                if nbr_id in visited:
                    continue
                visited.add(nbr_id)
                next_frontier.add(nbr_id)
                nbr_node = graph_store.get_node(nbr_id)
                if nbr_node is not None and float(nbr_node.get("elev_m", 9999.0)) <= max_elev_m:
                    downslope.append(nbr_node)
        frontier = next_frontier
    return downslope


def evaluate_dem_plausibility_and_supersede(
    graph_store: GraphStoreManager,
    report_id: str,
    lat: float,
    lon: float,
    claimed_depth_m: float,
    reporter_role: Literal["CITIZEN", "SDRF_RESPONDER", "DEOC_OFFICER", "UAV_SENSOR"],
    observed_at: datetime,
    raw_transcript: str = "",
    english_translation: str = "",
    source_lang: str = "ta-IN",
) -> PlausibilityGateVerdict:
    nearest_junction, snap_dist_m = graph_store.find_nearest_node(
        lat, lon, label="RoadJunction", max_dist_m=5000.0
    )
    if nearest_junction is None:
        raise ValueError(f"No RoadJunction found within 5km of ({lat}, {lon})")

    j_id = str(nearest_junction["id"])
    dem_elev_m = float(nearest_junction.get("elev_m", 0.0))
    downslope_nodes = _collect_two_hop_downslope_neighbors(
        graph_store, j_id, max_elev_m=dem_elev_m - 1.5
    )
    downslope_cnt = len(downslope_nodes)
    dry_downslope_cnt = sum(
        1
        for n in downslope_nodes
        if float(n.get("flood_depth_m", n.get("water_depth_m", 0.0))) <= 0.05
    )

    is_authoritative = reporter_role in ("SDRF_RESPONDER", "DEOC_OFFICER", "UAV_SENSOR")
    is_ridge_spoof = (
        claimed_depth_m >= 0.5
        and downslope_cnt >= 2
        and dry_downslope_cnt == downslope_cnt
        and not is_authoritative
    )

    if is_ridge_spoof:
        ver_state: Literal["VERIFIED", "PENDING", "PLAUSIBILITY_REJECTED", "SUPERSEDED"] = (
            "PLAUSIBILITY_REJECTED"
        )
        conf_score = 0.05
        audit_note = (
            f"REJECTED_BY_DEM_PHYSICS: Claimed {claimed_depth_m}m at elev {dem_elev_m}m "
            f"while {dry_downslope_cnt} lower adjacent nodes (<= {round(dem_elev_m - 1.5, 2)}m) "
            "are verified dry."
        )
    else:
        ver_state = "VERIFIED" if is_authoritative else "PENDING"
        conf_score = 0.96 if is_authoritative else 0.78
        audit_note = "PASSED_DEM_GRADIENT_CHECK"

    report_props = {
        "id": report_id,
        "report_id": report_id,
        "aoi_id": nearest_junction.get("aoi_id", "chennai"),
        "lat": lat,
        "lon": lon,
        "dem_elev_m": dem_elev_m,
        "claimed_depth_m": claimed_depth_m,
        "reporter_role": reporter_role,
        "source_lang": source_lang,
        "raw_transcript": raw_transcript,
        "english_translation": english_translation,
        "verification_state": ver_state,
        "confidence_score": conf_score,
        "physics_audit_note": audit_note,
        "observed_at": observed_at.isoformat(),
    }
    graph_store.upsert_node("CitizenReport", report_id, report_props)
    graph_store.upsert_edge(
        "OBSERVED_AT",
        report_id,
        j_id,
        f"OBS:{report_id}->{j_id}",
        {"snap_distance_m": round(snap_dist_m, 2), "elevation_delta_m": 0.0},
    )
    graph_store.upsert_edge(
        "AFFECTS_NODE",
        report_id,
        j_id,
        f"AFF:{report_id}->{j_id}",
        {"reported_depth_m": claimed_depth_m, "is_verified": ver_state == "VERIFIED"},
    )

    superseded_ids: list[str] = []
    if ver_state != "PLAUSIBILITY_REJECTED":
        for in_edge in graph_store.incoming_edges(j_id, {"OBSERVED_AT"}):
            old_id = str(in_edge["src_id"])
            if old_id == report_id:
                continue
            old_node = graph_store.get_node(old_id)
            if old_node is None or old_node.get("label") != "CitizenReport":
                continue
            old_state = old_node.get("verification_state")
            if old_state not in ("VERIFIED", "PENDING"):
                continue
            old_time = datetime.fromisoformat(str(old_node["observed_at"]))
            old_conf = float(old_node.get("confidence_score", 0.5))
            if observed_at > old_time and (conf_score >= old_conf or is_authoritative):
                old_node["verification_state"] = "SUPERSEDED"
                graph_store.upsert_node("CitizenReport", old_id, old_node)
                graph_store.upsert_edge(
                    "SUPERSEDES",
                    report_id,
                    old_id,
                    f"SUP:{report_id}->{old_id}",
                    {
                        "time_delta_s": int((observed_at - old_time).total_seconds()),
                        "reason": "NEWER_VERIFIED_OBSERVATION",
                    },
                )
                superseded_ids.append(old_id)

        # Mutate live junction water depth if verified or pending valid report
        nearest_junction["flood_depth_m"] = claimed_depth_m
        nearest_junction["is_passable"] = claimed_depth_m < 0.45
        graph_store.upsert_node("RoadJunction", j_id, nearest_junction)

    return PlausibilityGateVerdict(
        report_id=report_id,
        snapped_junction_osmid=j_id,
        dem_elev_m=dem_elev_m,
        claimed_depth_m=claimed_depth_m,
        verification_state=ver_state,
        confidence_score=conf_score,
        physics_audit_note=audit_note,
        superseded_report_ids=superseded_ids,
    )
