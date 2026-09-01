"""Date-wise forecast contract built from the existing risk/impact schemas."""
from __future__ import annotations

from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, Field

from app.schemas.impact import RoadSegmentRisk, SettlementPriority, VillageIsolation
from app.schemas.risk import CellRisk


class ForecastArea(BaseModel):
    id: str
    name: str
    risk_probability: float = Field(ge=0.0, le=1.0)
    risk_level: str


class RiskForecastDay(BaseModel):
    date: date
    day_label: str
    risk_level: str
    risk_probability: float = Field(ge=0.0, le=1.0)
    rainfall_mm: float = Field(ge=0.0)
    confidence: float = Field(ge=0.0, le=1.0)
    primary_driver: str
    explanation: str
    affected_villages: int = Field(ge=0)
    affected_road_segments: int = Field(ge=0)
    cell_risks: list[CellRisk] = Field(default_factory=list)
    road_risks: list[RoadSegmentRisk] = Field(default_factory=list)
    isolations: list[VillageIsolation] = Field(default_factory=list)
    priorities: list[SettlementPriority] = Field(default_factory=list)
    areas: list[ForecastArea] = Field(default_factory=list)


class RiskForecast(BaseModel):
    location: str
    location_id: str
    generated_at: datetime
    source: Literal["LIVE", "MODEL", "FALLBACK"]
    forecast: list[RiskForecastDay] = Field(min_length=5, max_length=5)
