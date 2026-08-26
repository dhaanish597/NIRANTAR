"""Contract test for decision/routing.py (BUILD_PLAN.md task 3.1)."""
from __future__ import annotations

import networkx as nx
import pytest
from shapely.geometry import LineString

from app.decision.routing import (
    ShelterCandidate,
    build_reference_graph,
    build_routable_graph,
    direct_route_avoided_roads,
    edge_cost,
    find_best_shelter_route,
    find_safe_route,
)
from app.schemas.impact import RoadSegmentRisk


def make_risk(edge_id: str, p_blocked: float, severed: bool, name=None, ref=None) -> RoadSegmentRisk:
    return RoadSegmentRisk(
        edge_id=edge_id, name=name, highway_class="trunk", is_bridge=False,
        p_blocked=p_blocked, severed=severed, contributing_cells=[],
    )


def multi_di_graph(nodes: dict, edges: list[tuple]) -> nx.MultiDiGraph:
    """nodes: {node_id: (x, y)}. edges: list of (u, v, edge_id, length_m, name, ref, geometry)."""
    g = nx.MultiDiGraph()
    for n, (x, y) in nodes.items():
        g.add_node(n, x=x, y=y)
    for u, v, edge_id, length_m, name, ref, geometry in edges:
        g.add_edge(
            u, v, edge_id=edge_id, highway_class="trunk", is_bridge=False,
            ref=ref, name=name, length_m=length_m, geometry=geometry,
        )
    return g


class TestEdgeCost:
    def test_matches_claude_md_formula(self):
        assert edge_cost(100.0, 0.5, 0.0, alpha=3.0, beta=1.0) == pytest.approx(250.0)

    def test_slope_term_contributes_when_supplied(self):
        assert edge_cost(100.0, 0.0, 0.4, alpha=3.0, beta=1.0) == pytest.approx(140.0)

    def test_zero_p_fail_and_slope_is_plain_length(self):
        assert edge_cost(250.0, 0.0, 0.0) == pytest.approx(250.0)


class TestBuildRoutableGraph:
    def test_severed_edge_is_removed_entirely_not_just_weighted_high(self):
        g = multi_di_graph(
            {"u": (0, 0), "v": (1, 1)},
            [("u", "v", "e1", 100.0, "NH-6", "NH-6", None)],
        )
        risks = {"e1": make_risk("e1", 0.95, True)}
        routable = build_routable_graph(g, risks)
        assert not routable.has_edge("u", "v")

    def test_non_severed_edge_survives_with_computed_cost(self):
        g = multi_di_graph({"u": (0, 0), "v": (1, 1)}, [("u", "v", "e1", 100.0, None, None, None)])
        risks = {"e1": make_risk("e1", 0.5, False)}
        routable = build_routable_graph(g, risks, alpha=3.0, beta=1.0)
        data = routable.get_edge_data("u", "v")
        assert data["cost"] == pytest.approx(edge_cost(100.0, 0.5, 0.0, alpha=3.0, beta=1.0))

    def test_edge_with_no_risk_entry_defaults_to_p_blocked_zero(self):
        g = multi_di_graph({"u": (0, 0), "v": (1, 1)}, [("u", "v", "e1", 100.0, None, None, None)])
        routable = build_routable_graph(g, {})
        assert routable.get_edge_data("u", "v")["cost"] == pytest.approx(100.0)

    def test_collapses_parallel_edges_keeping_the_shorter(self):
        g = multi_di_graph(
            {"u": (0, 0), "v": (1, 1)},
            [
                ("u", "v", "long", 500.0, None, None, None),
                ("u", "v", "short", 100.0, None, None, None),
            ],
        )
        routable = build_routable_graph(g, {})
        assert routable.number_of_edges() == 1
        assert routable.get_edge_data("u", "v")["length_m"] == 100.0

    def test_slope_norm_is_applied_per_edge_when_supplied(self):
        g = multi_di_graph({"u": (0, 0), "v": (1, 1)}, [("u", "v", "e1", 100.0, None, None, None)])
        routable = build_routable_graph(g, {}, slope_norm_by_edge_id={"e1": 0.5}, alpha=3.0, beta=2.0)
        assert routable.get_edge_data("u", "v")["cost"] == pytest.approx(edge_cost(100.0, 0.0, 0.5, alpha=3.0, beta=2.0))


class TestBuildReferenceGraph:
    def test_keeps_severed_edges_flagged_rather_than_removing_them(self):
        g = multi_di_graph({"u": (0, 0), "v": (1, 1)}, [("u", "v", "e1", 100.0, None, "NH-6", None)])
        risks = {"e1": make_risk("e1", 0.95, True, ref="NH-6")}
        reference = build_reference_graph(g, risks)
        assert reference.has_edge("u", "v")
        assert reference.get_edge_data("u", "v")["severed"] is True


