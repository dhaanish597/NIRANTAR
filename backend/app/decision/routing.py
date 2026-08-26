"""decision/routing.py — BUILD_PLAN.md task 3.1: village -> nearest USABLE shelter routing.

    C_edge = L_edge * (1 + alpha * P_fail_edge + beta * S_slope_edge)        (CLAUDE.md §4)

Dijkstra over the road graph (`impact/road_graph.py`'s `load_road_graph()`), with:

- P_fail_edge: this module's substitute for a per-EDGE failure probability is
  `impact/road_graph.py`'s `RoadSegmentRisk.p_blocked` — the max `p_fail` of any runout envelope
  intersecting that edge (task 2.3). `CellRisk.p_fail` is per analysis CELL, not per road edge;
  `p_blocked` is the finest-grained failure-probability figure this codebase actually attaches to
  a road SEGMENT, and it is precisely "the probability a landslide blocks this edge" — the
  natural reading of C_edge's own P_fail term for a routing cost. Documented substitution, not a
  re-derivation of CLAUDE.md's formula.

- S_slope_edge: road-surface slope gradient, normalized. **No data source computes this yet** —
  `scripts/build_road_graph.py`'s OSMnx extract carries no slope attribute, and `RoadEdge`
  (impact/road_graph.py) has none either; computing one would mean tracing the DEM along every
  edge's geometry, out of this task's scope (and `data/static/<aoi>/cells.gpkg` isn't even
  present in a fresh checkout — see this module's own test file for how it's exercised without
  one). The beta*S_slope term is therefore structurally real (config.ROUTING_BETA_SLOPE is a real,
  tunable weight, and `build_routable_graph()` accepts a `slope_norm_by_edge_id` map) but
  contributes 0.0 for every edge unless a caller supplies that map — a documented gap, not a
  fabricated slope figure. TODO(verify): wire in a real per-edge slope once one exists.

SEVERANCE: edges with `p_blocked > P_crit` (`RoadSegmentRisk.severed`, already computed by
impact/road_graph.py) are **removed from the routable graph entirely**, not merely cost-penalized
— BUILD_PLAN.md task 3.1's own explicit instruction, and the same "severed means gone, not just
expensive" rule impact/isolation.py already applies for RII.

UNDIRECTED, same convention `impact/isolation.py` already established for this codebase's road-
network reasoning: evacuation is about physical passability on foot/vehicle in an emergency, not
one-way traffic legality, and staying consistent with isolation.py means both modules agree on
what "connected" means for the exact same graph.

SHELTER SELECTION — "nearest USABLE shelter, capacity-aware, not merely nearest" (task 3.1's own
wording): every reachable shelter candidate gets a real routed cost (not straight-line distance —
that is the "not merely nearest" half), then candidates are ranked capacity-first, cost second.

CAPACITY-AWARE, HONEST GAP (a real ruling, documented here rather than silently defaulted):
`data/static/<aoi>/exposure.gpkg`'s `shelters` layer (`scripts/fetch_exposure.py`, task 1.3) is
built from OSM `amenity=school|community_centre` tags, which do not carry a `capacity=*` value for
Aizawl — there is no capacity field to read (confirmed by reading fetch_exposure.py itself: it
never extracts one, because there is nothing there to extract). Inventing a plausible-looking
capacity number here would be exactly the kind of fabrication CLAUDE.md's honesty rules ban. This
module is fully real and ready for capacity data the moment it exists — `ShelterCandidate` carries
optional `capacity`/`occupancy` fields, and ranking genuinely prefers a not-full shelter over a
nearer full one when both are known — but with today's real data every candidate's capacity is
`None`, so every reachable shelter is treated as usable and `EvacuationRoute.shelter_capacity_ok`
is always `True`. That is the honest state of the data, not a bug in this module.

Pure functions over a plain `networkx` graph + a `{edge_id: RoadSegmentRisk}` map — no LIVE/REPLAY
awareness (CLAUDE.md §2). `resolve_routing_inputs()` at the bottom is the real-data loader
(GeoPandas + the pickled Aizawl road graph), kept separate so the routing/ranking logic above is
testable with a handful of synthetic nodes and edges, same split every other impact/decision
module in this codebase already uses (see impact/isolation.py, impact/priority.py, impact/runout.py).
"""
from __future__ import annotations

import warnings
from dataclasses import dataclass
from pathlib import Path

import networkx as nx

from app.config import (
    ROUTING_ALPHA_P_FAIL,
    ROUTING_BETA_SLOPE,
    ROUTING_WALKING_SPEED_KMH,
)
from app.schemas.decision import EvacuationRoute
from app.schemas.impact import RoadSegmentRisk


