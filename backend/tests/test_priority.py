"""Contract test for impact/priority.py (BUILD_PLAN.md task 2.5, the Evacuation Priority Score)."""
from __future__ import annotations

from pathlib import Path

import pytest

from app.config import EPS_P1_THRESHOLD, EPS_P2_THRESHOLD, EPS_WEIGHTS
from app.impact.demographics import simulate_demographics
from app.impact.priority import compute_settlement_priorities, compute_settlement_priority
from app.schemas.impact import VillageIsolation

REPO_ROOT = Path(__file__).resolve().parents[2]
HAS_REAL_DATA = (
    (REPO_ROOT / "data" / "static" / "aizawl" / "cells.gpkg").is_file()
    and (REPO_ROOT / "data" / "static" / "aizawl" / "exposure.gpkg").is_file()
)


def make_village(
    population=100, p_isolated=0.0, isolated_now=False, village_id="v1"
) -> VillageIsolation:
    return VillageIsolation(
        village_id=village_id, name="Test Village", population=population,
        demographics=simulate_demographics(population),
        p_isolated=p_isolated, isolated_now=isolated_now, alternate_route_exists=not isolated_now,
        est_duration_hours=None, severed_links=[],
    )


class TestWeightsSumToOne:
    def test_config_weights_sum_to_one(self):
        assert sum(EPS_WEIGHTS.values()) == pytest.approx(1.0)


class TestComponents:
    def test_zero_everything_gives_zero_eps_and_p3(self):
        result = compute_settlement_priority(make_village(population=0), p_fail=0.0, shelter_distance_km=0.0)
        assert result.eps == pytest.approx(0.0)
        assert result.tier == "P3"
        assert result.components == {"p_fail": 0.0, "pop": 0.0, "rii": 0.0, "shelter": 1.0}

    def test_max_everything_gives_eps_one_and_p1(self):
        village = make_village(population=10_000, p_isolated=1.0, isolated_now=True)
        result = compute_settlement_priority(village, p_fail=1.0, shelter_distance_km=None)
        assert result.eps == pytest.approx(1.0)
        assert result.tier == "P1"

    def test_population_normalization_is_capped_at_one(self):
        from app.config import EPS_POPULATION_NORM_REF

        result = compute_settlement_priority(
            make_village(population=int(EPS_POPULATION_NORM_REF * 10)), p_fail=0.0, shelter_distance_km=None
        )
        assert result.components["pop"] == pytest.approx(1.0)

    def test_p_fail_is_clamped_to_valid_range(self):
        result = compute_settlement_priority(make_village(), p_fail=1.5, shelter_distance_km=None)
        assert result.components["p_fail"] == 1.0
        result2 = compute_settlement_priority(make_village(), p_fail=-0.5, shelter_distance_km=None)
        assert result2.components["p_fail"] == 0.0

    def test_rii_passes_through_p_isolated_directly(self):
        result = compute_settlement_priority(make_village(p_isolated=0.42), p_fail=0.0, shelter_distance_km=None)
        assert result.components["rii"] == pytest.approx(0.42)


class TestShelterAccessibility:
    def test_zero_distance_gives_full_accessibility(self):
        result = compute_settlement_priority(make_village(), p_fail=0.0, shelter_distance_km=0.0)
        assert result.components["shelter"] == pytest.approx(1.0)

    def test_distance_at_reference_gives_zero_accessibility(self):
        from app.config import EPS_SHELTER_ACCESS_REF_KM

        result = compute_settlement_priority(
            make_village(), p_fail=0.0, shelter_distance_km=EPS_SHELTER_ACCESS_REF_KM
        )
        assert result.components["shelter"] == pytest.approx(0.0)

    def test_distance_beyond_reference_is_floored_at_zero_not_negative(self):
        from app.config import EPS_SHELTER_ACCESS_REF_KM

        result = compute_settlement_priority(
            make_village(), p_fail=0.0, shelter_distance_km=EPS_SHELTER_ACCESS_REF_KM * 10
        )
        assert result.components["shelter"] == pytest.approx(0.0)

    def test_none_distance_gives_zero_accessibility(self):
        result = compute_settlement_priority(make_village(), p_fail=0.0, shelter_distance_km=None)
        assert result.components["shelter"] == pytest.approx(0.0)

    def test_isolated_now_forces_zero_accessibility_even_if_shelter_is_close(self):
        village = make_village(isolated_now=True)
        result = compute_settlement_priority(village, p_fail=0.0, shelter_distance_km=0.1)
        assert result.components["shelter"] == pytest.approx(0.0)


