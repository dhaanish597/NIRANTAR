"""impact/priority.py — BUILD_PLAN.md task 2.5: the Evacuation Priority Score (EPS).

    EPS = w1*p_fail + w2*E_pop_norm + w3*RII + w4*(1 - A_shelter)        (CLAUDE.md §4)

Per settlement, fuses:
  - p_fail: this village's own local landslide-failure probability — the nearest 500m analysis
    cell's (scripts/build_grid.py, task 1.2) `p_fail`. A coarse proxy: risk sitting in an
    adjacent/uphill cell that doesn't itself contain the village point could still threaten it.
    Refining this to "any cell whose runout envelope (impact/runout.py) could reach the village"
    is a natural improvement, not attempted here — this module takes p_fail as an input, it does
    not compute it, so that refinement can land later without touching this file.
  - E_pop_norm: population normalized against config.EPS_POPULATION_NORM_REF, capped at 1.0.
  - RII: this village's isolation probability, `VillageIsolation.p_isolated`
    (impact/isolation.py, task 2.4) — used directly, not re-derived. CLAUDE.md §4's glossary
    defines RII as "a per-village score for likelihood + duration of being cut off"; `p_isolated`
    already is that score's likelihood component. Duration (`est_duration_hours`) is deliberately
    NOT folded into this weighted sum — EPS is a ranking score, and combining a probability with
    an hours-count would need yet another made-up normalization constant; duration stays exposed
    separately on VillageIsolation for the UI to show alongside the rank, not blended into it.
  - A_shelter: shelter accessibility — a straight-line-distance proxy against
    config.EPS_SHELTER_ACCESS_REF_KM (Phase 2 has no routed distance yet; decision/routing.py,
    task 3.1, will supersede this once it exists), forced to 0.0 (no effective access) whenever
    the village is already `isolated_now` — an unreachable shelter is worth nothing if the
    village can't reach ANY of hospital/HQ/shelter right now regardless of raw distance.

Weights and tier cutoffs all live in backend/app/config.py (CLAUDE.md §4: "must be tunable from
the UI"), not here.

Pure function over (VillageIsolation, p_fail, shelter_distance_km) — no LIVE/REPLAY awareness
(CLAUDE.md §2), no file I/O of its own; see `resolve_priority_inputs` for the geometry-resolution
helper real integration needs (nearest-cell p_fail lookup + nearest-shelter distance, both from
real Aizawl data).
"""
from __future__ import annotations

import warnings
from pathlib import Path
from typing import Literal

from app.config import (
    EPS_P1_THRESHOLD,
    EPS_P2_THRESHOLD,
    EPS_POPULATION_NORM_REF,
    EPS_SHELTER_ACCESS_REF_KM,
    EPS_WEIGHTS,
)
from app.schemas.impact import SettlementPriority, VillageIsolation


def _tier(eps: float, p1_threshold: float, p2_threshold: float) -> Literal["P1", "P2", "P3"]:
    if eps >= p1_threshold:
        return "P1"
    if eps >= p2_threshold:
        return "P2"
    return "P3"


def compute_settlement_priority(
    village: VillageIsolation,
    p_fail: float,
    shelter_distance_km: float | None,
    *,
    weights: dict[str, float] = EPS_WEIGHTS,
    population_norm_ref: float = EPS_POPULATION_NORM_REF,
    shelter_access_ref_km: float = EPS_SHELTER_ACCESS_REF_KM,
    p1_threshold: float = EPS_P1_THRESHOLD,
    p2_threshold: float = EPS_P2_THRESHOLD,
) -> SettlementPriority:
    pop_norm = min(village.population / population_norm_ref, 1.0) if population_norm_ref > 0 else 0.0
    rii = village.p_isolated

    if village.isolated_now or shelter_distance_km is None or shelter_access_ref_km <= 0:
        a_shelter = 0.0
    else:
        a_shelter = min(max(1.0 - shelter_distance_km / shelter_access_ref_km, 0.0), 1.0)

    p_fail_clamped = min(max(p_fail, 0.0), 1.0)

    eps = (
        weights["p_fail"] * p_fail_clamped
        + weights["pop"] * pop_norm
        + weights["rii"] * rii
        + weights["shelter"] * (1.0 - a_shelter)
    )

    return SettlementPriority(
        village_id=village.village_id,
        eps=eps,
        tier=_tier(eps, p1_threshold, p2_threshold),
        components={"p_fail": p_fail_clamped, "pop": pop_norm, "rii": rii, "shelter": a_shelter},
    )