@dataclass(frozen=True)
class ShelterCandidate:
    shelter_id: str
    name: str
    node_id: object
    # None = capacity/occupancy not tracked for this shelter (today's real Aizawl data — see
    # module docstring). A candidate with either field None is treated as usable/capacity_ok.
    capacity: int | None = None
    occupancy: int | None = None

    @property
    def capacity_ok(self) -> bool:
        if self.capacity is None or self.occupancy is None:
            return True
        return self.occupancy < self.capacity


def edge_cost(
    length_m: float,
    p_fail_edge: float,
    slope_norm: float = 0.0,
    *,
    alpha: float = ROUTING_ALPHA_P_FAIL,
    beta: float = ROUTING_BETA_SLOPE,
) -> float:
    """C_edge = L_edge * (1 + alpha*P_fail_edge + beta*S_slope_edge) — CLAUDE.md §4, verbatim."""
    return length_m * (1.0 + alpha * p_fail_edge + beta * slope_norm)


def build_routable_graph(
    graph: nx.MultiDiGraph,
    edge_risk_by_id: dict[str, RoadSegmentRisk],
    *,
    slope_norm_by_edge_id: dict[str, float] | None = None,
    alpha: float = ROUTING_ALPHA_P_FAIL,
    beta: float = ROUTING_BETA_SLOPE,
) -> nx.Graph:
    """Collapses the raw MultiDiGraph to a plain undirected `nx.Graph` (same simplification
    `impact/isolation.py`'s `_to_simple_undirected_with_risk` uses — see module docstring),
    computing a `cost` weight per surviving edge via `edge_cost()`.

    Severed edges (`RoadSegmentRisk.severed`) are DROPPED from the returned graph entirely — they
    never even become a node in the adjacency, so `nx.shortest_path` cannot route through them no
    matter how it's called. This is the "removed, not merely weighted high" requirement.

    Every retained edge keeps `edge_id`, `name`, `ref`, `highway_class`, `is_bridge`, `length_m`,
    `p_blocked`, `cost`, `geometry`, plus the ORIGINAL directed endpoints `orig_u`/`orig_v` (needed
    to orient a stored curved `geometry` correctly when reconstructing a route — see
    `_route_geometry_and_avoided()` below).
    """
    slope_norm_by_edge_id = slope_norm_by_edge_id or {}
    simple = nx.Graph()
    simple.add_nodes_from(graph.nodes(data=True))

    best_edge: dict[tuple, tuple] = {}  # (min(u,v), max(u,v)) -> (orig_u, orig_v, data)
    for u, v, data in graph.edges(data=True):
        key = (u, v) if u <= v else (v, u)
        length = data.get("length_m", float("inf"))
        if key not in best_edge or length < best_edge[key][2].get("length_m", float("inf")):
            best_edge[key] = (u, v, data)

    for (a, b), (orig_u, orig_v, data) in best_edge.items():
        edge_id = data.get("edge_id")
        risk = edge_risk_by_id.get(edge_id)
        if risk is not None and risk.severed:
            continue  # removed from the routable graph entirely

        p_blocked = risk.p_blocked if risk is not None else 0.0
        slope_norm = slope_norm_by_edge_id.get(edge_id, 0.0)
        length_m = data.get("length_m", 0.0)
        cost = edge_cost(length_m, p_blocked, slope_norm, alpha=alpha, beta=beta)

        simple.add_edge(
            a,
            b,
            edge_id=edge_id,
            name=data.get("name"),
            ref=data.get("ref"),
            highway_class=data.get("highway_class", "unclassified"),
            is_bridge=bool(data.get("is_bridge", False)),
            length_m=length_m,
            p_blocked=p_blocked,
            severed=False,  # by construction: severed edges never reach this loop body
            cost=cost,
            geometry=data.get("geometry"),
            orig_u=orig_u,
            orig_v=orig_v,
        )
    return simple


def build_reference_graph(
    graph: nx.MultiDiGraph, edge_risk_by_id: dict[str, RoadSegmentRisk]
) -> nx.Graph:
    """Same collapse as `build_routable_graph`, but keeps EVERY edge (severed ones included,
    flagged via `severed=True`) — this is "what a resident's normal/default route would be,
    ignoring today's blockage," used by `_direct_route_avoided_roads()` below to work out which
    named roads a real route had to detour around. Weighted by plain `length_m`, not `cost` — the
    "direct" route is the shortest-by-distance one a person would normally take, not a risk-
    weighted one."""
    simple = nx.Graph()
    simple.add_nodes_from(graph.nodes(data=True))

    best_edge: dict[tuple, tuple] = {}
    for u, v, data in graph.edges(data=True):
        key = (u, v) if u <= v else (v, u)
        length = data.get("length_m", float("inf"))
        if key not in best_edge or length < best_edge[key][2].get("length_m", float("inf")):
            best_edge[key] = (u, v, data)

    for (a, b), (orig_u, orig_v, data) in best_edge.items():
        edge_id = data.get("edge_id")
        risk = edge_risk_by_id.get(edge_id)
        simple.add_edge(
            a,
            b,
            edge_id=edge_id,
            name=data.get("name"),
            ref=data.get("ref"),
            highway_class=data.get("highway_class", "unclassified"),
            is_bridge=bool(data.get("is_bridge", False)),
            length_m=data.get("length_m", 0.0),
            p_blocked=risk.p_blocked if risk is not None else 0.0,
            severed=bool(risk.severed) if risk is not None else False,
            geometry=data.get("geometry"),
            orig_u=orig_u,
            orig_v=orig_v,
        )
    return simple


