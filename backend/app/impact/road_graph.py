"""impact/road_graph.py — BUILD_PLAN.md task 2.3.

Spatial join of runout envelopes (impact/runout.py) onto road edges (scripts/build_road_graph.py,
task 2.1): each edge gets a `p_blocked` probability, derived from the MAXIMUM `p_fail` among every
runout envelope that intersects it (BUILD_PLAN.md task 2.3's own wording: "derived from the
max/aggregated p_fail of intersecting envelopes" — max, not sum, so one severely-failing cell
whose runout crosses a road is enough to flag it, and stacking multiple weak/unlikely envelopes
over the same edge doesn't manufacture false certainty the way summing would).

BRIDGES get separate, higher-severity treatment (BUILD_PLAN.md task 2.3's own instruction): a
LOWER severance threshold (config.P_CRIT_BRIDGE < config.P_CRIT_ROAD) — see config.py's comment
for the full rationale, which cites the Punapuzha bridge collapse at Mundakkai, Wayanad (30 Jul
2024) as the real-world case motivating this design (NOT an Aizawl-specific event; Aizawl's own
exposure.gpkg currently has 0 `man_made=bridge` point features per task 1.3 — this module's
bridge handling instead comes from the road graph's own `bridge=yes` way tag, a separate and
better-populated OSM tag; see scripts/build_road_graph.py).

Pure function over (RoadEdge, list[RunoutEnvelope]) — no LIVE/REPLAY awareness (CLAUDE.md §2), no
file I/O of its own. `load_road_graph()` below reads the pickled NetworkX graph
scripts/build_road_graph.py produced (task 2.1) and is exercised separately from the pure spatial-
join logic, same split as impact/runout.py's `load_cell_terrain()`.

CRS NOTE (see impact/runout.py's own note): this module's pure functions require `edge.geometry`
and every `RunoutEnvelope.geometry` to already be in the SAME coordinate system — they do not
reproject anything themselves. Real callers: road-graph edges come out of
scripts/build_road_graph.py in WGS84 (lon/lat, straight from OSM), so runout envelopes must be
run through `impact.runout.project_envelope_to_wgs84()` first before being passed in here.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from shapely.geometry import LineString, shape
from shapely.strtree import STRtree

from app.config import P_CRIT_BRIDGE, P_CRIT_ROAD
from app.schemas.impact import RoadSegmentRisk, RunoutEnvelope


@dataclass(frozen=True)
class RoadEdge:
    """The subset of a build_road_graph.py edge this module needs — deliberately independent of
    NetworkX so the pure spatial-join function below can be unit-tested with a handful of plain
    RoadEdge objects and no graph library at all."""

    edge_id: str
    name: str | None
    highway_class: str
    is_bridge: bool
    geometry: LineString


def compute_road_segment_risk(
    edge: RoadEdge,
    envelopes: list[RunoutEnvelope],
    *,
    p_crit_road: float = P_CRIT_ROAD,
    p_crit_bridge: float = P_CRIT_BRIDGE,
) -> RoadSegmentRisk:
    """Every edge gets a RoadSegmentRisk (not just the ones some envelope actually touches) —
    frontend task 2.7 colours the WHOLE road layer by `p_blocked`, so an edge nothing intersects
    must still come back with `p_blocked=0.0, severed=False`, not be silently absent."""
    contributing = [
        env for env in envelopes if edge.geometry.intersects(shape(env.geometry))
    ]
    p_blocked = max((env.p_fail for env in contributing), default=0.0)
    p_crit = p_crit_bridge if edge.is_bridge else p_crit_road

    return RoadSegmentRisk(
        edge_id=edge.edge_id,
        name=edge.name,
        highway_class=edge.highway_class,
        is_bridge=edge.is_bridge,
        p_blocked=p_blocked,
        severed=p_blocked > p_crit,
        contributing_cells=[env.source_cell_id for env in contributing],
    )


def compute_road_segment_risks(
    edges: list[RoadEdge],
    envelopes: list[RunoutEnvelope],
    **kwargs,
) -> list[RoadSegmentRisk]:
    """Batch form of `compute_road_segment_risk`, using an STRtree so this stays usable on a
    real Aizawl-sized graph (thousands of edges) instead of an O(edges * envelopes) scan — same
    spatial-indexing pattern scripts/build_grid.py already uses for distance-to-road."""
    if not envelopes:
        return [compute_road_segment_risk(edge, [], **kwargs) for edge in edges]

    envelope_geoms = [shape(env.geometry) for env in envelopes]
    tree = STRtree(envelope_geoms)

    risks = []
    for edge in edges:
        candidate_idx = tree.query(edge.geometry, predicate="intersects")
        candidates = [envelopes[i] for i in candidate_idx]
        risks.append(compute_road_segment_risk(edge, candidates, **kwargs))
    return risks


# =================================================================================================
# Loader: the real Aizawl road graph from data/osm/<aoi>_graph.pkl. Exercised by an
# integration-style test, kept separate from the pure functions above so those stay testable
# without networkx/a real AOI/a built graph on disk.
# =================================================================================================
def load_road_graph(aoi_id: str, repo_root: Path | None = None):
    """Returns the pickled `networkx.MultiDiGraph` scripts/build_road_graph.py (task 2.1) wrote.
    Only needs `networkx`/`pickle` to unpickle — never imports `osmnx` (CLAUDE.md §6 / task 2.1:
    "OSMnx runs only [in that script], never at request time")."""
    import pickle

    root = repo_root or Path(__file__).resolve().parents[3]
    graph_path = root / "data" / "osm" / f"{aoi_id}_graph.pkl"
    if not graph_path.is_file():
        raise FileNotFoundError(
            f"{graph_path} not found — run `python scripts/build_road_graph.py --aoi {aoi_id}` first"
        )
    with graph_path.open("rb") as f:
        return pickle.load(f)


def road_edges_from_graph(graph) -> list[RoadEdge]:
    """Extracts plain RoadEdge objects (WGS84 lon/lat geometry) from a graph loaded by
    `load_road_graph`. Reconstructs a straight-line geometry for edges that had no stored curved
    `geometry` attribute — identical fallback to scripts/build_road_graph.py's own GeoJSON writer,
    so the two artifacts (`.pkl` and `.geojson`) agree on edge shape."""
    edges = []
    for u, v, key, data in graph.edges(keys=True, data=True):
        geometry = data.get("geometry")
        if geometry is None:
            u_data, v_data = graph.nodes[u], graph.nodes[v]
            geometry = LineString([(u_data["x"], u_data["y"]), (v_data["x"], v_data["y"])])
        edges.append(
            RoadEdge(
                edge_id=data["edge_id"],
                name=data.get("name"),
                highway_class=data.get("highway_class", "unclassified"),
                is_bridge=bool(data.get("is_bridge", False)),
                geometry=geometry,
            )
        )
    return edges
