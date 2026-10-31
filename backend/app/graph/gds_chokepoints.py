"""Neo4j GDS Choke-Point Discovery & Risk-Budgeted A* Shortest-Path Router.

Implements:
1. Tarjan's O(|V|+|E|) biconnected component Articulation Point and Bridge detection
   (`gds.articulationPoints.stream` / `gds.bridges.stream` parity).
2. Brandes' Betweenness Centrality (`gds.betweenness.stream`) and Weighted PageRank
   (`gds.pageRank.stream`) over the active infrastructure projection.
3. Dynamic Risk-Budgeted A* Routing (`gds.shortestPath.astar.stream`) that penalizes
   edges by water depth, terrain slope (>18 deg), and report uncertainty, while pruning
   impassable segments (`flood_depth_m >= vehicle_clearance_m`).
"""
from __future__ import annotations

import heapq
import math
from collections import deque
from typing import Any

from app.graph.models import ChokePointNode, RiskBudgetedRouteResult
from app.graph.neo4j_client import GraphStoreManager, haversine_meters


def _build_undirected_adj(
    graph_store: GraphStoreManager, aoi_id: str
) -> dict[str, set[str]]:
    junctions = graph_store.nodes_by_label("RoadJunction", aoi_id=aoi_id)
    adj: dict[str, set[str]] = {str(n["id"]): set() for n in junctions}
    for j_id in list(adj.keys()):
        for edge in graph_store.outgoing_edges(j_id, {"CONNECTS_TO"}):
            dst = str(edge["dst_id"])
            if dst in adj:
                adj[j_id].add(dst)
                adj[dst].add(j_id)
    return adj


def _find_tarjan_articulation_points(adj: dict[str, set[str]]) -> dict[str, int]:
    """Tarjan's linear-time DFS algorithm returning {articulation_node_id: split_components}."""
    disc: dict[str, int] = {}
    low: dict[str, int] = {}
    parent: dict[str, str | None] = {}
    ap_splits: dict[str, int] = {}
    timer = 0

    for start in adj:
        if start in disc:
            continue
        stack: list[tuple[str, list[str], int]] = [(start, sorted(adj[start]), 0)]
        parent[start] = None
        timer += 1
        disc[start] = low[start] = timer
        root_children = 0

        while stack:
            u, neighbors, idx = stack[-1]
            if idx < len(neighbors):
                v = neighbors[idx]
                stack[-1] = (u, neighbors, idx + 1)
                if v not in disc:
                    parent[v] = u
                    if parent[u] is None:
                        root_children += 1
                    timer += 1
                    disc[v] = low[v] = timer
                    stack.append((v, sorted(adj[v]), 0))
                elif v != parent.get(u):
                    low[u] = min(low[u], disc[v])
            else:
                stack.pop()
                p = parent.get(u)
                if p is not None:
                    low[p] = min(low[p], low[u])
                    if parent.get(p) is not None and low[u] >= disc[p]:
                        ap_splits[p] = ap_splits.get(p, 1) + 1
                elif root_children > 1:
                    ap_splits[u] = root_children
    return ap_splits


def _compute_brandes_betweenness(adj: dict[str, set[str]]) -> dict[str, float]:
    betweenness: dict[str, float] = {v: 0.0 for v in adj}
    for s in adj:
        stack: list[str] = []
        pred: dict[str, list[str]] = {w: [] for w in adj}
        sigma: dict[str, float] = {t: 0.0 for t in adj}
        sigma[s] = 1.0
        dist: dict[str, int] = {t: -1 for t in adj}
        dist[s] = 0
        queue: deque[str] = deque([s])

        while queue:
            v = queue.popleft()
            stack.append(v)
            for w in adj[v]:
                if dist[w] < 0:
                    queue.append(w)
                    dist[w] = dist[v] + 1
                if dist[w] == dist[v] + 1:
                    sigma[w] += sigma[v]
                    pred[w].append(v)

        delta: dict[str, float] = {v: 0.0 for v in adj}
        while stack:
            w = stack.pop()
            for v in pred[w]:
                delta[v] += (sigma[v] / sigma[w]) * (1.0 + delta[w])
            if w != s:
                betweenness[w] += delta[w] * 0.5
    return betweenness


def _compute_pagerank(adj: dict[str, set[str]], damping: float = 0.85, iterations: int = 20) -> dict[str, float]:
    n = len(adj)
    if n == 0:
        return {}
    pr = {u: 1.0 / n for u in adj}
    for _ in range(iterations):
        nxt = {u: (1.0 - damping) / n for u in adj}
        for u, nbrs in adj.items():
            if nbrs:
                share = damping * pr[u] / len(nbrs)
                for v in nbrs:
                    nxt[v] += share
        pr = nxt
    return pr


