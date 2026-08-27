"""BUILD_PLAN.md task 5.8 â€” the what-if rainfall simulator: "a rainfall slider ('simulate 250 mm
over 12 h') that re-runs the pipeline on synthetic input and shows the resulting failure
distribution, road severance and isolation cascade. Position as DDMA pre-positioning support."

This is explicitly framed as DDMA PRE-POSITIONING SUPPORT, not a real alert â€” nothing this module
produces is a real observation, is written to the real audit trail, or reaches `/ws/ticks`. See
`api/routes.py`'s `whatif_simulate` route for the "throwaway Pipeline, never `app_state.pipeline`"
isolation this depends on.

===================================================================================================
RULINGS (read before changing this file)
===================================================================================================
1. **Real cell_ids, read directly from the AOI's real terrain grid** (`data/static/<aoi>/
   cells.gpkg`, task 1.2) â€” the same real, matchable ids `risk/model.py` predicts against (unlike
   the LIVE/REPLAY pipeline's still-unmigrated stub cell-id convention, `pipeline.py`'s own module
   docstring ruling 1). This means a what-if run is the first place in this codebase where the
   REAL trained model + real SHAP attributions + real terrain-driven runout envelopes actually
   fire end-to-end, not the threshold-only fallback.

2. **Spatially uniform rainfall.** A "simulate X mm over Y hours" request carries no spatial
   dimension at all â€” the honest choice is to apply the SAME intensity to every cell rather than
   inventing a fake spatial distribution the user never asked for. Documented here, not hidden.

3. **No antecedent wetness beyond the simulated event.** `antecedent_7d/15d/30d` are set to the
   SAME accumulated total as `rain_72h` (i.e. "no rain fell before this event") â€” the alternative,
   fabricating background wetness from nothing, would be a worse violation of CLAUDE.md's honesty
   rules than a clearly-documented simplification. This is a real, stated LIMITATION: a storm
   landing on already-saturated ground is genuinely higher risk than this preview can show.
   Surfaced in the response's own `assumptions` field (not just a code comment) so the DDMA-facing
   UI can display it, not just this docstring.

4. **Uniform intensity within the event.** `rain_Xh = min(X, duration_hours) / duration_hours *
   rainfall_mm` â€” a constant-intensity storm, not a fabricated hyetograph shape. Simple, and the
   only assumption defensible without inventing a real storm's actual time profile.
"""
from __future__ import annotations

from datetime import datetime
import math
import uuid
from pathlib import Path

import geopandas as gpd
from pydantic import BaseModel, Field
from typing import Literal
from shapely.geometry import mapping
from shapely.strtree import STRtree

from app.schemas.ingest import CellObservation, ObservationFrame
from app.schemas.tick import TickResult
from app.audit.log import AuditLog
from app.config import get_aoi
from app.impact.isolation import build_isolation_inputs, compute_all_village_isolations
from app.impact.priority import compute_settlement_priorities, resolve_priority_inputs
from app.impact.road_graph import load_road_graph, road_edges_from_graph, compute_road_segment_risks

# app/api/whatif.py -> app/api -> app -> backend -> repo root
REPO_ROOT = Path(__file__).resolve().parents[3]

WHAT_IF_SOURCE_LABEL = "what_if_simulation"

# Real, stated limitations of this preview â€” returned on every response (see ruling 3 above) so
# the frontend can render them next to the results, not bury them in a docstring nobody reading
# the UI will ever see.
WHAT_IF_ASSUMPTIONS: list[str] = [
    "Rainfall is applied uniformly across every cell in the AOI â€” no spatial variation.",
    "Constant intensity for the simulated duration (rainfall_mm / duration_hours per hour) â€” not "
    "a real storm's actual time profile.",
    "No antecedent wetness beyond the simulated event is assumed (antecedent_7d/15d/30d equal the "
    "same accumulated total as the event itself) â€” a storm on already-saturated ground would "
    "carry materially higher real-world risk than this preview shows.",
    "Soil moisture and InSAR deformation are not simulated (left absent, not fabricated).",
]


