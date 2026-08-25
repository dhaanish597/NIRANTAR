#!/usr/bin/env python
"""Turn published rainfall aggregate figures into a scenario frame series (BUILD_PLAN.md task
4.2), and auto-populate the resulting file's `provenance` block.

WHY A DISAGGREGATION METHOD IS NEEDED
--------------------------------------
Every case-study event we have a citable source for gives a rainfall *aggregate*, not an hourly
gauge trace: "253.7 mm over 3 days" (Aizawl), "~572 mm/48 h" (Wayanad), "705.5 mm May-Jun, 130%
above decadal average" (Tupul). Appendix B's `frames` array needs one `rain_1h` value per cell
per hour (`frame_interval_minutes`). Turning one published total into an hourly series requires a
*documented* temporal shape — CLAUDE.md forbids doing this silently ("cite the method you chose
in a docstring, don't silently interpolate").

THE METHOD: Alternating Block Method, shaped by our own cited I-D curve
------------------------------------------------------------------------
We use the **Alternating Block Method** (Chow, Maidment & Mays, *Applied Hydrology*, 1988,
S14.3) — a standard, widely-taught hydrology technique for turning a depth-duration relationship
into a design hyetograph:

1. A depth-duration curve gives the cumulative rainfall depth expected in any sub-duration `D` of
   a storm. We reuse the exact NE Himalaya intensity-duration curve already cited elsewhere in
   this project (CLAUDE.md S4 / docs/reference/: `I(D) = 5.8294 * D^-0.4141` mm/h, D in hours,
   frequentist method, TRMM 2007-2016), which gives cumulative depth `P(D) = I(D) * D`, i.e.
   `P(D) is proportional to D^(1 - 0.4141) = D^0.5859` -- a concave (diminishing-returns) curve,
   exactly the shape the Alternating Block Method wants. This borrows a REAL, cited local curve
   for the storm's SHAPE only, not its magnitude.
2. Successive differences of `P(D)` at each timestep give incremental "blocks" of rain that
   shrink monotonically as elapsed duration grows (classic Alternating Block Method step 1).
   These are then rescaled so their sum exactly equals the actually-published event total
   (`total_mm`) -- so this method invents no magnitude, only a temporal distribution for a total
   that is already public record.
3. The blocks are placed in decreasing order of size, alternating outward from a `peak_index` —
   the standard Alternating Block construction, generalised (as the method explicitly allows,
   see "advanced"/"delayed" design-storm variants) to let the peak sit anywhere in the window
   rather than only at the midpoint. Here `peak_index` is never a free choice: it is always
   derived from each scenario's own DOCUMENTED failure/initiation time (a cited fact, see the
   EVENTS registry below), so the storm's heaviest hour lands where the real event's own timeline
   says the ground was wettest, not wherever is dramatically convenient.

DERIVED QUANTITIES (not independently fabricated)
--------------------------------------------------
- `rain_6h`/`rain_24h`/`rain_72h`: true trailing rolling sums of the generated `rain_1h` series
  (mechanically implied by step 3 above, not a separate invention).
- `antecedent_7d`/`15d`/`30d`: trailing rolling sums of the SAME generated series, zero-padded
  before the scenario's own clock start. No citable pre-event background wetness figure exists in
  docs/reference/ for any of these three events, and CLAUDE.md forbids inventing one — so this is
  a documented, clearly conservative (likely-understating) proxy, not a fabricated baseline. Said
  explicitly in every scenario's `provenance.disclaimer`.
- `soil_moisture`: a simple, documented, deterministic saturating function of each cell's own
  `rain_72h` series, normalised to that cell's own maximum over the scenario window and floored at
  a background value. This is explicitly a SYNTHETIC proxy standing in for real SMAP retrievals
  (task 1.7, not yet built for these historical dates) -- CLAUDE.md rule 5 already frames
  satellite soil moisture as a rainfall-fused surrogate, so a rainfall-derived stand-in is
  consistent with that framing, but it is not a real satellite reading and is labelled as such.
- `insar_velocity_mm_yr`: always `null` for all three events built here. CLAUDE.md rule 4 scopes
  InSAR to slow/deep-seated deformation; none of Aizawl's quarry collapse, Wayanad's debris flow,
  or Tupul's cut-slope failure are documented as slow-moving InSAR precursor cases, so claiming an
  InSAR signal for them would be exactly the overclaim CLAUDE.md warns against.

PER-CELL SPATIAL SPREAD
-------------------------
Each scenario drives a small illustrative cell grid (see EVENTS below), split into "hotspot" cells
(near the documented failure) and "background" cells. Hotspot cells get a small documented
multiplier (1.15x) on the same generated series; background cells get 0.90x. This is explicitly
labelled as illustrative spatial spread for the CURRENT stub 3x3-cell demo grid (there is no real
per-slope grid for these events — see each scenario's own provenance note), not a claim about
measured spatial variation.

Usage:
    python scripts/build_scenario.py --id aizawl-2024
    python scripts/build_scenario.py --all
"""
from __future__ import annotations

