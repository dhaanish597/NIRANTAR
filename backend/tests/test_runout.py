"""Contract test for impact/runout.py (BUILD_PLAN.md task 2.2)."""
from __future__ import annotations

import math

import pytest

from app.config import RUNOUT_ANGLE_OF_REACH_DEG, RUNOUT_SPREAD_HALF_ANGLE_DEG, RUNOUT_TRIGGER_P_FAIL
from app.impact.runout import (
    CellTerrain,
    compute_runout_envelope,
    compute_runout_envelopes,
    project_envelope_to_wgs84,
)
from app.schemas.risk import CellRisk


def make_risk(p_fail: float, cell_id: str = "c1") -> CellRisk:
    return CellRisk(
        cell_id=cell_id, p_fail=p_fail, threshold_exceedance=p_fail, confidence=0.5,
        attributions=[], model_version="test",
    )


def make_terrain(
    cell_id: str = "c1", x: float = 0.0, y: float = 0.0, aspect_deg: float | None = 0.0,
    relief_m: float | None = 100.0,
) -> CellTerrain:
    return CellTerrain(cell_id=cell_id, centroid_x=x, centroid_y=y, aspect_deg=aspect_deg, relief_m=relief_m)


class TestTriggerThreshold:
    def test_below_threshold_returns_none(self):
        risk = make_risk(RUNOUT_TRIGGER_P_FAIL - 0.01)
        assert compute_runout_envelope(risk, make_terrain()) is None

    def test_at_threshold_produces_an_envelope(self):
        risk = make_risk(RUNOUT_TRIGGER_P_FAIL)
        envelope = compute_runout_envelope(risk, make_terrain())
        assert envelope is not None
        assert envelope.source_cell_id == "c1"
        assert envelope.p_fail == RUNOUT_TRIGGER_P_FAIL


class TestMissingTerrainDataIsSkippedNotFabricated:
    def test_none_aspect_returns_none(self):
        risk = make_risk(0.9)
        terrain = make_terrain(aspect_deg=None)
        assert compute_runout_envelope(risk, terrain) is None

    def test_none_relief_returns_none(self):
        risk = make_risk(0.9)
        terrain = make_terrain(relief_m=None)
        assert compute_runout_envelope(risk, terrain) is None

    def test_zero_or_negative_relief_returns_none(self):
        risk = make_risk(0.9)
        assert compute_runout_envelope(risk, make_terrain(relief_m=0.0)) is None
        assert compute_runout_envelope(risk, make_terrain(relief_m=-5.0)) is None


class TestCellIdMismatchRaises:
    def test_mismatched_cell_ids_raise(self):
        risk = make_risk(0.9, cell_id="a")
        terrain = make_terrain(cell_id="b")
        with pytest.raises(ValueError):
            compute_runout_envelope(risk, terrain)


