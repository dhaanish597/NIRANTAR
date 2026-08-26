"""Contract test for impact/road_graph.py (BUILD_PLAN.md task 2.3)."""
from __future__ import annotations

from shapely.geometry import LineString

from app.config import P_CRIT_BRIDGE, P_CRIT_ROAD
from app.impact.road_graph import RoadEdge, compute_road_segment_risk, compute_road_segment_risks
from app.schemas.impact import RunoutEnvelope


def make_edge(edge_id="e1", is_bridge=False, coords=((0, 0), (10, 0))) -> RoadEdge:
    return RoadEdge(
        edge_id=edge_id, name="NH-6", highway_class="trunk", is_bridge=is_bridge,
        geometry=LineString(coords),
    )


def make_envelope(p_fail: float, coords, cell_id="c1") -> RunoutEnvelope:
    ring = list(coords) + [coords[0]]
    return RunoutEnvelope(
        source_cell_id=cell_id,
        geometry={"type": "Polygon", "coordinates": [ring]},
        p_fail=p_fail,
        method="test",
    )


class TestNoIntersection:
    def test_no_envelopes_gives_zero_risk(self):
        risk = compute_road_segment_risk(make_edge(), [])
        assert risk.p_blocked == 0.0
        assert risk.severed is False
        assert risk.contributing_cells == []

    def test_non_intersecting_envelope_is_ignored(self):
        far_envelope = make_envelope(0.99, [(100, 100), (110, 100), (110, 110), (100, 110)])
        risk = compute_road_segment_risk(make_edge(), [far_envelope])
        assert risk.p_blocked == 0.0
        assert risk.severed is False


class TestIntersectionUsesMaxNotSum:
    def test_p_blocked_is_max_of_intersecting_envelopes(self):
        edge = make_edge(coords=((0, -5), (0, 5)))  # vertical line through the origin area
        low = make_envelope(0.3, [(-2, -2), (2, -2), (2, 2), (-2, 2)], cell_id="low")
        high = make_envelope(0.8, [(-1, -1), (1, -1), (1, 1), (-1, 1)], cell_id="high")
        risk = compute_road_segment_risk(edge, [low, high])
        assert risk.p_blocked == 0.8  # max, not 1.1 (which sum would give)
        assert set(risk.contributing_cells) == {"low", "high"}


class TestSeveranceThresholds:
    def test_ordinary_road_uses_road_threshold(self):
        edge = make_edge(is_bridge=False, coords=((0, -5), (0, 5)))
        just_over = make_envelope(P_CRIT_ROAD + 0.01, [(-2, -2), (2, -2), (2, 2), (-2, 2)])
        just_under = make_envelope(P_CRIT_ROAD - 0.01, [(-2, -2), (2, -2), (2, 2), (-2, 2)])
        assert compute_road_segment_risk(edge, [just_over]).severed is True
        assert compute_road_segment_risk(edge, [just_under]).severed is False

    def test_bridge_uses_lower_bridge_threshold(self):
        assert P_CRIT_BRIDGE < P_CRIT_ROAD  # the whole point of task 2.3's bridge handling
        edge = make_edge(is_bridge=True, coords=((0, -5), (0, 5)))
        between = make_envelope((P_CRIT_BRIDGE + P_CRIT_ROAD) / 2, [(-2, -2), (2, -2), (2, 2), (-2, 2)])
        risk = compute_road_segment_risk(edge, [between])
        assert risk.is_bridge is True
        assert risk.severed is True  # would NOT be severed at the same p_blocked on an ordinary road
        ordinary_edge = make_edge(is_bridge=False, coords=((0, -5), (0, 5)))
        assert compute_road_segment_risk(ordinary_edge, [between]).severed is False


class TestBatchMatchesSingleAndIndexesEveryEdge:
    def test_every_edge_gets_a_result_even_with_no_envelopes(self):
        edges = [make_edge("e1"), make_edge("e2", coords=((50, 50), (60, 50)))]
        risks = compute_road_segment_risks(edges, [])
        assert {r.edge_id for r in risks} == {"e1", "e2"}
        assert all(r.p_blocked == 0.0 and not r.severed for r in risks)

    def test_batch_str_tree_path_matches_single_edge_path(self):
        edges = [make_edge("e1", coords=((0, -5), (0, 5))), make_edge("e2", coords=((100, 100), (110, 100)))]
        envelope = make_envelope(0.9, [(-2, -2), (2, -2), (2, 2), (-2, 2)])
        batch_risks = {r.edge_id: r for r in compute_road_segment_risks(edges, [envelope])}
        single_risk = compute_road_segment_risk(edges[0], [envelope])
        assert batch_risks["e1"].p_blocked == single_risk.p_blocked
        assert batch_risks["e1"].severed == single_risk.severed
        assert batch_risks["e2"].p_blocked == 0.0
