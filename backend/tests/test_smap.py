"""Contract test for ingest/live/smap.py's pure logic (BUILD_PLAN.md task 1.7). No real network
access — real granule downloads (and even the CMR search API itself) were unreachable from this
sandboxed environment this session (see the module's own docstring), so this exercises everything
that CAN be verified without it: CMR query construction, CMR-response parsing against a recorded
fixture, HDF5 parsing against a recorded synthetic fixture built to the publicly-documented
SPL3SMP_E structure, AM/PM quality-based fallback selection, and cell-to-pixel assignment.

Skipped entirely if requirements-ingest.txt isn't installed.
"""
from __future__ import annotations

import importlib.util
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import pytest

pytest.importorskip("h5py")
pytest.importorskip("geopandas")
pytest.importorskip("pandas")

SCRIPT_PATH = Path(__file__).resolve().parents[1] / "app" / "ingest" / "live" / "smap.py"
FIXTURES_DIR = Path(__file__).resolve().parent / "fixtures"
SMAP_FIXTURE_H5 = FIXTURES_DIR / "smap_synthetic_granule.h5"
CMR_FIXTURE_JSON = FIXTURES_DIR / "cmr_smap_granule_response.json"

AIZAWL_BBOX = (92.60, 23.60, 92.85, 23.85)


def _load_smap():
    spec = importlib.util.spec_from_file_location("app.ingest.live.smap", SCRIPT_PATH)
    module = importlib.util.module_from_spec(spec)
    sys.modules["app.ingest.live.smap"] = module
    spec.loader.exec_module(module)
    return module


smap = _load_smap()


def test_module_exists():
    assert SCRIPT_PATH.is_file()


def test_recorded_fixtures_exist():
    """task 1.10's own requirement: a recorded fixture under tests/fixtures/, not just an
    inline-constructed one (see this session's spot-check note on imerg.py for why this matters)."""
    assert SMAP_FIXTURE_H5.is_file()
    assert CMR_FIXTURE_JSON.is_file()


class TestGranuleDayBounds:
    def test_floors_to_utc_day(self):
        dt = datetime(2026, 8, 25, 17, 42, tzinfo=timezone.utc)
        start, end = smap.granule_day_bounds(dt)
        assert start == datetime(2026, 8, 25, 0, 0, tzinfo=timezone.utc)
        assert end == datetime(2026, 8, 25, 23, 59, 59, tzinfo=timezone.utc)

    def test_naive_datetime_rejected(self):
        with pytest.raises(ValueError):
            smap.granule_day_bounds(datetime(2026, 8, 25))


class TestCmrQueryBuilding:
    def test_query_contains_product_identity_and_bbox(self):
        dt = datetime(2026, 8, 25, tzinfo=timezone.utc)
        url = smap.cmr_granule_search_url(dt, AIZAWL_BBOX)
        assert url.startswith(smap.CMR_GRANULE_SEARCH_URL + "?")
        assert f"short_name={smap.SMAP_SHORT_NAME}" in url
        assert f"version={smap.SMAP_VERSION}" in url
        assert "2026-08-25T00%3A00%3A00Z" in url or "2026-08-25T00:00:00Z" in url

    def test_granule_cache_path_stable_and_distinct_per_day(self, tmp_path):
        d1 = datetime(2026, 8, 25, 3, 0, tzinfo=timezone.utc)
        d2 = datetime(2026, 8, 26, 3, 0, tzinfo=timezone.utc)
        p1 = smap.granule_cache_path(d1, tmp_path)
        p2 = smap.granule_cache_path(d2, tmp_path)
        assert p1 != p2
        assert smap.granule_cache_path(d1, tmp_path) == p1