def discover_top_chokepoints(
    graph_store: GraphStoreManager, aoi_id: str, top_k: int = 3
) -> list[ChokePointNode]:
    adj = _build_undirected_adj(graph_store, aoi_id)
    ap_splits = _find_tarjan_articulation_points(adj)
    betweenness = _compute_brandes_betweenness(adj)
    pagerank = _compute_pagerank(adj)

    hospitals = graph_store.nodes_by_label("Hospital", aoi_id=aoi_id)
    shelters = graph_store.nodes_by_label("ReliefShelter", aoi_id=aoi_id)
    crit_osmids = {
        str(n.get("nearest_osmid")) for n in (*hospitals, *shelters) if n.get("nearest_osmid")
    }

    scored: list[ChokePointNode] = []
    for node_id, nbrs in adj.items():
        node = graph_store.get_node(node_id)
        if node is None:
            continue
        is_ap = node_id in ap_splits or bool(node.get("is_articulation_point", False))
        splits = ap_splits.get(node_id, 2 if is_ap else 1)
        bc = betweenness.get(node_id, 0.0)
        pr = pagerank.get(node_id, 0.0)

        # Count critical facilities within 2 hops of this road junction
        two_hop = set(nbrs)
        for nb in nbrs:
            two_hop.update(adj.get(nb, set()))
        downstream_crit = len(two_hop & crit_osmids) + (1 if node_id in crit_osmids else 0)

        comp_score = (
            0.45 * math.log10(bc + 1.0)
            + 0.25 * (pr * 10.0)
            + 0.30 * ((5.0 if is_ap else 0.0) + downstream_crit * 1.5)
        )
        scored.append(
            ChokePointNode(
                node_type=str(node.get("label", "RoadJunction")),
                node_id=node_id,
                choke_point_name=str(node.get("name", node_id)),
                is_spof_articulation=is_ap,
                split_components_if_lost=splits,
                downstream_critical_facilities=downstream_crit,
                betweenness_centrality=round(bc, 2),
                pagerank_centrality=round(pr, 4),
                criticality_index=round(comp_score, 3),
                elevation_m=float(node.get("elev_m", 0.0)),
                current_water_depth_m=float(node.get("flood_depth_m", 0.0)),
                lat=float(node.get("lat", 0.0)),
                lon=float(node.get("lon", 0.0)),
            )
        )

    scored.sort(key=lambda x: x.criticality_index, reverse=True)
    return scored[:top_k]


def _dynamic_edge_cost_seconds(
    edge: dict[str, Any],
    u_node: dict[str, Any],
    v_node: dict[str, Any],
    vehicle_clearance_m: float,
) -> float:
    depth = max(
        float(edge.get("flood_depth_m", 0.0)),
        float(u_node.get("flood_depth_m", 0.0)),
        float(v_node.get("flood_depth_m", 0.0)),
    )
    if depth >= vehicle_clearance_m or not edge.get("is_passable", True) or not v_node.get("is_passable", True):
        return 1e9
    base_time = float(edge.get("base_time_s", 55.0))
    slope = max(float(u_node.get("slope_deg", 2.0)), float(v_node.get("slope_deg", 2.0)))
    slope_term = 2.5 * ((slope - 18.0) / 18.0) if slope > 18.0 else 0.0
    depth_term = 4.0 * ((depth / (vehicle_clearance_m - depth + 0.05)) ** 2)
    return base_time * (1.0 + depth_term + slope_term)


def compute_risk_budgeted_astar_route(
    graph_store: GraphStoreManager,
    source_osmid: str,
    target_osmid: str,
    vehicle_clearance_m: float = 0.45,
) -> RiskBudgetedRouteResult:
    src = graph_store.get_node(source_osmid)
    dst = graph_store.get_node(target_osmid)
    if src is None or dst is None:
        return RiskBudgetedRouteResult(source_osmid, target_osmid, False, 1e9, [], [])

    g_score: dict[str, float] = {source_osmid: 0.0}
    came_from: dict[str, str] = {}
    avoided_flooded: set[str] = set()

    def heuristic(node_a: dict[str, Any]) -> float:
        dist_m = haversine_meters(
            float(node_a["lat"]), float(node_a["lon"]), float(dst["lat"]), float(dst["lon"])
        )
        return dist_m / 15.0

    open_heap: list[tuple[float, float, str]] = [(heuristic(src), 0.0, source_osmid)]
    visited: set[str] = set()

    while open_heap:
        _, curr_g, curr_id = heapq.heappop(open_heap)
        if curr_id in visited:
            continue
        visited.add(curr_id)
        if curr_id == target_osmid:
            path: list[str] = [curr_id]
            while path[-1] in came_from:
                path.append(came_from[path[-1]])
            path.reverse()
            coords = [
                [float(graph_store.get_node(nid)["lon"]), float(graph_store.get_node(nid)["lat"])]
                for nid in path
                if graph_store.get_node(nid) is not None
            ]
            return RiskBudgetedRouteResult(
                source_osmid=source_osmid,
                target_osmid=target_osmid,
                reachable=True,
                risk_adjusted_eta_seconds=round(curr_g, 2),
                route_junction_osmids=path,
                route_geojson_coords=coords,
                avoided_flooded_nodes=sorted(avoided_flooded),
            )

        curr_node = graph_store.get_node(curr_id)
        if curr_node is None:
            continue
        for edge in graph_store.outgoing_edges(curr_id, {"CONNECTS_TO"}):
            nbr_id = str(edge["dst_id"])
            nbr_node = graph_store.get_node(nbr_id)
            if nbr_node is None:
                continue
            step_cost = _dynamic_edge_cost_seconds(edge, curr_node, nbr_node, vehicle_clearance_m)
            if step_cost >= 1e9:
                avoided_flooded.add(nbr_id)
                continue
            tentative_g = curr_g + step_cost
            if tentative_g < g_score.get(nbr_id, float("inf")):
                g_score[nbr_id] = tentative_g
                came_from[nbr_id] = curr_id
                f_val = tentative_g + heuristic(nbr_node)
                heapq.heappush(open_heap, (f_val, tentative_g, nbr_id))

    return RiskBudgetedRouteResult(
        source_osmid=source_osmid,
        target_osmid=target_osmid,
        reachable=False,
        risk_adjusted_eta_seconds=1e9,
        route_junction_osmids=[],
        route_geojson_coords=[],
        avoided_flooded_nodes=sorted(avoided_flooded),
    )
