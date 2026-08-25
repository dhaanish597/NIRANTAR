"""Contract test for scripts/fetch_dem.py's pure logic (tile naming / tile selection). No
network access — the actual download is verified by manually running the script (see
CLAUDE.md §12 session log), not by an automated test that would make CI depend on AWS being up.

Skipped entirely if the geo stack (requirements-geo.txt) isn't installed — fetch_dem.py imports
rasterio/shapely at module level, and Phase 0's base requirements.txt deliberately doesn't
include them (see requirements-geo.txt's own docstring). Don't turn this into a hard failure for
anyone who hasn't run `pip install -r requirements-geo.txt` yet.
"""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

pytest.importorskip("rasterio")
pytest.importorskip("shapely")

SCRIPT_PATH = Path(__file__).resolve().parents[2] / "scripts" / "fetch_dem.py"


def _load_fetch_dem():
    spec = importlib.util.spec_from_file_location("fetch_dem", SCRIPT_PATH)
    module = importlib.util.module_from_spec(spec)
    sys.modules["fetch_dem"] = module
    spec.loader.exec_module(module)
    return module


fetch_dem = _load_fetch_dem()


def test_script_exists():
    assert SCRIPT_PATH.is_file()


class TestTileKey:
    def test_northern_eastern_hemisphere(self):
        assert fetch_dem.tile_key(23, 92) == (
            "Copernicus_DSM_COG_10_N23_00_E092_00_DEM/"
            "Copernicus_DSM_COG_10_N23_00_E092_00_DEM.tif"
        )

    def test_southern_western_hemisphere(self):
        assert fetch_dem.tile_key(-8, -34) == (
            "Copernicus_DSM_COG_10_S08_00_W034_00_DEM/"
            "Copernicus_DSM_COG_10_S08_00_W034_00_DEM.tif"
        )


class TestTilesForBbox:
    def test_bbox_within_a_single_tile(self):
        # Aizawl's actual AOI bbox — should need exactly one tile.
        assert fetch_dem.tiles_for_bbox(92.60, 23.60, 92.85, 23.85) == [(23, 92)]

    def test_bbox_spanning_two_tiles_in_longitude(self):
        tiles = fetch_dem.tiles_for_bbox(91.95, 23.10, 92.05, 23.20)
        assert set(tiles) == {(23, 91), (23, 92)}

    def test_bbox_spanning_a_two_by_two_block(self):
        tiles = fetch_dem.tiles_for_bbox(91.95, 22.95, 92.05, 23.05)
        assert set(tiles) == {(22, 91), (22, 92), (23, 91), (23, 92)}


def test_dem_nodata_is_outside_any_plausible_elevation():
    assert fetch_dem.DEM_NODATA < -1000  # nowhere on Earth is anywhere near this "elevation"
