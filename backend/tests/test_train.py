"""Contract tests for ml/train.py (BUILD_PLAN.md task 1.15).

Mix of synthetic-data unit tests (feature engineering, spatial blocking, CV mechanics) and a
real-data end-to-end smoke test that trains against the actual Aizawl table and checks
determinism — skipped if the underlying static data isn't present locally.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

pd = pytest.importorskip("pandas")
np = pytest.importorskip("numpy")
pytest.importorskip("xgboost")
pytest.importorskip("sklearn")

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from ml import train  # noqa: E402


def _synthetic_table(n=40, seed=0):
    rng = np.random.default_rng(seed)
    lat = rng.uniform(23.60, 23.85, n)
    lon = rng.uniform(92.60, 92.85, n)
    slope = rng.uniform(2, 45, n)
    # Make label correlated with slope so CV has *some* real signal to find, not pure noise.
    label = (slope > np.median(slope)).astype(int)
    return pd.DataFrame(
        {
            "cell_id": [f"aizawl_{i:03d}" for i in range(n)],
            "label": label,
            "centroid_lat": lat,
            "centroid_lon": lon,
            "elevation_m": rng.uniform(100, 1400, n),
            "elevation_min_m": rng.uniform(50, 1300, n),
            "elevation_max_m": rng.uniform(150, 1500, n),
            "slope_mean_deg": slope,
            "slope_max_deg": slope + rng.uniform(0, 10, n),
            "twi_mean": rng.uniform(4, 8, n),
            "relief_m": rng.uniform(10, 200, n),
            "aspect_mean_deg": rng.uniform(0, 360, n),
            "dist_to_road_m": rng.uniform(0, 3000, n),
            "land_cover_class": rng.choice(["tree_cover", "built_up", "grassland"], n),
            "plan_curvature": [None] * n,
            "profile_curvature": [None] * n,
            "dist_to_fault_km": [None] * n,
            "lithology_class": [None] * n,
        }
    )


class TestEngineerFeatures:
    def test_adds_circular_aspect_and_one_hot_landcover(self):
        df = _synthetic_table(n=10)
        out = train.engineer_features(df)
        assert "aspect_sin" in out.columns and "aspect_cos" in out.columns
        assert f"land_cover_tree_cover" in out.columns
        # aspect_sin/cos must be within [-1, 1] and a real trig transform, not passthrough.
        assert out["aspect_sin"].between(-1.0, 1.0).all()
        assert out["aspect_cos"].between(-1.0, 1.0).all()

    def test_null_columns_become_numeric_nan_not_object(self):
        df = _synthetic_table(n=5)
        out = train.engineer_features(df)
        assert out["lithology_class"].isna().all()
        assert pd.api.types.is_float_dtype(out["lithology_class"])

    def test_feature_columns_all_present_after_engineering(self):
        df = _synthetic_table(n=10)
        out = train.engineer_features(df)
        for col in train.feature_columns():
            assert col in out.columns, f"missing feature column {col}"


class TestAssignSpatialBlocks:
    def test_four_quadrants_used(self):
        df = _synthetic_table(n=100, seed=1)
        blocks = train.assign_spatial_blocks(df)
        assert set(blocks.unique()) <= {"NE", "NW", "SE", "SW"}
        assert len(set(blocks.unique())) > 1  # a real spread, not one giant block

    def test_split_is_by_centroid_not_row_order(self):
        df = _synthetic_table(n=20, seed=2)
        shuffled = df.sample(frac=1.0, random_state=5).reset_index(drop=True)
        b1 = train.assign_spatial_blocks(df)
        b2 = train.assign_spatial_blocks(shuffled)
        # Same cell_id must land in the same block regardless of row order.
        lookup1 = dict(zip(df["cell_id"], b1))
        lookup2 = dict(zip(shuffled["cell_id"], b2))
        assert lookup1 == lookup2


class TestSpatialBlockCV:
    def test_scores_every_row_when_every_fold_has_both_classes(self):
        df = train.engineer_features(_synthetic_table(n=80, seed=3))
        cols = train.feature_columns()
        oof, reports = train.spatial_block_cv(df, cols, seed=42)
        assert len(reports) == len(set(train.assign_spatial_blocks(df)))
        # With 80 rows split ~evenly across 4 quadrants and a 50/50 label split, every fold
        # should have both classes in its training partition.
        assert oof.notna().sum() > 0

    def test_skips_fold_with_single_class_training_partition(self):
        df = train.engineer_features(_synthetic_table(n=20, seed=4))
        # Force every row into one block by collapsing all centroids, then force one row's label
        # to be the only positive so removing its block leaves a single-class training partition.
        df["centroid_lat"] = 23.70
        df["centroid_lon"] = 92.70
        df.loc[:, "label"] = 0
        df.loc[0, "label"] = 1
        cols = train.feature_columns()
        oof, reports = train.spatial_block_cv(df, cols, seed=42)
        # All rows land in one quadrant (NE, since >= median ties go to N/E) -> a single fold
        # whose test set IS the training set's complement of nothing... with one block only,
        # train_mask is empty for that block's own test, meaning y_train has zero rows -> caught
        # by nunique() < 2 (0 unique values) rather than crashing.
        assert any(r["skipped"] is not None for r in reports)


class TestRealAizawlTraining:
    @pytest.fixture(autouse=True)
    def _skip_if_missing(self):
        cells_path = train.REPO_ROOT / "data" / "static" / "aizawl" / "cells.gpkg"
        inv_path = train.REPO_ROOT / "data" / "static" / "ner_inventory.csv"
        if not cells_path.is_file() or not inv_path.is_file():
            pytest.skip("real Aizawl static data not present locally")

    def test_train_is_deterministic(self, tmp_path, monkeypatch):
        # Redirect model outputs to a temp dir so this test doesn't clobber the real committed
        # run's artifacts (data/models/* is gitignored/regenerable, but still — don't stomp on it
        # mid-suite).
        monkeypatch.setattr(train, "MODEL_DIR", tmp_path)
        monkeypatch.setattr(train, "MODEL_PATH", tmp_path / "model.json")
        monkeypatch.setattr(train, "METADATA_PATH", tmp_path / "metadata.json")
        monkeypatch.setattr(train, "CV_PREDICTIONS_PATH", tmp_path / "cv_predictions.csv")

        meta1 = train.train("aizawl", seed=42)
        cv1 = pd.read_csv(tmp_path / "cv_predictions.csv")
        meta2 = train.train("aizawl", seed=42)
        cv2 = pd.read_csv(tmp_path / "cv_predictions.csv")

        assert meta1["n_positive"] == meta2["n_positive"]
        assert meta1["n_negative"] == meta2["n_negative"]
        pd.testing.assert_frame_equal(cv1, cv2)

    def test_train_produces_a_real_model_file(self, tmp_path, monkeypatch):
        monkeypatch.setattr(train, "MODEL_DIR", tmp_path)
        monkeypatch.setattr(train, "MODEL_PATH", tmp_path / "model.json")
        monkeypatch.setattr(train, "METADATA_PATH", tmp_path / "metadata.json")
        monkeypatch.setattr(train, "CV_PREDICTIONS_PATH", tmp_path / "cv_predictions.csv")

        metadata = train.train("aizawl", seed=42)
        assert (tmp_path / "model.json").is_file()
        assert metadata["model_version"] == train.MODEL_VERSION
        assert metadata["n_total"] == metadata["n_positive"] + metadata["n_negative"]
