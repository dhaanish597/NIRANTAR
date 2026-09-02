"""Counterfactual rainfall simulation over the shared ICONIX pipeline.

The simulator constructs an observation frame from explicit DDMA inputs, then runs a fresh
``Pipeline`` instance. It never mutates application replay/live state, publishes a websocket
tick, or writes into the operational audit log.
"""
from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Literal

import geopandas as gpd
from pydantic import BaseModel, Field

from app.pipeline import Pipeline
from app.schemas.ingest import CellObservation, ObservationFrame
from app.schemas.mode import RunMode
from app.schemas.tick import TickResult

REPO_ROOT = Path(__file__).resolve().parents[3]
WHAT_IF_SOURCE_LABEL = "what_if_simulation"

WHAT_IF_ASSUMPTIONS: list[str] = [
    "Rainfall is applied uniformly across every AOI cell.",
    "Storm intensity is constant over the simulated duration; this is not a forecast hyetograph.",
    "Antecedent rainfall, when supplied, is applied uniformly as a pre-event total.",
    "Soil moisture, when supplied, is a surface proxy (top 5 cm), not pore-water pressure.",
    "Risk, runout, road severance, isolation, priority, routing, and action cards use the same "
    "pipeline as replay.",
    "This is a counterfactual simulation, not predicted reality, and it does not change live or "
    "replay state.",
]


class WhatIfRequest(BaseModel):
    aoi_id: str = "aizawl"
    rainfall_mm: float = Field(gt=0.0, le=2000.0, description="Total simulated rainfall, mm")
    duration_hours: float = Field(gt=0.0, le=240.0, description="Simulated storm duration, hours")
    antecedent_rainfall_mm: float | None = Field(default=None, ge=0.0, le=350.0)
    soil_moisture_pct: float | None = Field(default=None, ge=0.0, le=100.0)

    # Accepted for API compatibility with the restored (ab785e5) What-If Simulator UI, which
    # exposes these as scenario controls. The current pipeline-based simulation consumes only
    # rainfall/duration/antecedent/soil-moisture; these are validated and echoed back but do not
    # (yet) influence a server-side run. The client-side offline fallback (buildWhatIfDemo) does
    # use them. Kept optional so existing 4-field callers are unaffected.
    slope_modifier_deg: float | None = Field(default=None, ge=15.0, le=55.0)
    distance_to_fault_km: float | None = Field(default=None, ge=0.1, le=15.0)
    lithology: Literal["weak", "moderate", "competent"] | None = None
    snow_mass_mm: float | None = Field(default=None, ge=0.0, le=150.0)
    snow_melt_active: bool | None = None
    exposure_weight: float | None = Field(default=None, ge=0.5, le=2.0)


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
    source: Literal["model"] = "model"
    mode: Literal["simulation"] = "simulation"
    spatial_resolution: str
    assumptions: list[str] = Field(default_factory=list)


class WhatIfResult(BaseModel):
    request: WhatIfRequest
    assumptions: list[str] = Field(default_factory=lambda: list(WHAT_IF_ASSUMPTIONS))
    cell_count: int
    tick: TickResult
    summary: WhatIfSummary
    metadata: WhatIfMetadata


def load_real_cell_ids(aoi_id: str) -> list[str]:
    """Load the built AOI grid; never invent cells for an unavailable AOI."""
    cells_path = REPO_ROOT / "data" / "static" / aoi_id / "cells.gpkg"
    if not cells_path.is_file():
        raise FileNotFoundError(
            f"{cells_path} not found; build static terrain data for AOI {aoi_id!r} first"
        )
    cells = gpd.read_file(cells_path, columns=["cell_id"])
    return [str(cell_id) for cell_id in cells["cell_id"].tolist()]


def build_synthetic_frame(
    aoi_id: str,
    rainfall_mm: float,
    duration_hours: float,
    *,
    t: datetime,
    antecedent_rainfall_mm: float | None = None,
    soil_moisture_pct: float | None = None,
) -> ObservationFrame:
    """Create a uniform, explicitly counterfactual observation frame for real AOI cells."""
    cell_ids = load_real_cell_ids(aoi_id)
    intensity_mm_per_hour = rainfall_mm / duration_hours

    def accumulated(window_hours: float) -> float:
        return intensity_mm_per_hour * min(window_hours, duration_hours)

    rain_1h = accumulated(1.0)
    rain_6h = accumulated(6.0)
    rain_24h = accumulated(24.0)
    rain_72h = accumulated(72.0)
    antecedent = rain_72h + (antecedent_rainfall_mm or 0.0)
    soil_moisture = None if soil_moisture_pct is None else soil_moisture_pct / 100.0

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
            soil_moisture=soil_moisture,
            insar_velocity_mm_yr=None,
            source=WHAT_IF_SOURCE_LABEL,
            is_reconstructed=True,
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
            "antecedent_rainfall_mm": str(antecedent_rainfall_mm or 0.0),
            "soil_moisture": "surface_proxy_top_5_cm" if soil_moisture is not None else "not_supplied",
        },
    )


def _summarize(tick: TickResult) -> WhatIfSummary:
    isolated = [village for village in tick.isolations if village.isolated_now]
    return WhatIfSummary(
        total_cells=len(tick.cell_risks),
        critical_cells=sum(cell.p_fail >= 0.75 for cell in tick.cell_risks),
        high_cells=sum(cell.p_fail >= 0.55 for cell in tick.cell_risks),
        total_roads=len(tick.road_risks),
        roads_at_risk=sum(road.p_blocked >= 0.3 for road in tick.road_risks),
        severed_roads=sum(road.severed for road in tick.road_risks),
        total_settlements=len(tick.isolations),
        isolated_settlements=len(isolated),
        population_at_risk=sum(village.population for village in isolated),
    )


def simulate_whatif(request: WhatIfRequest, *, t: datetime) -> WhatIfResult:
    """Run a fresh shared pipeline instance so operational state remains untouched."""
    frame = build_synthetic_frame(
        request.aoi_id,
        request.rainfall_mm,
        request.duration_hours,
        t=t,
        antecedent_rainfall_mm=request.antecedent_rainfall_mm,
        soil_moisture_pct=request.soil_moisture_pct,
    )
    tick = Pipeline().process(
        frame,
        mode=RunMode.REPLAY,
        scenario_id=f"whatif-{request.aoi_id}",
    )
    assumptions = list(WHAT_IF_ASSUMPTIONS)
    return WhatIfResult(
        request=request,
        assumptions=assumptions,
        cell_count=len(frame.cells),
        tick=tick,
        summary=_summarize(tick),
        metadata=WhatIfMetadata(
            spatial_resolution=f"{request.aoi_id} terrain grid and local OSM road graph",
            assumptions=assumptions,
        ),
    )
