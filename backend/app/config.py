"""All tunable constants live here (CLAUDE.md §4/§6) — no magic numbers scattered elsewhere.

Phase 0's stub modules deliberately did NOT put their throwaway fake thresholds here (see
risk/stub.py, impact/stub.py, decision/stub.py docstrings) — those numbers are meant to be
deleted, not tuned. AOI definitions are the first real, load-bearing entry: multiple Phase 1
scripts (fetch_dem.py, build_grid.py, fetch_exposure.py) and the API (api/routes.py) all need the
same AOI bounding box, so it lives here once instead of drifting across files.
"""
from __future__ import annotations

from pydantic import BaseModel


class AoiConfig(BaseModel):
    id: str
    name: str
    center_lat: float
    center_lon: float
    # (min_lon, min_lat, max_lon, max_lat) — the common GIS bbox convention (matches Shapely's
    # box() argument order).
    bbox: tuple[float, float, float, float]


# Aizawl's bbox is a Phase 1 engineering choice, not a cited research figure: centered on the
# city (23.7307N, 92.7173E — a public, unremarkable city-center coordinate) with a ~0.125deg
# (~13-14 km) margin so it comfortably covers the city and the general NH-6 corridor toward
# Hunthar. This is NOT a claim about the precise AOI boundary the final analysis grid will use —
# BUILD_PLAN.md task 1.2 (build_grid.py) may need to widen it once real village/road data shows
# what actually needs to be covered. TODO(verify): tighten toward Hunthar's precise coordinates
# once a source for them exists in docs/reference/ — CLAUDE.md rule: don't invent that figure.
AOIS: dict[str, AoiConfig] = {
    "aizawl": AoiConfig(
        id="aizawl",
        name="Aizawl, Mizoram",
        center_lat=23.7307,
        center_lon=92.7173,
        bbox=(92.60, 23.60, 92.85, 23.85),
    ),
}


def get_aoi(aoi_id: str) -> AoiConfig:
    try:
        return AOIS[aoi_id]
    except KeyError:
        raise KeyError(f"unknown AOI {aoi_id!r}; known AOIs: {sorted(AOIS)}") from None
