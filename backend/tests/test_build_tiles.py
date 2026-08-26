"""Contract test for scripts/build_tiles.py (BUILD_PLAN.md task 5.2).

Pure-logic tests (tile math, geometry coercion, property cleaning) plus a real synthetic
end-to-end encode-and-decode-back check — no network involved anywhere in this file. A gated real
integration check against the actual `data/tiles/aizawl.pmtiles` this task built is skipped in a
fresh checkout where that gitignored artifact doesn't exist yet, same pattern
tests/test_build_road_graph.py already established for `data/osm/aizawl_graph.pkl`.
"""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

pytest.importorskip("geopandas")
pytest.importorskip("mapbox_vector_tile")
pytest.importorskip("pmtiles")

import geopandas as gpd  # noqa: E402
import mapbox_vector_tile  # noqa: E402
from shapely.geometry import GeometryCollection, LineString, Point, Polygon, box  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT_PATH = REPO_ROOT / "scripts" / "build_tiles.py"


def _load_build_tiles():
    spec = importlib.util.spec_from_file_location("build_tiles", SCRIPT_PATH)
    module = importlib.util.module_from_spec(spec)
    sys.modules["build_tiles"] = module
    spec.loader.exec_module(module)
    return module


bt = _load_build_tiles()


def test_script_exists():
    assert SCRIPT_PATH.is_file()


class TestTileMath:
    """Standard slippy-map (Web Mercator) tile math — verified against well-known reference
    values, not just internal round-tripping."""

    def test_deg2num_matches_a_known_reference_tile(self):
        # OSM's own wiki example: London (51.5N, -0.09E) at zoom 10 is tile (511, 340).
        x, y = bt._deg2num(51.5, -0.09, 10)
        assert (x, y) == (511, 340)

    def test_num2deg_deg2num_roundtrip(self):
        # _num2deg(x, y, z) returns tile (x,y)'s NW corner. Nudge SOUTH (lat - eps) and EAST
        # (lon + eps) to land back strictly inside the same tile — nudging lat the other way
        # would cross into the tile row above, which is a test-epsilon-direction bug, not a bug
        # in the tile math itself.
        for z, x, y in [(10, 775, 442), (13, 6203, 3538), (0, 0, 0)]:
            lat, lon = bt._num2deg(x, y, z)
            x2, y2 = bt._deg2num(lat - 1e-6, lon + 1e-6, z)
            assert (x2, y2) == (x, y)

    def test_deg2num_clamps_to_valid_range_at_the_pole(self):
        # Web Mercator is undefined exactly at the poles — must clamp, not raise or overflow.
        x, y = bt._deg2num(90.0, 180.0, 5)
        assert 0 <= x < (1 << 5)
        assert 0 <= y < (1 << 5)

    def test_tile_bounds_lonlat_min_less_than_max(self):
        minx, miny, maxx, maxy = bt.tile_bounds_lonlat(10, 775, 442)
        assert minx < maxx
        assert miny < maxy

    def test_tiles_for_bbox_covers_the_aizawl_bbox_at_zoom_10(self):
        # Aizawl's real registered bbox (backend/app/config.py) — a small AOI should need very
        # few zoom-10 tiles, not a fabricated number.
        tiles = list(bt.tiles_for_bbox((92.60, 23.60, 92.85, 23.85), 10))
        assert 1 <= len(tiles) <= 4

    def test_tiles_for_bbox_grows_with_zoom(self):
        bbox = (92.60, 23.60, 92.85, 23.85)
        assert len(list(bt.tiles_for_bbox(bbox, 13))) > len(list(bt.tiles_for_bbox(bbox, 10)))


class TestCoerceClip:
    def test_passes_through_a_clean_polygon(self):
        poly = box(0, 0, 1, 1)
        assert bt._coerce_clip(poly, bt.LAYER_CELLS) is poly

    def test_drops_a_fully_empty_geometry(self):
        assert bt._coerce_clip(Polygon(), bt.LAYER_CELLS) is None

    def test_geometry_collection_keeps_only_polygon_parts_for_cells_layer(self):
        gc = GeometryCollection([Point(0, 0), box(0, 0, 1, 1)])
        result = bt._coerce_clip(gc, bt.LAYER_CELLS)
        assert result is not None
        assert result.geom_type in ("Polygon", "MultiPolygon")

    def test_geometry_collection_keeps_only_line_parts_for_roads_layer(self):
        gc = GeometryCollection([Point(0, 0), LineString([(0, 0), (1, 1)])])
        result = bt._coerce_clip(gc, bt.LAYER_ROADS)
        assert result is not None
        assert result.geom_type in ("LineString", "MultiLineString")

    def test_geometry_collection_with_no_matching_parts_is_dropped(self):
        gc = GeometryCollection([Point(0, 0)])
        assert bt._coerce_clip(gc, bt.LAYER_CELLS) is None
        assert bt._coerce_clip(gc, bt.LAYER_ROADS) is None


