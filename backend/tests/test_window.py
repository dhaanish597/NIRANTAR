"""Contract test for decision/window.py (BUILD_PLAN.md task 2.6, the safe evacuation window)."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from app.decision.window import (
    SafeWindowEstimate,
    WindowObservation,
    estimate_safe_window,
    exceedance_trajectory,
)
from app.schemas.ingest import CellObservation

T0 = datetime(2026, 5, 27, 0, 0, tzinfo=timezone.utc)


def obs_series(ratios: list[float], *, step_hours: float = 1.0, start: datetime = T0) -> list[WindowObservation]:
    return [
        WindowObservation(t=start + timedelta(hours=step_hours * i), exceedance_ratio=r)
        for i, r in enumerate(ratios)
    ]


class TestNeverSaysTimeToLandslide:
    """CLAUDE.md §4: 'Never call this "time to landslide"'. Structural check, same spirit as
    tests/test_no_wallclock.py's AST enforcement of rule 14 — every basis string this module can
    possibly produce must never contain the forbidden phrase."""

    def _all_basis_strings(self) -> list[str]:
        cases = [
            estimate_safe_window([]),
            estimate_safe_window(obs_series([1.5])),
            estimate_safe_window(obs_series([0.1, 0.1])),
            estimate_safe_window(obs_series([0.1, 0.2, 0.3])),
            estimate_safe_window(obs_series([0.5, 0.4, 0.3, 0.2])),
            estimate_safe_window(obs_series([0.01, 0.02, 0.03]), forecast_horizon_hours=1.0),
            estimate_safe_window(obs_series([0.1, 0.3, 0.5, 0.7])),
        ]
        return [c.basis for c in cases]

    def test_forbidden_phrase_never_appears(self):
        for basis in self._all_basis_strings():
            assert "time to landslide" not in basis.lower()


class TestAlreadyCritical:
    def test_at_or_above_critical_ratio_returns_immediate_window(self):
        result = estimate_safe_window(obs_series([0.2, 0.5, 1.3]))
        assert result.hours == (0.0, 1.0)
        assert result.confidence == 1.0

    def test_exactly_at_critical_ratio_counts_as_critical(self):
        result = estimate_safe_window(obs_series([0.2, 1.0]))
        assert result.hours is not None
        assert result.hours[0] == 0.0


class TestInsufficientData:
    def test_no_observations_returns_no_window(self):
        result = estimate_safe_window([])
        assert result.hours is None
        assert result.confidence == 0.0

    def test_fewer_than_min_points_returns_no_window(self):
        result = estimate_safe_window(obs_series([0.1, 0.2]), min_points=3)
        assert result.hours is None

    def test_all_same_timestamp_returns_no_window(self):
        same_t = [WindowObservation(t=T0, exceedance_ratio=r) for r in (0.1, 0.2, 0.3)]
        result = estimate_safe_window(same_t)
        assert result.hours is None


class TestFlatOrFallingTrend:
    def test_flat_trend_returns_no_window(self):
        result = estimate_safe_window(obs_series([0.3, 0.3, 0.3, 0.3]))
        assert result.hours is None
        assert result.confidence == 0.0

    def test_falling_trend_returns_no_window(self):
        result = estimate_safe_window(obs_series([0.6, 0.5, 0.4, 0.3]))
        assert result.hours is None


class TestRisingTrendProjection:
    def test_rising_trend_projects_a_future_window(self):
        # ratio rises 0.1/hour: 0.1, 0.2, 0.3, 0.4 at t=0,1,2,3h -> crosses 1.0 at t=9h from t0,
        # i.e. 6h from "now" (the last observation, t=3h).
        result = estimate_safe_window(obs_series([0.1, 0.2, 0.3, 0.4]))
        assert result.hours is not None
        lower, upper = result.hours
        assert lower <= 6.0 <= upper
        assert lower >= 0.0

    def test_window_is_a_range_not_a_point(self):
        result = estimate_safe_window(obs_series([0.1, 0.2, 0.3, 0.4]))
        assert result.hours[0] < result.hours[1]

    def test_lower_bound_never_negative(self):
        # crossing projected very soon after "now" -> margin could push lower below 0 without the
        # clamp.
        result = estimate_safe_window(obs_series([0.85, 0.9, 0.95, 0.999]))
        assert result.hours[0] >= 0.0

    def test_explicit_now_after_last_observation_shrinks_remaining_time(self):
        obs = obs_series([0.1, 0.2, 0.3, 0.4])
        at_last = estimate_safe_window(obs)
        later = estimate_safe_window(obs, now=obs[-1].t + timedelta(hours=2))
        assert later.hours[0] < at_last.hours[0]

    def test_projection_beyond_forecast_horizon_returns_no_window(self):
        # rising very slowly -> crossing is far in the future.
        result = estimate_safe_window(obs_series([0.01, 0.011, 0.012]), forecast_horizon_hours=1.0)
        assert result.hours is None

    def test_confidence_is_higher_for_a_clean_linear_trend_than_a_noisy_one(self):
        clean = estimate_safe_window(obs_series([0.1, 0.2, 0.3, 0.4, 0.5]))
        noisy = estimate_safe_window(obs_series([0.1, 0.35, 0.15, 0.45, 0.5]))
        assert clean.confidence > noisy.confidence

    def test_confidence_is_bounded_in_unit_interval(self):
        result = estimate_safe_window(obs_series([0.1, 0.2, 0.3, 0.4, 0.5, 0.6]))
        assert 0.0 <= result.confidence <= 1.0

    def test_fit_already_past_critical_as_of_now_is_treated_as_imminent(self):
        # Trend rising fast; "now" pushed well past the last observation so the *fitted* line
        # already implies critical risk even though the raw last reading (0.4) had not.
        obs = obs_series([0.1, 0.2, 0.3, 0.4])
        result = estimate_safe_window(obs, now=obs[-1].t + timedelta(hours=20))
        assert result.hours == (0.0, 1.0)


class TestExceedanceTrajectory:
    def _obs(self, rain_1h=0.0, rain_6h=0.0, rain_24h=0.0, rain_72h=0.0) -> CellObservation:
        return CellObservation(
            cell_id="aizawl_0101",
            rain_1h=rain_1h, rain_6h=rain_6h, rain_24h=rain_24h, rain_72h=rain_72h,
            antecedent_7d=0.0, antecedent_15d=0.0, antecedent_30d=0.0,
            soil_moisture=None, insar_velocity_mm_yr=None, source="test",
        )

    def test_wraps_threshold_exceedance_ratio_per_observation(self):
        from app.risk.thresholds import threshold_exceedance_ratio

        timed = [
            (T0, self._obs(rain_1h=1.0)),
            (T0 + timedelta(hours=1), self._obs(rain_1h=50.0)),
        ]
        traj = exceedance_trajectory(timed)
        assert len(traj) == 2
        assert traj[0].exceedance_ratio == pytest.approx(threshold_exceedance_ratio(timed[0][1]))
        assert traj[1].exceedance_ratio == pytest.approx(threshold_exceedance_ratio(timed[1][1]))
        assert traj[1].exceedance_ratio > traj[0].exceedance_ratio

    def test_feeds_directly_into_estimate_safe_window(self):
        timed = [
            (T0 + timedelta(hours=i), self._obs(rain_1h=1.0 + i * 3.0))
            for i in range(4)
        ]
        traj = exceedance_trajectory(timed)
        result = estimate_safe_window(traj)
        assert isinstance(result, SafeWindowEstimate)
