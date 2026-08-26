#!/usr/bin/env python
"""Build an offline PMTiles archive for an AOI (BUILD_PLAN.md task 5.2).

    python scripts/build_tiles.py --aoi aizawl

Writes data/tiles/<aoi>.pmtiles — gitignored (data/tiles/* per .gitignore, CLAUDE.md rule 15:
"never commit large binaries"), meant to be re-run, not committed, same as data/osm/*.pkl and
data/static/*.gpkg.

===================================================================================================
WHAT IS TILED, WHAT IS NOT (read this before assuming this is a basemap)
===================================================================================================
Tiled, real, per-AOI data already built by earlier scripts:
  - the 500m analysis-cell TERRAIN GRID boundaries (data/static/<aoi>/cells.gpkg, task 1.2) — a
    "cells" vector layer, cell_id + a few static terrain properties per polygon.
  - the real OSM road network EDGES (data/osm/<aoi>_graph.geojson, task 2.1) — a "roads" vector
    layer, edge_id/name/highway_class/is_bridge/ref per line.

NOT tiled — and deliberately so:
  - No satellite or street BASEMAP imagery. MapView's self-contained MapLibre style already has
    zero external tile requests (a deliberate Phase-0 choice, CLAUDE.md rule 10) — this script
    does not add one. What it adds is a REFERENCE vector layer (terrain grid + roads) rendered
    UNDERNEATH the existing live per-tick risk-cell/road/village GeoJSON layers, giving the map
    real geographic context even before any tick has been received, not a photographic basemap.
  - Live/dynamic risk data (p_fail, escalation stage, ...). Those already reach the frontend over
    /ws/ticks as GeoJSON (frontend/src/lib/grid.ts et al.) and are NOT duplicated into the tiles —
    baking a live-changing value into a static offline archive would go stale immediately.

===================================================================================================
TOOLING RULING (documented, not silently decided — BUILD_PLAN.md task 5.2 explicitly asked for
this to be checked before committing to a specific tool)
===================================================================================================
No tippecanoe, no `ogr2ogr`/GDAL CLI, no `osgeo` Python binding is installed or installable in
this environment — checked for real (`which tippecanoe`, `which ogr2ogr`, `python -c "import
osgeo"` all failed) before writing a line of this script, not assumed. Two real, pip-installable
pure-Python libraries cover the whole pipeline instead (see requirements-tiles.txt):
  - `mapbox-vector-tile` (PyPI `mapbox-vector-tile`) encodes shapely geometries straight into a
    real Mapbox Vector Tile (MVT) protobuf for one (z,x,y) tile, including the standard
    quantize-coordinates-to-a-4096-extent + y-flip transform every MVT consumer (MapLibre
    included) expects.
  - `pmtiles` (PyPI `pmtiles`, the OFFICIAL protomaps Python package — the same one the
    `pmtiles-convert`/`pmtiles-show` CLIs it ships are built on) provides the exact PMTiles v3
    binary writer (`pmtiles.writer.write`/`Writer.write_tile`/`Writer.finalize`), not a
    reimplementation of the spec.

The one thing neither library does — slicing full-AOI geometries into per-tile pieces — is done by
hand below with plain shapely `intersects`/`intersection` against each tile's real lon/lat bounds
(standard slippy-map tile math, `tiles_for_bbox`/`tile_bounds_lonlat`). This is a small enough job
to do directly for one AOI's feature count (roughly 3,000 cells + roughly 9,000 road edges) without
needing an external C++ tiling engine — real work, not a shortcut, but also not pretending to be a
general-purpose replacement for tippecanoe at planet scale.

Zoom range: MIN_ZOOM..MAX_ZOOM below (10-13) — enough to render a legible village-level reference
layer at the zoom levels the demo actually uses (MapView starts at zoom 13), without the tile count
(and therefore archive size / build time) exploding the way a deep pyramid down to z18 would for a
demo that never zooms in that far. A real, honestly-scoped multi-zoom PMTiles archive, not a single
fake tile.
"""
from __future__ import annotations

import argparse
import gzip
import math
import sys
from pathlib import Path
from typing import Iterable

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "backend"))