import argparse
import json
import math
import sys
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "backend"))

from app.schemas.scenario import ScenarioFile  # noqa: E402

SCENARIOS_DIR = REPO_ROOT / "data" / "scenarios"

# The NE Himalaya intensity-duration threshold curve (CLAUDE.md S4; docs/reference/ both
# reference docs cite it identically): I(D) = 5.8294 * D^-0.4141, I in mm/h, D in hours.
# Used here ONLY for its shape exponent (cumulative depth ~ D^(1 + ID_EXPONENT)) -- see module
# docstring. Never used to invent a magnitude.
ID_CURVE_EXPONENT = -0.4141
SHAPE_EXPONENT = 1 + ID_CURVE_EXPONENT  # 0.5859 -- concave cumulative-depth-vs-duration curve

HOTSPOT_MULTIPLIER = 1.15
BACKGROUND_MULTIPLIER = 0.90
SOIL_MOISTURE_BASELINE = 0.22
SOIL_MOISTURE_CEILING = 0.92


def alternating_block_hyetograph(
    *, total_mm: float, n_steps: int, peak_index: int
) -> list[float]:
    """Alternating Block Method (see module docstring). Returns `n_steps` hourly depths (mm)
    summing to exactly `total_mm`, peaking at `peak_index` and built up/receding on either side.
    """
    if n_steps <= 0:
        raise ValueError("n_steps must be positive")
    if not (0 <= peak_index < n_steps):
        raise ValueError(f"peak_index {peak_index} out of range [0, {n_steps})")

    # Step 1: cumulative shape value P(k) at k=0..n_steps (P(0)=0), using the ID curve's implied
    # depth-duration exponent as a dimensionless shape (no magnitude yet).
    cum_shape = [k**SHAPE_EXPONENT for k in range(0, n_steps + 1)]
    # Step 2: successive differences -> incremental "blocks", strictly decreasing as k grows
    # (concave cum_shape => diminishing increments). Rescale so blocks sum to total_mm exactly.
    raw_blocks = [cum_shape[k] - cum_shape[k - 1] for k in range(1, n_steps + 1)]
    total_raw = sum(raw_blocks)
    scale = total_mm / total_raw if total_raw > 0 else 0.0
    blocks_desc = sorted((b * scale for b in raw_blocks), reverse=True)

    # Step 3: alternating placement outward from peak_index (largest block at the peak, then
    # alternate forward/backward with the next-largest, falling back to whichever side still has
    # room once the other runs out -- this is what naturally produces a "build up to the peak,
    # short recession" shape when peak_index sits near the end of the window, matching every one
    # of our three events' documented narrative).
    order: list[int] = [peak_index]
    forward = peak_index + 1
    backward = peak_index - 1
    want_forward = True
    while len(order) < n_steps:
        if want_forward and forward < n_steps:
            order.append(forward)
            forward += 1
        elif not want_forward and backward >= 0:
            order.append(backward)
            backward -= 1
        elif forward < n_steps:
            order.append(forward)
            forward += 1
        elif backward >= 0:
            order.append(backward)
            backward -= 1
        else:
            break
        want_forward = not want_forward

    hyetograph = [0.0] * n_steps
    for idx, block in zip(order, blocks_desc):
        hyetograph[idx] = block
    return hyetograph


def _rolling_sum(series: list[float], *, window: int, index: int) -> float:
    """Trailing rolling sum ending at `index` (inclusive), zero-padded before series start —
    documented in the module docstring as a conservative simplification for antecedent_* fields."""
    start = max(0, index - window + 1)
    return sum(series[start : index + 1])


