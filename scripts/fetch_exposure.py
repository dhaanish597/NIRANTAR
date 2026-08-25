#!/usr/bin/env python
"""Fetch exposure data for an AOI (BUILD_PLAN.md task 1.3): villages, shelters, hospitals,
bridges, and a per-village population estimate. Writes data/static/<aoi>/exposure.gpkg with four
layers: villages, shelters, hospitals, bridges.

Sources and documented gaps (CLAUDE.md §10 — "say so and propose a cut", not silently drop):

- Villages: OSM `place=village|hamlet` nodes (Overpass). BUILD_PLAN.md's task text also names the
  Census 2011 village directory as an alternative — it's the more authoritative name/population
  source, but it's distributed as per-district Excel/PDF downloads with no stable public API to
  script against. Not fabricated, not scripted; OSM gives real geometry + names, and population
  comes from WorldPop instead (below), not from Census.
- Population: WorldPop India 2020 population-DENSITY raster (people/km2) at 1 km resolution —
  public, no auth, at data.worldpop.org. TRIED FIRST, and cut, per CLAUDE.md §10's "say so and
  propose a cut": the 100 m population-COUNT product (people per pixel) is the more precise
  source, but it ships as one ~1.8 GB whole-country file with no tiling scheme, so this script
  first tried a GDAL `/vsicurl/` windowed read over HTTP range requests — the server advertises
  `Accept-Ranges: bytes`, but a real request against it failed with
  "Range downloading not supported by this server!" (GDAL detected the range header isn't
  actually honoured correctly) and a raw `curl -H "Range: ..."` against it separately hung
  rather than returning partial content — confirmed by actually running both, not assumed. The
  1 km density product is a much smaller (~18 MB) whole-country file, so it's downloaded in full
  and cached, same pattern as fetch_dem.py's tiles / build_grid.py's WorldCover tile. Each
  village's estimate is `mean(density within VILLAGE_BUFFER_M) * buffer_area_km2` — a coarser
  approximation than a 100 m count-sum would have been (1 km pixels vs. a ~500 m-radius buffer
  mean one or two pixels almost always), on top of the same settlement-boundary caveat any
  gridded-surface approximation has. Documented, not hidden; output column is named
  `population_worldpop_est` (not `population`) so nothing downstream mistakes it for a ground
  truth or a precise figure.
- Shelters: OSM `amenity=school|community_centre`. BUILD_PLAN.md also calls for "state DM plan
  lists" (e.g. ASDMA-style state GIS, per docs/reference) — these exist only as per-state PDFs,
  no stable API, not scripted here. Same category of gap as GSI Bhukosh (Required_by_me.md).
- Hospitals: OSM `amenity=hospital`, kept as its own layer rather than folded into `shelters` —
  task 2.4 (RII) tests connectivity to "district HQ / nearest hospital / nearest shelter" as three
  distinct destination types, so keeping hospitals separate now avoids a re-split later.
- Bridges: OSM `man_made=bridge`, per BUILD_PLAN.md's literal wording. Note this tag is
  comparatively rare in OSM; `bridge=yes` on highway ways (much more common) is a documented
  fallback NOT implemented in this pass — flagging so it isn't mistaken for "no bridges near
  Aizawl" if the layer comes back sparse.

Every OSM-sourced row carries `osm_id` (the source element's OSM id) so scripts/load_db.py can
use (aoi_id, osm_id) as a stable identity for idempotent reloads.

Usage:
    python scripts/fetch_exposure.py --aoi aizawl
"""
from __future__ import annotations

import argparse
import math
import sys
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "backend"))

import geopandas as gpd  # noqa: E402
import numpy as np  # noqa: E402
import rasterio  # noqa: E402
import requests  # noqa: E402
from rasterio.features import geometry_mask  # noqa: E402
from rasterio.windows import from_bounds  # noqa: E402
from shapely.geometry import Point  # noqa: E402

from app.config import AoiConfig, get_aoi  # noqa: E402

