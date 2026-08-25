"""Contract test for risk/stub.py."""
from __future__ import annotations

from app.risk.stub import RAIN_1H_SATURATION_MM, compute_cell_risks
from app.schemas.ingest import CellObservation, ObservationFrame

T = "2025-01-01T00:00:00+05:30"


def make_frame(rain_1h: float, cell_id: str = "c1") -> ObservationFrame:
    return ObservationFrame(
        t=T,
        aoi_id="aizawl",
        cells=[
            CellObservation(
                cell_id=cell_id,
                rain_1h=rain_1h,
                rain_6h=0.0, rain_24h=0.0, rain_72h=0.0,
                antecedent_7d=0.0, antecedent_15d=0.0, antecedent_30d=0.0,
                soil_moisture=None, insar_velocity_mm_yr=None,
                source="test", is_reconstructed=True,
            )
        ],
        provenance={},
    )


def test_p_fail_scales_linearly_with_rain_1h_up_to_saturation():
    risks = compute_cell_risks(make_frame(RAIN_1H_SATURATION_MM / 2))
    assert risks[0].p_fail == 0.5


def test_p_fail_clamped_to_one_above_saturation():
    risks = compute_cell_risks(make_frame(RAIN_1H_SATURATION_MM * 10))
    assert risks[0].p_fail == 1.0


def test_p_fail_is_zero_for_no_rain():
    risks = compute_cell_risks(make_frame(0.0))
    assert risks[0].p_fail == 0.0


def test_output_is_one_risk_per_input_cell_preserving_cell_id():
    frame = ObservationFrame(
        t=T,
        aoi_id="aizawl",
        cells=[
            CellObservation(
                cell_id=f"c{i}",
                rain_1h=float(i), rain_6h=0.0, rain_24h=0.0, rain_72h=0.0,
                antecedent_7d=0.0, antecedent_15d=0.0, antecedent_30d=0.0,
                soil_moisture=None, insar_velocity_mm_yr=None,
                source="test", is_reconstructed=True,
            )
            for i in range(3)
        ],
        provenance={},
    )
    risks = compute_cell_risks(frame)
    assert [r.cell_id for r in risks] == ["c0", "c1", "c2"]


def test_attribution_is_present_and_labelled_as_a_stub():
    risks = compute_cell_risks(make_frame(15.0))
    assert len(risks[0].attributions) == 1
    assert "stub" in risks[0].attributions[0].plain_language.lower()
