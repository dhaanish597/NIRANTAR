#!/usr/bin/env python
"""Fetch Copernicus DEM GLO-30 tiles covering an AOI's bounding box, mosaic + clip to that bbox,
and cache to data/static/<aoi>/dem.tif (BUILD_PLAN.md task 1.1).

Source: Copernicus DEM GLO-30, distributed publicly with **no authentication** via the AWS Open
Data Registry (https://registry.opendata.aws/copernicus-dem/), bucket `copernicus-dem-30m`.
Chosen over ALOS PALSAR specifically because it needs no Earthdata login — see
Required_by_me.md for the credentials that ARE needed for Phase 1's rainfall/soil-moisture
adapters (tasks 1.6/1.7), which this script deliberately avoids depending on.

Tile naming convention: one tile per whole degree of lat/lon, origin at the tile's SW corner:
    Copernicus_DSM_COG_10_N{lat:02d}_00_E{lon:03d}_00_DEM/Copernicus_DSM_COG_10_..._DEM.tif

Idempotent: raw tiles are cached under data/static/_dem_tiles/ and never re-downloaded once
present (verify by deleting the file if you need a fresh copy); the clipped per-AOI output is
regenerated every run from whatever tiles are cached, which is cheap.

Usage:
    python scripts/fetch_dem.py --aoi aizawl
"""
from __future__ import annotations

import argparse
import math
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "backend"))

import rasterio  # noqa: E402
import requests  # noqa: E402
from rasterio.mask import mask  # noqa: E402
from rasterio.merge import merge  # noqa: E402
from shapely.geometry import box, mapping  # noqa: E402

from app.config import get_aoi  # noqa: E402

BUCKET_URL = "https://copernicus-dem-30m.s3.amazonaws.com"
TILE_CACHE_DIR = REPO_ROOT / "data" / "static" / "_dem_tiles"
# Outside the plausible elevation range for anywhere on Earth, so unambiguous as a sentinel.
DEM_NODATA = -9999.0


def tile_key(lat_deg: int, lon_deg: int) -> str:
    lat_code = f"N{lat_deg:02d}" if lat_deg >= 0 else f"S{-lat_deg:02d}"
    lon_code = f"E{lon_deg:03d}" if lon_deg >= 0 else f"W{-lon_deg:03d}"
    name = f"Copernicus_DSM_COG_10_{lat_code}_00_{lon_code}_00_DEM"
    return f"{name}/{name}.tif"


def tiles_for_bbox(
    min_lon: float, min_lat: float, max_lon: float, max_lat: float
) -> list[tuple[int, int]]:
    """Every whole-degree (lat, lon) tile origin that intersects the bbox."""
    lat_start, lat_end = math.floor(min_lat), math.floor(max_lat)
    lon_start, lon_end = math.floor(min_lon), math.floor(max_lon)
    return [
        (lat_deg, lon_deg)
        for lat_deg in range(lat_start, lat_end + 1)
        for lon_deg in range(lon_start, lon_end + 1)
    ]


def download_tile(lat_deg: int, lon_deg: int) -> Path:
    key = tile_key(lat_deg, lon_deg)
    dest = TILE_CACHE_DIR / Path(key).name
    if dest.is_file():
        print(f"  cached: {dest.name}")
        return dest

    dest.parent.mkdir(parents=True, exist_ok=True)
    url = f"{BUCKET_URL}/{key}"
    print(f"  downloading: {url}")
    response = requests.get(url, timeout=180)
    response.raise_for_status()
    dest.write_bytes(response.content)
    print(f"  wrote: {dest} ({len(response.content) / 1_000_000:.1f} MB)")
    return dest


def fetch_dem(aoi_id: str) -> Path:
    aoi = get_aoi(aoi_id)
    min_lon, min_lat, max_lon, max_lat = aoi.bbox

    tile_coords = tiles_for_bbox(*aoi.bbox)
    print(f"AOI {aoi_id!r}: bbox {aoi.bbox}, {len(tile_coords)} DEM tile(s) needed")
    tile_paths = [download_tile(lat, lon) for lat, lon in tile_coords]

    out_dir = REPO_ROOT / "data" / "static" / aoi_id
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / "dem.tif"

    srcs = [rasterio.open(p) for p in tile_paths]
    try:
        mosaic, mosaic_transform = merge(srcs)
        mosaic_meta = srcs[0].meta.copy()
        mosaic_meta.update(
            {
                "driver": "GTiff",
                "height": mosaic.shape[1],
                "width": mosaic.shape[2],
                "transform": mosaic_transform,
            }
        )

        mosaic_path = out_dir / "_dem_mosaic_tmp.tif"
        with rasterio.open(mosaic_path, "w", **mosaic_meta) as dst:
            dst.write(mosaic)

        with rasterio.open(mosaic_path) as mosaic_src:
            # Explicit nodata sentinel: the source tiles declare no nodata value at all, so
            # rasterio.mask() silently fills any edge pixel that doesn't perfectly align with the
            # crop rectangle with 0.0 — which reads as a real (and wrong) "sea level" elevation
            # to anything downstream, rather than "no data here". Caught by checking the actual
            # output values rather than trusting a "no exception raised" result.
            clip_geom = [mapping(box(min_lon, min_lat, max_lon, max_lat))]
            clipped, clipped_transform = mask(
                mosaic_src, clip_geom, crop=True, nodata=DEM_NODATA, filled=True
            )
            clipped_meta = mosaic_src.meta.copy()
            clipped_meta.update(
                {
                    "height": clipped.shape[1],
                    "width": clipped.shape[2],
                    "transform": clipped_transform,
                    "nodata": DEM_NODATA,
                }
            )
            with rasterio.open(out_path, "w", **clipped_meta) as dst:
                dst.write(clipped)

        mosaic_path.unlink()
    finally:
        for src in srcs:
            src.close()

    print(f"Wrote {out_path} ({out_path.stat().st_size / 1_000_000:.1f} MB)")
    return out_path


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--aoi", required=True, help="AOI id from backend/app/config.py, e.g. aizawl")
    args = parser.parse_args()
    fetch_dem(args.aoi)


if __name__ == "__main__":
    main()
