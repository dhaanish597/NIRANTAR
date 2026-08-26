"""Contract test for impact/isolation.py (BUILD_PLAN.md task 2.4, the Road Isolation Index)."""
from __future__ import annotations

import networkx as nx
import pytest

from app.config import BRIDGE_CLEARANCE_MULTIPLIER, ROAD_CLEARANCE_HOURS_BY_CLASS
from app.impact.isolation import (
    IsolationTarget,
    VillageNode,
    _bottleneck_path_risk,
    _to_simple_undirected_with_risk,
    compute_all_village_isolations,
    compute_village_isolation,
)
from app.schemas.impact import RoadSegmentRisk


def make_risk(edge_id: str, p_blocked: float, severed: bool, is_bridge=False, highway_class="trunk") -> RoadSegmentRisk:
    return RoadSegmentRisk(
        edge_id=edge_id, name=None, highway_class=highway_class, is_bridge=is_bridge,
        p_blocked=p_blocked, severed=severed, contributing_cells=[],
    )


def line_graph_risk_augmented(edge_specs: list[tuple]) -> nx.Graph:
    """edge_specs: list of (u, v, edge_id, length_m, p_blocked, severed, is_bridge, highway_class)."""
    g = nx.Graph()
    for u, v, edge_id, length_m, p_blocked, severed, is_bridge, highway_class in edge_specs:
        g.add_edge(
            u, v, edge_id=edge_id, length_m=length_m, p_blocked=p_blocked, severed=severed,
            is_bridge=is_bridge, highway_class=highway_class,
        )
    return g


class TestBottleneckPathRisk:
    def test_unreachable_target_gives_risk_one(self):
        g = nx.Graph()
        g.add_node("isolated_node")
        g.add_edge("v", "hq", p_blocked=0.1)
        assert _bottleneck_path_risk(g, "v", "isolated_node") == 1.0

    def test_same_source_and_target_is_zero_risk(self):
        g = nx.Graph()
        g.add_node("v")
        assert _bottleneck_path_risk(g, "v", "v") == 0.0

    def test_single_edge_risk_equals_that_edges_p_blocked(self):
        g = nx.Graph()
        g.add_edge("v", "hq", p_blocked=0.4)
        assert _bottleneck_path_risk(g, "v", "hq") == 0.4

    def test_picks_the_lower_bottleneck_of_two_alternative_paths(self):
        # v -> hq direct (risky, 0.9); v -> mid -> hq (both edges low-risk, 0.2/0.3) => best=0.3
        g = nx.Graph()
        g.add_edge("v", "hq", p_blocked=0.9)
        g.add_edge("v", "mid", p_blocked=0.2)
        g.add_edge("mid", "hq", p_blocked=0.3)
        assert _bottleneck_path_risk(g, "v", "hq") == pytest.approx(0.3)

    def test_bottleneck_is_the_max_edge_on_a_path_not_the_sum(self):
        g = nx.Graph()
        g.add_edge("v", "mid", p_blocked=0.1)
        g.add_edge("mid", "hq", p_blocked=0.6)
        assert _bottleneck_path_risk(g, "v", "hq") == pytest.approx(0.6)  # not 0.7


class TestToSimpleUndirectedWithRisk:
    def test_collapses_multidigraph_to_undirected_keeping_shortest_parallel_edge(self):
        g = nx.MultiDiGraph()
        g.add_node(1, x=0.0, y=0.0)
        g.add_node(2, x=1.0, y=1.0)
        g.add_edge(1, 2, edge_id="long", length_m=500.0, highway_class="trunk", is_bridge=False)
        g.add_edge(1, 2, edge_id="short", length_m=100.0, highway_class="trunk", is_bridge=False)
        g.add_edge(2, 1, edge_id="reverse", length_m=100.0, highway_class="trunk", is_bridge=False)

        simple = _to_simple_undirected_with_risk(g, {})
        assert simple.number_of_edges() == 1
        data = simple.get_edge_data(1, 2)
        assert data["length_m"] == 100.0
        assert data["p_blocked"] == 0.0  # no entry in edge_risk_by_id -> defaults, not fabricated
        assert data["severed"] is False

    def test_merges_in_road_segment_risk_by_edge_id(self):
        g = nx.MultiDiGraph()
        g.add_node(1, x=0.0, y=0.0)
        g.add_node(2, x=1.0, y=1.0)
        g.add_edge(1, 2, edge_id="e1", length_m=100.0, highway_class="trunk", is_bridge=False)
        risk = make_risk("e1", p_blocked=0.8, severed=True)

        simple = _to_simple_undirected_with_risk(g, {"e1": risk})
        data = simple.get_edge_data(1, 2)
        assert data["p_blocked"] == 0.8
        assert data["severed"] is True


