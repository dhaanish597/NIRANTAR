#!/usr/bin/env python
"""Build the 500 m analysis grid for an AOI (BUILD_PLAN.md task 1.2).

For each cell, computes: elevation (mean/min/max), slope (mean/max), aspect (circular mean),
relief (max-min elevation), TWI (topographic wetness index, via D8 flow accumulation),
distance to nearest road (OSM), and land-cover class (ESA WorldCover majority). Writes
data/static/<aoi>/cells.gpkg.

SCOPE CUT, flagged rather than silently dropped (CLAUDE.md §10 — "say so and propose a cut"):
task 1.2 also asks for plan/profile curvature, distance to nearest fault/lineament, and
lithology class. Curvature is cut this pass — every other feature here has a hand-verified
closed-form test case (see tests/test_build_grid.py); curvature's Zevenbergen & Thorne formula
has more ways to get a subtle sign error, and it's not one of the load-bearing terms in any of
the reference formulae in CLAUDE.md §4 the way slope and TWI are. Distance-to-fault has no
public data source I could confirm (not fabricating one); lithology_class is null pending task
1.4 (GSI Bhukosh access, or its documented coarse fallback — see Required_by_me.md). All three
are written as null/None columns so the schema is stable when they DO land, not silently
omitted from the output.

Terrain math runs on the DEM reprojected to the AOI's UTM zone (config.py) at native ~30 m
resolution — slope/aspect/curvature/flow-routing all assume locally-uniform-distance pixels,
which EPSG:4326 degrees are not. Flow accumulation is a standard D8 algorithm; NOTE it does not
include a depression-filling ("fill sinks") pre-pass, so TWI will be somewhat degraded in any
genuinely flat or pitted areas of the DEM — a documented simplification, not an oversight.

Usage:
    python scripts/build_grid.py --aoi aizawl
"""
from __future__ import annotations

import argparse
import math
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "backend"))

import geopandas as gpd  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
import rasterio  # noqa: E402
import requests  # noqa: E402
from rasterio.features import rasterize  # noqa: E402
from rasterio.warp import Resampling, calculate_default_transform, reproject, transform_bounds  # noqa: E402
from scipy import ndimage  # noqa: E402
from shapely.geometry import LineString, box  # noqa: E402
from shapely.strtree import STRtree  # noqa: E402

from app.config import AoiConfig, get_aoi  # noqa: E402

CELL_SIZE_M = 500.0
DEM_NODATA = -9999.0  # must match scripts/fetch_dem.py's sentinel
WORLDCOVER_BUCKET = "https://esa-worldcover.s3.eu-central-1.amazonaws.com"
WORLDCOVER_NODATA = 0  # ESA WorldCover's own "no data" class code

# --- 8-connected neighbourhood, (row_offset, col_offset), and distance factor in cell-size units.
_NEIGHBORS = [
    (dr, dc)
    for dr in (-1, 0, 1)
    for dc in (-1, 0, 1)
    if not (dr == 0 and dc == 0)
]
_SQRT2 = math.sqrt(2.0)


# =============================================================================================
# DEM reprojection
# =============================================================================================
def reproject_dem_to_utm(
    dem_path: Path, dst_crs: str, resolution_m: float = 30.0
) -> tuple[np.ndarray, rasterio.Affine, str]:
    """Reprojects a DEM (any CRS) to `dst_crs` at `resolution_m`, filling with DEM_NODATA."""
    with rasterio.open(dem_path) as src:
        transform, width, height = calculate_default_transform(
            src.crs, dst_crs, src.width, src.height, *src.bounds, resolution=resolution_m
        )
        dst = np.full((height, width), DEM_NODATA, dtype=np.float32)
        reproject(
            source=rasterio.band(src, 1),
            destination=dst,
            src_transform=src.transform,
            src_crs=src.crs,
            dst_transform=transform,
            dst_crs=dst_crs,
            src_nodata=src.nodata,
            dst_nodata=DEM_NODATA,
            resampling=Resampling.bilinear,
        )
    return dst, transform, dst_crs