def _road_label(edge_data: dict) -> str:
    """"Named roads explicitly avoided" (task 3.1) — prefer the NH-6-style `ref`, then the OSM
    `name`, and only fall back to the bare edge_id when a segment genuinely has neither (a very
    minor residential lane, in practice)."""
    return edge_data.get("ref") or edge_data.get("name") or f"unnamed segment {edge_data.get('edge_id')}"


def direct_route_avoided_roads(reference_graph: nx.Graph, source, target) -> list[str]:
    """The named roads on the shortest-BY-DISTANCE path from `source` to `target` (i.e. what a
    resident would normally take, ignoring blockage) that are `severed` — exactly "the roads
    explicitly avoided" the actual (safe) route had to route around. Deduplicated, order-
    preserving. Returns `[]` if no such direct path exists at all (nothing to avoid because there
    was never a single "normal route" to begin with) or if the direct route happens to have no
    severed edges on it."""
    try:
        path = nx.shortest_path(reference_graph, source, target, weight="length_m")
    except (nx.NetworkXNoPath, nx.NodeNotFound):
        return []

    seen: set[str] = set()
    avoided: list[str] = []
    for a, b in zip(path[:-1], path[1:]):
        data = reference_graph.get_edge_data(a, b)
        if data and data.get("severed"):
            label = _road_label(data)
            if label not in seen:
                seen.add(label)
                avoided.append(label)
    return avoided


def _route_geometry(routable_graph: nx.Graph, path: list) -> dict:
    """Assembles a single GeoJSON LineString by concatenating each edge's own geometry along the
    path, oriented to match the direction actually travelled (`orig_u`/`orig_v` say which way the
    stored geometry naturally runs; reversed if the path crosses it backward). Falls back to a
    straight line between node x/y when an edge has no stored curved geometry — the identical
    fallback `impact/road_graph.py`'s `road_edges_from_graph()` already uses, so this stays
    consistent with how the road layer itself is rendered."""
    coords: list[list[float]] = []
    for a, b in zip(path[:-1], path[1:]):
        data = routable_graph.get_edge_data(a, b)
        geometry = data.get("geometry")
        if geometry is not None:
            seg = [list(c) for c in geometry.coords]
            if data.get("orig_u") != a:
                seg = list(reversed(seg))
        else:
            na, nb = routable_graph.nodes[a], routable_graph.nodes[b]
            seg = [[na["x"], na["y"]], [nb["x"], nb["y"]]]

        if coords and coords[-1] == seg[0]:
            coords.extend(seg[1:])
        else:
            coords.extend(seg)
    return {"type": "LineString", "coordinates": coords}


@dataclass(frozen=True)
class _RouteResult:
    path: list
    distance_m: float
    cost: float
    geometry: dict


def find_safe_route(routable_graph: nx.Graph, source, target) -> _RouteResult | None:
    """Dijkstra (via `nx.shortest_path`'s default `dijkstra` method) over the ALREADY-severance-
    filtered `routable_graph`, weighted by `cost` (the C_edge formula). Returns `None` if `target`
    is unreachable — either genuinely disconnected in the base network, or only reachable through
    edges that got removed for being severed."""
    if source not in routable_graph or target not in routable_graph:
        return None
    try:
        path = nx.shortest_path(routable_graph, source, target, weight="cost", method="dijkstra")
    except nx.NetworkXNoPath:
        return None
    if len(path) < 2:
        return _RouteResult(path=path, distance_m=0.0, cost=0.0, geometry={"type": "LineString", "coordinates": []})

    distance_m = sum(routable_graph.get_edge_data(a, b)["length_m"] for a, b in zip(path[:-1], path[1:]))
    cost = sum(routable_graph.get_edge_data(a, b)["cost"] for a, b in zip(path[:-1], path[1:]))
    geometry = _route_geometry(routable_graph, path)
    return _RouteResult(path=path, distance_m=distance_m, cost=cost, geometry=geometry)


