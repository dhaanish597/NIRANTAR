"""Contracts for the crowdsourced, geotagged citizen-report workflow."""
from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

CitizenReportCategory = Literal[
    "Slope crack",
    "Blocked road",
    "Rockfall or debris",
    "Water seepage",
    "Retaining wall damage",
    "Other",
]
CitizenReportStatus = Literal["submitted", "acknowledged", "in_review", "actioned", "dismissed"]
ClassificationSource = Literal["nvidia", "fallback"]


class CitizenReportSubmit(BaseModel):
    aoi_id: str = "aizawl"
    category: CitizenReportCategory
    description: str = Field(default="", max_length=1000)
    lat: float = Field(ge=-90, le=90)
    lon: float = Field(ge=-180, le=180)
    accuracy_m: float | None = Field(default=None, ge=0, le=100_000)
    image_data_url: str = Field(min_length=16)


class CitizenReportStatusUpdate(BaseModel):
    status: CitizenReportStatus
    officer_id: str = Field(min_length=1, max_length=120)
    notes: str = Field(default="", max_length=1000)


class AgentTrace(BaseModel):
    step_name: Literal[
        "Ingestion",
        "Classification",
        "Dedup",
        "Hotspot",
        "Forecast",
        "Urgency",
        "Recommendation",
    ]
    step_order: int = Field(ge=1, le=7)
    detail: str
    source: Literal["deterministic", "nvidia"] = "deterministic"
    created_at: datetime


class CitizenReport(BaseModel):
    id: str
    aoi_id: str
    category: CitizenReportCategory
    citizen_selected_category: CitizenReportCategory
    description: str
    lat: float
    lon: float
    accuracy_m: float | None = None
    image_url: str
    image_mime_type: str
    image_width: int | None = None
    image_height: int | None = None
    image_size_bytes: int = Field(ge=1)
    quality_score: float = Field(ge=0, le=1)
    relevance_score: float = Field(ge=0, le=1)
    severity: int = Field(ge=1, le=5)
    classification_source: ClassificationSource
    classification_reasoning: str
    duplicate_of: str | None = None
    hotspot_count: int = Field(ge=1)
    forecast_next_7_days: int = Field(ge=0)
    current_aoi_max_p_fail: float | None = Field(default=None, ge=0, le=1)
    urgency_score: int = Field(ge=0, le=100)
    recommendation: str
    status: CitizenReportStatus = "submitted"
    officer_id: str | None = None
    officer_notes: str = ""
    created_at: datetime
    updated_at: datetime
    agent_traces: list[AgentTrace]