# =============================================================================================
# Slope / aspect (Horn 1981, standard 3x3 weighted finite-difference kernel)
# =============================================================================================
def compute_slope_aspect_deg(
    elevation: np.ndarray, pixel_size_m: float, nodata: float = DEM_NODATA
) -> tuple[np.ndarray, np.ndarray]:
    """Returns (slope_deg, aspect_deg). aspect is compass bearing (0=N, 90=E, 180=S, 270=W) of
    the downhill direction — standard GIS convention. NaN where the 3x3 window touches nodata.

    Hand-verified sign convention (see tests/test_build_grid.py): a surface that rises to the
    east gives aspect=270 (faces west, i.e. downhill); a surface that rises to the north gives
    aspect=180 (faces south).
    """
    valid = elevation != nodata
    z = np.where(valid, elevation, np.nan).astype(np.float64)

    # 3x3 window: z1 z2 z3 / z4 z5 z6 / z7 z8 z9 (z1=NW ... z9=SE), via explicit shifted views
    # (not np.roll — roll wraps at edges, which would silently invent fake neighbours there).
    padded = np.pad(z, 1, mode="constant", constant_values=np.nan)

    def win(dr: int, dc: int) -> np.ndarray:
        return padded[1 + dr : 1 + dr + z.shape[0], 1 + dc : 1 + dc + z.shape[1]]

    z1, z2, z3 = win(-1, -1), win(-1, 0), win(-1, 1)
    z4, z6 = win(0, -1), win(0, 1)
    z7, z8, z9 = win(1, -1), win(1, 0), win(1, 1)

    with np.errstate(invalid="ignore"):
        dzdx_east = ((z3 + 2 * z6 + z9) - (z1 + 2 * z4 + z7)) / (8 * pixel_size_m)
        dzdy_north = ((z1 + 2 * z2 + z3) - (z7 + 2 * z8 + z9)) / (8 * pixel_size_m)

        slope_deg = np.degrees(np.arctan(np.hypot(dzdx_east, dzdy_north)))

        downhill_east = -dzdx_east
        downhill_north = -dzdy_north
        aspect_deg = np.degrees(np.arctan2(downhill_east, downhill_north)) % 360.0

    slope_deg[~valid] = np.nan
    aspect_deg[~valid] = np.nan
    return slope_deg, aspect_deg


# =============================================================================================
# D8 flow direction + accumulation, and TWI
# =============================================================================================
def compute_flow_accumulation_d8(elevation: np.ndarray, nodata: float = DEM_NODATA) -> np.ndarray:
    """Cells-draining-through-this-cell count, via D8 (steepest single downhill neighbour).

    NOTE: no depression-filling pre-pass (see module docstring) — a documented simplification,
    not a bug: local pits simply don't route flow onward, same as an unfilled real DEM would.
    """
    rows, cols = elevation.shape
    valid = elevation != nodata
    flat_elev = elevation.ravel()

    padded = np.pad(elevation, 1, mode="constant", constant_values=nodata)
    padded_valid = np.pad(valid, 1, mode="constant", constant_values=False)

    best_drop = np.zeros(rows * cols, dtype=np.float64)
    downstream = np.full(rows * cols, -1, dtype=np.int64)

    row_idx, col_idx = np.indices((rows, cols))

    for dr, dc in _NEIGHBORS:
        dist = _SQRT2 if dr != 0 and dc != 0 else 1.0
        neighbor = padded[1 + dr : 1 + dr + rows, 1 + dc : 1 + dc + cols]
        neighbor_valid = padded_valid[1 + dr : 1 + dr + rows, 1 + dc : 1 + dc + cols]

        drop = np.where(valid & neighbor_valid, (elevation - neighbor) / dist, -np.inf)
        better = drop > best_drop.reshape(rows, cols)
        if not better.any():
            continue

        nbr_row = np.clip(row_idx + dr, 0, rows - 1)
        nbr_col = np.clip(col_idx + dc, 0, cols - 1)
        nbr_flat = (nbr_row * cols + nbr_col).ravel()

        flat_better = better.ravel()
        best_drop[flat_better] = drop.ravel()[flat_better]
        downstream[flat_better] = nbr_flat[flat_better]

    # Process cells from highest to lowest elevation so every upstream contribution has already
    # been added to a cell before that cell passes its total onward. Plain Python loop (this
    # dependency chain is inherently sequential — vectorizing it would need a proper graph
    # algorithm, not worth it for a one-shot script) — converted to lists first because numpy
    # scalar-at-a-time indexing has real per-access overhead that adds up over ~10^5-10^6 pixels.
    order = np.argsort(-flat_elev, kind="stable").tolist()
    valid_flat = valid.ravel().tolist()
    downstream_list = downstream.tolist()
    accum = np.where(valid.ravel(), 1.0, 0.0).tolist()

    for idx in order:
        if not valid_flat[idx]:
            continue
        target = downstream_list[idx]
        if target >= 0:
            accum[target] += accum[idx]

    return np.array(accum, dtype=np.float64).reshape(rows, cols)