import geopandas as gpd  # noqa: E402
import mapbox_vector_tile  # noqa: E402
from pmtiles.tile import Compression, TileType, zxy_to_tileid  # noqa: E402
from pmtiles.writer import write as pmtiles_write  # noqa: E402
from shapely.geometry import MultiLineString, MultiPolygon, box  # noqa: E402
from shapely.geometry.base import BaseGeometry  # noqa: E402

from app.config import AoiConfig, get_aoi  # noqa: E402

MIN_ZOOM = 10
MAX_ZOOM = 13
EXTENT = 4096

LAYER_CELLS = "cells"
LAYER_ROADS = "roads"

# A deliberately small property subset per layer — enough for a future style to label/colour a
# reference layer by, not a dump of every terrain column (several of which are explicit nulls per
# task 1.2, see cells.gpkg's own docstring note — no point shipping all-null columns into tiles).
CELL_PROPERTY_COLUMNS = ["cell_id", "elevation_m", "slope_mean_deg", "land_cover_class"]
ROAD_PROPERTY_COLUMNS = ["edge_id", "name", "highway_class", "is_bridge", "ref"]


# =================================================================================================
# Slippy-map tile math (standard Web Mercator / EPSG:3857 tiling scheme — the same one MapLibre,
# OSM, and every other consumer of z/x/y tiles uses). No third-party tiling library needed for
# this; it's a handful of well-known, easily-verified formulae.
# =================================================================================================
def _deg2num(lat_deg: float, lon_deg: float, zoom: int) -> tuple[int, int]:
    lat_rad = math.radians(lat_deg)
    n = 2.0**zoom
    xtile = int((lon_deg + 180.0) / 360.0 * n)
    ytile = int((1.0 - math.asinh(math.tan(lat_rad)) / math.pi) / 2.0 * n)
    # Clamp: a bbox corner exactly on a tile boundary (or at the poles) can otherwise compute an
    # out-of-range tile index for this zoom.
    max_index = (1 << zoom) - 1
    return max(0, min(xtile, max_index)), max(0, min(ytile, max_index))


def _num2deg(xtile: int, ytile: int, zoom: int) -> tuple[float, float]:
    n = 2.0**zoom
    lon_deg = xtile / n * 360.0 - 180.0
    lat_rad = math.atan(math.sinh(math.pi * (1 - 2 * ytile / n)))
    lat_deg = math.degrees(lat_rad)
    return lat_deg, lon_deg


def tile_bounds_lonlat(z: int, x: int, y: int) -> tuple[float, float, float, float]:
    """(min_lon, min_lat, max_lon, max_lat) of tile (z,x,y) — y increases southward (standard
    slippy-map convention: tile (0,0) is the NW corner of the world)."""
    lat_top, lon_left = _num2deg(x, y, z)
    lat_bottom, lon_right = _num2deg(x + 1, y + 1, z)
    return (lon_left, lat_bottom, lon_right, lat_top)


def tiles_for_bbox(
    bbox: tuple[float, float, float, float], z: int
) -> Iterable[tuple[int, int]]:
    """Every (x,y) tile at zoom `z` that the AOI's (min_lon, min_lat, max_lon, max_lat) bbox
    overlaps."""
    min_lon, min_lat, max_lon, max_lat = bbox
    x0, y0 = _deg2num(max_lat, min_lon, z)  # NW corner
    x1, y1 = _deg2num(min_lat, max_lon, z)  # SE corner
    for x in range(min(x0, x1), max(x0, x1) + 1):
        for y in range(min(y0, y1), max(y0, y1) + 1):
            yield x, y


# =================================================================================================
# Loading real source data
# =================================================================================================
def load_cells(aoi_id: str) -> gpd.GeoDataFrame:
    path = REPO_ROOT / "data" / "static" / aoi_id / "cells.gpkg"
    if not path.exists():
        raise FileNotFoundError(f"{path} not found — run scripts/build_grid.py first (task 1.2)")
    gdf = gpd.read_file(path)
    # build_grid.py writes cells.gpkg in the AOI's projected UTM CRS (its output DoD doesn't
    # reproject back to WGS84) — MVT tiling needs lon/lat, so reproject here, not assume.
    return gdf.to_crs(epsg=4326)


