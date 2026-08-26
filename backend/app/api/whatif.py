"""BUILD_PLAN.md task 5.8 — the what-if rainfall simulator: "a rainfall slider ('simulate 250 mm
over 12 h') that re-runs the pipeline on synthetic input and shows the resulting failure
distribution, road severance and isolation cascade. Position as DDMA pre-positioning support."

This is explicitly framed as DDMA PRE-POSITIONING SUPPORT, not a real alert — nothing this module
produces is a real observation, is written to the real audit trail, or reaches `/ws/ticks`. See
`api/routes.py`'s `whatif_simulate` route for the "throwaway Pipeline, never `app_state.pipeline`"
isolation this depends on.

===================================================================================================
RULINGS (read before changing this file)
===================================================================================================
1. **Real cell_ids, read directly from the AOI's real terrain grid** (`data/static/<aoi>/
   cells.gpkg`, task 1.2) — the same real, matchable ids `risk/model.py` predicts against (unlike
   the LIVE/REPLAY pipeline's still-unmigrated stub cell-id convention, `pipeline.py`'s own module
   docstring ruling 1). This means a what-if run is the first place in this codebase where the
   REAL trained model + real SHAP attributions + real terrain-driven runout envelopes actually
   fire end-to-end, not the threshold-only fallback.

2. **Spatially uniform rainfall.** A "simulate X mm over Y hours" request carries no spatial
   dimension at all — the honest choice is to apply the SAME intensity to every cell rather than
   inventing a fake spatial distribution the user never asked for. Documented here, not hidden.

3. **No antecedent wetness beyond the simulated event.** `antecedent_7d/15d/30d` are set to the
   SAME accumulated total as `rain_72h` (i.e. "no rain fell before this event") — the alternative,
   fabricating background wetness from nothing, would be a worse violation of CLAUDE.md's honesty
   rules than a clearly-documented simplification. This is a real, stated LIMITATION: a storm
   landing on already-saturated ground is genuinely higher risk than this preview can show.
   Surfaced in the response's own `assumptions` field (not just a code comment) so the DDMA-facing
   UI can display it, not just this docstring.

4. **Uniform intensity within the event.** `rain_Xh = min(X, duration_hours) / duration_hours *
   rainfall_mm` — a constant-intensity storm, not a fabricated hyetograph shape. Simple, and the
   only assumption defensible without inventing a real storm's actual time profile.
"""
from __future__ import annotations

from datetime import datetime
from pathlib import Path

import geopandas as gpd
from pydantic import BaseModel, Field

from app.schemas.ingest import CellObservation, ObservationFrame
from app.schemas.tick import TickResult

# app/api/whatif.py -> app/api -> app -> backend -> repo root
REPO_ROOT = Path(__file__).resolve().parents[3]

WHAT_IF_SOURCE_LABEL = "what_if_simulation"

# Real, stated limitations of this preview — returned on every response (see ruling 3 above) so
# the frontend can render them next to the results, not bury them in a docstring nobody reading
# the UI will ever see.
WHAT_IF_ASSUMPTIONS: list[str] = [
    "Rainfall is applied uniformly across every cell in the AOI — no spatial variation.",
    "Constant intensity for the simulated duration (rainfall_mm / duration_hours per hour) — not "
    "a real storm's actual time profile.",
    "No antecedent wetness beyond the simulated event is assumed (antecedent_7d/15d/30d equal the "
    "same accumulated total as the event itself) — a storm on already-saturated ground would "
    "carry materially higher real-world risk than this preview shows.",
    "Soil moisture and InSAR deformation are not simulated (left absent, not fabricated).",
]


class WhatIfRequest(BaseModel):
    aoi_id: str = "aizawl"
    rainfall_mm: float = Field(gt=0.0, le=2000.0, description="Total simulated rainfall, mm")
    duration_hours: float = Field(gt=0.0, le=240.0, description="Simulated storm duration, hours")


class WhatIfResult(BaseModel):
    """Wraps the real `TickResult` a throwaway `Pipeline` produced with the request that
    generated it and this preview's documented assumptions — so the frontend never has to guess
    what was simulated or silently drop the caveats."""

    request: WhatIfRequest
    assumptions: list[str] = Field(default_factory=lambda: list(WHAT_IF_ASSUMPTIONS))
    cell_count: int
    tick: TickResult


def load_real_cell_ids(aoi_id: str) -> list[str]:
    """The AOI's real cell ids straight from its real terrain grid (task 1.2) — every cell in the
    bbox, including the ones with no valid DEM pixel (task 1.2's documented null-terrain cells).
    Those simply degrade to `risk/thresholds.py`'s threshold-only fallback inside the real
    pipeline (`pipeline.py` ruling 2) exactly like any other unmatched cell would — not filtered
    out here, so a what-if run's cell count/coverage matches the AOI's real grid honestly."""
    cells_path = REPO_ROOT / "data" / "static" / aoi_id / "cells.gpkg"
    if not cells_path.is_file():
        raise FileNotFoundError(
            f"{cells_path} not found — no static terrain grid built for AOI {aoi_id!r} yet "
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
    # Ruling 3: no antecedent rain beyond the simulated event — same total as the 72h window.
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
            is_reconstructed=True,  # never a live/scenario observation — see ruling block above
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