def compute_twi(
    slope_deg: np.ndarray, flow_accum: np.ndarray, pixel_size_m: float, min_slope_deg: float = 0.1
) -> np.ndarray:
    """TWI = ln(specific catchment area / tan(slope)). Specific catchment area is approximated
    as (flow_accum * pixel_area) / pixel_size (contour length), the standard raster-TWI
    approximation. `min_slope_deg` floors slope to avoid a divide-by-zero blowup on perfectly
    flat pixels (a documented approximation, not a claim that flat ground has zero wetness risk).
    """
    slope_rad = np.radians(np.maximum(slope_deg, min_slope_deg))
    specific_catchment_area = (flow_accum * pixel_size_m**2) / pixel_size_m
    with np.errstate(invalid="ignore", divide="ignore"):
        return np.log(specific_catchment_area / np.tan(slope_rad))


# =============================================================================================
# Grid generation
# =============================================================================================
def make_grid(aoi: AoiConfig, cell_size_m: float = CELL_SIZE_M) -> gpd.GeoDataFrame:
    """A regular cell_size_m x cell_size_m grid covering the AOI bbox, in the AOI's UTM CRS."""
    min_x, min_y, max_x, max_y = transform_bounds("EPSG:4326", f"EPSG:{aoi.utm_epsg}", *aoi.bbox)

    n_cols = math.ceil((max_x - min_x) / cell_size_m)
    n_rows = math.ceil((max_y - min_y) / cell_size_m)

    rows = []
    for r in range(n_rows):
        for c in range(n_cols):
            x0 = min_x + c * cell_size_m
            y0 = min_y + r * cell_size_m
            rows.append(
                {
                    "cell_id": f"{aoi.id}_{r:03d}_{c:03d}",
                    "geometry": box(x0, y0, x0 + cell_size_m, y0 + cell_size_m),
                }
            )

    return gpd.GeoDataFrame(rows, crs=f"EPSG:{aoi.utm_epsg}")


def _rasterize_grid_labels(
    grid: gpd.GeoDataFrame, transform: rasterio.Affine, shape: tuple[int, int]
) -> np.ndarray:
    """Burns each grid row's positional index (0..N-1) into a raster matching `shape`/`transform`
    — -1 outside every cell. `grid`'s index must be a clean 0..N-1 RangeIndex (true for whatever
    make_grid() returns; re-derive with reset_index if the grid was filtered/reordered first)."""
    return rasterize(
        [(geom, idx) for idx, geom in enumerate(grid.geometry)],
        out_shape=shape,
        transform=transform,
        fill=-1,
        dtype="int32",
    )


# =============================================================================================
# Zonal terrain stats
# =============================================================================================
def zonal_terrain_stats(
    grid: gpd.GeoDataFrame,
    elevation: np.ndarray,
    slope_deg: np.ndarray,
    aspect_deg: np.ndarray,
    twi: np.ndarray,
    transform: rasterio.Affine,
    nodata: float = DEM_NODATA,
) -> gpd.GeoDataFrame:
    label_raster = _rasterize_grid_labels(grid, transform, elevation.shape)
    valid_dem = elevation != nodata
    labels = np.where(valid_dem, label_raster, -1)

    present = np.unique(labels)
    present = present[present >= 0]
    if len(present) == 0:
        raise ValueError("no grid cell overlaps any valid DEM pixel — check the AOI bbox/DEM")

    aspect_rad = np.radians(aspect_deg)
    # aspect_sin/cos are NaN exactly where elevation is nodata (compute_slope_aspect_deg already
    # masks those), and `labels` already excludes nodata pixels from every zone, so no NaN ever
    # enters an ndimage reduction below.
    aspect_sin = np.sin(aspect_rad)
    aspect_cos = np.cos(aspect_rad)

    stats = {
        "elevation_m": ndimage.mean(elevation, labels=labels, index=present),
        "elevation_min_m": ndimage.minimum(elevation, labels=labels, index=present),
        "elevation_max_m": ndimage.maximum(elevation, labels=labels, index=present),
        "slope_mean_deg": ndimage.mean(slope_deg, labels=labels, index=present),
        "slope_max_deg": ndimage.maximum(slope_deg, labels=labels, index=present),
        "twi_mean": ndimage.mean(twi, labels=labels, index=present),
        "pixel_count": ndimage.sum(np.ones_like(elevation), labels=labels, index=present),
    }
    aspect_sin_mean = ndimage.mean(aspect_sin, labels=labels, index=present)
    aspect_cos_mean = ndimage.mean(aspect_cos, labels=labels, index=present)
    stats["aspect_mean_deg"] = np.degrees(np.arctan2(aspect_sin_mean, aspect_cos_mean)) % 360.0
    stats["relief_m"] = stats["elevation_max_m"] - stats["elevation_min_m"]

    stats_df = pd.DataFrame(stats, index=present)
    return grid.join(stats_df)  # left join on the shared 0..N-1 index; missing cells -> NaN