def _soil_moisture(rain_72h_series: list[float], index: int) -> float:
    """Documented synthetic proxy (see module docstring): a saturating function of this cell's
    own rain_72h, normalised to that cell's own scenario-window maximum."""
    peak_72h = max(rain_72h_series) if rain_72h_series else 0.0
    if peak_72h <= 0:
        return SOIL_MOISTURE_BASELINE
    fraction = rain_72h_series[index] / peak_72h
    span = SOIL_MOISTURE_CEILING - SOIL_MOISTURE_BASELINE
    return round(SOIL_MOISTURE_BASELINE + span * fraction, 4)


@dataclass(frozen=True)
class EventSpec:
    """Everything build_scenario_dict() needs for one real case-study event. Every field that
    states a fact about the real world carries an inline citation to docs/reference/ or to
    BUILD_PLAN.md's own given anchors — nothing here is invented."""

    id: str
    name: str
    event_date: str  # ISO date
    aoi_id: str
    hazard_type: str
    trigger: str
    clock_start: str  # ISO datetime, +05:30
    clock_end: str
    frame_interval_minutes: int
    default_speed_factor: float
    total_rain_mm: float
    peak_time: str  # ISO datetime the hyetograph peaks at (see per-event rationale in EVENTS)
    cell_ids: list[str]
    hotspot_cell_ids: list[str]
    sources: list[str]
    method_note: str
    disclaimer_extra: str
    ground_truth: dict
    narration: list[dict]


def build_scenario_dict(spec: EventSpec) -> dict:
    clock_start = datetime.fromisoformat(spec.clock_start)
    clock_end = datetime.fromisoformat(spec.clock_end)
    peak_time = datetime.fromisoformat(spec.peak_time)
    dt = timedelta(minutes=spec.frame_interval_minutes)

    n_steps = int(round((clock_end - clock_start) / dt)) + 1
    peak_index = int(round((peak_time - clock_start) / dt))
    peak_index = max(0, min(n_steps - 1, peak_index))

    base_rain_1h = alternating_block_hyetograph(
        total_mm=spec.total_rain_mm, n_steps=n_steps, peak_index=peak_index
    )

    steps_per_hour = 60.0 / spec.frame_interval_minutes
    window_6h = max(1, round(6 * steps_per_hour))
    window_24h = max(1, round(24 * steps_per_hour))
    window_72h = max(1, round(72 * steps_per_hour))
    window_7d = max(1, round(7 * 24 * steps_per_hour))
    window_15d = max(1, round(15 * 24 * steps_per_hour))
    window_30d = max(1, round(30 * 24 * steps_per_hour))

    per_cell_series: dict[str, list[float]] = {}
    for cell_id in spec.cell_ids:
        multiplier = HOTSPOT_MULTIPLIER if cell_id in spec.hotspot_cell_ids else BACKGROUND_MULTIPLIER
        per_cell_series[cell_id] = [round(v * multiplier, 4) for v in base_rain_1h]

    per_cell_rain72 = {
        cell_id: [_rolling_sum(series, window=window_72h, index=i) for i in range(n_steps)]
        for cell_id, series in per_cell_series.items()
    }

    frames = []
    for i in range(n_steps):
        t = clock_start + i * dt
        cells = []
        for cell_id in spec.cell_ids:
            series = per_cell_series[cell_id]
            cells.append(
                {
                    "cell_id": cell_id,
                    "rain_1h": round(series[i], 4),
                    "rain_6h": round(_rolling_sum(series, window=window_6h, index=i), 4),
                    "rain_24h": round(_rolling_sum(series, window=window_24h, index=i), 4),
                    "rain_72h": round(_rolling_sum(series, window=window_72h, index=i), 4),
                    "antecedent_7d": round(_rolling_sum(series, window=window_7d, index=i), 4),
                    "antecedent_15d": round(_rolling_sum(series, window=window_15d, index=i), 4),
                    "antecedent_30d": round(_rolling_sum(series, window=window_30d, index=i), 4),
                    "soil_moisture": _soil_moisture(per_cell_rain72[cell_id], i),
                    "insar_velocity_mm_yr": None,
                }
            )
        frames.append({"t": t.isoformat(), "cells": cells, "defaults": {}})

    provenance = {
        "confidence": "reconstructed",
        "method": (
            "Published rainfall aggregate disaggregated to an hourly series via the Alternating "
            "Block Method (Chow, Maidment & Mays, Applied Hydrology, 1988, S14.3), shaped by this "
            "project's own cited NE Himalaya intensity-duration curve (I = 5.8294*D^-0.4141) used "
            "only as a dimensionless depth-duration SHAPE, rescaled to the actually-published "
            "event total. See scripts/build_scenario.py's module docstring for the full method, "
            "including the antecedent_* and soil_moisture derivations. " + spec.method_note
        ),
        "sources": spec.sources,
        "disclaimer": (
            "Rainfall series is reconstructed from a published aggregate figure, not archived "
            "gauge observation. Per-cell spatial variation and soil_moisture are illustrative "
            "synthetic proxies for this project's current stub demo grid, not measured "
            "per-slope data. antecedent_7d/15d/30d reflect only the reconstructed event-window "
            "rainfall (zero-padded before it) and likely UNDERSTATE true pre-event background "
            "wetness, since no cited pre-event baseline exists in docs/reference/ for this event "
            "-- a documented limitation, not a fabricated number. " + spec.disclaimer_extra
        ),
    }

    return {
        "id": spec.id,
        "name": spec.name,
        "event_date": spec.event_date,
        "aoi_id": spec.aoi_id,
        "hazard_type": spec.hazard_type,
        "trigger": spec.trigger,
        "held_out_of_training": True,
        "provenance": provenance,
        "clock": {
            "start": spec.clock_start,
            "end": spec.clock_end,
            "frame_interval_minutes": spec.frame_interval_minutes,
            "default_speed_factor": spec.default_speed_factor,
        },
        "frames": frames,
        "ground_truth": spec.ground_truth,
        "narration": spec.narration,
    }


