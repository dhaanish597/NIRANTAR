"""Contract tests for risk/fusion.py (BUILD_PLAN.md task 1.19)."""
from __future__ import annotations

import pytest

from app.risk import fusion


class TestExceedanceAsProbabilityLike:
    def test_caps_at_one(self):
        assert fusion.exceedance_as_probability_like(5.0) == 1.0

    def test_passes_through_below_one(self):
        assert fusion.exceedance_as_probability_like(0.3) == pytest.approx(0.3)

    def test_floors_negative_at_zero(self):
        # threshold_exceedance_ratio (risk/thresholds.py) is documented >= 0.0, but this function
        # is defensive against a caller passing something out of that contract anyway.
        assert fusion.exceedance_as_probability_like(-1.0) == 0.0

    def test_exactly_one_at_threshold(self):
        assert fusion.exceedance_as_probability_like(1.0) == 1.0


class TestFuseFail:
    def test_ml_wins_when_higher(self):
        assert fusion.fuse_p_fail(ml_p_fail=0.9, threshold_exceedance=0.2) == pytest.approx(0.9)

    def test_threshold_wins_when_higher(self):
        assert fusion.fuse_p_fail(ml_p_fail=0.1, threshold_exceedance=2.0) == pytest.approx(1.0)

    def test_equal_values_pass_through(self):
        assert fusion.fuse_p_fail(ml_p_fail=0.5, threshold_exceedance=0.5) == pytest.approx(0.5)

    def test_never_exceeds_one(self):
        assert fusion.fuse_p_fail(ml_p_fail=0.99, threshold_exceedance=10.0) == 1.0

    def test_never_below_ml_p_fail(self):
        for ml_p in (0.0, 0.2, 0.5, 0.8, 1.0):
            assert fusion.fuse_p_fail(ml_p_fail=ml_p, threshold_exceedance=0.0) >= ml_p

    def test_zero_and_zero_is_zero(self):
        assert fusion.fuse_p_fail(ml_p_fail=0.0, threshold_exceedance=0.0) == 0.0


class TestFusionWiredIntoRiskModel:
    """An integration check, not just a unit test of fusion.py in isolation — proves
    risk/model.py's predict_batch() actually calls fuse_p_fail rather than returning the raw ML
    probability directly."""

    @pytest.fixture(autouse=True)
    def _skip_if_missing(self):
        pytest.importorskip("xgboost")
        pytest.importorskip("geopandas")
        from app.risk import model as risk_model

        if not risk_model.MODEL_PATH.is_file():
            pytest.skip("data/models/xgb_terrain_v1.json not trained yet")
        cells_path = risk_model.REPO_ROOT / "data" / "static" / "aizawl" / "cells.gpkg"
        if not cells_path.is_file():
            pytest.skip("data/static/aizawl/cells.gpkg not present locally")

    def test_extreme_rainfall_forces_p_fail_to_reflect_threshold_exceedance(self):
        """Real, meaningful check: an observation whose rainfall massively exceeds the published
        I-D/E-D thresholds must produce a CellRisk.p_fail at least as large as the (capped)
        exceedance ratio, even for a cell the terrain-only model itself scores low — proving the
        threshold engine's signal is never suppressed by a weak ML score, exactly as
        risk/fusion.py's docstring claims."""
        from app.risk.model import RiskModel
        from app.risk.thresholds import threshold_exceedance_ratio
        from app.schemas.ingest import CellObservation

        model = RiskModel.load("aizawl")
        cell_id = model.terrain_by_cell.index[0]
        extreme_obs = CellObservation(
            cell_id=cell_id,
            rain_1h=200.0,
            rain_6h=400.0,
            rain_24h=600.0,
            rain_72h=800.0,
            antecedent_7d=0.0,
            antecedent_15d=0.0,
            antecedent_30d=0.0,
            source="test",
        )
        expected_exceedance = threshold_exceedance_ratio(extreme_obs)
        assert expected_exceedance > 1.0, "fixture should genuinely exceed the published threshold"

        risks, _ = model.predict_batch([extreme_obs], include_attributions=False)
        assert risks[0].p_fail == pytest.approx(1.0)  # capped exceedance dominates
        assert risks[0].threshold_exceedance == pytest.approx(expected_exceedance)
