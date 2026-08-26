"""impact/isolation.py — BUILD_PLAN.md task 2.4: the Road Isolation Index (RII).

For each village, tests connectivity — over the AOI's road graph (scripts/build_road_graph.py,
task 2.1), with per-edge blockage risk from impact/road_graph.py (task 2.3) — to three kinds of
essential destination named in task 2.4's own text: the district HQ, the nearest hospital, and
the nearest shelter.

TWO DIFFERENT QUERIES per (village, target-kind), matching the two distinct booleans on
VillageIsolation:

  1. DEFAULT-ROUTE CHECK (`isolated_now`) — the shortest path by road length on the FULL,
     unrestricted graph (what a resident would normally use). If ANY edge on that path is
     `severed` (impact/road_graph.py's boolean, itself driven by
     config.P_CRIT_ROAD/P_CRIT_BRIDGE), that route is blocked right now. A village counts as
     `isolated_now` only if its normal route to EVERY ONE of the three target kinds is blocked —
     matching the real event this feature is named for: NH-6 severed at Hunthar, 2024, cutting
     Aizawl off from essential services generally, not merely inconveniencing one route among
     several (CLAUDE.md §7).

  2. ALTERNATE-ROUTE CHECK (`alternate_route_exists`) — only asked when `isolated_now` is True
     (no need to look for "another way" when the normal way already works): does ANY path
     survive to ANY target kind once every `severed` edge is removed from the graph entirely?

`p_isolated` is a THIRD, continuous quantity, deliberately not the same thing as the
`isolated_now` boolean: for each target kind it runs the "widest path" / minimax-path graph
algorithm (Pollack, M. (1960), "Letter to the Editor — The Maximum Capacity Route Problem,"
Operations Research 8(5), 733-736) — a Dijkstra-style search that, instead of summing edge
weights, tracks the SINGLE riskiest edge a route is forced to cross, and finds the route that
minimizes that value. This uses the continuous `p_blocked` values (not the hard `severed`
threshold), so it answers "how close is this village's BEST available option to being cut off,"
not just "has it already happened." `p_isolated` is the MINIMUM of that bottleneck risk across
the three target kinds (a village is only really at risk of total isolation once even its best
remaining option is risky).

`est_duration_hours` (VillageIsolation's own docstring: "ALWAYS labelled 'estimate' in UI" —
CLAUDE.md's "safe evacuation window" honesty rule applies with equal force) is a heuristic scaled
by the road class and severity of whichever `severed` edges sit on a blocked default route
(config.ROAD_CLEARANCE_HOURS_BY_CLASS / BRIDGE_CLEARANCE_MULTIPLIER) — None when nothing is
actually severed.

Pure functions over plain node ids + a NetworkX graph augmented with `p_blocked`/`severed` edge
data — no LIVE/REPLAY awareness (CLAUDE.md §2). Deliberately independent of the geometry/nearest-
node resolution needed to map real villages/hospitals/shelters onto graph nodes (that lives in
`resolve_nearest_node`/`build_isolation_inputs` below and needs GeoPandas/shapely + real exposure
data) — so the graph algorithm itself is testable with a handful of synthetic nodes and edges.
"""
from __future__ import annotations

import heapq
import warnings
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

import networkx as nx

from app.config import (
    BRIDGE_CLEARANCE_MULTIPLIER,
    P_CRIT_BRIDGE,
    P_CRIT_ROAD,
    ROAD_CLEARANCE_HOURS_BY_CLASS,
    ROAD_CLEARANCE_HOURS_DEFAULT,
)
from app.impact.demographics import simulate_demographics
from app.schemas.impact import RoadSegmentRisk, VillageIsolation


@dataclass(frozen=True)
class VillageNode:
    village_id: str
    name: str
    population: int
    node_id: object  # a node id in the road graph (whatever type build_road_graph.py used)


@dataclass(frozen=True)
class IsolationTarget:
    kind: Literal["district_hq", "hospital", "shelter"]
    target_id: str
    node_id: object