# ---------------------------------------------------------------------------------------------
# EVENT REGISTRY (BUILD_PLAN.md tasks 4.3-4.5)
#
# Every fact below is either a BUILD_PLAN.md-given anchor (Appendix B's own worked example, and
# the task 4.3/4.4/4.5 bullet points) or is drawn from docs/reference/SIH26001_Technical_
# Architecture_Reference.md and docs/reference/AI-Based Early Warning & Landslide Risk Monitoring
# System for the North Eastern Region.md (the two files the task instructions named). Anything
# not found in either is marked TODO(verify) inline rather than invented, per CLAUDE.md.
# ---------------------------------------------------------------------------------------------

_AIZAWL_CELLS = [
    "aizawl_401", "aizawl_402", "aizawl_403",
    "aizawl_411", "aizawl_412", "aizawl_413",
    "aizawl_421", "aizawl_422", "aizawl_423",
]
# aizawl_412 is the illustrative "center" cell nearest the quarry-collapse narrative beat.
_AIZAWL_HOTSPOTS = ["aizawl_412", "aizawl_413", "aizawl_422"]

AIZAWL_2024 = EventSpec(
    id="aizawl-2024",
    name="Aizawl multi-slope failures, Mizoram",
    event_date="2024-05-28",
    aoi_id="aizawl",
    hazard_type="rainfall_triggered_shallow",
    trigger="Cyclone Remal",
    # Clock window, rainfall total, and every ground_truth/narration fact below reuse BUILD_PLAN.md
    # Appendix B's own worked example verbatim (it IS the given anchor for this exact scenario).
    clock_start="2024-05-26T00:00:00+05:30",
    clock_end="2024-05-28T18:00:00+05:30",
    frame_interval_minutes=60,
    default_speed_factor=3600,
    total_rain_mm=253.7,  # "~253.7mm over 3 days in Aizawl" -- BUILD_PLAN.md task 4.3 / both ref docs
    # Peak set one hour before the documented ~6AM quarry collapse: a methodological choice
    # (the disaggregation's peak-placement parameter), not a new fact -- the collapse itself is
    # the cited fact (see ground_truth.failures below).
    peak_time="2024-05-28T05:00:00+05:30",
    cell_ids=_AIZAWL_CELLS,
    hotspot_cell_ids=_AIZAWL_HOTSPOTS,
    sources=[
        "IMD daily rainfall bulletins, May 2024",
        "Peer-reviewed post-event study (see docs/reference/)",
        "Mizoram SDMA situation reports",
        "docs/reference/SIH26001_Technical_Architecture_Reference.md S7 (case study table)",
        "docs/reference/AI-Based Early Warning & Landslide Risk Monitoring System for the North Eastern Region.md S1 (case-study table)",
    ],
    method_note=(
        "Clock window, rainfall total, quarry-collapse coordinates, NH-6/Hunthar severance, "
        "IMD warning, and death toll are BUILD_PLAN.md Appendix B's own worked example for this "
        "exact scenario, reused verbatim rather than re-derived."
    ),
    disclaimer_extra=(
        "cell_id values reuse the Phase 0 stub 3x3 demo-grid convention "
        "(aizawl_{row}{col}) -- see frontend/src/lib/grid.ts and CLAUDE.md's Current State. Real "
        "per-slope cell geometry exists in data/static/aizawl/cells.gpkg (2,912 cells) but is not "
        "yet wired into the live/replay pipeline, so this scenario's spatial resolution is "
        "illustrative, not the real analysis grid. insar_velocity_mm_yr is null throughout: this "
        "is a rainfall-triggered shallow failure, not a slow/deep-seated deformation case "
        "(CLAUDE.md rule 4)."
    ),
    ground_truth={
        "failures": [
            {
                "t": "2024-05-28T06:00:00+05:30",
                "lat": 23.70,
                "lon": 92.71,
                "note": "Stone quarry collapse, Melthum-Hlimen",
                "deaths_attributed": "multiple",
            }
        ],
        "road_events": [
            {
                "t": "2024-05-28T07:00:00+05:30",
                "road": "NH-6",
                "location": "Hunthar",
                "effect": "severed",
                "consequence": "Aizawl isolated from the rest of the country",
            }
        ],
        "official_warnings": [
            {
                "t": "2024-05-27T08:00:00+05:30",
                "issuer": "IMD",
                "level": "red",
                "spatial_scale": "district",
                "note": "No slope-specific warning issued",
            }
        ],
        "outcome": {
            "deaths": "27-34 (state total; 33 bodies recovered per academic study)",
            "source_note": "Report as a range with source; do not assert a single figure.",
        },
    },
    narration=[
        {
            "t": "2024-05-28T04:00:00+05:30",
            "text": (
                "Antecedent rainfall from Cyclone Remal has been saturating Aizawl's slopes "
                "since the 26th; cumulative wetness is at its highest of the event as dawn "
                "approaches on the 28th."
            ),
        },
        {
            "t": "2024-05-28T06:00:00+05:30",
            "text": "Stone quarry collapse reported at Melthum-Hlimen (documented failure time).",
        },
        {
            "t": "2024-05-28T07:00:00+05:30",
            "text": "NH-6 severed at Hunthar -- Aizawl isolated from the rest of the country.",
        },
    ],
)