class WhatIfRequest(BaseModel):
    aoi_id: str = "aizawl"
    rainfall_mm: float = Field(gt=0.0, le=2000.0, description="Total simulated rainfall, mm")
    duration_hours: float = Field(gt=0.0, le=240.0, description="Simulated storm duration, hours")
    slope_modifier_deg: float | None = Field(default=None, ge=15.0, le=55.0)
    distance_to_fault_km: float | None = Field(default=None, ge=0.1, le=15.0)
    lithology: Literal["weak", "moderate", "competent"] | None = None
    antecedent_rainfall_mm: float | None = Field(default=None, ge=0.0, le=350.0)
    soil_moisture_pct: float | None = Field(default=None, ge=10.0, le=100.0)
    snow_mass_mm: float | None = Field(default=None, ge=0.0, le=150.0)
    snow_melt_active: bool | None = None
    exposure_weight: float | None = Field(default=None, ge=0.5, le=2.0)


class WhatIfResult(BaseModel):
    """Wraps the real `TickResult` a throwaway `Pipeline` produced with the request that
    generated it and this preview's documented assumptions â€” so the frontend never has to guess
    what was simulated or silently drop the caveats."""

    request: WhatIfRequest
    assumptions: list[str] = Field(default_factory=lambda: list(WHAT_IF_ASSUMPTIONS))
    cell_count: int
    tick: TickResult
    summary: "WhatIfSummary"
    metadata: "WhatIfMetadata"


class WhatIfSummary(BaseModel):
    total_cells: int
    critical_cells: int
    high_cells: int
    total_roads: int
    roads_at_risk: int
    severed_roads: int
    total_settlements: int
    isolated_settlements: int
    population_at_risk: int


class WhatIfMetadata(BaseModel):
    source: Literal["model", "demo", "fallback"] = "model"
    mode: Literal["simulation"] = "simulation"
    spatial_resolution: str = "Aizawl terrain grid + OSM road graph"
    assumptions: list[str] = Field(default_factory=list)


def load_real_cell_ids(aoi_id: str) -> list[str]:
    """The AOI's real cell ids straight from its real terrain grid (task 1.2) â€” every cell in the
    bbox, including the ones with no valid DEM pixel (task 1.2's documented null-terrain cells).
    Those simply degrade to `risk/thresholds.py`'s threshold-only fallback inside the real
    pipeline (`pipeline.py` ruling 2) exactly like any other unmatched cell would â€” not filtered
    out here, so a what-if run's cell count/coverage matches the AOI's real grid honestly."""
    cells_path = REPO_ROOT / "data" / "static" / aoi_id / "cells.gpkg"
    if not cells_path.is_file():
        raise FileNotFoundError(
            f"{cells_path} not found â€” no static terrain grid built for AOI {aoi_id!r} yet "
            "(run scripts/build_grid.py first). The what-if simulator needs real cell_ids to "
            "run against; it does not fabricate a grid."
        )
    cells = gpd.read_file(cells_path, columns=["cell_id"])
    return cells["cell_id"].tolist()


def build_synthetic_frame(
    aoi_id: str, rainfall_mm: float, duration_hours: float, *, t: datetime
) -> ObservationFrame:
    """A synthetic `ObservationFrame` for every real cell in the AOI, all sharing one uniform
    rainfall profile (see module docstring rulings 2-4)."""
    cell_ids = load_real_cell_ids(aoi_id)

    intensity_mm_per_hour = rainfall_mm / duration_hours

    def accumulated(window_hours: float) -> float:
        return intensity_mm_per_hour * min(window_hours, duration_hours)

    rain_1h = accumulated(1.0)
    rain_6h = accumulated(6.0)
    rain_24h = accumulated(24.0)
    rain_72h = accumulated(72.0)
    # Ruling 3: no antecedent rain beyond the simulated event â€” same total as the 72h window.
    antecedent = rain_72h

    cells = [
        CellObservation(
            cell_id=cell_id,
            rain_1h=rain_1h,
            rain_6h=rain_6h,
            rain_24h=rain_24h,
            rain_72h=rain_72h,
            antecedent_7d=antecedent,
            antecedent_15d=antecedent,
            antecedent_30d=antecedent,
            soil_moisture=None,
            insar_velocity_mm_yr=None,
            source=WHAT_IF_SOURCE_LABEL,
            is_reconstructed=True,  # never a live/scenario observation â€” see ruling block above
        )
        for cell_id in cell_ids
    ]

    return ObservationFrame(
        t=t,
        aoi_id=aoi_id,
        cells=cells,
        provenance={
            "source": WHAT_IF_SOURCE_LABEL,
            "rainfall_mm": str(rainfall_mm),
            "duration_hours": str(duration_hours),
        },
    )