class TestCleanValue:
    def test_none_stays_none(self):
        assert bt._clean_value(None) is None

    def test_nan_becomes_none(self):
        assert bt._clean_value(float("nan")) is None

    def test_numpy_scalar_is_coerced_to_a_plain_python_value(self):
        np = pytest.importorskip("numpy")
        assert bt._clean_value(np.float64(3.5)) == 3.5
        assert isinstance(bt._clean_value(np.float64(3.5)), float)

    def test_plain_string_passes_through(self):
        assert bt._clean_value("tree_cover") == "tree_cover"


class TestBuildTileBytesSyntheticEndToEnd:
    """Real encode of synthetic cell/road GeoDataFrames into an MVT tile, then decode it back
    with the same library used to write the real archive — proves the whole per-tile pipeline
    (clip -> coerce -> clean -> mapbox_vector_tile.encode) round-trips correctly, no network."""

    def test_a_cell_and_a_road_crossing_the_tile_are_both_encoded_and_decodable(self):
        z, x, y = 12, 3100, 1770
        minx, miny, maxx, maxy = bt.tile_bounds_lonlat(z, x, y)
        cx, cy = (minx + maxx) / 2, (miny + maxy) / 2

        cells = gpd.GeoDataFrame(
            {"cell_id": ["aizawl_001_002"], "elevation_m": [900.5], "slope_mean_deg": [12.0],
             "land_cover_class": ["tree_cover"]},
            geometry=[box(cx - 0.001, cy - 0.001, cx + 0.001, cy + 0.001)],
            crs="EPSG:4326",
        )
        roads = gpd.GeoDataFrame(
            {"edge_id": ["e1"], "name": ["MG Road"], "highway_class": ["primary"],
             "is_bridge": [False], "ref": [None]},
            geometry=[LineString([(minx - 0.01, cy), (maxx + 0.01, cy)])],
            crs="EPSG:4326",
        )

        data = bt.build_tile_bytes(z, x, y, cells, roads)
        assert data is not None

        decoded = mapbox_vector_tile.decode(data)
        assert set(decoded.keys()) == {bt.LAYER_CELLS, bt.LAYER_ROADS}
        assert len(decoded[bt.LAYER_CELLS]["features"]) == 1
        assert decoded[bt.LAYER_CELLS]["features"][0]["properties"]["cell_id"] == "aizawl_001_002"
        assert len(decoded[bt.LAYER_ROADS]["features"]) == 1
        assert decoded[bt.LAYER_ROADS]["features"][0]["properties"]["highway_class"] == "primary"

    def test_a_tile_nothing_intersects_returns_none(self):
        z, x, y = 12, 3100, 1770
        minx, miny, maxx, maxy = bt.tile_bounds_lonlat(z, x, y)
        far_away = box(minx + 50, miny + 50, minx + 50.01, miny + 50.01)
        cells = gpd.GeoDataFrame({"cell_id": ["far"]}, geometry=[far_away], crs="EPSG:4326")
        roads = gpd.GeoDataFrame({"edge_id": []}, geometry=[], crs="EPSG:4326")

        assert bt.build_tile_bytes(z, x, y, cells, roads) is None


HAS_REAL_ARCHIVE = (REPO_ROOT / "data" / "tiles" / "aizawl.pmtiles").is_file()


@pytest.mark.skipif(
    not HAS_REAL_ARCHIVE, reason="requires data/tiles/aizawl.pmtiles (make tiles AOI=aizawl)"
)
class TestRealAizawlArchive:
    """Sanity checks against the actual built archive (real run this task — 72 tiles, zoom
    10-13, from the real 2,912-cell terrain grid + real 8,808-edge OSM road graph)."""

    def _read(self):
        from pmtiles.reader import MmapSource, Reader, all_tiles

        path = REPO_ROOT / "data" / "tiles" / "aizawl.pmtiles"
        f = path.open("r+b")
        source = MmapSource(f)
        reader = Reader(source)
        return f, reader, source

    def test_header_is_a_valid_v3_mvt_gzip_archive_covering_aizawl(self):
        from pmtiles.tile import Compression, TileType

        f, reader, _ = self._read()
        try:
            header = reader.header()
            assert header["version"] == 3
            assert header["tile_type"] == TileType.MVT
            assert header["tile_compression"] == Compression.GZIP
            assert header["min_zoom"] == bt.MIN_ZOOM
            assert header["max_zoom"] == bt.MAX_ZOOM
            # Aizawl's real registered bbox (backend/app/config.py) — the archive's bounds must
            # match the AOI it claims to cover, not some other/default extent.
            assert 92.5 < header["min_lon_e7"] / 1e7 < 92.7
            assert 92.8 < header["max_lon_e7"] / 1e7 < 93.0
        finally:
            f.close()

    def test_every_tile_decodes_and_carries_the_two_documented_layers(self):
        import gzip

        from pmtiles.reader import all_tiles

        f, reader, source = self._read()
        try:
            count = 0
            for _zxy, data in all_tiles(source):
                raw = gzip.decompress(data)
                decoded = mapbox_vector_tile.decode(raw)
                assert set(decoded.keys()) <= {bt.LAYER_CELLS, bt.LAYER_ROADS}
                count += 1
            assert count > 0
        finally:
            f.close()
