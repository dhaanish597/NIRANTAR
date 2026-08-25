"""Contract test for ingest/live/imerg.py's pure logic (BUILD_PLAN.md task 1.6). No real network
access — real granule downloads are blocked pending a one-time GES DISC app authorization (see
Required_by_me.md and the module's own docstring), so this exercises everything that CAN be
verified without it: URL/path construction, HDF5 parsing against a synthetic fixture built to the
publicly-documented IMERG structure, rolling-window math, and cell-to-pixel assignment.

Skipped entirely if requirements-ingest.txt isn't installed.
"""
from __future__ import annotations

import importlib.util
import sys
from datetime import datetime, timezone
from pathlib import Path

import pytest

pytest.importorskip("h5py")
pytest.importorskip("geopandas")
pytest.importorskip("pandas")

SCRIPT_PATH = (
    Path(__file__).resolve().parents[1] / "app" / "ingest" / "live" / "imerg.py"
)


def _load_imerg():
    spec = importlib.util.spec_from_file_location("app.ingest.live.imerg", SCRIPT_PATH)
    module = importlib.util.module_from_spec(spec)
    sys.modules["app.ingest.live.imerg"] = module
    spec.loader.exec_module(module)
    return module


imerg = _load_imerg()


def test_module_exists():
    assert SCRIPT_PATH.is_file()


class TestGranuleNaming:
    def test_half_hour_floor_first_half(self):
        dt = datetime(2026, 8, 25, 6, 17, tzinfo=timezone.utc)
        assert imerg.granule_half_hour_start(dt) == datetime(2026, 8, 25, 6, 0, tzinfo=timezone.utc)

    def test_half_hour_floor_second_half(self):
        dt = datetime(2026, 8, 25, 6, 47, tzinfo=timezone.utc)
        assert imerg.granule_half_hour_start(dt) == datetime(2026, 8, 25, 6, 30, tzinfo=timezone.utc)

    def test_naive_datetime_rejected(self):
        with pytest.raises(ValueError):
            imerg.granule_half_hour_start(datetime(2026, 8, 25, 6, 0))

    def test_url_matches_real_confirmed_pattern(self):
        # This exact filename (for 06:00-06:29:59 UTC on day 237/2026) was confirmed present in
        # a real GES DISC directory listing while writing this module — not a guess.
        start = datetime(2026, 8, 25, 6, 0, tzinfo=timezone.utc)
        url = imerg.granule_url(start)
        assert url == (
            "https://gpm1.gesdisc.eosdis.nasa.gov/data/GPM_L3/GPM_3IMERGHHE.07/2026/237/"
            "3B-HHR-E.MS.MRG.3IMERG.20260825-S060000-E062959.0360.V07C.HDF5"
        )

    def test_cache_path_is_stable_and_distinct_per_granule(self, tmp_path):
        t1 = datetime(2026, 8, 25, 6, 0, tzinfo=timezone.utc)
        t2 = datetime(2026, 8, 25, 6, 30, tzinfo=timezone.utc)
        p1 = imerg.granule_cache_path(t1, tmp_path)
        p2 = imerg.granule_cache_path(t2, tmp_path)
        assert p1 != p2
        assert imerg.granule_cache_path(t1, tmp_path) == p1  # stable across calls


class TestEarthdataSessionAuthForwarding:
    def test_keeps_auth_within_earthdata_family(self):
        session = imerg._EarthdataSession("user", "pass")

        class FakeRequest:
            headers = {"Authorization": "Basic xyz"}
            url = "https://urs.earthdata.nasa.gov/oauth/redirect"

        session.rebuild_auth(FakeRequest(), response=None)
        assert "Authorization" in FakeRequest.headers

    def test_strips_auth_outside_earthdata_family(self):
        session = imerg._EarthdataSession("user", "pass")

        class FakeRequest:
            headers = {"Authorization": "Basic xyz"}
            url = "https://evil.example.com/steal"

        session.rebuild_auth(FakeRequest(), response=None)
        assert "Authorization" not in FakeRequest.headers


class TestDownloadGranuleValidation:
    def test_rejects_non_hdf5_response(self, tmp_path, monkeypatch):
        """The exact failure mode this session actually hit: a 200 response containing the GES
        DISC web-app HTML shell instead of real HDF5 bytes."""

        class FakeResponse:
            content = b"<!DOCTYPE html><html>not a granule</html>"

            def raise_for_status(self):
                pass

        class FakeSession:
            def __init__(self, *a, **kw):
                pass

            def get(self, url, timeout):
                return FakeResponse()

        monkeypatch.setattr(imerg, "_EarthdataSession", FakeSession)
        with pytest.raises(RuntimeError, match="not an HDF5 file"):
            imerg.download_granule(
                datetime(2026, 8, 25, 6, 0, tzinfo=timezone.utc), "u", "p", cache_dir=tmp_path
            )

    def test_returns_cached_path_without_network(self, tmp_path, monkeypatch):
        half_hour = datetime(2026, 8, 25, 6, 0, tzinfo=timezone.utc)
        dest = imerg.granule_cache_path(half_hour, tmp_path)
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(imerg.HDF5_MAGIC + b"fake-cached-granule")

        def fail_if_called(*a, **kw):
            raise AssertionError("should not hit the network for an already-cached granule")

        monkeypatch.setattr(imerg, "_EarthdataSession", fail_if_called)
        result = imerg.download_granule(half_hour, "u", "p", cache_dir=tmp_path)
        assert result == dest