def compute_settlement_priorities(
    villages: list[VillageIsolation],
    p_fail_by_village: dict[str, float],
    shelter_distance_km_by_village: dict[str, float | None],
    **kwargs,
) -> list[SettlementPriority]:
    """Batch form. A village missing from `p_fail_by_village` (e.g. its nearest cell had no
    CellRisk yet this tick) defaults to p_fail=0.0 rather than raising — a settlement with
    momentarily-unknown local risk should rank low on that component, not crash the tick."""
    return [
        compute_settlement_priority(
            v,
            p_fail_by_village.get(v.village_id, 0.0),
            shelter_distance_km_by_village.get(v.village_id),
            **kwargs,
        )
        for v in villages
    ]


# =================================================================================================
# Loader: real Aizawl geometry resolution (nearest cell's p_fail, nearest shelter distance) — see
# module docstring. Needs GeoPandas/shapely; exercised by an integration-style test, kept
# separate from the pure functions above so those stay testable with plain floats.
# =================================================================================================
def resolve_priority_inputs(
    aoi_id: str,
    cell_risks_by_cell_id: dict[str, float],
    repo_root: Path | None = None,
) -> tuple[dict[str, float], dict[str, float | None]]:
    """Reads data/static/<aoi>/{cells.gpkg,exposure.gpkg} and returns
    (p_fail_by_village_id, shelter_distance_km_by_village_id) for every village in exposure.gpkg.

    `cell_risks_by_cell_id` is {cell_id: p_fail} for the CURRENT tick (dynamic — passed in, not
    read from disk) — this function only resolves the STATIC geometry question of "which cell is
    nearest to this village," then looks that cell's p_fail up in the caller-supplied dict."""
    import geopandas as gpd
    from shapely.strtree import STRtree

    root = repo_root or Path(__file__).resolve().parents[3]
    cells_path = root / "data" / "static" / aoi_id / "cells.gpkg"
    exposure_path = root / "data" / "static" / aoi_id / "exposure.gpkg"
    if not cells_path.is_file():
        raise FileNotFoundError(f"{cells_path} not found — run scripts/build_grid.py first")
    if not exposure_path.is_file():
        raise FileNotFoundError(f"{exposure_path} not found — run scripts/fetch_exposure.py first")

    cells = gpd.read_file(cells_path)  # native CRS = the AOI's projected UTM zone (build_grid.py)
    villages = gpd.read_file(exposure_path, layer="villages")
    shelters = gpd.read_file(exposure_path, layer="shelters")

    # Centroid in the NATIVE projected CRS, THEN reproject the resulting points to WGS84 — not
    # the other way around. Reprojecting the polygons to WGS84 first and taking `.centroid`
    # there is both a GeoPandas UserWarning ("geometry is in a geographic CRS... likely
    # incorrect") and genuinely less correct for planar-square cells like these.
    cell_centroids = cells.geometry.centroid.to_crs(epsg=4326)
    cell_tree = STRtree(cell_centroids.values)
    cell_ids = cells["cell_id"].tolist()

    p_fail_by_village: dict[str, float] = {}
    for _, row in villages.iterrows():
        village_id = f"v_{row.osm_id}"
        idx = cell_tree.nearest(row.geometry)
        nearest_cell_id = cell_ids[idx]
        p_fail_by_village[village_id] = cell_risks_by_cell_id.get(nearest_cell_id, 0.0)

    shelter_distance_km: dict[str, float | None] = {}
    if shelters.empty:
        for _, row in villages.iterrows():
            shelter_distance_km[f"v_{row.osm_id}"] = None
    else:
        # Degree-based distance is a coarse approximation at Aizawl's latitude (good to within a
        # few percent at ~23.7N — real precision would reproject to the AOI's UTM zone first, as
        # scripts/fetch_exposure.py's population sampling does); acceptable here since A_shelter
        # only needs to rank villages relative to a 5km reference, not report a precise distance.
        # GeoPandas warns on `.distance()` over a geographic CRS for exactly this reason — the
        # warning is suppressed here because the approximation is deliberate and documented, not
        # accidental; it is NOT suppressed globally, only around this one known call.
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", category=UserWarning)
            for _, row in villages.iterrows():
                village_id = f"v_{row.osm_id}"
                nearest_dist_deg = shelters.geometry.distance(row.geometry).min()
                shelter_distance_km[village_id] = nearest_dist_deg * 111.0

    return p_fail_by_village, shelter_distance_km
