"""Impact contracts. See docs/ARCHITECTURE.md §4.4.

Output of impact/ (runout, road_graph, isolation/RII, priority/EPS) — Phase 2 per BUILD_PLAN.md.
Phase 0 stubs return a small fixed set so the schema is exercised end to end before Phase 2
implements it for real.
"""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class RunoutEnvelope(BaseModel):
    source_cell_id: str
    geometry: dict  # GeoJSON Polygon
    p_fail: float = Field(ge=0.0, le=1.0)
    method: str  # empirical relation used


class RoadSegmentRisk(BaseModel):
    edge_id: str
    name: str | None = None  # "NH-6"
    highway_class: str
    is_bridge: bool
    p_blocked: float = Field(ge=0.0, le=1.0)
    severed: bool
    contributing_cells: list[str] = Field(default_factory=list)


class Demographics(BaseModel):
    """Simulated household/census-level breakdown — no such dataset exists for the NER pilot
    AOIs. Derived deterministically from each village's real WorldPop-based `population` figure
    (see impact/demographics.py). Never presented as Census/ground-truth data."""

    children: int = Field(ge=0)
    seniors: int = Field(ge=0)
    adults: int = Field(ge=0)
    high_risk_households: int = Field(ge=0)
    source: Literal["simulated"] = "simulated"


class VillageIsolation(BaseModel):
    village_id: str
    name: str
    population: int = Field(ge=0)
    demographics: Demographics
    p_isolated: float = Field(ge=0.0, le=1.0)
    isolated_now: bool
    alternate_route_exists: bool
    est_duration_hours: float | None = None  # ALWAYS labelled "estimate" in UI
    severed_links: list[str] = Field(default_factory=list)


class SettlementPriority(BaseModel):
    village_id: str
    eps: float
    tier: Literal["P1", "P2", "P3"]
    components: dict[str, float]  # {"p_fail":.., "pop":.., "rii":.., "shelter":..}