class TestComputeVillageIsolation:
    def make_village(self, node_id="v"):
        return VillageNode(village_id="v1", name="Test Village", population=500, node_id=node_id)

    def test_not_isolated_when_default_route_to_any_target_is_open(self):
        g = line_graph_risk_augmented([
            ("v", "hq", "e_hq", 100.0, 0.0, False, False, "trunk"),
            ("v", "hospital", "e_hosp", 100.0, 0.9, True, False, "trunk"),
        ])
        targets = [
            IsolationTarget("district_hq", "hq", "hq"),
            IsolationTarget("hospital", "hosp", "hospital"),
        ]
        result = compute_village_isolation(self.make_village(), g, targets)
        assert result.isolated_now is False
        assert result.alternate_route_exists is True
        # severed_links is NOT gated on isolated_now: the hospital route is genuinely blocked
        # even though the village isn't cut off overall (HQ route is fine) — see the
        # `severed_links` code comment in impact/isolation.py for why this is intentional.
        assert result.severed_links == ["e_hosp"]
        # est_duration_hours mirrors severed_links: some route is blocked, so an estimate exists,
        # even though the village overall is not isolated_now.
        assert result.est_duration_hours is not None

    def test_isolated_when_all_default_routes_are_severed_but_alternate_survives(self):
        # v -> hq direct is severed, but v -> mid -> hq is not (so alt_route_exists=True even
        # though the DEFAULT shortest path to hq is blocked and there's only one target).
        g = line_graph_risk_augmented([
            ("v", "hq", "e_direct", 10.0, 0.9, True, False, "trunk"),  # shortest path (len 10)
            ("v", "mid", "e_a", 100.0, 0.1, False, False, "residential"),
            ("mid", "hq", "e_b", 100.0, 0.1, False, False, "residential"),
        ])
        targets = [IsolationTarget("district_hq", "hq", "hq")]
        result = compute_village_isolation(self.make_village(), g, targets)
        assert result.isolated_now is True  # default (shortest) route is severed
        assert result.alternate_route_exists is True  # but a detour still connects
        assert result.severed_links == ["e_direct"]
        assert result.est_duration_hours is not None

    def test_fully_isolated_when_no_path_survives_at_all(self):
        g = line_graph_risk_augmented([
            ("v", "hq", "e_only", 10.0, 0.9, True, False, "trunk"),
        ])
        targets = [IsolationTarget("district_hq", "hq", "hq")]
        result = compute_village_isolation(self.make_village(), g, targets)
        assert result.isolated_now is True
        assert result.alternate_route_exists is False
        assert result.severed_links == ["e_only"]

    def test_p_isolated_is_the_min_bottleneck_risk_across_targets(self):
        g = line_graph_risk_augmented([
            ("v", "hq", "e_hq", 10.0, 0.9, True, False, "trunk"),
            ("v", "shelter", "e_shelter", 10.0, 0.2, False, False, "residential"),
        ])
        targets = [
            IsolationTarget("district_hq", "hq", "hq"),
            IsolationTarget("shelter", "shelter", "shelter"),
        ]
        result = compute_village_isolation(self.make_village(), g, targets)
        assert result.p_isolated == pytest.approx(0.2)  # the safer of the two options

    def test_est_duration_hours_scales_with_road_class_and_bridge_multiplier(self):
        g = line_graph_risk_augmented([
            ("v", "hq", "e_bridge", 10.0, 0.9, True, True, "trunk"),
        ])
        targets = [IsolationTarget("district_hq", "hq", "hq")]
        result = compute_village_isolation(self.make_village(), g, targets)
        expected = ROAD_CLEARANCE_HOURS_BY_CLASS["trunk"] * BRIDGE_CLEARANCE_MULTIPLIER * (1.0 + 0.9)
        assert result.est_duration_hours == pytest.approx(expected)

    def test_village_id_name_population_pass_through(self):
        g = line_graph_risk_augmented([("v", "hq", "e", 10.0, 0.0, False, False, "trunk")])
        targets = [IsolationTarget("district_hq", "hq", "hq")]
        result = compute_village_isolation(self.make_village(), g, targets)
        assert result.village_id == "v1"
        assert result.name == "Test Village"
        assert result.population == 500

    def test_requires_at_least_one_target(self):
        g = nx.Graph()
        with pytest.raises(ValueError):
            compute_village_isolation(self.make_village(), g, [])


class TestComputeAllVillageIsolations:
    def test_batch_uses_per_village_targets(self):
        raw = nx.MultiDiGraph()
        for n in ("v1", "v2", "hq"):
            raw.add_node(n, x=0.0, y=0.0)
        raw.add_edge("v1", "hq", edge_id="e1", length_m=10.0, highway_class="trunk", is_bridge=False)
        raw.add_edge("v2", "hq", edge_id="e2", length_m=10.0, highway_class="trunk", is_bridge=False)

        risks = {
            "e1": make_risk("e1", 0.9, True),
            "e2": make_risk("e2", 0.1, False),
        }
        villages = [
            VillageNode("v1", "Village 1", 100, "v1"),
            VillageNode("v2", "Village 2", 200, "v2"),
        ]
        targets_by_village = {
            "v1": [IsolationTarget("district_hq", "hq", "hq")],
            "v2": [IsolationTarget("district_hq", "hq", "hq")],
        }
        results = {
            r.village_id: r
            for r in compute_all_village_isolations(villages, raw, risks, targets_by_village)
        }
        assert results["v1"].isolated_now is True
        assert results["v2"].isolated_now is False
