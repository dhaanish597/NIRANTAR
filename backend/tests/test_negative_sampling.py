"""Contract tests for ml/negative_sampling.py (BUILD_PLAN.md task 1.14).

Mix of pure-logic unit tests (synthetic data, no file dependency) and real-data smoke tests
against the actual Aizawl AOI (skip if the underlying files aren't present — same pattern as
test_build_grid.py/test_fetch_exposure.py).
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

gpd = pytest.importorskip("geopandas")
pd = pytest.importorskip("pandas")
np = pytest.importorskip("numpy")

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from ml import negative_sampling  # noqa: E402


class TestTerrainStratum:
    def test_returns_n_bins_distinct_codes_for_well_spread_data(self):
        df = pd.DataFrame({"slope_mean_deg": list(range(30))})  # 30 evenly spaced values
        strata = negative_sampling.terrain_stratum(df, n_bins=3)
        assert set(strata.unique()) == {0, 1, 2}

    def test_handles_duplicate_values_without_raising(self):
        # All-identical slope values would normally break qcut's default label assignment —
        # duplicates="drop" plus labels=False must not raise (this is the exact bug caught by
        # running this module against the real Aizawl grid the first time).
        df = pd.DataFrame({"slope_mean_deg": [5.0] * 20})
        strata = negative_sampling.terrain_stratum(df, n_bins=3)
        assert len(strata) == 20


class TestSampleNegatives:
    def _cells(self, n=30):
        # 3 terrain strata of 10 cells each (slope 1-10, 11-20, 21-30), none positive, none
        # in a holdout buffer, all with terrain.
        return gpd.GeoDataFrame(
            {
                "cell_id": [f"c_{i:03d}" for i in range(n)],
                "slope_mean_deg": list(range(1, n + 1)),
                "has_terrain": [True] * n,
                "in_holdout_buffer": [False] * n,
            }
        )

    def test_deterministic_given_same_seed(self):
        cells = self._cells()
        positive_strata = pd.Series([0, 1, 2])  # one "positive" in each stratum
        a = negative_sampling.sample_negatives(cells, set(), positive_strata, ratio=2, seed=42)
        b = negative_sampling.sample_negatives(cells, set(), positive_strata, ratio=2, seed=42)
        assert list(a["cell_id"]) == list(b["cell_id"])

    def test_different_seed_can_change_selection(self):
        cells = self._cells()
        positive_strata = pd.Series([0, 1, 2])
        a = negative_sampling.sample_negatives(cells, set(), positive_strata, ratio=3, seed=1)
        b = negative_sampling.sample_negatives(cells, set(), positive_strata, ratio=3, seed=2)
        # Not a hard guarantee for every possible RNG pair, but true for these two seeds against
        # this fixture — regression-guards that seed is actually threaded through, not ignored.
        assert list(a["cell_id"]) != list(b["cell_id"])

    def test_excludes_positive_cells_from_negative_pool(self):
        cells = self._cells()
        positive_ids = {"c_000", "c_001", "c_002"}
        positive_strata = pd.Series([0, 1, 2])
        negs = negative_sampling.sample_negatives(cells, positive_ids, positive_strata, ratio=5, seed=42)
        assert not set(negs["cell_id"]) & positive_ids

    def test_excludes_holdout_buffer_cells_from_negative_pool(self):
        cells = self._cells()
        cells.loc[cells["cell_id"] == "c_005", "in_holdout_buffer"] = True
        positive_strata = pd.Series([0])
        negs = negative_sampling.sample_negatives(cells, set(), positive_strata, ratio=30, seed=42)
        assert "c_005" not in set(negs["cell_id"])

    def test_no_duplicate_cell_ids(self):
        cells = self._cells()
        positive_strata = pd.Series([0, 0, 1, 1, 2, 2])
        negs = negative_sampling.sample_negatives(cells, set(), positive_strata, ratio=10, seed=42)
        assert negs["cell_id"].is_unique


class TestRealAizawlData:
    """Real-data smoke tests. Skip (not fail) if the AOI's static data isn't present locally —
    it's gitignored and machine-specific, same pattern as test_build_grid.py."""

    @pytest.fixture(autouse=True)
    def _skip_if_missing(self):
        cells_path = negative_sampling.REPO_ROOT / "data" / "static" / "aizawl" / "cells.gpkg"
        inv_path = negative_sampling.REPO_ROOT / "data" / "static" / "ner_inventory.csv"
        if not cells_path.is_file() or not inv_path.is_file():
            pytest.skip("data/static/aizawl/cells.gpkg or ner_inventory.csv not present locally")

    def test_load_eligible_cells_shape(self):
        cells = negative_sampling.load_eligible_cells("aizawl")
        assert len(cells) == 2912
        assert "has_terrain" in cells.columns
        assert "in_holdout_buffer" in cells.columns
        # A real, previously-verified fact (CLAUDE.md Current State): 212 of 2,912 cells have no
        # valid DEM pixel.
        assert int((~cells["has_terrain"]).sum()) == 212

    def test_build_training_table_produces_a_real_labeled_dataset(self):
        table = negative_sampling.build_training_table("aizawl")
        assert len(table) > 0
        assert set(table["label"].unique()) <= {0, 1}
        assert table["cell_id"].is_unique
        n_pos = int((table["label"] == 1).sum())
        n_neg = int((table["label"] == 0).sum())
        assert n_pos > 0, "expected at least one positive cell from the real Aizawl inventory"
        assert n_neg > 0
        # All declared terrain feature columns must be present (even if 100% null for the
        # deferred ones — see TERRAIN_FEATURE_COLUMNS docstring).
        for col in negative_sampling.TERRAIN_FEATURE_COLUMNS:
            assert col in table.columns

    def test_build_training_table_is_deterministic(self):
        a = negative_sampling.build_training_table("aizawl", seed=7)
        b = negative_sampling.build_training_table("aizawl", seed=7)
        assert list(a["cell_id"]) == list(b["cell_id"])
        assert list(a["label"]) == list(b["label"])