class TestExtractDataDownloadUrl:
    @pytest.fixture
    def cmr_response(self):
        return json.loads(CMR_FIXTURE_JSON.read_text())

    def test_finds_h5_data_link(self, cmr_response):
        href = smap.extract_data_download_url(cmr_response)
        assert href is not None
        assert href.endswith(".h5")
        assert href.startswith("https://n5eil01u.ecs.nsidc.org/")

    def test_ignores_metadata_and_browse_links(self, cmr_response):
        href = smap.extract_data_download_url(cmr_response)
        assert not href.endswith(".xml")
        assert not href.endswith(".jpg")

    def test_no_entries_returns_none(self):
        assert smap.extract_data_download_url({"feed": {"entry": []}}) is None

    def test_missing_feed_key_returns_none(self):
        assert smap.extract_data_download_url({}) is None


class TestFindGranuleDownloadUrl:
    def test_raises_clear_error_when_cmr_finds_nothing(self, monkeypatch):
        class FakeResponse:
            def raise_for_status(self):
                pass

            def json(self):
                return {"feed": {"entry": []}}

        def fake_get(url, timeout):
            return FakeResponse()

        monkeypatch.setattr(smap.requests, "get", fake_get)
        with pytest.raises(RuntimeError, match="No SPL3SMP_E granule found"):
            smap.find_granule_download_url(datetime(2026, 8, 25, tzinfo=timezone.utc), AIZAWL_BBOX)

    def test_returns_href_from_real_shaped_fixture(self, monkeypatch):
        cmr_response = json.loads(CMR_FIXTURE_JSON.read_text())

        class FakeResponse:
            def raise_for_status(self):
                pass

            def json(self):
                return cmr_response

        monkeypatch.setattr(smap.requests, "get", lambda url, timeout: FakeResponse())
        href = smap.find_granule_download_url(datetime(2026, 8, 25, tzinfo=timezone.utc), AIZAWL_BBOX)
        assert href.endswith(".h5")


class TestFindLatestAvailableDate:
    def test_falls_back_to_earlier_day_when_today_missing(self, monkeypatch):
        calls = []

        def fake_find(date, bbox, timeout=60.0):
            calls.append(date)
            if len(calls) < 3:
                raise RuntimeError("not published yet")
            return "https://example.invalid/granule.h5"

        monkeypatch.setattr(smap, "find_granule_download_url", fake_find)
        now = datetime(2026, 8, 25, tzinfo=timezone.utc)
        found = smap.find_latest_available_date(now, AIZAWL_BBOX, max_lookback_days=5)
        assert len(calls) == 3
        assert found == now - __import__("datetime").timedelta(days=2)

    def test_raises_after_exhausting_lookback_window(self, monkeypatch):
        monkeypatch.setattr(
            smap,
            "find_granule_download_url",
            lambda date, bbox, timeout=60.0: (_ for _ in ()).throw(RuntimeError("nope")),
        )
        with pytest.raises(RuntimeError, match="No SPL3SMP_E granule found"):
            smap.find_latest_available_date(
                datetime(2026, 8, 25, tzinfo=timezone.utc), AIZAWL_BBOX, max_lookback_days=2
            )


class TestDownloadGranuleValidation:
    def test_rejects_non_hdf5_response(self, tmp_path, monkeypatch):
        class FakeResponse:
            content = b"<!DOCTYPE html><html>not a granule</html>"

            def raise_for_status(self):
                pass

        class FakeSession:
            def __init__(self, *a, **kw):
                pass

            def get(self, url, timeout):
                return FakeResponse()

        monkeypatch.setattr(smap, "_EarthdataSession", FakeSession)
        monkeypatch.setattr(
            smap, "find_granule_download_url", lambda date, bbox: "https://example.invalid/x.h5"
        )
        with pytest.raises(RuntimeError, match="not an HDF5 file"):
            smap.download_granule(
                datetime(2026, 8, 25, tzinfo=timezone.utc), AIZAWL_BBOX, "u", "p", cache_dir=tmp_path
            )

    def test_returns_cached_path_without_network(self, tmp_path, monkeypatch):
        day = datetime(2026, 8, 25, tzinfo=timezone.utc)
        dest = smap.granule_cache_path(day, tmp_path)
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(smap.HDF5_MAGIC + b"fake-cached-granule")

        def fail_if_called(*a, **kw):
            raise AssertionError("should not hit CMR/network for an already-cached granule")

        monkeypatch.setattr(smap, "find_granule_download_url", fail_if_called)
        result = smap.download_granule(day, AIZAWL_BBOX, "u", "p", cache_dir=tmp_path)
        assert result == dest


