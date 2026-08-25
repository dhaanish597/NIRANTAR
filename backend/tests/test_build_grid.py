"""Contract test for scripts/build_grid.py's pure logic (BUILD_PLAN.md task 1.2). No network
access — OSM/WorldCover fetches are verified by manually running the script against the real
Aizawl AOI (see CLAUDE.md §12 session log), not by tests that would make CI depend on those
services being up.

Skipped entirely if the geo stack (requirements-geo.txt) isn't installed — same reasoning as
test_fetch_dem.py.
"""
from __future__ import annotations

import importlib.util
import math
import sys
from pathlib import Path

import pytest

pytest.importorskip("rasterio")
pytest.importorskip("shapely")
pytest.importorskip("scipy")
pytest.importorskip("geopandas")

import numpy as np  # noqa: E402
import rasterio  # noqa: E402

SCRIPT_PATH = Path(__file__).resolve().parents[2] / "scripts" / "build_grid.py"


def _load_build_grid():
    spec = importlib.util.spec_from_file_location("build_grid", SCRIPT_PATH)
    module = importlib.util.module_from_spec(spec)
    sys.modules["build_grid"] = module
    spec.loader.exec_module(module)
    return module


bg = _load_build_grid()


def test_script_exists():
    assert SCRIPT_PATH.is_file()


class TestSlopeAspect:
    """Sign convention hand-derived and verified in the module docstring / commit message —
    these are the same two cases, re-verified here as an executable check."""

    def test_flat_surface_has_zero_slope(self):
        z = np.full((5, 5), 100.0)
        slope, _aspect = bg.compute_slope_aspect_deg(z, pixel_size_m=10.0)
        center = slope[2, 2]
        assert center == pytest.approx(0.0, abs=1e-6)

    def test_rising_east_faces_west(self):
        # elevation increases eastward (columns) -> downhill is west -> aspect 270
        z = np.array([[c * 10.0 for c in range(5)] for _ in range(5)])
        slope, aspect = bg.compute_slope_aspect_deg(z, pixel_size_m=10.0)
        assert aspect[2, 2] == pytest.approx(270.0, abs=1e-3)
        assert slope[2, 2] == pytest.approx(math.degrees(math.atan(1.0)), abs=1e-3)  # dz/dx=1

    def test_rising_north_faces_south(self):
        # row 0 = north (top of raster); elevation increases toward row 0 -> downhill is south
        z = np.array([[(4 - r) * 10.0 for _ in range(5)] for r in range(5)])
        _slope, aspect = bg.compute_slope_aspect_deg(z, pixel_size_m=10.0)
        assert aspect[2, 2] == pytest.approx(180.0, abs=1e-3)

    def test_nodata_neighbourhood_gives_nan(self):
        z = np.full((3, 3), 100.0)
        z[0, 0] = bg.DEM_NODATA
        slope, aspect = bg.compute_slope_aspect_deg(z, pixel_size_m=10.0)
        assert math.isnan(slope[1, 1])  # center cell's 3x3 window touches the nodata pixel
        assert math.isnan(aspect[1, 1])
        assert math.isnan(slope[0, 0])  # the nodata cell itself is always NaN


class TestFlowAccumulationD8:
    def test_all_flow_converges_on_the_global_minimum(self):
        # elevation = row + col: cell (0,0) is the unique global minimum every other cell can
        # reach by strictly descending steps, so its accumulation must equal the cell count.
        z = np.array([[float(r + c) for c in range(2)] for r in range(2)])
        accum = bg.compute_flow_accumulation_d8(z)
        assert accum[0, 0] == pytest.approx(4.0)  # itself + all 3 others
        assert accum[0, 1] == pytest.approx(1.0)  # a leaf, nothing flows into it
        assert accum[1, 0] == pytest.approx(1.0)
        assert accum[1, 1] == pytest.approx(1.0)  # flows diagonally straight to (0,0)

    def test_every_valid_cell_contributes_at_least_itself(self):
        rng_z = np.array([[1.0, 5.0, 3.0], [8.0, 2.0, 9.0], [4.0, 7.0, 6.0]])
        accum = bg.compute_flow_accumulation_d8(rng_z)
        assert (accum >= 1.0).all()
        assert accum.sum() >= rng_z.size  # conservation: total flow >= number of source cells

    def test_nodata_cells_have_zero_accumulation(self):
        z = np.full((3, 3), 100.0)
        z[1, 1] = bg.DEM_NODATA
        accum = bg.compute_flow_accumulation_d8(z)
        assert accum[1, 1] == 0.0