class TestDirectRouteAvoidedRoads:
    def test_lists_severed_named_roads_on_the_direct_path(self):
        g = multi_di_graph(
            {"u": (0, 0), "v": (1, 1)},
            [("u", "v", "e1", 10.0, None, "NH-6", None)],
        )
        reference = build_reference_graph(g, {"e1": make_risk("e1", 0.9, True, ref="NH-6")})
        assert direct_route_avoided_roads(reference, "u", "v") == ["NH-6"]

    def test_no_severance_on_direct_path_means_nothing_avoided(self):
        g = multi_di_graph({"u": (0, 0), "v": (1, 1)}, [("u", "v", "e1", 10.0, None, "SH-1", None)])
        reference = build_reference_graph(g, {"e1": make_risk("e1", 0.1, False, ref="SH-1")})
        assert direct_route_avoided_roads(reference, "u", "v") == []

    def test_unreachable_pair_returns_empty_list_not_an_error(self):
        g = nx.MultiDiGraph()
        g.add_node("u", x=0, y=0)
        g.add_node("v", x=1, y=1)
        reference = build_reference_graph(g, {})
        assert direct_route_avoided_roads(reference, "u", "v") == []

    def test_deduplicates_repeated_road_name(self):
        # two consecutive severed segments both named "NH-6"
        g = multi_di_graph(
            {"u": (0, 0), "mid": (1, 0), "v": (2, 0)},
            [
                ("u", "mid", "e1", 10.0, None, "NH-6", None),
                ("mid", "v", "e2", 10.0, None, "NH-6", None),
            ],
        )
        risks = {"e1": make_risk("e1", 0.9, True, ref="NH-6"), "e2": make_risk("e2", 0.9, True, ref="NH-6")}
        reference = build_reference_graph(g, risks)
        assert direct_route_avoided_roads(reference, "u", "v") == ["NH-6"]


class TestFindSafeRoute:
    def test_routes_around_a_severed_direct_edge_via_a_detour(self):
        g = multi_di_graph(
            {"u": (0, 0), "v": (0, 10), "mid": (5, 5)},
            [
                ("u", "v", "e_direct", 10.0, None, "NH-6", None),
                ("u", "mid", "e_a", 100.0, None, None, None),
                ("mid", "v", "e_b", 100.0, None, None, None),
            ],
        )
        risks = {
            "e_direct": make_risk("e_direct", 0.9, True, ref="NH-6"),
            "e_a": make_risk("e_a", 0.1, False),
            "e_b": make_risk("e_b", 0.1, False),
        }
        routable = build_routable_graph(g, risks)
        route = find_safe_route(routable, "u", "v")
        assert route is not None
        assert route.distance_m == pytest.approx(200.0)  # forced onto the 100+100 detour

    def test_returns_none_when_target_totally_unreachable(self):
        g = multi_di_graph({"u": (0, 0), "v": (1, 1)}, [("u", "v", "e1", 10.0, None, None, None)])
        risks = {"e1": make_risk("e1", 0.95, True)}
        routable = build_routable_graph(g, risks)  # the only edge is severed -> removed
        assert find_safe_route(routable, "u", "v") is None

    def test_cost_weighting_prefers_lower_risk_over_shorter_distance(self):
        # Direct edge is short (50m) but high p_blocked (0.8, below severance so still present);
        # detour is longer (2x50=100m) but essentially risk-free. With alpha=3 the direct edge's
        # cost is 50*(1+3*0.8)=170, more than the detour's 100 -> the router should prefer the
        # detour on cost even though it's physically longer.
        g = multi_di_graph(
            {"u": (0, 0), "v": (0, 10), "mid": (5, 5)},
            [
                ("u", "v", "e_direct", 50.0, None, None, None),
                ("u", "mid", "e_a", 50.0, None, None, None),
                ("mid", "v", "e_b", 50.0, None, None, None),
            ],
        )
        risks = {
            "e_direct": make_risk("e_direct", 0.8, False),
            "e_a": make_risk("e_a", 0.0, False),
            "e_b": make_risk("e_b", 0.0, False),
        }
        routable = build_routable_graph(g, risks, alpha=3.0)
        route = find_safe_route(routable, "u", "v")
        assert route.distance_m == pytest.approx(100.0)  # took the detour, not the direct 50m edge

    def test_route_geometry_orients_stored_linestrings_to_travel_direction(self):
        forward_line = LineString([(0.0, 0.0), (0.5, 0.5), (1.0, 1.0)])
        g = multi_di_graph(
            {"u": (0.0, 0.0), "v": (1.0, 1.0)},
            [("u", "v", "e1", 10.0, None, None, forward_line)],
        )
        routable = build_routable_graph(g, {})

        forward_route = find_safe_route(routable, "u", "v")
        assert forward_route.geometry["coordinates"][0] == [0.0, 0.0]
        assert forward_route.geometry["coordinates"][-1] == [1.0, 1.0]

        backward_route = find_safe_route(routable, "v", "u")
        assert backward_route.geometry["coordinates"][0] == [1.0, 1.0]
        assert backward_route.geometry["coordinates"][-1] == [0.0, 0.0]

    def test_route_geometry_falls_back_to_straight_line_when_no_stored_geometry(self):
        g = multi_di_graph({"u": (0.0, 0.0), "v": (2.0, 2.0)}, [("u", "v", "e1", 10.0, None, None, None)])
        routable = build_routable_graph(g, {})
        route = find_safe_route(routable, "u", "v")
        assert route.geometry == {"type": "LineString", "coordinates": [[0.0, 0.0], [2.0, 2.0]]}