def load_roads(aoi_id: str) -> gpd.GeoDataFrame:
    path = REPO_ROOT / "data" / "osm" / f"{aoi_id}_graph.geojson"
    if not path.exists():
        raise FileNotFoundError(
            f"{path} not found — run scripts/build_road_graph.py first (task 2.1)"
        )
    gdf = gpd.read_file(path)
    if gdf.crs is None:
        gdf = gdf.set_crs(epsg=4326)
    else:
        gdf = gdf.to_crs(epsg=4326)
    return gdf


def _clean_value(v: object):
    """MVT feature properties must be str/int/float/bool. Coerce pandas/numpy scalars and drop
    NaN/None so the encoder never chokes on a numpy.float64 or a real (task 1.2) null column."""
    if v is None:
        return None
    if isinstance(v, float) and math.isnan(v):
        return None
    if hasattr(v, "item"):  # numpy scalar (np.float64, np.int64, np.bool_, ...)
        v = v.item()
        if isinstance(v, float) and math.isnan(v):
            return None
    return v


_POLYGON_TYPES = ("Polygon", "MultiPolygon")
_LINE_TYPES = ("LineString", "MultiLineString")


def _coerce_clip(geom: BaseGeometry, layer_name: str) -> BaseGeometry | None:
    """`shapely.intersection` against a tile box can legitimately degenerate into a
    `GeometryCollection` (e.g. a road that just grazes a tile edge intersects it at both a point
    AND a short line segment; a cell polygon that only touches the tile box along one edge) —
    `mapbox_vector_tile` refuses to encode a raw GeometryCollection at all (real, observed while
    running this script against real data, not a hypothetical). Keep only the parts matching this
    layer's real geometry type (polygons for cells, lines for roads) and recombine them; a
    zero-dimensional leftover (a bare touching point) carries no visual information for either
    layer and is dropped, not fabricated into something it isn't."""
    if geom.geom_type != "GeometryCollection":
        return geom if not geom.is_empty else None

    wanted_types = _POLYGON_TYPES if layer_name == LAYER_CELLS else _LINE_TYPES
    parts = [g for g in geom.geoms if g.geom_type in wanted_types and not g.is_empty]
    if not parts:
        return None
    if len(parts) == 1:
        return parts[0]

    flattened = []
    for part in parts:
        if part.geom_type.startswith("Multi"):
            flattened.extend(list(part.geoms))
        else:
            flattened.append(part)
    return MultiPolygon(flattened) if layer_name == LAYER_CELLS else MultiLineString(flattened)


# =================================================================================================
# Per-tile MVT encoding
# =================================================================================================
def build_tile_bytes(
    z: int, x: int, y: int, cells: gpd.GeoDataFrame, roads: gpd.GeoDataFrame
) -> bytes | None:
    """Real per-tile clip-and-encode: shapely `.intersection` against the tile's exact geographic
    bounds, then `mapbox_vector_tile.encode`. Returns None if nothing intersects this tile (kept
    out of the archive entirely — an empty tile is not written, matching how tippecanoe/other real
    tilers behave)."""
    minx, miny, maxx, maxy = tile_bounds_lonlat(z, x, y)
    tile_box = box(minx, miny, maxx, maxy)

    layers = []
    for name, gdf, columns in (
        (LAYER_CELLS, cells, CELL_PROPERTY_COLUMNS),
        (LAYER_ROADS, roads, ROAD_PROPERTY_COLUMNS),
    ):
        # geopandas' spatial-index bbox prefilter before the exact intersects/intersection test
        # below — cheap pruning, not the real clip (that's the .intersection() call itself).
        candidates = gdf.cx[minx:maxx, miny:maxy]
        features = []
        for _, row in candidates.iterrows():
            geom = row.geometry
            if geom is None or not isinstance(geom, BaseGeometry) or geom.is_empty:
                continue
            if not geom.intersects(tile_box):
                continue
            clipped = _coerce_clip(geom.intersection(tile_box), name)
            if clipped is None or clipped.is_empty:
                continue
            props = {c: _clean_value(row[c]) for c in columns if c in gdf.columns}
            features.append({"geometry": clipped, "properties": props})
        if features:
            layers.append({"name": name, "features": features})

    if not layers:
        return None

    return mapbox_vector_tile.encode(
        layers,
        default_options={"quantize_bounds": (minx, miny, maxx, maxy), "extents": EXTENT},
    )