class TestReadGranuleSoilMoistureRecordedFixture:
    """Parses the recorded synthetic HDF5 fixture (see its own generator script's docstring for
    what each cell in it is designed to exercise) built to the publicly-documented SPL3SMP_E v5
    layout. Validates the parsing LOGIC, not NASA's actual file bytes (see module docstring)."""

    def test_am_excludes_fill_and_out_of_bbox_pixels(self):
        df = smap.read_granule_soil_moisture(SMAP_FIXTURE_H5, AIZAWL_BBOX, pass_name="AM")
        # Fixture has exactly 3 non-fill, in-bbox AM cells: (1,1), (1,2), (3,3). (0,1) is
        # out-of-bbox (lon=92.50 < 92.60); (0,0)/(2,2) are fill in AM; everything else is fill.
        assert set(df["pixel_id"]) == {"ease_1_1", "ease_1_2", "ease_3_3"}

    def test_out_of_bbox_pixel_excluded_even_though_value_looks_valid(self):
        df = smap.read_granule_soil_moisture(SMAP_FIXTURE_H5, AIZAWL_BBOX, pass_name="AM")
        assert "ease_0_1" not in set(df["pixel_id"])

    def test_recommended_quality_flag_parsed_correctly(self):
        df = smap.read_granule_soil_moisture(SMAP_FIXTURE_H5, AIZAWL_BBOX, pass_name="AM")
        by_pixel = df.set_index("pixel_id")
        assert bool(by_pixel.loc["ease_1_1", "recommended_quality"]) is True
        assert bool(by_pixel.loc["ease_1_2", "recommended_quality"]) is False

    def test_soil_moisture_values_match_fixture(self):
        df = smap.read_granule_soil_moisture(SMAP_FIXTURE_H5, AIZAWL_BBOX, pass_name="AM")
        by_pixel = df.set_index("pixel_id")
        assert by_pixel.loc["ease_1_1", "soil_moisture"] == pytest.approx(0.28)
        assert by_pixel.loc["ease_3_3", "soil_moisture"] == pytest.approx(0.40)

    def test_pm_group_parses_suffixed_fields(self):
        df = smap.read_granule_soil_moisture(SMAP_FIXTURE_H5, AIZAWL_BBOX, pass_name="PM")
        by_pixel = df.set_index("pixel_id")
        assert by_pixel.loc["ease_2_2", "soil_moisture"] == pytest.approx(0.19)

    def test_missing_group_raises_clear_error(self, tmp_path):
        import h5py

        path = tmp_path / "wrong_structure.h5"
        with h5py.File(path, "w") as f:
            f.create_group("Nope")
        with pytest.raises(RuntimeError, match="not found"):
            smap.read_granule_soil_moisture(path, AIZAWL_BBOX, pass_name="AM")

    def test_invalid_pass_name_rejected(self):
        with pytest.raises(ValueError):
            smap.read_granule_soil_moisture(SMAP_FIXTURE_H5, AIZAWL_BBOX, pass_name="NOON")


