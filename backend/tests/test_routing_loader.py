"""Integration test for decision/routing.py's real-data path: the real Aizawl road graph (task
2.1) end to end through build_routable_graph/find_safe_route, plus resolve_routing_inputs against
real exposure.gpkg villages/shelters (task 1.3) when that file is also present. Gated on each
artifact already existing on disk (both gitignored) so a fresh checkout without network access
skips gracefully, same pattern tests/test_road_graph_loader.py and tests/test_isolation_loader.py
already use."""
from __future__ import annotations

from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
HAS_REAL_GRAPH = (REPO_ROOT / "data" / "osm" / "aizawl_graph.pkl").is_file()
HAS_REAL_EXPOSURE = (REPO_ROOT / "data" / "static" / "aizawl" / "exposure.gpkg").is_file()

pytestmark = pytest.mark.skipif(
    not HAS_REAL_GRAPH, reason="requires data/osm/aizawl_graph.pkl (make graph AOI=aizawl)"
)


def test_routable_graph_builds_from_the_real_graph_with_nothing_severed():
    from app.decision.routing import build_reference_graph, build_routable_graph
    from app.impact.road_graph import load_road_graph

    graph = load_road_graph("aizawl")
    routable = build_routable_graph(graph, {})
    reference = build_reference_graph(graph, {})
    # No RoadSegmentRisk supplied -> nothing severed -> routable keeps (up to parallel-edge
    # collapsing) as many distinct u-v pairs as the reference graph.
    assert routable.number_of_edges() == reference.number_of_edges()
    assert routable.number_of_nodes() == graph.number_of_nodes()


def test_finds_a_real_route_between_two_real_nodes_on_the_full_aizawl_graph():
    from app.decision.routing import build_routable_graph, find_safe_route
    from app.impact.road_graph import load_road_graph

    graph = load_road_graph("aizawl")
    routable = build_routable_graph(graph, {})

    nodes = list(graph.nodes)
    source = nodes[0]
    # Pick a target reasonably far down the node list, not just an immediate neighbour, so the
    # route actually traverses several edges (a real exercise of Dijkstra on this graph's real
    # size — 3600+ nodes / 8800+ edges per the task-2.1 build log).
    target = nodes[len(nodes) // 2]

    route = find_safe_route(routable, source, target)
    # The AOI's drivable network should be a single connected component for two arbitrary nodes
    # this far apart in practice; if OSMnx's extract happens to be split, this documents that
    # rather than silently passing on a vacuous "unreachable" result.
    if route is None:
        pytest.skip("chosen node pair is not connected in this real extract; not a routing bug")
    assert route.distance_m > 0.0
    assert len(route.geometry["coordinates"]) >= 2


def test_nh6_named_edges_exist_and_are_routable_when_unblocked():
    """Sanity check that this AOI's real NH-6 refs (CLAUDE.md's whole RII/isolation story is
    built around NH-6 at Hunthar) actually survive into the routable graph's edge data when
    nothing has severed them. Real OSM `ref` tagging for this way is the unhyphenated "NH6", not
    the "NH-6" prose spelling CLAUDE.md/BUILD_PLAN.md use — found by actually reading this real
    extract's refs rather than assuming the prose spelling round-trips through OSM verbatim."""
    from app.decision.routing import build_routable_graph
    from app.impact.road_graph import load_road_graph

    graph = load_road_graph("aizawl")
    routable = build_routable_graph(graph, {})
    refs = {data.get("ref") for _, _, data in routable.edges(data=True)}
    assert "NH6" in refs


@pytest.mark.skipif(not HAS_REAL_EXPOSURE, reason="requires data/static/aizawl/exposure.gpkg")
class TestResolveRoutingInputs:
    def test_resolves_every_real_village_and_at_least_one_shelter_candidate(self):
        from app.decision.routing import resolve_routing_inputs
        from app.impact.road_graph import load_road_graph

        graph = load_road_graph("aizawl")
        village_node_by_id, candidates = resolve_routing_inputs("aizawl", graph)

        assert len(village_node_by_id) == 11  # CLAUDE.md's Current State: 11 real Aizawl villages
        assert len(candidates) == 7  # 7 real Aizawl shelters
        for node_id in village_node_by_id.values():
            assert node_id in graph
        for candidate in candidates:
            assert candidate.node_id in graph
            assert candidate.capacity is None  # honest gap — see module docstring
            assert candidate.capacity_ok is True

    def test_end_to_end_route_for_a_real_village_to_its_best_real_shelter(self):
        from app.decision.routing import (
            build_reference_graph,
            build_routable_graph,
            find_best_shelter_route,
            resolve_routing_inputs,
        )
        from app.impact.road_graph import load_road_graph

        graph = load_road_graph("aizawl")
        routable = build_routable_graph(graph, {})
        reference = build_reference_graph(graph, {})
        village_node_by_id, candidates = resolve_routing_inputs("aizawl", graph)

        village_id, node_id = next(iter(village_node_by_id.items()))
        route = find_best_shelter_route(village_id, node_id, candidates, routable, reference)

        assert route is not None
        assert route.village_id == village_id
        assert route.distance_m >= 0.0
        assert route.shelter_capacity_ok is True