class TestTWI:
    def test_matches_the_formula_directly(self):
        slope = np.array([[45.0]])
        flow_accum = np.array([[4.0]])
        twi = bg.compute_twi(slope, flow_accum, pixel_size_m=10.0)
        expected = math.log((4.0 * 100.0 / 10.0) / math.tan(math.radians(45.0)))
        assert twi[0, 0] == pytest.approx(expected)

    def test_higher_flow_accumulation_gives_higher_twi(self):
        slope = np.array([[20.0, 20.0]])
        low_accum = bg.compute_twi(slope, np.array([[1.0, 1.0]]), pixel_size_m=10.0)
        high_accum = bg.compute_twi(slope, np.array([[1.0, 100.0]]), pixel_size_m=10.0)
        assert high_accum[0, 1] > low_accum[0, 1]

    def test_flatter_slope_gives_higher_twi(self):
        flow = np.array([[10.0, 10.0]])
        steep = bg.compute_twi(np.array([[60.0, 60.0]]), flow, pixel_size_m=10.0)
        shallow = bg.compute_twi(np.array([[5.0, 5.0]]), flow, pixel_size_m=10.0)
        assert shallow[0, 0] > steep[0, 0]


class TestMakeGrid:
    def test_cell_count_and_size(self):
        aoi = bg.AoiConfig(
            id="test", name="Test", center_lat=0.0, center_lon=0.0,
            bbox=(0.0, 0.0, 0.02, 0.02), utm_epsg=32631,  # a tiny bbox, arbitrary UTM zone
        )
        grid = bg.make_grid(aoi, cell_size_m=1000.0)
        assert len(grid) > 0
        first = grid.geometry.iloc[0]
        bounds = first.bounds
        assert bounds[2] - bounds[0] == pytest.approx(1000.0)
        assert bounds[3] - bounds[1] == pytest.approx(1000.0)

    def test_cell_ids_are_unique(self):
        aoi = bg.AoiConfig(
            id="test", name="Test", center_lat=0.0, center_lon=0.0,
            bbox=(0.0, 0.0, 0.03, 0.03), utm_epsg=32631,
        )
        grid = bg.make_grid(aoi, cell_size_m=1000.0)
        assert grid["cell_id"].is_unique


class TestWorldcoverTileName:
    def test_matches_the_verified_aizawl_tile(self):
        # Verified against the real bucket listing during this session — see commit message.
        assert bg.worldcover_tile_name(23.7307, 92.7173) == "ESA_WorldCover_10m_2021_v200_N21E090_Map.tif"

    def test_floors_to_the_nearest_3_degrees(self):
        assert bg.worldcover_tile_name(23.99, 92.99) == "ESA_WorldCover_10m_2021_v200_N21E090_Map.tif"
        assert bg.worldcover_tile_name(24.0, 93.0) == "ESA_WorldCover_10m_2021_v200_N24E093_Map.tif"


class TestZonalTerrainStats:
    def test_simple_two_cell_case(self):
        # A 4x2 raster split into two 2x2 grid cells (top and bottom half), each with a known,
        # distinct constant elevation so the expected zonal mean is unambiguous.
        transform = rasterio.transform.from_origin(0, 4, 1, 1)  # 1-unit pixels, origin (0,4)
        elevation = np.array(
            [[100.0, 100.0], [100.0, 100.0], [200.0, 200.0], [200.0, 200.0]], dtype=np.float32
        )
        slope = np.zeros_like(elevation)
        aspect = np.zeros_like(elevation)
        twi = np.zeros_like(elevation)

        from shapely.geometry import box
        import geopandas as gpd

        grid = gpd.GeoDataFrame(
            {"cell_id": ["top", "bottom"]},
            geometry=[box(0, 2, 2, 4), box(0, 0, 2, 2)],
            crs="EPSG:32646",
        )

        result = bg.zonal_terrain_stats(grid, elevation, slope, aspect, twi, transform)
        assert result.loc[result["cell_id"] == "top", "elevation_m"].iloc[0] == pytest.approx(100.0)
        assert result.loc[result["cell_id"] == "bottom", "elevation_m"].iloc[0] == pytest.approx(200.0)
        assert result.loc[result["cell_id"] == "top", "relief_m"].iloc[0] == pytest.approx(0.0)