def _walk_minutes(distance_m: float, *, walking_speed_kmh: float = ROUTING_WALKING_SPEED_KMH) -> int:
    if walking_speed_kmh <= 0 or distance_m <= 0:
        return 0
    hours = (distance_m / 1000.0) / walking_speed_kmh
    return max(0, round(hours * 60.0))


def find_best_shelter_route(
    village_id: str,
    village_node_id,
    candidates: list[ShelterCandidate],
    routable_graph: nx.Graph,
    reference_graph: nx.Graph,
    *,
    walking_speed_kmh: float = ROUTING_WALKING_SPEED_KMH,
) -> EvacuationRoute | None:
    """The full task-3.1 pipeline for one village: route to every candidate shelter, drop
    unreachable ones, rank the survivors capacity-first-then-cost ("nearest USABLE shelter,
    capacity-aware, not merely nearest" — see module docstring for why capacity is `True` for
    every real candidate today), and build the `EvacuationRoute` for the winner. Returns `None`
    only when NO candidate shelter is reachable at all — genuinely no usable route exists."""
    reachable: list[tuple[ShelterCandidate, _RouteResult]] = []
    for candidate in candidates:
        route = find_safe_route(routable_graph, village_node_id, candidate.node_id)
        if route is not None:
            reachable.append((candidate, route))

    if not reachable:
        return None

    # Capacity-aware ranking: prefer a candidate with room (capacity_ok=True) over a known-full
    # one, THEN prefer lower routed cost. `not candidate.capacity_ok` sorts False (has room, or
    # unknown) before True (confirmed full).
    reachable.sort(key=lambda pair: (not pair[0].capacity_ok, pair[1].cost))
    winner, route = reachable[0]

    avoided_roads = direct_route_avoided_roads(reference_graph, village_node_id, winner.node_id)

    return EvacuationRoute(
        village_id=village_id,
        shelter_id=winner.shelter_id,
        shelter_name=winner.name,
        geometry=route.geometry,
        distance_m=route.distance_m,
        est_walk_minutes=_walk_minutes(route.distance_m, walking_speed_kmh=walking_speed_kmh),
        avoided_roads=avoided_roads,
        shelter_capacity_ok=winner.capacity_ok,
    )


# =================================================================================================
# Loader: real Aizawl villages/shelters resolved onto the real road graph. Needs GeoPandas +
# shapely; exercised by an integration-style test, kept separate from the pure routing/ranking
# logic above — same split `impact/isolation.py`'s `build_isolation_inputs` and
# `impact/priority.py`'s `resolve_priority_inputs` already use for exactly this reason.
# =================================================================================================
def resolve_routing_inputs(
    aoi_id: str, graph: nx.MultiDiGraph, repo_root: Path | None = None
) -> tuple[dict[str, object], list[ShelterCandidate]]:
    """Reads `data/static/<aoi>/exposure.gpkg` (villages + shelters, task 1.3) and returns
    ({village_id: nearest_road_graph_node_id}, [ShelterCandidate, ...]) — every shelter snapped
    onto its nearest road-graph node by straight-line distance, same coarse-but-documented
    approximation `impact/isolation.py`'s `build_isolation_inputs` already makes for the identical
    reason (no routed-nearest-node algorithm is worth the extra machinery here).

    `ShelterCandidate.capacity`/`.occupancy` are always `None` here — see module docstring's
    CAPACITY-AWARE, HONEST GAP note: `exposure.gpkg` has no capacity column to read.
    """
    import geopandas as gpd
    from shapely.geometry import Point
    from shapely.strtree import STRtree

    root = repo_root or Path(__file__).resolve().parents[3]
    exposure_path = root / "data" / "static" / aoi_id / "exposure.gpkg"
    if not exposure_path.is_file():
        raise FileNotFoundError(
            f"{exposure_path} not found — run `python scripts/fetch_exposure.py --aoi {aoi_id}` first"
        )

    node_ids = list(graph.nodes)
    node_points = [Point(graph.nodes[n]["x"], graph.nodes[n]["y"]) for n in node_ids]
    node_tree = STRtree(node_points)

    def _nearest_node(pt: Point):
        idx = node_tree.nearest(pt)
        return node_ids[idx]

    villages_gdf = gpd.read_file(exposure_path, layer="villages")
    shelters_gdf = gpd.read_file(exposure_path, layer="shelters")

    with warnings.catch_warnings():
        warnings.simplefilter("ignore", category=UserWarning)
        village_node_by_id = {
            f"v_{row.osm_id}": _nearest_node(row.geometry) for _, row in villages_gdf.iterrows()
        }
        candidates = [
            ShelterCandidate(
                shelter_id=f"shelter_{row.osm_id}",
                name=row.get("name") or "unnamed shelter",
                node_id=_nearest_node(row.geometry),
            )
            for _, row in shelters_gdf.iterrows()
        ]

    return village_node_by_id, candidates