class TestReadGranulePrecipSyntheticFixture:
    """Builds a tiny synthetic HDF5 file matching the publicly-documented IMERG /Grid/precipitation
    layout ((time=1, lon, lat), fill value -9999.9) and verifies the parser handles it correctly.
    This validates the parsing LOGIC, not NASA's actual file structure (see module docstring)."""

    @pytest.fixture
    def synthetic_granule(self, tmp_path):
        import h5py
        import numpy as np

        path = tmp_path / "synthetic.HDF5"
        lon = np.array([92.5, 92.6, 92.7, 92.8], dtype=np.float32)
        lat = np.array([23.6, 23.7, 23.8], dtype=np.float32)
        # shape (time=1, lon=4, lat=3); one fill-value cell to verify it's excluded.
        precip = np.full((1, 4, 3), 2.0, dtype=np.float32)
        precip[0, 0, 0] = imerg.IMERG_FILL_VALUE

        with h5py.File(path, "w") as f:
            grid = f.create_group("Grid")
            grid.create_dataset("lon", data=lon)
            grid.create_dataset("lat", data=lat)
            grid.create_dataset("precipitation", data=precip)
        return path

    def test_parses_expected_pixel_count_and_excludes_fill(self, synthetic_granule):
        df = imerg.read_granule_precip_mm(synthetic_granule, bbox=(92.5, 23.6, 92.8, 23.8))
        # 4 lon x 3 lat = 12 pixels, minus 1 fill-value pixel = 11.
        assert len(df) == 11

    def test_converts_rate_to_half_hour_depth(self, synthetic_granule):
        df = imerg.read_granule_precip_mm(synthetic_granule, bbox=(92.5, 23.6, 92.8, 23.8))
        # 2.0 mm/hr over a 30-minute granule -> 1.0 mm depth.
        assert df["precip_mm"].iloc[0] == pytest.approx(1.0)

    def test_bbox_filters_pixels(self, synthetic_granule):
        df = imerg.read_granule_precip_mm(synthetic_granule, bbox=(92.5, 23.6, 92.6, 23.7))
        assert set(df["lon"].round(2)) <= {92.5, 92.6}

    def test_missing_variable_raises_clear_error(self, tmp_path):
        import h5py

        path = tmp_path / "wrong_structure.HDF5"
        with h5py.File(path, "w") as f:
            f.create_group("Grid").create_dataset("lon", data=[1.0])
        with pytest.raises(RuntimeError, match="not found"):
            imerg.read_granule_precip_mm(path, bbox=(0, 0, 1, 1))


class TestRollingFeatures:
    def test_sums_within_window_excludes_outside(self):
        import pandas as pd

        now = datetime(2026, 8, 25, 12, 0, tzinfo=timezone.utc)
        ts = pd.DataFrame(
            {
                "timestamp": [
                    (now - pd.Timedelta(minutes=30)).isoformat(),
                    (now - pd.Timedelta(hours=2)).isoformat(),
                    (now - pd.Timedelta(hours=100)).isoformat(),
                ],
                "pixel_id": ["92.70_23.70"] * 3,
                "precip_mm": [1.0, 2.0, 100.0],
            }
        )
        features, earliest = imerg.compute_rolling_features(ts, now)
        # rain_1h only sees the 30-min-ago row (1.0); rain_6h sees the first two (1.0+2.0=3.0).
        assert features["92.70_23.70"]["rain_1h"] == pytest.approx(1.0)
        assert features["92.70_23.70"]["rain_6h"] == pytest.approx(3.0)
        assert earliest is not None

    def test_empty_timeseries_returns_empty(self):
        import pandas as pd

        features, earliest = imerg.compute_rolling_features(pd.DataFrame(), datetime.now(timezone.utc))
        assert features == {}
        assert earliest is None

    def test_missing_pixel_defaults_handled_by_caller_not_crash(self):
        import pandas as pd

        now = datetime(2026, 8, 25, 12, 0, tzinfo=timezone.utc)
        ts = pd.DataFrame(
            {
                "timestamp": [now.isoformat()],
                "pixel_id": ["92.70_23.70"],
                "precip_mm": [5.0],
            }
        )
        features, _ = imerg.compute_rolling_features(ts, now)
        assert "92.70_23.70" in features
        assert features["92.70_23.70"]["antecedent_30d"] == pytest.approx(5.0)


class TestAssignCellsToPixels:
    def test_maps_cell_to_nearest_pixel(self, tmp_path):
        import geopandas as gpd
        from shapely.geometry import Point

        gdf = gpd.GeoDataFrame(
            {"cell_id": ["aizawl_000_000", "aizawl_000_001"]},
            geometry=[Point(92.73, 23.71), Point(92.77, 23.74)],
            crs="EPSG:4326",
        )
        path = tmp_path / "cells.gpkg"
        gdf.to_file(path, driver="GPKG")

        mapping = imerg.assign_cells_to_pixels(path)
        assert set(mapping.columns) == {"cell_id", "pixel_id"}
        assert len(mapping) == 2
        # 92.73 rounds to 92.70 at 0.1deg grid; 92.77 rounds to 92.80.
        row0 = mapping[mapping["cell_id"] == "aizawl_000_000"].iloc[0]
        assert row0["pixel_id"] == "92.70_23.70"