_WAYANAD_CELLS = [
    "wayanad_401", "wayanad_402", "wayanad_403",
    "wayanad_411", "wayanad_412", "wayanad_413",
    "wayanad_421", "wayanad_422", "wayanad_423",
]
_WAYANAD_HOTSPOTS = ["wayanad_412", "wayanad_421", "wayanad_422"]

WAYANAD_2024 = EventSpec(
    id="wayanad-2024",
    name="Wayanad (Mundakkai-Chooralmala-Punchirimattom) debris flows, Kerala",
    event_date="2024-07-30",
    # AOI-config gap (flagged per this task's own instructions): backend/app/config.py only
    # registers "aizawl" (Phase 1 built its DEM/grid/road-graph pipeline for Aizawl only). No
    # static grid/DEM/road-graph has been built for Wayanad -- standing one up is out of scope
    # for this scenario-file task. "wayanad" is used here as a plain identifier; it resolves fine
    # through ScenarioFile/ScenarioSource/Pipeline (schema-driven, no config.get_aoi() call on
    # this path) but will 404 on GET /api/aoi/wayanad and has no real terrain/road data.
    aoi_id="wayanad",
    hazard_type="rainfall_triggered_debris_flow",
    trigger="Southwest monsoon rainfall (no named cyclone)",
    # 48h leading up to the 02:00-04:30 failure, extended a few hours back to also cover the
    # Hume Centre's 09:00 (29 Jul) alert -- the whole point of this scenario (task 4.4).
    clock_start="2024-07-28T00:00:00+05:30",
    clock_end="2024-07-30T06:00:00+05:30",
    frame_interval_minutes=60,
    default_speed_factor=3600,
    total_rain_mm=572.0,  # "~572mm/48h at Puthumala" -- BUILD_PLAN.md task 4.4 / both ref docs
    # Midpoint of the documented 02:00-04:30 initiation window.
    peak_time="2024-07-30T03:00:00+05:30",
    cell_ids=_WAYANAD_CELLS,
    hotspot_cell_ids=_WAYANAD_HOTSPOTS,
    sources=[
        "docs/reference/AI-Based Early Warning & Landslide Risk Monitoring System for the North Eastern Region.md S1 (case-study table) and Caveats section",
        "docs/reference/SIH26001_Technical_Architecture_Reference.md S7 (case study table)",
        "IMD orange-alert bulletins, 29-30 Jul 2024 (referenced in docs/reference/, exact bulletin text not reproduced)",
        "Hume Centre for Ecology & Wildlife Biology (Kalpetta) public alert reporting, 29 Jul 2024",
    ],
    method_note=(
        "48h/572mm Puthumala figure and the 02:00-04:30 initiation window are both directly "
        "cited in docs/reference/; peak_time is the midpoint of that cited window, a "
        "disaggregation-method choice, not an additional fact."
    ),
    disclaimer_extra=(
        "AOI-config gap: aoi_id 'wayanad' is NOT registered in backend/app/config.py (Phase 1's "
        "static-data pipeline -- DEM, 500m grid, road graph -- was built for Aizawl only); this "
        "scenario replays correctly through the backend pipeline (schema-driven, no config "
        "lookup on that path) but has no real terrain/road/AOI-bbox data and will not resolve via "
        "GET /api/aoi/wayanad. cell_id values follow a wayanad_{row}{col} convention parallel to "
        "Aizawl's own stub grid, but frontend/src/lib/grid.ts's parser only recognises the "
        "'aizawl_' prefix, so this scenario will not yet paint cells on the current map UI -- a "
        "frontend follow-up, not a backend defect. Death toll is reported as a wide range "
        "(200-400+) across official/Wikipedia/academic sources -- see ground_truth.outcome; do "
        "not collapse it to one figure. Precise lat/lon for Mundakkai/Chooralmala/Puthumala are "
        "not cited in docs/reference/ and are therefore null (TODO(verify)) rather than invented. "
        "IMD's own district alert was orange (not red); its exact issuance timestamp is not cited "
        "in docs/reference/ and is therefore omitted from ground_truth.official_warnings rather "
        "than invented -- only the Hume Centre alert (which DOES have a cited time) is included. "
        "insar_velocity_mm_yr is null throughout: this is a rainfall-triggered debris flow, not a "
        "slow/deep-seated deformation case (CLAUDE.md rule 4)."
    ),
    ground_truth={
        "failures": [
            {
                "t": "2024-07-30T02:00:00+05:30",
                "lat": None,
                "lon": None,
                "note": (
                    "Debris flow initiation, Mundakkai/Chooralmala/Punchirimattom, on a "
                    "pre-existing 2020 crack; peaked ~28 m/s, ~8km runout (window 02:00-04:30 IST). "
                    "Precise coordinates TODO(verify) -- not cited in docs/reference/."
                ),
                "deaths_attributed": "official ~298+32 declared; Wikipedia 420; academic estimates 254-392",
            }
        ],
        "road_events": [
            {
                "t": "2024-07-30T04:00:00+05:30",
                "road": "Punapuzha bridge (local access road)",
                "location": "Mundakkai",
                "effect": "collapsed",
                "consequence": "Mundakkai isolated from rescue/road access",
            }
        ],
        "official_warnings": [
            {
                "t": "2024-07-29T09:00:00+05:30",
                "issuer": "Hume Centre for Ecology & Wildlife Biology, Kalpetta (200+ weather stations)",
                "level": "landslide alert (station-network based, not an official IMD colour code)",
                "spatial_scale": "local station network",
                "note": (
                    "Issued ~16 hours before the 02:00-04:30 failure window; reportedly not acted "
                    "on / district administration reportedly denied receiving it. IMD's separate "
                    "district alert was orange, not red -- exact IMD issuance time not cited in "
                    "docs/reference/, omitted here rather than invented."
                ),
            }
        ],
        "outcome": {
            "deaths": "200-400+ (official ~298+32 declared dead; Wikipedia 420; academic estimates 254-392)",
            "source_note": (
                "Wayanad death toll varies materially by source -- report as a range, never a "
                "single figure (docs/reference/ Caveats section explicitly warns against this)."
            ),
        },
    },
    narration=[
        {
            "t": "2024-07-29T09:00:00+05:30",
            "text": (
                "The Hume Centre for Ecology & Wildlife Biology issues a landslide alert based on "
                "its own station network -- roughly 16 hours before the failure. It does not "
                "convert into an evacuation."
            ),
        },
        {
            "t": "2024-07-30T02:00:00+05:30",
            "text": (
                "Debris flow initiates on a pre-existing 2020 crack above Mundakkai-Chooralmala, "
                "at night, after ~572mm of rain in 48 hours at the Puthumala gauge."
            ),
        },
        {
            "t": "2024-07-30T04:00:00+05:30",
            "text": "The Punapuzha bridge collapses, isolating Mundakkai from road access.",
        },
    ],
)