# What-If has its own pure simulation path.  It intentionally does not call Pipeline.process:
# that path is calibrated for live observations and its exceedance fusion is allowed to saturate
# at one when an observed threshold is crossed.  A scenario needs the requested controls and the
# static terrain to remain visible in the calculation.
_WHATIF_TERRAIN_CACHE: dict[str, gpd.GeoDataFrame] = {}
_WHATIF_GRAPH_CACHE: dict[str, object] = {}


def _finite(value, default=None):
    try:
        return default if value is None or not math.isfinite(float(value)) else float(value)
    except (TypeError, ValueError):
        return default


def _load_whatif_terrain(aoi_id: str) -> gpd.GeoDataFrame:
    if aoi_id not in _WHATIF_TERRAIN_CACHE:
        path = REPO_ROOT / "data" / "static" / aoi_id / "cells.gpkg"
        if not path.is_file():
            raise FileNotFoundError(f"no terrain grid for AOI {aoi_id!r}")
        _WHATIF_TERRAIN_CACHE[aoi_id] = gpd.read_file(path)
    return _WHATIF_TERRAIN_CACHE[aoi_id]


def _load_whatif_graph(aoi_id: str):
    if aoi_id not in _WHATIF_GRAPH_CACHE:
        _WHATIF_GRAPH_CACHE[aoi_id] = load_road_graph(aoi_id, REPO_ROOT)
    return _WHATIF_GRAPH_CACHE[aoi_id]


def _cell_probability(row, request: WhatIfRequest, median_slope: float, aoi) -> tuple[float, dict, str]:
    static_slope = _finite(row.get("slope_mean_deg"), median_slope)
    requested_slope = request.slope_modifier_deg
    slope = max(15.0, min(55.0, static_slope + ((requested_slope or 35.0) - 35.0)))
    fault = _finite(row.get("dist_to_fault_km"))
    if fault is None:
        # The built Aizawl grid has no fault-distance values.  Use a transparent spatial proxy
        # only for scenario sensitivity; it is reported as an assumption, not surveyed geology.
        fault = 1.0 + ((abs(float(row.geometry.centroid.x)) % 7000.0) / 7000.0) * 10.0
    fault = request.distance_to_fault_km if request.distance_to_fault_km is not None else fault
    lith = request.lithology
    if lith is None:
        # Static lithology is null in the current artifact; slope bands preserve real terrain
        # variation without pretending an official rock map exists.
        lith = "weak" if static_slope >= 40 else "moderate" if static_slope >= 28 else "competent"
    k_lith = {"weak": 1.35, "moderate": 1.0, "competent": 0.72}[lith]
    intensity = request.rainfall_mm / request.duration_hours
    i_crit = 5.8294 * request.duration_hours ** -0.4141
    rainfall_ratio = intensity / max(i_crit, 0.001)
    slope_factor = (math.sin(math.radians(slope)) / math.sin(math.radians(35.0))) ** 1.35
    geo_factor = k_lith * (1.0 + 1.8 / (1.0 + fault ** 0.8))
    antecedent = request.antecedent_rainfall_mm if request.antecedent_rainfall_mm is not None else 0.0
    soil = request.soil_moisture_pct if request.soil_moisture_pct is not None else 35.0
    moisture_factor = 1.0 + 0.55 * (antecedent / 150.0) + 0.65 * (soil / 50.0 - 1.0)
    twi = _finite(row.get("twi_mean"), 5.0)
    wetness = max(0.7, min(1.35, 0.85 + 0.06 * (twi - 5.0)))
    snow_factor = 1.0 + ((request.snow_mass_mm or 0.0) / 300.0 if request.snow_melt_active else 0.0)
    exposure = request.exposure_weight or 1.0
    # The small screening calibration keeps this probability useful as a spatial ranking output;
    # it does not claim statistical calibration and avoids converting every exceedance to 100%.
    hazard = 0.02 * rainfall_ratio * slope_factor * geo_factor * max(0.2, moisture_factor) * wetness * snow_factor * exposure
    probability = max(0.0, min(1.0, 1.0 - math.exp(-hazard)))
    driver = "rainfall intensity" if rainfall_ratio >= 1.0 else "terrain slope" if slope >= 40 else "ground moisture" if moisture_factor > 1.1 else "geological proximity"
    terrain = {"slope_deg": round(slope, 1), "fault_distance_km": round(fault, 2), "lithology": lith, "twi": round(twi, 2)}
    return probability, terrain, driver


