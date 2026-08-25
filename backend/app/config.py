"""All tunable constants live here (CLAUDE.md §4/§6) — no magic numbers scattered elsewhere.

Phase 0's stub modules deliberately did NOT put their throwaway fake thresholds here (see
risk/stub.py, impact/stub.py, decision/stub.py docstrings) — those numbers are meant to be
deleted, not tuned. AOI definitions are the first real, load-bearing entry: multiple Phase 1
scripts (fetch_dem.py, build_grid.py, fetch_exposure.py) and the API (api/routes.py) all need the
same AOI bounding box, so it lives here once instead of drifting across files.
"""
from __future__ import annotations

from pydantic import BaseModel, Field


class AoiConfig(BaseModel):
    id: str
    name: str
    center_lat: float
    center_lon: float
    # (min_lon, min_lat, max_lon, max_lat) — the common GIS bbox convention (matches Shapely's
    # box() argument order).
    bbox: tuple[float, float, float, float]
    # UTM zone EPSG code covering this AOI — terrain math (slope/aspect/curvature/flow
    # accumulation) needs a projected, equal-distance CRS; EPSG:4326 degrees are not uniform
    # distance. Used by scripts/build_grid.py (task 1.2) and will be reused by
    # scripts/build_road_graph.py (task 2.1).
    utm_epsg: int


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
        utm_epsg=32646,  # WGS 84 / UTM zone 46N — covers 90-96E, Aizawl (92.7E) is well inside
    ),
}


def get_aoi(aoi_id: str) -> AoiConfig:
    try:
        return AOIS[aoi_id]
    except KeyError:
        raise KeyError(f"unknown AOI {aoi_id!r}; known AOIs: {sorted(AOIS)}") from None


class EscalationConfig(BaseModel):
    """Escalation stage thresholds (CLAUDE.md §4 glossary: Green Watch -> Yellow Pre-Alert ->
    Orange Evacuation Ready -> Red Evacuate Now) plus the downgrade hysteresis margin, both
    consumed by `decision/escalation.py` (BUILD_PLAN.md task 3.2).

    The three entry thresholds match decision/stub.py's Phase 0 placeholder cutoffs on purpose —
    escalation.py adds hysteresis + a real audit trail on top of behaviour the Phase 0 demo
    already validated, it does not silently re-tune the alert boundaries too.

    CLAUDE.md §4 says these weights/thresholds "must be tunable from the UI (the false-alarm-cost
    slider is a demo feature, not a hidden constant)" — that UI wiring is Phase 5 task 5.6; this
    class existing as a plain, mutable Pydantic model here is what makes that wiring possible
    later without another schema change.
    """

    yellow_threshold: float = Field(default=0.25, ge=0.0, le=1.0)
    orange_threshold: float = Field(default=0.5, ge=0.0, le=1.0)
    red_threshold: float = Field(default=0.75, ge=0.0, le=1.0)
    # How far below a stage's own entry threshold p_fail must fall before we leave that stage.
    # See decision/escalation.py's module docstring for the full hysteresis rationale.
    downgrade_hysteresis_margin: float = Field(default=0.1, ge=0.0, le=1.0)


ESCALATION = EscalationConfig()