_TUPUL_CELLS = [
    "tupul_401", "tupul_402", "tupul_403",
    "tupul_411", "tupul_412", "tupul_413",
    "tupul_421", "tupul_422", "tupul_423",
]
_TUPUL_HOTSPOTS = ["tupul_412", "tupul_422", "tupul_423"]

# 705.5mm is a May-Jun 2022 (~2-month) aggregate (docs/reference/), far too long a period to
# reconstruct hour-by-hour for a demo replay (Phase 4's DoD targets ~90s replays of ~60h events).
# We model only the acute pre-failure window and derive ITS total by apportioning the cited
# 2-month total proportionally to this window's share of that period -- a documented, mechanical
# derivation from the cited figure, not an independently invented finer-grained total. See
# WINDOW_HOURS/PERIOD_HOURS below and the method_note this feeds into provenance.method.
_TUPUL_WINDOW_START = datetime.fromisoformat("2022-06-27T00:00:00+05:30")
_TUPUL_WINDOW_END = datetime.fromisoformat("2022-06-30T08:00:00+05:30")
_TUPUL_WINDOW_HOURS = (_TUPUL_WINDOW_END - _TUPUL_WINDOW_START).total_seconds() / 3600.0
_TUPUL_PERIOD_HOURS = 61 * 24.0  # May 1 - Jun 30 2022, inclusive-ish -- the cited "May-Jun" period
_TUPUL_TOTAL_MM_CITED = 705.5
_TUPUL_WINDOW_MM = round(
    _TUPUL_TOTAL_MM_CITED * (_TUPUL_WINDOW_HOURS / _TUPUL_PERIOD_HOURS), 2
)