class TestFindBestShelterRoute:
    def _graph_two_shelters(self):
        g = multi_di_graph(
            {"village": (0, 0), "near": (1, 0), "far": (0, 5), "unreachable": (99, 99)},
            [
                ("village", "near", "e1", 100.0, None, None, None),
                ("village", "far", "e2", 500.0, None, None, None),
            ],
        )
        return g

    def test_picks_reachable_candidate_when_another_is_unreachable(self):
        g = self._graph_two_shelters()
        routable = build_routable_graph(g, {})
        reference = build_reference_graph(g, {})
        candidates = [
            ShelterCandidate("s_unreachable", "Unreachable Shelter", "unreachable"),
            ShelterCandidate("s_near", "Near Shelter", "near"),
        ]
        route = find_best_shelter_route("v1", "village", candidates, routable, reference)
        assert route is not None
        assert route.shelter_id == "s_near"

    def test_prefers_lower_cost_when_capacity_unknown_for_both(self):
        g = self._graph_two_shelters()
        routable = build_routable_graph(g, {})
        reference = build_reference_graph(g, {})
        candidates = [
            ShelterCandidate("s_far", "Far Shelter", "far"),
            ShelterCandidate("s_near", "Near Shelter", "near"),
        ]
        route = find_best_shelter_route("v1", "village", candidates, routable, reference)
        assert route.shelter_id == "s_near"

    def test_capacity_aware_prefers_shelter_with_room_over_a_full_nearer_one(self):
        g = self._graph_two_shelters()
        routable = build_routable_graph(g, {})
        reference = build_reference_graph(g, {})
        candidates = [
            ShelterCandidate("s_near_full", "Near Full Shelter", "near", capacity=50, occupancy=50),
            ShelterCandidate("s_far_room", "Far Shelter With Room", "far", capacity=50, occupancy=10),
        ]
        route = find_best_shelter_route("v1", "village", candidates, routable, reference)
        assert route.shelter_id == "s_far_room"
        assert route.shelter_capacity_ok is True

    def test_no_reachable_candidates_returns_none(self):
        g = nx.MultiDiGraph()
        g.add_node("village", x=0, y=0)
        g.add_node("island", x=9, y=9)
        routable = build_routable_graph(g, {})
        reference = build_reference_graph(g, {})
        candidates = [ShelterCandidate("s1", "Island Shelter", "island")]
        assert find_best_shelter_route("v1", "village", candidates, routable, reference) is None

    def test_evacuation_route_fields_populated_correctly(self):
        g = self._graph_two_shelters()
        routable = build_routable_graph(g, {})
        reference = build_reference_graph(g, {})
        candidates = [ShelterCandidate("s_near", "Near Shelter", "near")]
        route = find_best_shelter_route("v1", "village", candidates, routable, reference, walking_speed_kmh=6.0)
        assert route.village_id == "v1"
        assert route.shelter_name == "Near Shelter"
        assert route.distance_m == pytest.approx(100.0)
        # 100m at 6 km/h = 0.1/6 h = 1 minute (rounded)
        assert route.est_walk_minutes == 1
        assert route.shelter_capacity_ok is True
        assert route.geometry["type"] == "LineString"

    def test_avoided_roads_reflect_the_chosen_shelters_own_direct_route(self):
        g = multi_di_graph(
            {"village": (0, 0), "shelter": (0, 10), "mid": (5, 5)},
            [
                ("village", "shelter", "e_direct", 10.0, None, "NH-6", None),
                ("village", "mid", "e_a", 100.0, None, None, None),
                ("mid", "shelter", "e_b", 100.0, None, None, None),
            ],
        )
        risks = {
            "e_direct": make_risk("e_direct", 0.9, True, ref="NH-6"),
            "e_a": make_risk("e_a", 0.0, False),
            "e_b": make_risk("e_b", 0.0, False),
        }
        routable = build_routable_graph(g, risks)
        reference = build_reference_graph(g, risks)
        candidates = [ShelterCandidate("s1", "The Shelter", "shelter")]
        route = find_best_shelter_route("v1", "village", candidates, routable, reference)
        assert route.avoided_roads == ["NH-6"]