class TestTierBuckets:
    def test_tier_boundaries_match_config(self):
        just_below_p1 = compute_settlement_priority(
            make_village(), p_fail=EPS_P1_THRESHOLD - 0.001, shelter_distance_km=None,
            weights={"p_fail": 1.0, "pop": 0.0, "rii": 0.0, "shelter": 0.0},
        )
        at_p1 = compute_settlement_priority(
            make_village(), p_fail=EPS_P1_THRESHOLD, shelter_distance_km=None,
            weights={"p_fail": 1.0, "pop": 0.0, "rii": 0.0, "shelter": 0.0},
        )
        assert just_below_p1.tier != "P1"
        assert at_p1.tier == "P1"

        just_below_p2 = compute_settlement_priority(
            make_village(), p_fail=EPS_P2_THRESHOLD - 0.001, shelter_distance_km=None,
            weights={"p_fail": 1.0, "pop": 0.0, "rii": 0.0, "shelter": 0.0},
        )
        at_p2 = compute_settlement_priority(
            make_village(), p_fail=EPS_P2_THRESHOLD, shelter_distance_km=None,
            weights={"p_fail": 1.0, "pop": 0.0, "rii": 0.0, "shelter": 0.0},
        )
        assert just_below_p2.tier == "P3"
        assert at_p2.tier == "P2"


class TestBatch:
    def test_missing_village_defaults_to_zero_p_fail_not_a_crash(self):
        village = make_village(village_id="unknown_to_p_fail_map")
        results = compute_settlement_priorities([village], p_fail_by_village={}, shelter_distance_km_by_village={})
        assert len(results) == 1
        assert results[0].components["p_fail"] == 0.0

    def test_batch_matches_single_call(self):
        village = make_village(village_id="v9", population=500, p_isolated=0.3)
        single = compute_settlement_priority(village, p_fail=0.5, shelter_distance_km=2.0)
        batch = compute_settlement_priorities(
            [village], p_fail_by_village={"v9": 0.5}, shelter_distance_km_by_village={"v9": 2.0}
        )
        assert batch[0] == single


@pytest.mark.skipif(not HAS_REAL_DATA, reason="requires data/static/aizawl/{cells,exposure}.gpkg")
class TestResolvePriorityInputsAgainstRealAizawlData:
    def test_returns_an_entry_per_real_village(self):
        from app.impact.priority import resolve_priority_inputs

        p_fail_by_village, shelter_km_by_village = resolve_priority_inputs("aizawl", {})
        assert len(p_fail_by_village) == 11  # CLAUDE.md's Current State: 11 real Aizawl villages
        assert set(p_fail_by_village) == set(shelter_km_by_village)
        # Aizawl has 7 real shelters (CLAUDE.md's Current State) — every village should resolve
        # a real, positive, finite distance to its nearest one, not None.
        assert all(v is not None and v > 0 for v in shelter_km_by_village.values())

    def test_cell_risk_lookup_actually_reaches_the_nearest_real_cell(self):
        from app.impact.priority import resolve_priority_inputs

        p_fail_by_village, _ = resolve_priority_inputs("aizawl", {})
        some_village_id = next(iter(p_fail_by_village))
        # With an empty cell-risk dict every village defaults to 0.0 (no crash on an unknown key).
        assert p_fail_by_village[some_village_id] == 0.0

        # Now prove the nearest-cell resolution is real by injecting a distinctive p_fail for
        # EVERY real Aizawl cell and confirming every village picks one of those real values up
        # (not silently 0.0, i.e. the STRtree nearest-cell lookup is genuinely wired through).
        import geopandas as gpd

        cells = gpd.read_file(REPO_ROOT / "data" / "static" / "aizawl" / "cells.gpkg")
        fake_risk = {cid: 0.777 for cid in cells["cell_id"]}
        p_fail_by_village_2, _ = resolve_priority_inputs("aizawl", fake_risk)
        assert all(v == pytest.approx(0.777) for v in p_fail_by_village_2.values())