# Same Overpass identification requirement discovered in scripts/build_grid.py (task 1.2) —
# the default requests User-Agent gets a flat 406 from this server.
_OVERPASS_USER_AGENT = "NIRANTAR-SIH26001/0.1 (research prototype; contact 240186.cs@rmkec.ac.in)"
_OVERPASS_URL = "https://overpass-api.de/api/interpreter"
# Courtesy delay between successive Overpass calls in one run (this script makes 4). Found by
# actually running this script, not assumed: the public instance rate-limited us with HTTP 429
# after just 2 calls at a 2s gap, so this is deliberately generous rather than a guess.
_OVERPASS_CALL_DELAY_S = 15.0
_OVERPASS_MAX_RETRIES = 5

WORLDPOP_URL = "https://data.worldpop.org/GIS/Population_Density/Global_2000_2020_1km/2020/IND/ind_pd_2020_1km.tif"
WORLDPOP_CACHE_DIR = REPO_ROOT / "data" / "static" / "_worldpop_tiles"
# Engineering choice, not a cited figure (same honesty standard as config.py's AOI bbox note):
# an approximate per-settlement catchment radius for summing gridded population around a village
# point. 500 m matches the analysis cell size (build_grid.py) as a reasonable "close enough to
# call it this village" default — TODO(verify): revisit if it over/under-counts once compared
# against any real population figure we obtain (e.g. from a Census source, if one materializes).
VILLAGE_BUFFER_M = 500.0


# =============================================================================================
# OSM / Overpass
# =============================================================================================
def _overpass_query(query: str) -> dict:
    """POSTs to Overpass, retrying on HTTP 429 (rate limit) with backoff. The public instance
    rate-limits per-IP regardless of the inter-call delay we impose ourselves, so a single delay
    isn't sufficient on its own — confirmed by actually hitting a 429 while writing this script."""
    # 429 = rate limited; 502/503/504 = the shared public instance is overloaded/restarting a
    # query slot — both observed while writing this script, both transient, both worth a backoff
    # retry rather than failing the whole run.
    retryable = {429, 502, 503, 504}
    for attempt in range(_OVERPASS_MAX_RETRIES):
        response = requests.post(
            _OVERPASS_URL,
            data={"data": query},
            timeout=120,
            headers={"User-Agent": _OVERPASS_USER_AGENT},
        )
        if response.status_code in retryable:
            retry_after = float(response.headers.get("Retry-After", 0) or 0)
            wait_s = max(retry_after, _OVERPASS_CALL_DELAY_S * (attempt + 1))
            print(
                f"  Overpass HTTP {response.status_code}, waiting {wait_s:.0f}s before retry "
                f"{attempt + 1}/{_OVERPASS_MAX_RETRIES} ..."
            )
            time.sleep(wait_s)
            continue
        response.raise_for_status()
        return response.json()
    raise RuntimeError(f"Overpass still failing after {_OVERPASS_MAX_RETRIES} retries")


def _safe_int(value) -> int | None:
    if value is None:
        return None
    try:
        return int(str(value).replace(",", "").strip())
    except (ValueError, TypeError):
        return None


def _element_point(element: dict) -> Point | None:
    """A node's own coordinates, or a way/relation's `out center` centroid."""
    if element.get("type") == "node" and "lon" in element and "lat" in element:
        return Point(element["lon"], element["lat"])
    center = element.get("center")
    if center:
        return Point(center["lon"], center["lat"])
    return None


def _empty_gdf(columns: list[str]) -> gpd.GeoDataFrame:
    """An explicitly-empty GeoDataFrame with the expected schema — so a layer that legitimately
    found zero features still writes with the right columns, rather than being silently absent
    or crashing gpkg write (CLAUDE.md §10 — explicit gaps, not silent ones)."""
    return gpd.GeoDataFrame({c: [] for c in columns if c != "geometry"}, geometry=[], crs="EPSG:4326")