class TestSelectBestReading:
    def test_prefers_am_recommended_over_everything(self):
        readings = smap.extract_pixel_readings(SMAP_FIXTURE_H5, AIZAWL_BBOX)
        best = smap.select_best_reading(readings, "ease_3_3")
        # AM=0.40 and PM=0.90 are BOTH recommended at this pixel; AM must win (priority order).
        assert best["pass_name"] == "AM"
        assert best["soil_moisture"] == pytest.approx(0.40)

    def test_falls_back_to_pm_recommended_when_am_not_recommended(self):
        readings = smap.extract_pixel_readings(SMAP_FIXTURE_H5, AIZAWL_BBOX)
        best = smap.select_best_reading(readings, "ease_1_2")
        assert best["pass_name"] == "PM"
        assert best["soil_moisture"] == pytest.approx(0.31)
        assert best["recommended_quality"] is True

    def test_falls_back_to_pm_when_am_missing_entirely(self):
        readings = smap.extract_pixel_readings(SMAP_FIXTURE_H5, AIZAWL_BBOX)
        best = smap.select_best_reading(readings, "ease_2_2")
        assert best["pass_name"] == "PM"
        assert best["soil_moisture"] == pytest.approx(0.19)

    def test_missing_pixel_returns_none(self):
        readings = smap.extract_pixel_readings(SMAP_FIXTURE_H5, AIZAWL_BBOX)
        assert smap.select_best_reading(readings, "ease_99_99") is None


class TestUpdateLatestCache:
    def test_upsert_creates_and_overwrites(self, tmp_path):
        store = tmp_path / "latest.csv"
        readings = smap.extract_pixel_readings(SMAP_FIXTURE_H5, AIZAWL_BBOX)
        day1 = datetime(2026, 8, 24, tzinfo=timezone.utc)
        smap.update_latest_cache(readings, day1, store)

        import pandas as pd

        df1 = pd.read_csv(store)
        assert "ease_1_1" in set(df1["pixel_id"])
        assert (df1["date"] == "2026-08-24").all()

        # Re-run for a later day with the SAME readings: must overwrite, not duplicate.
        day2 = datetime(2026, 8, 25, tzinfo=timezone.utc)
        smap.update_latest_cache(readings, day2, store)
        df2 = pd.read_csv(store)
        assert len(df2) == len(df1)  # same pixel set -> same row count, not doubled
        assert (df2["date"] == "2026-08-25").all()


class TestAssignCellsToPixels:
    def test_maps_cell_to_nearest_pixel(self, tmp_path):
        import geopandas as gpd
        import pandas as pd
        from shapely.geometry import Point

        gdf = gpd.GeoDataFrame(
            {"cell_id": ["aizawl_000_000", "aizawl_000_001"]},
            geometry=[Point(92.71, 23.71), Point(92.81, 23.91)],
            crs="EPSG:4326",
        )
        cells_path = tmp_path / "cells.gpkg"
        gdf.to_file(cells_path, driver="GPKG")

        pixel_lookup = pd.DataFrame(
            {
                "pixel_id": ["ease_1_1", "ease_3_3"],
                "lon": [92.70, 92.80],
                "lat": [23.70, 23.90],
            }
        )
        mapping = smap.assign_cells_to_pixels(cells_path, pixel_lookup)
        assert set(mapping.columns) == {"cell_id", "pixel_id"}
        row0 = mapping[mapping["cell_id"] == "aizawl_000_000"].iloc[0]
        assert row0["pixel_id"] == "ease_1_1"
        row1 = mapping[mapping["cell_id"] == "aizawl_000_001"].iloc[0]
        assert row1["pixel_id"] == "ease_3_3"

    def test_empty_pixel_lookup_raises(self, tmp_path):
        import geopandas as gpd
        import pandas as pd
        from shapely.geometry import Point

        gdf = gpd.GeoDataFrame(
            {"cell_id": ["aizawl_000_000"]}, geometry=[Point(92.71, 23.71)], crs="EPSG:4326"
        )
        cells_path = tmp_path / "cells.gpkg"
        gdf.to_file(cells_path, driver="GPKG")
        with pytest.raises(ValueError, match="empty"):
            smap.assign_cells_to_pixels(cells_path, pd.DataFrame(columns=["pixel_id", "lon", "lat"]))