# =============================================================================================
# Distance to nearest road (OpenStreetMap, via Overpass — no auth)
# =============================================================================================
# Overpass's usage policy asks for a descriptive User-Agent identifying the client; requests'
# default ("python-requests/x.x") gets a flat 406 from this server (found by actually running
# this against the real API, not assumed).
_OVERPASS_USER_AGENT = "NIRANTAR-SIH26001/0.1 (research prototype; contact 240186.cs@rmkec.ac.in)"


def fetch_osm_roads(bbox_lonlat: tuple[float, float, float, float]) -> list[LineString]:
    min_lon, min_lat, max_lon, max_lat = bbox_lonlat
    query = (
        "[out:json][timeout:90];"
        f'way["highway"]({min_lat},{min_lon},{max_lat},{max_lon});'
        "out geom;"
    )
    response = requests.post(
        "https://overpass-api.de/api/interpreter",
        data={"data": query},
        timeout=120,
        headers={"User-Agent": _OVERPASS_USER_AGENT},
    )
    response.raise_for_status()
    data = response.json()

    lines = []
    for element in data.get("elements", []):
        if element.get("type") != "way" or "geometry" not in element:
            continue
        coords = [(pt["lon"], pt["lat"]) for pt in element["geometry"]]
        if len(coords) >= 2:
            lines.append(LineString(coords))
    return lines


def distance_to_nearest_road_m(
    grid: gpd.GeoDataFrame, roads_lonlat: list[LineString], utm_epsg: int
) -> np.ndarray:
    if not roads_lonlat:
        return np.full(len(grid), np.nan)

    roads_utm = gpd.GeoSeries(roads_lonlat, crs="EPSG:4326").to_crs(epsg=utm_epsg)
    tree = STRtree(roads_utm.values)

    distances = np.empty(len(grid), dtype=np.float64)
    for i, centroid in enumerate(grid.geometry.centroid):
        nearest_idx = tree.nearest(centroid)
        distances[i] = centroid.distance(roads_utm.values[nearest_idx])
    return distances


# =============================================================================================
# Land cover (ESA WorldCover, via its public AWS Open Data bucket — no auth)
# =============================================================================================
WORLDCOVER_CACHE_DIR = REPO_ROOT / "data" / "static" / "_worldcover_tiles"

LANDCOVER_CLASSES = {
    10: "tree_cover",
    20: "shrubland",
    30: "grassland",
    40: "cropland",
    50: "built_up",
    60: "bare_sparse_vegetation",
    70: "snow_ice",
    80: "water",
    90: "herbaceous_wetland",
    95: "mangroves",
    100: "moss_lichen",
}


def worldcover_tile_name(lat: float, lon: float) -> str:
    """ESA WorldCover v200 (2021) tiles are 3x3 degrees, named by their SW corner floored to the
    nearest multiple of 3. Verified against the actual bucket listing for N21E090 (Aizawl)."""
    lat_floor = int(math.floor(lat / 3.0) * 3)
    lon_floor = int(math.floor(lon / 3.0) * 3)
    lat_code = f"N{lat_floor:02d}" if lat_floor >= 0 else f"S{-lat_floor:02d}"
    lon_code = f"E{lon_floor:03d}" if lon_floor >= 0 else f"W{-lon_floor:03d}"
    return f"ESA_WorldCover_10m_2021_v200_{lat_code}{lon_code}_Map.tif"


def download_worldcover_tile(lat: float, lon: float) -> Path:
    name = worldcover_tile_name(lat, lon)
    dest = WORLDCOVER_CACHE_DIR / name
    if dest.is_file():
        print(f"  cached: {dest.name}")
        return dest

    dest.parent.mkdir(parents=True, exist_ok=True)
    url = f"{WORLDCOVER_BUCKET}/v200/2021/map/{name}"
    print(f"  downloading: {url}")
    response = requests.get(url, timeout=300)
    response.raise_for_status()
    dest.write_bytes(response.content)
    print(f"  wrote: {dest} ({len(response.content) / 1_000_000:.1f} MB)")
    return dest


