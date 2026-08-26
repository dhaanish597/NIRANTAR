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


# =================================================================================================
# Phase 2 — impact layer (BUILD_PLAN.md tasks 2.2-2.5): runout, road_graph, isolation (RII),
# priority (EPS). All constants below are ENGINEERING DEFAULTS, not measured/fit values, unless a
# citation says otherwise — CLAUDE.md rule 1 bans stating an unmeasured number as validated. These
# are meant to be retuned once real eval data exists (ml/evaluate.py, task 1.16) and to be
# UI-tunable (the false-alarm-cost slider, task 5.6) rather than hidden constants, per CLAUDE.md §4.
# =================================================================================================

# impact/runout.py (task 2.2): p_fail floor above which a cell's failure is projected downslope
# into a runout envelope. Matches the number impact/stub.py used as a Phase 0 placeholder (kept
# for continuity, not re-derived — there is no labeled failure inventory yet to calibrate an
# operating threshold against; that calibration is ml/evaluate.py's job, task 1.16).
RUNOUT_TRIGGER_P_FAIL = 0.5

# Angle of reach (Fahrboschung, Heim 1932) for a debris-flow/shallow-slide runout, in degrees:
# tan(angle) = vertical_drop / horizontal_runout_length. See impact/runout.py's module docstring
# for the full citation (Corominas 1996; Rickenmann 2005) and the TODO(verify) on replacing this
# single fixed value with a volume-calibrated or NE-Himalaya-specific one once one exists.
RUNOUT_ANGLE_OF_REACH_DEG = 25.0

# Lateral spread half-angle of the runout "cone" used to turn a 1-D reach distance into a 2-D
# footprint polygon (impact/runout.py) — our own geometric simplification, not itself a published
# landslide-specific figure; borrowed from the fixed-opening-angle convention used in regional
# rockfall/debris "energy cone" runout screening (Jaboyedoff, M. & Labiouse, V. (2011),
# "Preliminary estimation of rockfall runout zones," Nat. Hazards Earth Syst. Sci. 11(3), 819-828).
# TODO(verify): recalibrate against a real mapped debris-flow footprint width if one becomes
# available in docs/reference/.
RUNOUT_SPREAD_HALF_ANGLE_DEG = 15.0

# impact/road_graph.py (task 2.3) / impact/isolation.py (task 2.4): the p_blocked probability
# above which a road edge is treated as functionally severed for routing/connectivity purposes.
# This realizes CLAUDE.md §4's C_edge formula ("edge severed if P_fail > P_crit") as two
# thresholds rather than one:
P_CRIT_ROAD = 0.7
# Bridges get a LOWER (more conservative) severance threshold than ordinary road segments — a
# single-point-of-failure structure with materially higher failure consequence and (usually) no
# redundant crossing nearby. This design choice is motivated by the Punapuzha bridge collapse at
# Mundakkai, Wayanad (30 Jul 2024) isolating Mundakkai — see
# docs/reference/AI-Based Early Warning & Landslide Risk Monitoring System for the North Eastern
# Region.md — per BUILD_PLAN.md task 2.3's own instruction to cite it. This is NOT a claim that an
# Aizawl bridge has failed this way. It governs bridge-tagged *road* edges from
# scripts/build_road_graph.py's OSMnx extract (the `bridge=yes` highway-way tag), which is a
# different and much better-populated OSM tag than the `man_made=bridge` point layer
# scripts/fetch_exposure.py queried (0 results for Aizawl — see task 1.3's notes).
P_CRIT_BRIDGE = 0.5

# impact/priority.py (task 2.5): EPS = w1*p_fail + w2*E_pop_norm + w3*RII + w4*(1-A_shelter)
# (CLAUDE.md §4). Weights sum to 1.0 so EPS stays in [0,1] when every component is in [0,1].
EPS_WEIGHTS: dict[str, float] = {
    "p_fail": 0.35,
    "pop": 0.25,
    "rii": 0.25,
    "shelter": 0.15,
}

# impact/priority.py tier cutoffs. P1 = Immediate Mandatory Evacuation, P2 = Evacuation Ready,
# P3 = Watch (CLAUDE.md §4 glossary).
EPS_P1_THRESHOLD = 0.65
EPS_P2_THRESHOLD = 0.35

# impact/priority.py's population-normalization reference: E_pop_norm = min(population / this,
# 1.0). Aizawl's own exposure.gpkg villages (task 1.3) top out well under 100 people within their
# 500m sampling buffer (`population_worldpop_est` — a coarse 1km-density-based estimate, see
# scripts/fetch_exposure.py's own caveat about it), so a literal "largest village in India"
# reference would flatten every real Aizawl village to near-zero. This constant is deliberately
# AOI-scale rather than a national constant. TODO(verify): revisit once other AOIs' exposure data
# (Tupul, Wayanad) gives a wider real distribution of village sizes to calibrate against.
EPS_POPULATION_NORM_REF = 200.0

# impact/priority.py's shelter-accessibility term A_shelter — a straight-line-distance proxy.
# Phase 2 has no routed distance yet (decision/routing.py, task 3.1, will supersede this once it
# exists); A_shelter = clamp(1 - distance_km / this constant, 0, 1). 5 km is an engineering
# placeholder for "a plausible walk to a shelter in hilly terrain within a few hours," not a
# measured figure.
EPS_SHELTER_ACCESS_REF_KM = 5.0

# impact/isolation.py (task 2.4)'s `est_duration_hours` heuristic: BUILD_PLAN.md task 2.4 itself
# calls this "a heuristic from road class + blockage severity," and VillageIsolation's schema
# comment requires it be "ALWAYS labelled 'estimate' in UI" (CLAUDE.md's "safe evacuation
# window" honesty rule, §3 rule 6, applies with equal force here — never present this as a
# measured clearance time). Base hours are ordered by road class only (bigger/more important
# roads generally get faster official clearance priority in practice) — engineering defaults, not
# a cited restoration-time study; nothing in docs/reference gives per-class clearance durations.
ROAD_CLEARANCE_HOURS_BY_CLASS: dict[str, float] = {
    "trunk": 24.0,
    "primary": 24.0,
    "secondary": 18.0,
    "tertiary": 12.0,
    "residential": 6.0,
    "unclassified": 6.0,
    "service": 4.0,
}
ROAD_CLEARANCE_HOURS_DEFAULT = 12.0  # highway class not in the table above

# Bridges take materially longer than debris clearance — a collapsed/damaged bridge is a rebuild,
# not a cleanup — motivated by the same Punapuzha bridge (Mundakkai, Wayanad) case P_CRIT_BRIDGE
# cites above. Multiplies the base class hours; not itself a measured rebuild-time figure.
BRIDGE_CLEARANCE_MULTIPLIER = 2.0
