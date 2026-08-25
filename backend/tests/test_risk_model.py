"""Contract tests for risk/model.py (BUILD_PLAN.md task 1.17)."""
from __future__ import annotations

import pytest

pytest.importorskip("xgboost")
pytest.importorskip("geopandas")

from app.risk import model as risk_model  # noqa: E402
from app.schemas.ingest import CellObservation  # noqa: E402


def _obs(cell_id: str, **overrides) -> CellObservation:
    defaults = dict(
        rain_1h=0.0,
        rain_6h=0.0,
        rain_24h=0.0,
        rain_72h=0.0,
        antecedent_7d=0.0,
        antecedent_15d=0.0,
        antecedent_30d=0.0,
        source="test",
    )
    defaults.update(overrides)
    return CellObservation(cell_id=cell_id, **defaults)


class TestConfidenceHeuristic:
    def test_maximally_decisive_at_extremes(self):
        assert risk_model._confidence_from_probability(0.0) == pytest.approx(1.0, abs=1e-3)
        assert risk_model._confidence_from_probability(1.0) == pytest.approx(1.0, abs=1e-3)

    def test_minimally_decisive_at_half(self):
        assert risk_model._confidence_from_probability(0.5) == pytest.approx(0.0, abs=1e-6)

    def test_monotonically_more_confident_away_from_half(self):
        c1 = risk_model._confidence_from_probability(0.6)
        c2 = risk_model._confidence_from_probability(0.9)
        assert c1 < c2

    def test_bounded_in_unit_interval(self):
        for p in (0.01, 0.1, 0.3, 0.5, 0.7, 0.9, 0.99):
            c = risk_model._confidence_from_probability(p)
            assert 0.0 <= c <= 1.0


class TestModelNotTrainedError:
    def test_raises_actionable_error_when_artifact_missing(self, tmp_path, monkeypatch):
        monkeypatch.setattr(risk_model, "MODEL_PATH", tmp_path / "does_not_exist.json")
        monkeypatch.setattr(risk_model, "METADATA_PATH", tmp_path / "does_not_exist.json")
        with pytest.raises(risk_model.ModelNotTrainedError, match="ml.train"):
            risk_model.RiskModel.load("aizawl")


class TestRealAizawlModel:
    @pytest.fixture(autouse=True)
    def _skip_if_missing(self):
        if not risk_model.MODEL_PATH.is_file() or not risk_model.METADATA_PATH.is_file():
            pytest.skip("data/models/xgb_terrain_v1.json not trained yet — run `python -m ml.train`")
        cells_path = risk_model.REPO_ROOT / "data" / "static" / "aizawl" / "cells.gpkg"
        if not cells_path.is_file():
            pytest.skip("data/static/aizawl/cells.gpkg not present locally")

    def test_load_returns_a_usable_model(self):
        model = risk_model.RiskModel.load("aizawl")
        assert model.model_version == "xgb-terrain-v1"
        assert len(model.terrain_by_cell) == 2912

    def test_predict_batch_on_real_cell_ids(self):
        model = risk_model.RiskModel.load("aizawl")
        real_cell_id = model.terrain_by_cell.index[0]
        observations = [_obs(real_cell_id, rain_72h=50.0)]
        risks, unmatched = model.predict_batch(observations)
        assert unmatched == []
        assert len(risks) == 1
        risk = risks[0]
        assert risk.cell_id == real_cell_id
        assert 0.0 <= risk.p_fail <= 1.0
        assert risk.threshold_exceedance >= 0.0
        assert 0.0 <= risk.confidence <= 1.0
        assert risk.model_version == "xgb-terrain-v1"

    def test_unmatched_cell_id_reported_not_fabricated(self):
        model = risk_model.RiskModel.load("aizawl")
        observations = [_obs("not_a_real_cell_id")]
        risks, unmatched = model.predict_batch(observations)
        assert risks == []
        assert unmatched == ["not_a_real_cell_id"]

    def test_mixed_matched_and_unmatched(self):
        model = risk_model.RiskModel.load("aizawl")
        real_cell_id = model.terrain_by_cell.index[0]
        observations = [_obs(real_cell_id), _obs("bogus_cell")]
        risks, unmatched = model.predict_batch(observations)
        assert len(risks) == 1
        assert unmatched == ["bogus_cell"]

    def test_predict_cell_risks_module_function(self):
        model = risk_model.RiskModel.load("aizawl")
        real_cell_id = model.terrain_by_cell.index[5]
        risks = risk_model.predict_cell_risks([_obs(real_cell_id)], "aizawl")
        assert len(risks) == 1
        assert risks[0].cell_id == real_cell_id

    def test_deterministic_prediction(self):
        model_a = risk_model.RiskModel.load("aizawl")
        model_b = risk_model.RiskModel.load("aizawl")
        cell_id = model_a.terrain_by_cell.index[10]
        obs = [_obs(cell_id, rain_72h=80.0)]
        risks_a, _ = model_a.predict_batch(obs)
        risks_b, _ = model_b.predict_batch(obs)
        assert risks_a[0].p_fail == risks_b[0].p_fail

    def test_threshold_exceedance_reacts_to_rainfall(self):
        """A real, meaningful check — not just 'doesn't crash': heavier rainfall observations
        must raise the reported threshold_exceedance for the same cell."""
        model = risk_model.RiskModel.load("aizawl")
        cell_id = model.terrain_by_cell.index[0]
        dry_risks, _ = model.predict_batch([_obs(cell_id, rain_1h=0.0, rain_6h=0.0, rain_24h=0.0, rain_72h=0.0)])
        wet_risks, _ = model.predict_batch([_obs(cell_id, rain_1h=50.0, rain_6h=120.0, rain_24h=200.0, rain_72h=260.0)])
        assert wet_risks[0].threshold_exceedance > dry_risks[0].threshold_exceedance
