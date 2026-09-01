#!/usr/bin/env python
"""Generate an offline DEM-derived hillshade PNG for a configured AOI."""
from __future__ import annotations

import argparse
import math
import sys
from pathlib import Path

import numpy as np
import rasterio

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "backend"))

from app.config import get_aoi  # noqa: E402


def build_hillshade(aoi_id: str, *, azimuth_deg: float = 315.0, altitude_deg: float = 45.0) -> Path:
    aoi = get_aoi(aoi_id)
    dem_path = REPO_ROOT / "data" / "static" / aoi_id / "dem.tif"
    if not dem_path.is_file():
        raise FileNotFoundError(f"{dem_path} not found; run scripts/fetch_dem.py first")

    with rasterio.open(dem_path) as src:
        elevation = src.read(1, masked=True).astype(np.float64)
        transform = src.transform
        latitude = (aoi.bbox[1] + aoi.bbox[3]) / 2.0
        if src.crs and src.crs.is_geographic:
            x_resolution_m = abs(transform.a) * 111_320.0 * math.cos(math.radians(latitude))
            y_resolution_m = abs(transform.e) * 110_540.0
        else:
            x_resolution_m = abs(transform.a)
            y_resolution_m = abs(transform.e)

    filled = elevation.filled(float(elevation.mean()))
    dz_dy, dz_dx = np.gradient(filled, y_resolution_m, x_resolution_m)
    slope = np.pi / 2.0 - np.arctan(np.hypot(dz_dx, dz_dy))
    aspect = np.arctan2(-dz_dx, dz_dy)
    azimuth = math.radians(azimuth_deg)
    altitude = math.radians(altitude_deg)
    shaded = (
        np.sin(altitude) * np.sin(slope)
        + np.cos(altitude) * np.cos(slope) * np.cos(azimuth - aspect)
    )
    intensity = np.clip((shaded + 1.0) * 127.5, 0, 255).astype(np.uint8)
    alpha = np.where(np.ma.getmaskarray(elevation), 0, 255).astype(np.uint8)

    out_dir = REPO_ROOT / "data" / "tiles"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"{aoi_id}-hillshade.png"
    profile = {
        "driver": "PNG",
        "width": intensity.shape[1],
        "height": intensity.shape[0],
        "count": 4,
        "dtype": "uint8",
    }
    with rasterio.open(out_path, "w", **profile) as dst:
        dst.write(intensity, 1)
        dst.write(intensity, 2)
        dst.write(intensity, 3)
        dst.write(alpha, 4)

    print(f"Wrote {out_path} ({out_path.stat().st_size / 1_000_000:.1f} MB)")
    return out_path


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--aoi", default="aizawl")
    args = parser.parse_args()
    build_hillshade(args.aoi)


if __name__ == "__main__":
    main()