def _to_simple_undirected_with_risk(
    graph: nx.MultiDiGraph, edge_risk_by_id: dict[str, RoadSegmentRisk]
) -> nx.Graph:
    """Collapses a MultiDiGraph into a plain undirected Graph, keeping (per u-v pair) whichever
    parallel edge has the smallest `length_m` — the one a shortest-path search would have used
    anyway. RII cares about PHYSICAL connectivity (can a person get from A to B at all), not
    legal one-way traffic direction, so undirected is the right model here; decision/routing.py
    (Phase 3, real turn-by-turn routes) can still work off the original directed pickle directly,
    unaffected by this simplification. Each retained edge carries `p_blocked`/`severed` merged in
    from `edge_risk_by_id` (0.0/False if that edge_id has no entry, e.g. a road with nothing
    computed for it yet)."""
    simple = nx.Graph()
    simple.add_nodes_from(graph.nodes(data=True))

    best_edge: dict[tuple, dict] = {}
    for u, v, data in graph.edges(data=True):
        key = (u, v) if u <= v else (v, u)
        length = data.get("length_m", float("inf"))
        if key not in best_edge or length < best_edge[key].get("length_m", float("inf")):
            best_edge[key] = data

    for (u, v), data in best_edge.items():
        risk = edge_risk_by_id.get(data.get("edge_id"))
        simple.add_edge(
            u,
            v,
            edge_id=data.get("edge_id"),
            highway_class=data.get("highway_class", "unclassified"),
            is_bridge=bool(data.get("is_bridge", False)),
            length_m=data.get("length_m", 0.0),
            p_blocked=risk.p_blocked if risk is not None else 0.0,
            severed=risk.severed if risk is not None else False,
        )
    return simple


def _bottleneck_path_risk(
    graph: nx.Graph, source, target
) -> float:
    """Widest-path / minimax-path search (see module docstring for the citation): the minimum,
    over every possible path from `source` to `target`, of the MAXIMUM `p_blocked` edge weight
    encountered on that path. Returns 1.0 if `target` is unreachable at all (fully isolated —
    treat "no path exists" as maximal risk, not as an undefined/zero value, which would silently
    under-state isolation)."""
    if source not in graph or target not in graph:
        return 1.0
    if source == target:
        return 0.0

    best: dict = {source: 0.0}
    visited: set = set()
    pq: list[tuple[float, object]] = [(0.0, source)]
    while pq:
        risk, node = heapq.heappop(pq)
        if node in visited:
            continue
        visited.add(node)
        if node == target:
            return risk
        for neighbor, edge_data in graph.adj[node].items():
            candidate = max(risk, edge_data.get("p_blocked", 0.0))
            if candidate < best.get(neighbor, float("inf")):
                best[neighbor] = candidate
                heapq.heappush(pq, (candidate, neighbor))
    return 1.0  # target never reached


def _default_route_severed_edges(graph: nx.Graph, source, target) -> list[dict] | None:
    """The shortest path (by `length_m`) from `source` to `target` on the FULL graph (ignoring
    blockage), returned as the list of its edge-data dicts that are `severed`. Returns None if no
    path exists at all (the two nodes aren't even in the same connected component of the base
    road network — a data/topology issue, not a "current blockage" one)."""
    try:
        path = nx.shortest_path(graph, source, target, weight="length_m")
    except (nx.NetworkXNoPath, nx.NodeNotFound):
        return None
    severed = []
    for u, v in zip(path[:-1], path[1:]):
        data = graph.get_edge_data(u, v)
        if data and data.get("severed"):
            severed.append(data)
    return severed


def _estimate_clearance_hours(severed_edges: list[dict]) -> float | None:
    if not severed_edges:
        return None
    worst = max(severed_edges, key=lambda e: e.get("p_blocked", 0.0))
    base = ROAD_CLEARANCE_HOURS_BY_CLASS.get(worst.get("highway_class"), ROAD_CLEARANCE_HOURS_DEFAULT)
    bridge_multiplier = BRIDGE_CLEARANCE_MULTIPLIER if worst.get("is_bridge") else 1.0
    severity_multiplier = 1.0 + worst.get("p_blocked", 0.0)  # p_blocked in (P_crit, 1] here
    return base * bridge_multiplier * severity_multiplier