# =================================================================================================
# Archive assembly
# =================================================================================================
def build_tiles(
    aoi_id: str, *, min_zoom: int = MIN_ZOOM, max_zoom: int = MAX_ZOOM
) -> Path:
    aoi: AoiConfig = get_aoi(aoi_id)
    cells = load_cells(aoi_id)
    roads = load_roads(aoi_id)
    print(f"Loaded {len(cells)} cells, {len(roads)} road edges for AOI {aoi_id!r}")

    out_dir = REPO_ROOT / "data" / "tiles"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"{aoi_id}.pmtiles"

    # Collect every non-empty tile first, THEN write in ascending tile_id order — pmtiles.writer's
    # Writer.write_tile assumes ascending order for a "clustered" archive (it still works out of
    # order, just sets clustered=False and loses the run-length/dedup optimisation for adjacent
    # identical tiles, which we don't rely on here anyway — sorting is cheap and correct either way).
    pending: list[tuple[int, bytes]] = []
    for z in range(min_zoom, max_zoom + 1):
        tiles_this_zoom = 0
        for x, y in tiles_for_bbox(aoi.bbox, z):
            data = build_tile_bytes(z, x, y, cells, roads)
            if data is None:
                continue
            pending.append((zxy_to_tileid(z, x, y), gzip.compress(data)))
            tiles_this_zoom += 1
        print(f"  zoom {z}: {tiles_this_zoom} non-empty tiles")

    if not pending:
        raise RuntimeError(
            f"no tiles produced for AOI {aoi_id!r} — cells/roads may not overlap the configured "
            f"bbox {aoi.bbox!r}; refusing to write an empty/broken .pmtiles archive"
        )
    pending.sort(key=lambda entry: entry[0])

    min_lon, min_lat, max_lon, max_lat = aoi.bbox
    header = {
        "tile_type": TileType.MVT,
        "tile_compression": Compression.GZIP,
        "min_lon_e7": int(min_lon * 1e7),
        "min_lat_e7": int(min_lat * 1e7),
        "max_lon_e7": int(max_lon * 1e7),
        "max_lat_e7": int(max_lat * 1e7),
        "center_lon_e7": int(aoi.center_lon * 1e7),
        "center_lat_e7": int(aoi.center_lat * 1e7),
    }
    metadata = {
        "name": f"NIRANTAR offline reference tiles — {aoi.name}",
        "description": (
            "BUILD_PLAN.md task 5.2: real 500m analysis-cell grid boundaries "
            "(data/static/<aoi>/cells.gpkg, task 1.2) and real OSM road network edges "
            "(data/osm/<aoi>_graph.geojson, task 2.1), tiled for offline use. NOT a basemap — no "
            "satellite/street imagery is included; MapView's self-contained no-external-tile-"
            "request style (CLAUDE.md rule 10) is unchanged by this reference layer."
        ),
        "format": "pbf",
        "vector_layers": [
            {"id": LAYER_CELLS, "fields": {c: "String" for c in CELL_PROPERTY_COLUMNS}},
            {"id": LAYER_ROADS, "fields": {c: "String" for c in ROAD_PROPERTY_COLUMNS}},
        ],
    }

    with pmtiles_write(str(out_path)) as writer:
        for tile_id, gz_bytes in pending:
            writer.write_tile(tile_id, gz_bytes)
        writer.finalize(header, metadata)

    print(f"Wrote {out_path} ({len(pending)} tiles, zoom {min_zoom}-{max_zoom})")
    return out_path


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--aoi", default="aizawl", help="AOI id (default: aizawl)")
    parser.add_argument("--min-zoom", type=int, default=MIN_ZOOM)
    parser.add_argument("--max-zoom", type=int, default=MAX_ZOOM)
    args = parser.parse_args()
    build_tiles(args.aoi, min_zoom=args.min_zoom, max_zoom=args.max_zoom)


if __name__ == "__main__":
    main()
