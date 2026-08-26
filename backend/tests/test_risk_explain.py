"""Contract tests for risk/explain.py (BUILD_PLAN.md task 1.18)."""
from __future__ import annotations

import pytest

pytest.importorskip("shap")
pytest.importorskip("xgboost")
pytest.importorskip("geopandas")

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

from app.risk import explain  # noqa: E402
from app.risk import model as risk_model  # noqa: E402


class TestCompass:
    def test_north(self):
        assert explain._compass(0.0) == "N"

    def test_east(self):
        assert explain._compass(90.0) == "E"

    def test_south(self):
        assert explain._compass(180.0) == "S"

    def test_west(self):
        assert explain._compass(270.0) == "W"

    def test_wraps_near_360(self):
        assert explain._compass(359.0) == "N"


class TestBuildFeatureGroups:
    def test_land_cover_columns_are_grouped_together(self):
        cols = ["elevation_m", "slope_mean_deg", "land_cover_tree_cover", "land_cover_built_up", "aspect_sin", "aspect_cos"]
        groups = explain._build_feature_groups(cols)
        land_cover_group = next(g for g in groups if g.key == "land_cover")
        assert set(land_cover_group.columns) == {"land_cover_tree_cover", "land_cover_built_up"}

    def test_aspect_sin_cos_grouped_together(self):
        cols = ["elevation_m", "aspect_sin", "aspect_cos"]
        groups = explain._build_feature_groups(cols)
        aspect_group = next(g for g in groups if g.key == "aspect")
        assert set(aspect_group.columns) == {"aspect_sin", "aspect_cos"}

    def test_drops_groups_with_no_matching_columns(self):
        cols = ["elevation_m"]
        groups = explain._build_feature_groups(cols)
        keys = {g.key for g in groups}
        assert "land_cover" not in keys
        assert "aspect" not in keys
        assert "elevation" in keys


class TestAttributionsForRows:
    def test_top_n_respected(self):
        cols = ["elevation_m", "slope_mean_deg", "twi_mean", "dist_to_road_m", "relief_m"]
        X = pd.DataFrame([{"elevation_m": 500, "slope_mean_deg": 20, "twi_mean": 5, "dist_to_road_m": 100, "relief_m": 50}])
        shap_values = np.array([[1.0, 0.5, 0.3, 0.2, 0.1]])
        result = explain.attributions_for_rows(X, shap_values, top_n=2)
        assert len(result[0]) == 2

    def test_ranked_by_absolute_contribution(self):
        cols = ["elevation_m", "slope_mean_deg"]
        X = pd.DataFrame([{"elevation_m": 500, "slope_mean_deg": 20}])
        shap_values = np.array([[-2.0, 0.5]])  # elevation's contribution is larger in magnitude
        result = explain.attributions_for_rows(X, shap_values, top_n=2)
        assert result[0][0].feature == "elevation"
        assert result[0][0].contribution == pytest.approx(-2.0)

    def test_display_pct_reflects_share_of_total_abs_contribution(self):
        X = pd.DataFrame([{"elevation_m": 500, "slope_mean_deg": 20}])
        shap_values = np.array([[3.0, 1.0]])  # total abs = 4.0
        result = explain.attributions_for_rows(X, shap_values, top_n=2)
        elevation_attr = next(a for a in result[0] if a.feature == "elevation")
        assert elevation_attr.display_pct == pytest.approx(75.0)

    def test_plain_language_includes_actual_value(self):
        X = pd.DataFrame([{"elevation_m": 842.0}])
        shap_values = np.array([[1.0]])
        result = explain.attributions_for_rows(X, shap_values, top_n=1)
        assert "842" in result[0][0].plain_language


class TestRealAizawlExplain:
    @pytest.fixture(autouse=True)
    def _skip_if_missing(self):
        if not risk_model.MODEL_PATH.is_file():
            pytest.skip("data/models/xgb_terrain_v1.json not trained yet")
        cells_path = risk_model.REPO_ROOT / "data" / "static" / "aizawl" / "cells.gpkg"
        if not cells_path.is_file():
            pytest.skip("data/static/aizawl/cells.gpkg not present locally")

    def test_explain_cells_returns_top4_per_cell(self):
        model = risk_model.RiskModel.load("aizawl")
        cell_ids = list(model.terrain_by_cell.index[:5])
        result = explain.explain_cells(model, cell_ids)
        assert set(result.keys()) == set(cell_ids)
        for attrs in result.values():
            assert len(attrs) == 4
            for a in attrs:
                assert a.plain_language
                assert isinstance(a.contribution, float)

    def test_empty_input_returns_empty_dict(self):
        model = risk_model.RiskModel.load("aizawl")
        assert explain.explain_cells(model, []) == {}

    def test_deterministic(self):
        model = risk_model.RiskModel.load("aizawl")
        cell_ids = list(model.terrain_by_cell.index[:3])
        r1 = explain.explain_cells(model, cell_ids)
        r2 = explain.explain_cells(model, cell_ids)
        for cid in cell_ids:
            assert [a.feature for a in r1[cid]] == [a.feature for a in r2[cid]]
            assert [a.contribution for a in r1[cid]] == [a.contribution for a in r2[cid]]
