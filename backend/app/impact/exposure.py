"""Loads real village/shelter points from `data/static/<aoi>/exposure.gpkg` for the map's
exposure layer (see schemas/exposure.py's module docstring for why this is a separate static
endpoint rather than per-tick fields). Read-only; never mutates or is mutated by the risk/impact
pipeline.
"""
from __future__ import annotations

from pathlib import Path

from app.schemas.exposure import AoiExposure, ShelterExposure, VillageExposure

REPO_ROOT = Path(__file__).resolve().parents[3]

# Static geometry never changes within a process lifetime — cache like impact/priority.py's
# _STATIC_RESOLUTION_CACHE, keyed the same way (repo root, aoi_id) for the same reason (tests
# that point repo_root at a fixture tree must not collide with a real-data cache entry).
_EXPOSURE_CACHE: dict[tuple[str, str], AoiExposure] = {}


def load_aoi_exposure(aoi_id: str, repo_root: Path | None = None) -> AoiExposure:
    root = repo_root or REPO_ROOT
    cache_key = (str(root.resolve()), aoi_id)
    cached = _EXPOSURE_CACHE.get(cache_key)
    if cached is not None:
        return cached

    exposure_path = root / "data" / "static" / aoi_id / "exposure.gpkg"
    if not exposure_path.is_file():
        raise FileNotFoundError(
            f"{exposure_path} not found — run `python scripts/fetch_exposure.py --aoi {aoi_id}` first"
        )

    import geopandas as gpd

    villages_gdf = gpd.read_file(exposure_path, layer="villages")
    if villages_gdf.crs is not None and str(villages_gdf.crs) != "EPSG:4326":
        villages_gdf = villages_gdf.to_crs(epsg=4326)
    villages = [
        VillageExposure(
            village_id=f"v_{row.osm_id}",
            name=row.get("name") or "unnamed",
            lat=row.geometry.y,
            lon=row.geometry.x,
            population_worldpop_est=row.get("population_worldpop_est"),
            osm_population=row.get("osm_population"),
        )
        for _, row in villages_gdf.iterrows()
    ]

    shelters_gdf = gpd.read_file(exposure_path, layer="shelters")
    if shelters_gdf.crs is not None and str(shelters_gdf.crs) != "EPSG:4326":
        shelters_gdf = shelters_gdf.to_crs(epsg=4326)
    shelters = [
        ShelterExposure(
            shelter_id=f"s_{row.osm_id}",
            name=row.get("name") or "unnamed",
            amenity=row.get("amenity"),
            lat=row.geometry.y,
            lon=row.geometry.x,
        )
        for _, row in shelters_gdf.iterrows()
    ]

    result = AoiExposure(aoi_id=aoi_id, villages=villages, shelters=shelters)
    _EXPOSURE_CACHE[cache_key] = result
    return result
