"""Contract test for scripts/fetch_exposure.py's pure logic (BUILD_PLAN.md task 1.3). No network
access — Overpass/WorldPop fetches are verified by manually running the script against the real
Aizawl AOI (see CLAUDE.md §12 session log), same reasoning as test_build_grid.py.

Skipped entirely if the geo stack (requirements-geo.txt) isn't installed.
"""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

pytest.importorskip("rasterio")
pytest.importorskip("shapely")
pytest.importorskip("geopandas")

SCRIPT_PATH = Path(__file__).resolve().parents[2] / "scripts" / "fetch_exposure.py"


def _load_fetch_exposure():
    spec = importlib.util.spec_from_file_location("fetch_exposure", SCRIPT_PATH)
    module = importlib.util.module_from_spec(spec)
    sys.modules["fetch_exposure"] = module
    spec.loader.exec_module(module)
    return module


fe = _load_fetch_exposure()


def test_script_exists():
    assert SCRIPT_PATH.is_file()


class TestSafeInt:
    def test_plain_number(self):
        assert fe._safe_int("1500") == 1500

    def test_comma_separated(self):
        assert fe._safe_int("1,500") == 1500

    def test_none_is_none(self):
        assert fe._safe_int(None) is None

    def test_garbage_is_none(self):
        assert fe._safe_int("about 500 people") is None


class TestElementPoint:
    def test_node_uses_own_coords(self):
        pt = fe._element_point({"type": "node", "lon": 92.7, "lat": 23.7})
        assert (pt.x, pt.y) == (92.7, 23.7)

    def test_way_uses_center(self):
        pt = fe._element_point({"type": "way", "center": {"lon": 92.71, "lat": 23.71}})
        assert (pt.x, pt.y) == (92.71, 23.71)

    def test_way_without_center_is_none(self):
        assert fe._element_point({"type": "way"}) is None


class TestFetchVillagesParsing:
    """Exercises the Overpass-response-to-GeoDataFrame parsing directly, bypassing the network
    call — same pattern as test_build_grid.py's OSM tests."""

    def test_parses_node_with_population_tag(self, monkeypatch):
        fake_response = {
            "elements": [
                {
                    "type": "node",
                    "id": 12345,
                    "lon": 92.7,
                    "lat": 23.7,
                    "tags": {"place": "village", "name": "Test Village", "population": "1,200"},
                }
            ]
        }
        monkeypatch.setattr(fe, "_overpass_query", lambda query: fake_response)
        gdf = fe.fetch_villages((92.6, 23.6, 92.85, 23.85))
        assert len(gdf) == 1
        row = gdf.iloc[0]
        assert row["osm_id"] == 12345
        assert row["name"] == "Test Village"
        assert row["osm_population"] == 1200

    def test_empty_result_has_expected_columns(self, monkeypatch):
        monkeypatch.setattr(fe, "_overpass_query", lambda query: {"elements": []})
        gdf = fe.fetch_villages((92.6, 23.6, 92.85, 23.85))
        assert len(gdf) == 0
        assert set(gdf.columns) == {"osm_id", "name", "place_type", "osm_population", "geometry"}


class TestFetchAmenityParsing:
    def test_way_with_center_becomes_point(self, monkeypatch):
        fake_response = {
            "elements": [
                {
                    "type": "way",
                    "id": 999,
                    "center": {"lon": 92.72, "lat": 23.72},
                    "tags": {"amenity": "hospital", "name": "Civil Hospital"},
                }
            ]
        }
        monkeypatch.setattr(fe, "_overpass_query", lambda query: fake_response)
        gdf = fe.fetch_amenity((92.6, 23.6, 92.85, 23.85), "^hospital$")
        assert len(gdf) == 1
        assert gdf.iloc[0]["amenity"] == "hospital"
        assert gdf.iloc[0].geometry.x == pytest.approx(92.72)


class TestSamplePopulationWorldpop:
    def test_empty_villages_returns_empty_array(self):
        gdf = fe._empty_gdf(["osm_id", "name", "place_type", "osm_population", "geometry"])
        from app.config import get_aoi

        result = fe.sample_population_worldpop(gdf, get_aoi("aizawl"))
        assert len(result) == 0