class TestGeometry:
    def test_hand_derived_triangle_for_due_north_flow(self):
        """aspect=0 (due north/+y), relief=100m, angle_of_reach=45deg (tan=1) => length=100m.
        spread_half_angle=45deg (tan=1) => half_width=100m. Hand-verified vertices."""
        risk = make_risk(0.9)
        terrain = make_terrain(x=0.0, y=0.0, aspect_deg=0.0, relief_m=100.0)
        envelope = compute_runout_envelope(
            risk, terrain, angle_of_reach_deg=45.0, spread_half_angle_deg=45.0
        )
        ring = envelope.geometry["coordinates"][0]
        assert envelope.geometry["type"] == "Polygon"
        apex, left, right, closing = ring
        assert apex == pytest.approx([0.0, 0.0])
        assert closing == pytest.approx(apex)
        # base center at (0, 100); left/right offset by ±100 on x.
        assert left == pytest.approx([100.0, 100.0])
        assert right == pytest.approx([-100.0, 100.0])

    def test_length_scales_with_relief_via_angle_of_reach(self):
        risk = make_risk(0.9)
        short = compute_runout_envelope(risk, make_terrain(relief_m=50.0), angle_of_reach_deg=45.0)
        long = compute_runout_envelope(risk, make_terrain(relief_m=200.0), angle_of_reach_deg=45.0)
        apex = (0.0, 0.0)

        def base_center_distance(env):
            ring = env.geometry["coordinates"][0]
            left, right = ring[1], ring[2]
            base_center = ((left[0] + right[0]) / 2, (left[1] + right[1]) / 2)
            return math.dist(apex, base_center)

        assert base_center_distance(long) == pytest.approx(4 * base_center_distance(short))

    def test_direction_points_downhill_aspect_east(self):
        """aspect=90 (east) => runout should extend in +x, not +y."""
        risk = make_risk(0.9)
        terrain = make_terrain(aspect_deg=90.0, relief_m=100.0)
        envelope = compute_runout_envelope(risk, terrain, angle_of_reach_deg=45.0, spread_half_angle_deg=10.0)
        ring = envelope.geometry["coordinates"][0]
        left, right = ring[1], ring[2]
        base_center_x = (left[0] + right[0]) / 2
        base_center_y = (left[1] + right[1]) / 2
        assert base_center_x == pytest.approx(100.0, abs=1e-6)
        assert base_center_y == pytest.approx(0.0, abs=1e-6)

    def test_method_string_records_the_constants_used(self):
        risk = make_risk(0.9)
        envelope = compute_runout_envelope(risk, make_terrain(), angle_of_reach_deg=25.0, spread_half_angle_deg=15.0)
        assert "25" in envelope.method
        assert "15" in envelope.method

    def test_default_constants_match_config(self):
        risk = make_risk(RUNOUT_TRIGGER_P_FAIL)
        envelope = compute_runout_envelope(risk, make_terrain())
        expected_length = 100.0 / math.tan(math.radians(RUNOUT_ANGLE_OF_REACH_DEG))
        ring = envelope.geometry["coordinates"][0]
        left, right = ring[1], ring[2]
        base_center = ((left[0] + right[0]) / 2, (left[1] + right[1]) / 2)
        assert math.dist((0.0, 0.0), base_center) == pytest.approx(expected_length)
        expected_half_width = expected_length * math.tan(math.radians(RUNOUT_SPREAD_HALF_ANGLE_DEG))
        assert math.dist(left, right) == pytest.approx(2 * expected_half_width)


class TestBatch:
    def test_skips_cells_with_no_matching_terrain(self):
        risks = [make_risk(0.9, "a"), make_risk(0.9, "b")]
        terrain_by_id = {"a": make_terrain(cell_id="a")}
        envelopes = compute_runout_envelopes(risks, terrain_by_id)
        assert len(envelopes) == 1
        assert envelopes[0].source_cell_id == "a"

    def test_empty_inputs_produce_empty_output(self):
        assert compute_runout_envelopes([], {}) == []


class TestProjectToWgs84:
    def test_identity_like_transform_shape_preserved(self):
        """EPSG:4326 -> EPSG:4326 is an identity transform; a cheap way to test the reprojection
        plumbing (ring length, closure, coordinate order) without needing a real projected CRS."""
        risk = make_risk(0.9)
        envelope = compute_runout_envelope(risk, make_terrain(x=92.7, y=23.7))
        reprojected = project_envelope_to_wgs84(envelope, src_epsg=4326)
        original_ring = envelope.geometry["coordinates"][0]
        new_ring = reprojected.geometry["coordinates"][0]
        assert len(new_ring) == len(original_ring)
        for (ox, oy), (nx_, ny) in zip(original_ring, new_ring):
            assert nx_ == pytest.approx(ox)
            assert ny == pytest.approx(oy)
        assert reprojected.source_cell_id == envelope.source_cell_id
        assert reprojected.p_fail == envelope.p_fail
        assert reprojected.method == envelope.method
