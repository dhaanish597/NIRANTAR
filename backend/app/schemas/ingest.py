"""Ingest contracts. See docs/ARCHITECTURE.md §4.2.

ObservationFrame is the one object every DataSource implementation (live or replay) must produce.
Everything from risk/ onward only ever sees this — never a raw feed response, never a scenario
file. `source` and `is_reconstructed` carry provenance through as data, which is what lets the
pipeline stay mode-blind (CLAUDE.md §2).
"""
from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


class CellObservation(BaseModel):
    cell_id: str
    rain_1h: float = Field(ge=0.0)
    rain_6h: float = Field(ge=0.0)
    rain_24h: float = Field(ge=0.0)
    rain_72h: float = Field(ge=0.0)
    antecedent_7d: float = Field(ge=0.0)
    antecedent_15d: float = Field(ge=0.0)
    antecedent_30d: float = Field(ge=0.0)
    soil_moisture: float | None = Field(default=None, ge=0.0, le=1.0)  # surface proxy, 0-1
    insar_velocity_mm_yr: float | None = None
    source: str  # "imerg" | "scenario:aizawl-2024" | ...
    is_reconstructed: bool = False


class ObservationFrame(BaseModel):
    t: datetime
    aoi_id: str
    cells: list[CellObservation]
    provenance: dict[str, str]