def reproject_landcover_to_grid(
    tile_path: Path, dst_transform: rasterio.Affine, dst_shape: tuple[int, int], dst_crs: str
) -> np.ndarray:
    """Warps the (categorical) land-cover tile onto the same pixel grid as the elevation raster
    — nearest-neighbour resampling, since averaging class codes would be meaningless."""
    with rasterio.open(tile_path) as src:
        dst = np.full(dst_shape, WORLDCOVER_NODATA, dtype=np.uint8)
        reproject(
            source=rasterio.band(src, 1),
            destination=dst,
            src_transform=src.transform,
            src_crs=src.crs,
            dst_transform=dst_transform,
            dst_crs=dst_crs,
            resampling=Resampling.nearest,
        )
    return dst


def zonal_landcover_majority(
    grid: gpd.GeoDataFrame, landcover: np.ndarray, transform: rasterio.Affine
) -> gpd.GeoDataFrame:
    label_raster = _rasterize_grid_labels(grid, transform, landcover.shape)
    valid = landcover != WORLDCOVER_NODATA
    labels = np.where(valid, label_raster, -1)

    present = np.unique(labels)
    present = present[present >= 0]

    classes = np.unique(landcover[valid])
    majority_code = np.full(len(present), -1, dtype=np.int64)
    best_count = np.zeros(len(present), dtype=np.float64)
    for cls in classes:
        indicator = (landcover == cls).astype(np.float64)
        counts = ndimage.sum(indicator, labels=labels, index=present)
        better = counts > best_count
        majority_code[better] = cls
        best_count[better] = counts[better]

    majority_series = pd.Series(
        [LANDCOVER_CLASSES.get(c) for c in majority_code], index=present, name="land_cover_class"
    )
    return grid.join(majority_series)


# =============================================================================================
# Orchestration
# =============================================================================================
def build_grid(aoi_id: str) -> Path:
    aoi = get_aoi(aoi_id)
    dem_path = REPO_ROOT / "data" / "static" / aoi_id / "dem.tif"
    if not dem_path.is_file():
        raise FileNotFoundError(
            f"{dem_path} not found — run `python scripts/fetch_dem.py --aoi {aoi_id}` first"
        )

    print(f"Reprojecting DEM to EPSG:{aoi.utm_epsg} ...")
    elevation, transform, crs = reproject_dem_to_utm(dem_path, f"EPSG:{aoi.utm_epsg}")
    pixel_size_m = transform.a
    print(f"  shape={elevation.shape}, pixel_size={pixel_size_m:.1f} m")

    print("Computing slope/aspect ...")
    slope_deg, aspect_deg = compute_slope_aspect_deg(elevation, pixel_size_m)

    print("Computing D8 flow accumulation (native-resolution grid; can take a while) ...")
    flow_accum = compute_flow_accumulation_d8(elevation)

    print("Computing TWI ...")
    twi = compute_twi(slope_deg, flow_accum, pixel_size_m)

    print("Building grid ...")
    grid = make_grid(aoi)
    print(f"  {len(grid)} cells")

    print("Computing zonal terrain stats ...")
    grid = zonal_terrain_stats(grid, elevation, slope_deg, aspect_deg, twi, transform)

    print("Fetching OSM roads and computing distance-to-road ...")
    roads = fetch_osm_roads(aoi.bbox)
    print(f"  {len(roads)} road segments")
    grid["dist_to_road_m"] = distance_to_nearest_road_m(grid, roads, aoi.utm_epsg)

    print("Fetching ESA WorldCover and computing land-cover majority ...")
    tile_path = download_worldcover_tile(aoi.center_lat, aoi.center_lon)
    landcover = reproject_landcover_to_grid(tile_path, transform, elevation.shape, crs)
    grid = zonal_landcover_majority(grid, landcover, transform)

    # Documented gaps (module docstring) — explicit null columns, not silently omitted from the
    # schema, so consumers can tell "not computed yet" apart from "computed as zero/empty".
    grid["plan_curvature"] = None
    grid["profile_curvature"] = None
    grid["dist_to_fault_km"] = None
    grid["lithology_class"] = None

    out_path = REPO_ROOT / "data" / "static" / aoi_id / "cells.gpkg"
    grid.to_file(out_path, driver="GPKG")
    print(f"Wrote {out_path} ({len(grid)} cells)")
    return out_path


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--aoi", required=True, help="AOI id from backend/app/config.py, e.g. aizawl")
    args = parser.parse_args()
    build_grid(args.aoi)


if __name__ == "__main__":
    main()