def fetch_villages(bbox_lonlat: tuple[float, float, float, float]) -> gpd.GeoDataFrame:
    min_lon, min_lat, max_lon, max_lat = bbox_lonlat
    query = (
        "[out:json][timeout:90];"
        f'node["place"~"^(village|hamlet)$"]({min_lat},{min_lon},{max_lat},{max_lon});'
        "out body;"
    )
    data = _overpass_query(query)
    rows = []
    for el in data.get("elements", []):
        pt = _element_point(el)
        if pt is None:
            continue
        tags = el.get("tags", {})
        rows.append(
            {
                "osm_id": el["id"],
                "name": tags.get("name", "unnamed"),
                "place_type": tags.get("place"),
                "osm_population": _safe_int(tags.get("population")),
                "geometry": pt,
            }
        )
    if not rows:
        return _empty_gdf(["osm_id", "name", "place_type", "osm_population", "geometry"])
    return gpd.GeoDataFrame(rows, crs="EPSG:4326")


def fetch_amenity(bbox_lonlat: tuple[float, float, float, float], amenity_regex: str) -> gpd.GeoDataFrame:
    min_lon, min_lat, max_lon, max_lat = bbox_lonlat
    query = (
        "[out:json][timeout:90];"
        f'(node["amenity"~"{amenity_regex}"]({min_lat},{min_lon},{max_lat},{max_lon});'
        f'way["amenity"~"{amenity_regex}"]({min_lat},{min_lon},{max_lat},{max_lon});'
        ");"
        "out center;"
    )
    data = _overpass_query(query)
    rows = []
    for el in data.get("elements", []):
        pt = _element_point(el)
        if pt is None:
            continue
        tags = el.get("tags", {})
        rows.append(
            {
                "osm_id": el["id"],
                "name": tags.get("name", "unnamed"),
                "amenity": tags.get("amenity"),
                "geometry": pt,
            }
        )
    if not rows:
        return _empty_gdf(["osm_id", "name", "amenity", "geometry"])
    return gpd.GeoDataFrame(rows, crs="EPSG:4326")


def fetch_bridges(bbox_lonlat: tuple[float, float, float, float]) -> gpd.GeoDataFrame:
    min_lon, min_lat, max_lon, max_lat = bbox_lonlat
    query = (
        "[out:json][timeout:90];"
        f'(node["man_made"="bridge"]({min_lat},{min_lon},{max_lat},{max_lon});'
        f'way["man_made"="bridge"]({min_lat},{min_lon},{max_lat},{max_lon});'
        ");"
        "out center;"
    )
    data = _overpass_query(query)
    rows = []
    for el in data.get("elements", []):
        pt = _element_point(el)
        if pt is None:
            continue
        tags = el.get("tags", {})
        rows.append({"osm_id": el["id"], "name": tags.get("name", "unnamed"), "geometry": pt})
    if not rows:
        return _empty_gdf(["osm_id", "name", "geometry"])
    return gpd.GeoDataFrame(rows, crs="EPSG:4326")


# =============================================================================================
# Population (WorldPop 1km density, downloaded whole and cached — see module docstring for why
# this isn't a windowed /vsicurl/ read against the larger 100m product)
# =============================================================================================
def download_worldpop_density(worldpop_url: str = WORLDPOP_URL) -> Path:
    dest = WORLDPOP_CACHE_DIR / Path(worldpop_url).name
    if dest.is_file():
        print(f"  cached: {dest.name}")
        return dest

    dest.parent.mkdir(parents=True, exist_ok=True)
    print(f"  downloading: {worldpop_url}")
    response = requests.get(worldpop_url, timeout=300)
    response.raise_for_status()
    dest.write_bytes(response.content)
    print(f"  wrote: {dest} ({len(response.content) / 1_000_000:.1f} MB)")
    return dest


