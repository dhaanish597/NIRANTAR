"""Contract test for risk/thresholds.py (BUILD_PLAN.md task 1.11)."""
from __future__ import annotations

import pytest

from app.risk.thresholds import (
    event_duration_threshold_mm,
    intensity_duration_threshold_mm_per_hr,
    threshold_exceedance_ratio,
)
from app.schemas.ingest import CellObservation

T = "2025-01-01T00:00:00+05:30"


def make_obs(rain_1h=0.0, rain_6h=0.0, rain_24h=0.0, rain_72h=0.0) -> CellObservation:
    return CellObservation(
        cell_id="c1",
        rain_1h=rain_1h, rain_6h=rain_6h, rain_24h=rain_24h, rain_72h=rain_72h,
        antecedent_7d=0.0, antecedent_15d=0.0, antecedent_30d=0.0,
        soil_moisture=None, insar_velocity_mm_yr=None,
        source="test", is_reconstructed=True,
    )


class TestIntensityDurationCurve:
    def test_matches_the_published_formula_directly(self):
        for d in (1.0, 6.0, 24.0, 72.0, 200.0):
            assert intensity_duration_threshold_mm_per_hr(d) == pytest.approx(5.8294 * d**-0.4141)

    def test_decreasing_in_duration(self):
        """Longer storms have a lower sustainable intensity threshold — the curve's whole point."""
        values = [intensity_duration_threshold_mm_per_hr(d) for d in (1, 6, 24, 72, 200)]
        assert values == sorted(values, reverse=True)

    def test_one_hour_value_is_close_to_the_coefficient(self):
        # D^-0.4141 == 1 at D=1, so I(1) == the bare coefficient.
        assert intensity_duration_threshold_mm_per_hr(1.0) == pytest.approx(5.8294)


class TestEventDurationCurve:
    def test_matches_the_published_formula_within_validity(self):
        assert event_duration_threshold_mm(72.0) == pytest.approx(-11.10 + 0.62 * 72.0)

    def test_none_at_or_below_24_hours(self):
        assert event_duration_threshold_mm(24.0) is None
        assert event_duration_threshold_mm(10.0) is None

    def test_none_at_or_above_1440_hours(self):
        assert event_duration_threshold_mm(1440.0) is None
        assert event_duration_threshold_mm(2000.0) is None

    def test_valid_just_inside_the_boundaries(self):
        assert event_duration_threshold_mm(24.001) is not None
        assert event_duration_threshold_mm(1439.999) is not None


class TestThresholdExceedanceRatio:
    def test_zero_rainfall_gives_zero_ratio(self):
        assert threshold_exceedance_ratio(make_obs()) == 0.0

    def test_exactly_at_the_one_hour_id_threshold_gives_ratio_one(self):
        one_hour_threshold = intensity_duration_threshold_mm_per_hr(1.0)
        obs = make_obs(rain_1h=one_hour_threshold)
        assert threshold_exceedance_ratio(obs) == pytest.approx(1.0)

    def test_double_the_one_hour_threshold_gives_ratio_two(self):
        one_hour_threshold = intensity_duration_threshold_mm_per_hr(1.0)
        obs = make_obs(rain_1h=one_hour_threshold * 2)
        assert threshold_exceedance_ratio(obs) == pytest.approx(2.0)

    def test_event_duration_curve_can_dominate_the_max(self):
        # 100mm over 72h: E-D ratio (100 / ~33.5 ≈ 2.98) exceeds the I-D ratio for the same
        # window (≈1.40) — the function must pick up the larger one.
        obs = make_obs(rain_72h=100.0)
        ed_threshold = event_duration_threshold_mm(72.0)
        expected = 100.0 / ed_threshold
        assert threshold_exceedance_ratio(obs) == pytest.approx(expected)

    def test_ratio_is_never_negative(self):
        assert threshold_exceedance_ratio(make_obs(rain_1h=0.001)) >= 0.0