TUPUL_2022 = EventSpec(
    id="tupul-2022",
    name="Tupul/Noney railway construction-site failure, Manipur",
    event_date="2022-06-30",
    aoi_id="tupul",  # same AOI-config gap as wayanad-2024 -- see disclaimer_extra below
    hazard_type="rainfall_triggered_shallow",
    trigger="Heavy May-June 2022 monsoon rainfall (no named cyclone)",
    clock_start=_TUPUL_WINDOW_START.isoformat(),
    clock_end=_TUPUL_WINDOW_END.isoformat(),
    frame_interval_minutes=60,
    default_speed_factor=3600,
    total_rain_mm=_TUPUL_WINDOW_MM,
    # Second, larger-impact failure (06:00) is the one that buried the construction camp and
    # dammed the Ijai river -- peak set just before it, matching the intensification narrative.
    peak_time="2022-06-30T05:00:00+05:30",
    cell_ids=_TUPUL_CELLS,
    hotspot_cell_ids=_TUPUL_HOTSPOTS,
    sources=[
        "docs/reference/AI-Based Early Warning & Landslide Risk Monitoring System for the North Eastern Region.md S1 (case-study table)",
        "docs/reference/SIH26001_Technical_Architecture_Reference.md S7 (case study table)",
    ],
    method_note=(
        f"total_rain_mm for this scenario's ~{_TUPUL_WINDOW_HOURS:.0f}h acute window "
        f"({_TUPUL_WINDOW_MM}mm) is NOT independently cited -- docs/reference/ only gives a "
        f"May-Jun 2022 (~{_TUPUL_PERIOD_HOURS:.0f}h) aggregate of {_TUPUL_TOTAL_MM_CITED}mm "
        "(130% above decadal average). This window's total is that cited aggregate apportioned "
        "proportionally by duration -- a documented mechanical derivation, not an independent "
        "invention. The two-phase failure timing (~00:30 and ~06:00, 30 Jun) and the 61-death "
        "toll are the real, cited anchors this scenario is built around; the exact sub-window "
        "rainfall distribution is a modelling simplification, stated here rather than hidden."
    ),
    disclaimer_extra=(
        "AOI-config gap (same as wayanad-2024): aoi_id 'tupul' is NOT registered in "
        "backend/app/config.py -- no static terrain/road data exists for Noney district. "
        "cell_id values follow a tupul_{row}{col} convention; frontend/src/lib/grid.ts does not "
        "yet parse this prefix, so this scenario will not paint cells on the current map UI, "
        "same caveat as wayanad-2024. THE POINT OF THIS SCENARIO: the Tupul site was mapped "
        "low-to-moderate susceptibility by NLSM (National Landslide Susceptibility Mapping) prior "
        "to the failure -- see ground_truth and narration below, and CLAUDE.md task 4.5's own "
        "framing ('static maps miss things, dynamic risk does not'). Precise lat/lon for the "
        "Tupul/Noney site are not cited in docs/reference/ and are therefore null (TODO(verify)) "
        "rather than invented. total_rain_mm for this window is an apportioned derivation of the "
        "cited 2-month aggregate, not an independently published figure -- see provenance.method. "
        "insar_velocity_mm_yr is null throughout: this is a rainfall-triggered cut-slope failure, "
        "not a slow/deep-seated deformation case (CLAUDE.md rule 4)."
    ),
    ground_truth={
        "failures": [
            {
                "t": "2022-06-30T00:30:00+05:30",
                "lat": None,
                "lon": None,
                "note": (
                    "First-phase slope failure near the Tupul railway construction site (Noney "
                    "district, Manipur), on the Jiribam-Imphal line. Site had been mapped "
                    "low-to-moderate susceptibility by NLSM prior to this event; back-slopes were "
                    "separately noted as moderate-high. TODO(verify): precise coordinates."
                ),
                "deaths_attributed": "part of the combined 61 dead across both phases",
            },
            {
                "t": "2022-06-30T06:00:00+05:30",
                "lat": None,
                "lon": None,
                "note": (
                    "Second, larger-impact failure; buried the railway construction camp and "
                    "blocked the Ijai river, creating a dam-breach hazard."
                ),
                "deaths_attributed": "61 total (29-30 Territorial Army personnel + civilians, across both phases)",
            },
        ],
        "road_events": [
            {
                "t": "2022-06-30T06:00:00+05:30",
                "road": "Jiribam-Imphal railway line (under construction)",
                "location": "Tupul, Noney district",
                "effect": "construction site destroyed; Ijai river channel blocked",
                "consequence": "dam-breach flood hazard created upstream/downstream of the blockage",
            }
        ],
        # Deliberately empty: docs/reference/ is explicit that NO warning was issued for this
        # site -- that absence IS the point of the scenario (see narration below), not a gap in
        # this file.
        "official_warnings": [],
        "outcome": {
            "deaths": "61 (29-30 Territorial Army personnel + civilians)",
            "source_note": (
                "Widely reported as 61 total; the Army-personnel-vs-civilian split varies "
                "slightly by source (29 vs 30 TA) -- reported as '~61' rather than asserting one "
                "exact breakdown."
            ),
        },
    },
    narration=[
        {
            "t": "2022-06-27T00:00:00+05:30",
            "text": (
                "May-June 2022 rainfall across the region has run roughly 130% above the decadal "
                "average. The Tupul railway construction bench had been mapped low-to-moderate "
                "susceptibility -- no elevated static warning exists for this site."
            ),
        },
        {
            "t": "2022-06-30T00:30:00+05:30",
            "text": "First-phase failure near the Tupul construction camp.",
        },
        {
            "t": "2022-06-30T06:00:00+05:30",
            "text": (
                "Second, larger failure buries the camp and blocks the Ijai river. No warning "
                "was ever issued for this site -- the static susceptibility map said low-moderate."
            ),
        },
    ],
)


EVENTS: dict[str, EventSpec] = {
    spec.id: spec for spec in (AIZAWL_2024, WAYANAD_2024, TUPUL_2022)
}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--id", choices=sorted(EVENTS), help="build just this scenario")
    group.add_argument("--all", action="store_true", help="build every registered scenario")
    parser.add_argument(
        "--out-dir", type=Path, default=SCENARIOS_DIR, help="output directory (default: data/scenarios)"
    )
    args = parser.parse_args(argv)

    ids = sorted(EVENTS) if args.all else [args.id]
    for scenario_id in ids:
        spec = EVENTS[scenario_id]
        data = build_scenario_dict(spec)
        # Fail loudly before writing anything if the generated dict doesn't even satisfy the
        # schema -- scripts/validate_scenario.py does the fuller (honesty-rule + dry-run) check.
        ScenarioFile.model_validate(data)
        out_path = args.out_dir / f"{scenario_id}.json"
        out_path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
        print(f"wrote {out_path} ({len(data['frames'])} frames)")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