def sample_population_worldpop(
    villages: gpd.GeoDataFrame,
    aoi: AoiConfig,
    buffer_m: float = VILLAGE_BUFFER_M,
    worldpop_url: str = WORLDPOP_URL,
) -> np.ndarray:
    """Estimates population near each village as mean(density within `buffer_m`) * buffer_area_km2,
    reading a bbox-windowed clip of the (locally cached, whole-file) 1 km density raster."""
    if villages.empty:
        return np.array([], dtype=np.float64)

    tile_path = download_worldpop_density(worldpop_url)

    villages_utm = villages.to_crs(epsg=aoi.utm_epsg)
    buffers_wgs84 = gpd.GeoSeries(villages_utm.geometry.buffer(buffer_m), crs=aoi.utm_epsg).to_crs(epsg=4326)
    buffer_area_km2 = math.pi * (buffer_m / 1000.0) ** 2

    # Generous padding (buffer converted from metres to degrees at ~111 km/degree, doubled) so the
    # window comfortably contains every buffer even near the AOI bbox edge.
    pad_deg = (buffer_m / 111_000.0) * 2.0
    min_lon, min_lat, max_lon, max_lat = aoi.bbox
    read_bounds = (min_lon - pad_deg, min_lat - pad_deg, max_lon + pad_deg, max_lat + pad_deg)

    with rasterio.open(tile_path) as src:
        window = from_bounds(*read_bounds, transform=src.transform).round_offsets().round_lengths()
        density = src.read(1, window=window)
        density_transform = src.window_transform(window)
        nodata = src.nodata

    valid_density = np.where(density == nodata, np.nan, density) if nodata is not None else density.astype(np.float64)

    estimates = np.zeros(len(villages), dtype=np.float64)
    for i, geom in enumerate(buffers_wgs84):
        mask = geometry_mask([geom], out_shape=valid_density.shape, transform=density_transform, invert=True)
        cell_values = valid_density[mask]
        cell_values = cell_values[~np.isnan(cell_values)]
        mean_density = float(cell_values.mean()) if len(cell_values) else 0.0
        estimates[i] = mean_density * buffer_area_km2
    return estimates


# =============================================================================================
# Orchestration
# =============================================================================================
def fetch_exposure(aoi_id: str) -> Path:
    aoi = get_aoi(aoi_id)

    print("Fetching villages (OSM place=village|hamlet) ...")
    villages = fetch_villages(aoi.bbox)
    print(f"  {len(villages)} villages")
    time.sleep(_OVERPASS_CALL_DELAY_S)

    print("Fetching shelters (OSM amenity=school|community_centre) ...")
    shelters = fetch_amenity(aoi.bbox, "^(school|community_centre)$")
    print(f"  {len(shelters)} shelters")
    time.sleep(_OVERPASS_CALL_DELAY_S)

    print("Fetching hospitals (OSM amenity=hospital) ...")
    hospitals = fetch_amenity(aoi.bbox, "^hospital$")
    print(f"  {len(hospitals)} hospitals")
    time.sleep(_OVERPASS_CALL_DELAY_S)

    print("Fetching bridges (OSM man_made=bridge) ...")
    bridges = fetch_bridges(aoi.bbox)
    print(f"  {len(bridges)} bridges")

    print(f"Sampling WorldPop population within {VILLAGE_BUFFER_M:.0f} m of each village ...")
    villages["population_worldpop_est"] = sample_population_worldpop(villages, aoi)

    out_dir = REPO_ROOT / "data" / "static" / aoi_id
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / "exposure.gpkg"

    villages.to_file(out_path, layer="villages", driver="GPKG")
    shelters.to_file(out_path, layer="shelters", driver="GPKG")
    hospitals.to_file(out_path, layer="hospitals", driver="GPKG")
    bridges.to_file(out_path, layer="bridges", driver="GPKG")

    print(
        f"Wrote {out_path} "
        f"(villages={len(villages)}, shelters={len(shelters)}, hospitals={len(hospitals)}, "
        f"bridges={len(bridges)})"
    )
    return out_path


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--aoi", required=True, help="AOI id from backend/app/config.py, e.g. aizawl")
    args = parser.parse_args()
    fetch_exposure(args.aoi)


if __name__ == "__main__":
    main()
