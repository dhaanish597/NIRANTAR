"""impact/runout.py — BUILD_PLAN.md task 2.2.

For each cell whose failure probability exceeds a trigger threshold, project a runout envelope
polygon downslope from the cell, using:

  - DIRECTION: the cell's DEM-derived downhill aspect (already computed by
    scripts/build_grid.py's Horn's-method slope/aspect kernel — a compass bearing, 0=N, 90=E,
    180=S, 270=W, of the cell's downhill direction).

  - LENGTH: the classical "angle of reach" / Fahrboschung relation (Heim, A. (1932),
    "Bergsturz und Menschenleben," Fretz & Wasmuth) — empirically quantified for landslide
    mobility across many events by Corominas, J. (1996), "The angle of reach as a mobility index
    for small and large landslides," Canadian Geotechnical Journal 33(2), 260-271:

        tan(angle_of_reach) = H / L   =>   L = H / tan(angle_of_reach)

    where H is the vertical drop available to the failing mass and L is the horizontal runout
    distance. Corominas (1996) fits `angle_of_reach` as DECREASING with landslide volume (larger
    failures travel proportionally farther) — we have no per-cell debris-volume estimate (only
    p_fail), so as a documented simplification this module uses ONE FIXED angle_of_reach,
    representative of small-to-moderate-volume, rainfall-triggered shallow debris flows/slides
    (the hazard type this AOI targets — see CLAUDE.md §4's I-D/E-D thresholds and
    data/scenarios's `hazard_type: "rainfall_triggered_shallow"`), rather than a volume-scaled
    regression. The constant (config.RUNOUT_ANGLE_OF_REACH_DEG = 25.0 degrees) and its
    TODO(verify) live in backend/app/config.py, not here, per CLAUDE.md §4 ("weights and
    constants live in config.py").

  - VERTICAL DROP (H): the cell's own DEM-derived relief (elevation_max_m - elevation_min_m,
    already computed by scripts/build_grid.py) — the elevation drop across the cell's own 500m
    footprint. This is a coarse, cell-level approximation: a finer model would trace the DEM flow
    path beyond the cell into its downslope neighbours, which is out of scope for this 500m-grid
    pass (documented simplification, not an oversight — matches the same "no depression-filling,
    no cross-cell tracing" scope cut build_grid.py already made for flow accumulation).

  - WIDTH: a fixed lateral spread half-angle from the flow direction
    (config.RUNOUT_SPREAD_HALF_ANGLE_DEG), producing a triangular "debris cone" footprint —
    apex at the source cell centroid, widening downslope. This is our own geometric device for
    turning a 1-D reach distance into a 2-D polygon; it borrows the fixed-opening-angle
    convention used in regional rockfall/debris "energy cone" runout screening (Jaboyedoff, M. &
    Labiouse, V. (2011), "Preliminary estimation of rockfall runout zones," Nat. Hazards Earth
    Syst. Sci. 11(3), 819-828), adapted here to a per-cell debris source rather than a single
    rockfall release point.

This module is a PURE FUNCTION over (CellRisk, CellTerrain) pairs — see CLAUDE.md §2 / task
2.2's own instruction: it does not read cells.gpkg itself, does not call risk/model.py, and does
not know or care whether the CellRisk came from LIVE or REPLAY. `load_cell_terrain()` below reads
cells.gpkg for real Aizawl terrain and is exercised separately (tests/test_runout.py) from the
pure geometry function, so the geometry logic is fully testable against synthetic terrain without
needing the risk model, the DEM, or GeoPandas at all.

CRS NOTE: `compute_runout_envelope` operates entirely in whatever CRS `CellTerrain.centroid_x/y`
were given in (real callers use the AOI's projected UTM CRS — metres — same as cells.gpkg's
storage CRS, so straight-line distance math is valid). The `RunoutEnvelope.geometry` produced is
therefore in that same CRS, NOT literal WGS84 lon/lat, even though the schema field is documented
as "GeoJSON Polygon" (which conventionally implies EPSG:4326). `project_envelope_to_wgs84()`
below does the reprojection step real integration needs before treating the output as genuine
GeoJSON for the frontend/API — keeping that reprojection out of the pure function itself avoids
tying the testable geometry logic to pyproj/GeoPandas.
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from pathlib import Path

from app.config import RUNOUT_ANGLE_OF_REACH_DEG, RUNOUT_SPREAD_HALF_ANGLE_DEG, RUNOUT_TRIGGER_P_FAIL
from app.schemas.impact import RunoutEnvelope
from app.schemas.risk import CellRisk


@dataclass(frozen=True)
class CellTerrain:
    """The subset of a cells.gpkg row this module needs. Independent of CellRisk/ObservationFrame
    on purpose — terrain is static (built once by scripts/build_grid.py), risk is dynamic
    (recomputed every tick); keeping them as separate inputs is what makes this function testable
    without a live risk model (task 2.2's own instruction)."""

    cell_id: str
    centroid_x: float  # projected CRS (AOI's UTM zone), metres
    centroid_y: float
    aspect_deg: float | None  # downhill compass bearing, 0=N/90=E/180=S/270=W; None if unknown
    relief_m: float | None  # elevation_max_m - elevation_min_m within the cell; None if unknown


def compute_runout_envelope(
    cell_risk: CellRisk,
    terrain: CellTerrain,
    *,
    p_fail_threshold: float = RUNOUT_TRIGGER_P_FAIL,
    angle_of_reach_deg: float = RUNOUT_ANGLE_OF_REACH_DEG,
    spread_half_angle_deg: float = RUNOUT_SPREAD_HALF_ANGLE_DEG,
) -> RunoutEnvelope | None:
    """Returns a triangular runout envelope for `cell_risk`, or None if no envelope should be
    projected (p_fail below threshold, or terrain data insufficient to project one).

    Returns None rather than a degenerate/fabricated shape when:
      - `cell_risk.p_fail < p_fail_threshold` — this cell isn't failing seriously enough to model
        a runout at all (BUILD_PLAN.md task 2.2: "for cells above a probability threshold").
      - `terrain.aspect_deg` or `terrain.relief_m` is None — real cells.gpkg has ~212/2,912 cells
        with null terrain stats (edge cells with no valid DEM pixel — task 1.2's documented gap,
        NOT a bug). Silently inventing a direction/length for those would be a fabricated number;
        skipping is the honest behaviour (CLAUDE.md §10's "not detected" caveat, in spirit).
      - `terrain.relief_m <= 0` — a (near-)flat cell has no modelled vertical drop to convert into
        a runout length under this relation; again, skip rather than fabricate a floor value.
    """
    if cell_risk.cell_id != terrain.cell_id:
        raise ValueError(
            f"cell_risk/terrain mismatch: {cell_risk.cell_id!r} != {terrain.cell_id!r}"
        )

    if cell_risk.p_fail < p_fail_threshold:
        return None
    if terrain.aspect_deg is None or terrain.relief_m is None:
        return None
    if terrain.relief_m <= 0:
        return None

    length_m = terrain.relief_m / math.tan(math.radians(angle_of_reach_deg))

    bearing_rad = math.radians(terrain.aspect_deg)
    # Compass bearing -> unit vector in a standard x-east/y-north projected CRS.
    dir_x = math.sin(bearing_rad)
    dir_y = math.cos(bearing_rad)
    # Perpendicular to the flow direction (rotated -90 degrees), for the cone's lateral spread.
    perp_x = dir_y
    perp_y = -dir_x

    half_width_m = length_m * math.tan(math.radians(spread_half_angle_deg))

    apex = (terrain.centroid_x, terrain.centroid_y)
    base_center = (terrain.centroid_x + dir_x * length_m, terrain.centroid_y + dir_y * length_m)
    left = (base_center[0] + perp_x * half_width_m, base_center[1] + perp_y * half_width_m)
    right = (base_center[0] - perp_x * half_width_m, base_center[1] - perp_y * half_width_m)

    ring = [list(apex), list(left), list(right), list(apex)]  # closed ring

    return RunoutEnvelope(
        source_cell_id=cell_risk.cell_id,
        geometry={"type": "Polygon", "coordinates": [ring]},
        p_fail=cell_risk.p_fail,
        method=(
            f"angle_of_reach_{angle_of_reach_deg:g}deg_corominas1996"
            f"_spread_{spread_half_angle_deg:g}deg"
        ),
    )


def compute_runout_envelopes(
    cell_risks: list[CellRisk],
    terrain_by_cell_id: dict[str, CellTerrain],
    **kwargs,
) -> list[RunoutEnvelope]:
    """Batch form of `compute_runout_envelope`. Cells with no matching terrain entry are skipped
    (not an error) — a CellRisk can legitimately arrive for a cell_id this AOI's static data
    doesn't (yet) cover, and that should degrade gracefully, not crash a tick."""
    envelopes = []
    for risk in cell_risks:
        terrain = terrain_by_cell_id.get(risk.cell_id)
        if terrain is None:
            continue
        envelope = compute_runout_envelope(risk, terrain, **kwargs)
        if envelope is not None:
            envelopes.append(envelope)
    return envelopes


def project_envelope_to_wgs84(envelope: RunoutEnvelope, src_epsg: int) -> RunoutEnvelope:
    """Reprojects a RunoutEnvelope's polygon from `src_epsg` (a projected CRS, metres) to
    EPSG:4326 (lon/lat) — the CRS the `RunoutEnvelope.geometry` field is actually documented to
    hold ("GeoJSON Polygon"). Kept separate from `compute_runout_envelope` so the pure geometry
    function above never needs pyproj/GeoPandas (see module docstring's CRS note)."""
    from pyproj import Transformer

    transformer = Transformer.from_crs(f"EPSG:{src_epsg}", "EPSG:4326", always_xy=True)
    ring = envelope.geometry["coordinates"][0]
    reprojected_ring = [list(transformer.transform(x, y)) for x, y in ring]
    return envelope.model_copy(
        update={"geometry": {"type": "Polygon", "coordinates": [reprojected_ring]}}
    )


# =================================================================================================
# Loader: real Aizawl terrain from cells.gpkg. Exercised by an integration-style test, kept
# separate from the pure functions above so those stay testable without GeoPandas/a real AOI.
# =================================================================================================
def load_cell_terrain(aoi_id: str, repo_root: Path | None = None) -> dict[str, CellTerrain]:
    """Reads data/static/<aoi>/cells.gpkg (built by scripts/build_grid.py, task 1.2) and returns
    a {cell_id: CellTerrain} map in the file's own storage CRS (the AOI's projected UTM zone —
    see config.AoiConfig.utm_epsg / build_grid.py's `make_grid()`), i.e. already in the metres-
    based CRS `compute_runout_envelope` expects."""
    import geopandas as gpd

    root = repo_root or Path(__file__).resolve().parents[3]
    cells_path = root / "data" / "static" / aoi_id / "cells.gpkg"
    if not cells_path.is_file():
        raise FileNotFoundError(
            f"{cells_path} not found — run `python scripts/build_grid.py --aoi {aoi_id}` first"
        )

    cells = gpd.read_file(cells_path)
    centroids = cells.geometry.centroid

    terrain: dict[str, CellTerrain] = {}
    for i, row in cells.iterrows():
        aspect = row.get("aspect_mean_deg")
        relief = row.get("relief_m")
        terrain[row["cell_id"]] = CellTerrain(
            cell_id=row["cell_id"],
            centroid_x=float(centroids.iloc[i].x),
            centroid_y=float(centroids.iloc[i].y),
            aspect_deg=None if aspect is None or (isinstance(aspect, float) and math.isnan(aspect)) else float(aspect),
            relief_m=None if relief is None or (isinstance(relief, float) and math.isnan(relief)) else float(relief),
        )
    return terrain
