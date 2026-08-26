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
    # District name string as IMD's public API is expected to spell it (`District`/`Station`
    # fields of the districtnowcast/districtwarning endpoints — ingest/live/imd.py, task 1.8).
    # Optional (defaults to None, existing AOI configs/tests that predate task 1.8 stay valid
    # unchanged) — imd.py falls back to deriving a guess from `name` when unset. NOT verified
    # against a real IMD response (network access to api.imd.gov.in was blocked this session, and
    # IMD API access itself hasn't been requested yet per Required_by_me.md) — TODO(verify) the
    # exact casing/spelling IMD actually uses once a real response can be inspected.
    imd_district_name: str | None = None


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
        imd_district_name="Aizawl",  # TODO(verify) — see AoiConfig.imd_district_name's comment
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

# =================================================================================================
# Phase 3 — decision layer (BUILD_PLAN.md tasks 2.6, 3.1, 3.3): safe evacuation window, routing,
# action cards. All ENGINEERING DEFAULTS (CLAUDE.md rule 1), not measured/fit values, same status
# as the Phase 2 constants above.
# =================================================================================================

# decision/window.py (task 2.6): the exceedance-ratio value (risk/thresholds.py's
# threshold_exceedance_ratio — 1.0 means observed rainfall meets the published I-D/E-D threshold
# for that duration) at/above which the safe evacuation window collapses to "now" rather than a
# projected future crossing. 1.0 is the threshold engine's own natural "met" boundary, not a
# separately-fit number.
WINDOW_CRITICAL_EXCEEDANCE_RATIO = 1.0
# Fewer than this many trend observations and a linear fit is not attempted at all (CLAUDE.md
# rule 1: don't state a projection we can't back with data) — returns no window rather than a
# noisy one-line-through-two-points guess.
WINDOW_MIN_TREND_POINTS = 3
# A projected crossing further out than this is not reported — matches rain_72h, the longest
# accumulation window CellObservation actually carries (schemas/ingest.py); projecting past the
# horizon of our own longest observed signal would overstate this module's real predictive reach.
WINDOW_MAX_FORECAST_HOURS = 72.0
# Half-width of the returned range, as a fraction of the projected hours-until-crossing — an
# engineering default expressing "this is a rough projection, not a precise ETA" (CLAUDE.md's
# "safe evacuation window ... never time to landslide" framing). TODO(verify): replace with a
# statistically-derived prediction interval once enough real replayed events exist to calibrate one.
WINDOW_MARGIN_FRACTION = 0.25
# Floor on the range half-width in hours, so a crossing projected only an hour or two out doesn't
# collapse to a falsely-precise point estimate.
WINDOW_MIN_MARGIN_HOURS = 0.5
# When already at/above WINDOW_CRITICAL_EXCEEDANCE_RATIO, the window is reported as (0, this) —
# "act now", not a projection at all.
WINDOW_IMMEDIATE_UPPER_HOURS = 1.0

# decision/routing.py (task 3.1): C_edge = L_edge * (1 + alpha*P_fail_edge + beta*S_slope_edge)
# (CLAUDE.md §4). P_fail_edge here is impact/road_graph.py's RoadSegmentRisk.p_blocked for that
# edge — see decision/routing.py's module docstring for why that substitution is the right one.
# alpha=3.0 means a fully-at-risk-but-not-yet-severed edge (p_blocked approx 1.0, just under
# P_CRIT_ROAD) costs roughly 4x its plain length — strongly discourages routing through it without
# banning it outright (edges past P_crit are removed entirely, a separate, harder rule). Engineering
# default, not a cited figure; tunable (CLAUDE.md §4: "must be tunable from the UI").
ROUTING_ALPHA_P_FAIL = 3.0
# beta*S_slope_edge: structurally present, currently a no-op for every edge in practice — no
# per-edge road-surface-slope dataset exists yet (see decision/routing.py's module docstring).
# Kept non-zero so the term is visibly "real" the moment slope data is wired in, not disabled.
ROUTING_BETA_SLOPE = 1.0
# Average walking pace used ONLY to convert a computed route's physical distance into
# EvacuationRoute.est_walk_minutes — hilly terrain, on foot, an engineering default (not a cited
# figure); ALWAYS presented as an estimate, matching VillageIsolation.est_duration_hours's own
# honesty framing.
ROUTING_WALKING_SPEED_KMH = 4.0

# decision/action_card.py (task 3.3).
# How long an issued ActionCard is treated as current before it should be considered stale/
# re-issued. Matches decision/stub.py's Phase 0 placeholder value (kept for continuity, not
# re-derived — see EscalationConfig's own docstring note for the same pattern).
ACTION_CARD_VALID_FOR_HOURS = 6.0
# General emergency-evacuation checklist — NOT scenario- or hazard-specific, and not sourced from
# docs/reference/ (CLAUDE.md: don't invent facts — this is a generic, defensible checklist, not a
# claimed authoritative one). Documented explicitly as such wherever it's rendered.
WHAT_TO_CARRY_CHECKLIST: list[str] = [
    "Identity documents",
    "Essential medicines",
    "Torch/flashlight with spare batteries",
    "Drinking water",
    "Mobile phone with charger or power bank",
    "Warm/weatherproof clothing",
]
# CLAUDE.md rule: don't invent a real DDMA phone number — none is cited anywhere in
# docs/reference/. This is an explicit, self-labelling placeholder string, not a real contact.
ACTION_CARD_CONTACT_PLACEHOLDER = (
    "District Disaster Management Authority (DDMA) control room — "
    "contact number not yet configured for this AOI (placeholder, not a real number)"
)


# =================================================================================================
# pipeline.py real-module wiring (a later session, task-1.12-through-3.6's integration into the
# live/replay pipeline — see pipeline.py's own module docstring for the full design rationale).
# =================================================================================================
# decision/window.py needs a chronological trajectory of `WindowObservation`s (BUILD_PLAN.md task
# 2.6). pipeline.py maintains one AOI-level rolling history — see its module docstring's "why
# AOI-level, not per-village" ruling — capped at this many most-recent ticks so memory stays
# bounded across a long-running LIVE session or a many-frame REPLAY. Not itself a physically cited
# figure; large enough to give estimate_safe_window's linear fit (WINDOW_MIN_TREND_POINTS=3
# minimum) a stable-looking recent trend without holding an unbounded history.
PIPELINE_EXCEEDANCE_HISTORY_LEN = 50