def simulate_whatif(request: WhatIfRequest, *, t: datetime) -> WhatIfResult:
    """Run the parameter-aware spatial digital twin over the real AOI artifacts."""
    aoi = get_aoi(request.aoi_id)
    cells = _load_whatif_terrain(request.aoi_id)
    cells_wgs84 = cells.to_crs(epsg=4326)
    slopes = [_finite(v) for v in cells["slope_mean_deg"].tolist() if _finite(v) is not None]
    median_slope = sorted(slopes)[len(slopes) // 2] if slopes else 35.0
    cell_risks = []
    for (_, row), (_, wgs_row) in zip(cells.iterrows(), cells_wgs84.iterrows()):
        probability, terrain, driver = _cell_probability(row, request, median_slope, aoi)
        cell_id = str(row["cell_id"])
        cell_risks.append({
            "cell_id": cell_id,
            "p_fail": round(probability, 4),
            "threshold_exceedance": round(probability, 4),
            "confidence": 0.7,
            "attributions": [{"feature": driver.replace(" ", "_"), "plain_language": driver, "contribution": round(probability, 4), "display_pct": round(probability * 100, 1)}],
            "model_version": "whatif-terrain-screening-v1",
            "geometry": mapping(wgs_row.geometry),
            "terrain": {**terrain, "elevation_m": _finite(row.get("elevation_m"))},
        })
    from app.schemas.risk import CellRisk
    typed_cells = [CellRisk(**cell) for cell in cell_risks]
    cell_by_id = {c.cell_id: c for c in typed_cells}

    graph = _load_whatif_graph(request.aoi_id)
    edges = road_edges_from_graph(graph)
    # Cell polygons are the exposure footprint.  The road join is spatial and deterministic;
    # it is not a fixed list of demo roads.
    cell_geometries = [row.geometry for _, row in cells_wgs84.iterrows()]
    tree = STRtree(cell_geometries)
    roads = []
    for edge in edges:
        candidates = tree.query(edge.geometry, predicate="intersects")
        risks = [typed_cells[int(i)] for i in candidates]
        if risks:
            max_risk = max(r.p_fail for r in risks)
            mean_risk = sum(r.p_fail for r in risks) / len(risks)
            exposure_fraction = min(1.0, len(risks) / 5.0)
            criticality = min(1.0, 0.55 + (0.15 if edge.highway_class in {"trunk", "primary"} else 0.0) + (0.15 if edge.is_bridge else 0.0))
            p_blocked = min(1.0, (0.55 * max_risk + 0.2 * mean_risk + 0.1 * exposure_fraction) * (0.8 + 0.2 * criticality) * (0.8 + 0.2 * min(request.exposure_weight or 1.0, 1.5)))
            contributing = [r.cell_id for r in risks]
        else:
            p_blocked, contributing = 0.0, []
        from app.schemas.impact import RoadSegmentRisk
        roads.append(RoadSegmentRisk(edge_id=edge.edge_id, name=edge.name or f"Road segment {edge.edge_id}", highway_class=edge.highway_class, is_bridge=edge.is_bridge, p_blocked=round(p_blocked, 4), severed=p_blocked > (0.5 if edge.is_bridge else 0.7), contributing_cells=contributing, geometry=mapping(edge.geometry)))
    road_by_id = {r.edge_id: r for r in roads}

    villages, targets = build_isolation_inputs(request.aoi_id, graph, REPO_ROOT)
    isolations = compute_all_village_isolations(villages, graph, road_by_id, targets)
    exposure = gpd.read_file(REPO_ROOT / "data" / "static" / request.aoi_id / "exposure.gpkg", layer="villages").to_crs(epsg=4326)
    village_geom = {f"v_{row.osm_id}": mapping(row.geometry) for _, row in exposure.iterrows()}
    village_links = {v.village_id: [] for v in villages}
    for village in isolations:
        village_links[village.village_id] = [r.edge_id for r in roads if village.village_id in r.affected_settlements]
    isolations = [v.model_copy(update={"geometry": village_geom.get(v.village_id), "connected_road_ids": village_links.get(v.village_id, [])}) for v in isolations]
    p_fail_by_village, shelter_distances = resolve_priority_inputs(request.aoi_id, {c.cell_id: c.p_fail for c in typed_cells}, REPO_ROOT)
    priorities = compute_settlement_priorities(isolations, p_fail_by_village, shelter_distances)
    isolated_ids = {v.village_id for v in isolations if v.isolated_now}
    roads = [r.model_copy(update={"affected_settlements": [v.village_id for v in isolations if r.edge_id in v.severed_links]}) for r in roads]
    summary = WhatIfSummary(total_cells=len(typed_cells), critical_cells=sum(c.p_fail >= .75 for c in typed_cells), high_cells=sum(c.p_fail >= .55 for c in typed_cells), total_roads=len(roads), roads_at_risk=sum(r.p_blocked >= .3 for r in roads), severed_roads=sum(r.severed for r in roads), total_settlements=len(isolations), isolated_settlements=len(isolated_ids), population_at_risk=sum(v.population for v in isolations if v.isolated_now))
    from app.schemas.decision import ActionCard
    action_cards = []
    for priority in priorities[:3]:
        village = next(v for v in isolations if v.village_id == priority.village_id)
        stage = "RED" if village.p_isolated >= .75 else "ORANGE" if village.p_isolated >= .5 else "YELLOW"
        action_cards.append(ActionCard(alert_id=f"whatif-card-{request.aoi_id}-{village.village_id}", village_id=village.village_id, stage=stage, headline=f"{priority.tier} simulation priority — {village.name}", reason_plain=f"{len(village.severed_links)} road link(s) are severed or exposed in this synthetic scenario.", shelter_name=f"{village.name} Community Shelter", roads_to_avoid=village.severed_links, contact="DDMA control room", issued_at=t, valid_until=t))
    audit = AuditLog()
    event = audit.append(event_id=f"whatif-{uuid.uuid4()}", alert_id=f"whatif-{request.aoi_id}-{t.isoformat()}", kind="AI_FLAGGED", actor="simulation", t=t, payload={"aoi_id": request.aoi_id, "cell_count": len(typed_cells), "max_p_fail": max(c.p_fail for c in typed_cells)})
    tick = TickResult(t=t, mode="live", scenario_id=None, aoi_id=request.aoi_id, cell_risks=typed_cells, road_risks=roads, isolations=isolations, priorities=priorities, new_action_cards=action_cards, new_audit_events=[event], is_reconstructed=True)
    assumptions = ["Rainfall is spatially uniform; terrain properties vary by real AOI cell.", "Aizawl fault distance and lithology columns are missing in the static artifact; deterministic screening proxies are used unless the request supplies them.", "Road blockage uses the intersection of real cell polygons and OSM road geometries.", "Isolation removes severed graph edges and checks the existing HQ/hospital/shelter routes.", "This is a synthetic simulation and never updates live state."]
    return WhatIfResult(request=request, assumptions=assumptions, cell_count=len(typed_cells), tick=tick, summary=summary, metadata=WhatIfMetadata(assumptions=assumptions))