def compute_village_isolation(
    village: VillageNode,
    graph: nx.Graph,
    targets: list[IsolationTarget],
) -> VillageIsolation:
    """`graph` must already be the undirected, risk-augmented graph `_to_simple_undirected_with_
    risk` produces (or an equivalent synthetic one in tests — see tests/test_isolation.py) — every
    edge needs `length_m`, `p_blocked`, `severed`, `highway_class`, `is_bridge`, `edge_id`."""
    if not targets:
        raise ValueError("compute_village_isolation requires at least one IsolationTarget")

    per_target_severed: dict[str, list[dict] | None] = {}
    per_target_bottleneck: dict[str, float] = {}
    for target in targets:
        per_target_severed[target.target_id] = _default_route_severed_edges(
            graph, village.node_id, target.node_id
        )
        per_target_bottleneck[target.target_id] = _bottleneck_path_risk(
            graph, village.node_id, target.node_id
        )

    # isolated_now: every target's default/normal route is blocked (severed list non-empty) OR
    # there was no route to it at all in the base network.
    default_blocked = [
        (sev is None or len(sev) > 0) for sev in per_target_severed.values()
    ]
    isolated_now = all(default_blocked)

    if not isolated_now:
        alternate_route_exists = True
    else:
        # Bug caught by tests/test_isolation.py's
        # test_fully_isolated_when_no_path_survives_at_all: checking `has_path` on the
        # unmodified `graph` is meaningless here — `graph` still contains every severed edge as
        # traversable (only its `severed` attribute is set), so a path "exists" trivially even
        # when every route is blocked. The alternate-route question has to be asked on a graph
        # with severed edges actually removed.
        pruned = graph.edge_subgraph(
            [(u, v) for u, v, data in graph.edges(data=True) if not data.get("severed")]
        )
        alternate_route_exists = any(
            village.node_id in pruned
            and t.node_id in pruned
            and nx.has_path(pruned, village.node_id, t.node_id)
            for t in targets
        )

    p_isolated = min(per_target_bottleneck.values())

    # Deliberately not gated on `isolated_now`: this lists every severed edge sitting on ANY
    # target kind's default route, even a kind whose route happens to be fine (e.g. the road to
    # the district HQ is open, but the normal road to the nearest hospital is cut) — a village
    # doesn't have to be totally isolated for "your hospital road is blocked" to be worth
    # surfacing. `isolated_now` still answers the aggregate "cut off from everything" question.
    severed_links = sorted(
        {
            edge["edge_id"]
            for sev in per_target_severed.values()
            if sev
            for edge in sev
            if edge.get("edge_id") is not None
        }
    )
    all_severed_edge_dicts = [
        edge for sev in per_target_severed.values() if sev for edge in sev
    ]
    est_duration_hours = _estimate_clearance_hours(all_severed_edge_dicts)

    return VillageIsolation(
        village_id=village.village_id,
        name=village.name,
        population=village.population,
        demographics=simulate_demographics(village.population),
        p_isolated=p_isolated,
        isolated_now=isolated_now,
        alternate_route_exists=alternate_route_exists,
        est_duration_hours=est_duration_hours,
        severed_links=severed_links,
    )


def compute_all_village_isolations(
    villages: list[VillageNode],
    graph: nx.MultiDiGraph,
    edge_risk_by_id: dict[str, RoadSegmentRisk],
    targets_by_village: dict[str, list[IsolationTarget]],
) -> list[VillageIsolation]:
    """Batch entry point: takes the raw MultiDiGraph + a {edge_id: RoadSegmentRisk} map (exactly
    what impact/road_graph.py's `compute_road_segment_risks` produces, keyed by `.edge_id`),
    builds the simplified risk-augmented graph once, and evaluates every village against its OWN
    three targets (district HQ + THAT village's nearest hospital + THAT village's nearest
    shelter — task 2.4's literal wording is per-village nearest, not "every hospital in the
    AOI"; see `build_isolation_inputs`, which resolves this per village)."""
    simple_graph = _to_simple_undirected_with_risk(graph, edge_risk_by_id)
    return [
        compute_village_isolation(v, simple_graph, targets_by_village[v.village_id])
        for v in villages
    ]


# =================================================================================================
# Loader: real Aizawl villages/hospitals/shelters/district-HQ resolved onto the real road graph.
# Needs GeoPandas + shapely; exercised by an integration-style test, kept separate from the pure
# graph algorithm above so that stays testable with tiny synthetic graphs.
# =================================================================================================
def build_isolation_inputs(
    aoi_id: str, graph: nx.MultiDiGraph, repo_root: Path | None = None
) -> tuple[list[VillageNode], dict[str, list[IsolationTarget]]]:
    """Reads data/static/<aoi>/exposure.gpkg (villages/shelters/hospitals, task 1.3) and, for
    EACH village, resolves exactly three targets — matching task 2.4's literal wording
    ("the district HQ / nearest hospital / nearest shelter", per village, not "every hospital in
    the AOI"): the district HQ (the AOI's own centre, config.AoiConfig.center_lat/lon — Aizawl
    town IS the seat of Aizawl district, a real fact, not a placeholder), that village's
    straight-line-nearest hospital, and that village's straight-line-nearest shelter. Every point
    (village/hospital/shelter/HQ) is then snapped onto its nearest road-graph node by straight-
    line distance.

    Two coarse approximations, both documented rather than silently made precise-looking:
      - "nearest" hospital/shelter is by straight-line distance to the VILLAGE POINT, not by
        routed road distance — a village's actual closest-by-road destination could differ from
        its closest-as-the-crow-flies one. Refining this to a routed nearest-destination query
        is a natural improvement, not attempted here (it would need a full all-pairs or
        multi-source shortest-path pass, more machinery than this task's scope needs).
      - snapping a point onto its nearest road-graph NODE (not the nearest point on the nearest
        EDGE) can occasionally pick a node slightly further down a road than the true closest
        access point. Same category of approximation build_grid.py already makes for
        distance-to-road (task 1.2)."""
    import geopandas as gpd
    from shapely.geometry import Point
    from shapely.strtree import STRtree

    from app.config import get_aoi

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
    hospitals_gdf = gpd.read_file(exposure_path, layer="hospitals")
    shelters_gdf = gpd.read_file(exposure_path, layer="shelters")

    aoi = get_aoi(aoi_id)
    hq_target = IsolationTarget(
        kind="district_hq",
        target_id=f"hq_{aoi_id}",
        node_id=_nearest_node(Point(aoi.center_lon, aoi.center_lat)),
    )

    def _nearest_row(gdf: gpd.GeoDataFrame, pt: Point):
        # Degree-based distance (same documented approximation as impact/priority.py's shelter-
        # distance calculation) — fine for picking the argmin (nearest by degrees ~= nearest by
        # metres at this AOI's small extent and near-constant latitude), not for reporting an
        # actual distance value, which this function never does.
        if gdf.empty:
            return None
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", category=UserWarning)
            idx = gdf.geometry.distance(pt).idxmin()
        return gdf.loc[idx]

    villages: list[VillageNode] = []
    targets_by_village: dict[str, list[IsolationTarget]] = {}
    for _, row in villages_gdf.iterrows():
        village_id = f"v_{row.osm_id}"
        villages.append(
            VillageNode(
                village_id=village_id,
                name=row.get("name") or "unnamed",
                population=int(round(row.get("population_worldpop_est") or 0)),
                node_id=_nearest_node(row.geometry),
            )
        )

        village_targets = [hq_target]
        nearest_hospital = _nearest_row(hospitals_gdf, row.geometry)
        if nearest_hospital is not None:
            village_targets.append(
                IsolationTarget(
                    kind="hospital",
                    target_id=f"hospital_{nearest_hospital.osm_id}",
                    node_id=_nearest_node(nearest_hospital.geometry),
                )
            )
        nearest_shelter = _nearest_row(shelters_gdf, row.geometry)
        if nearest_shelter is not None:
            village_targets.append(
                IsolationTarget(
                    kind="shelter",
                    target_id=f"shelter_{nearest_shelter.osm_id}",
                    node_id=_nearest_node(nearest_shelter.geometry),
                )
            )
        targets_by_village[village_id] = village_targets

    return villages, targets_by_village
