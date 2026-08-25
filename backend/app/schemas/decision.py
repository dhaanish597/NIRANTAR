"""Decision contracts. See docs/ARCHITECTURE.md §4.5.

Output of decision/ (routing, escalation, action_card) — Phase 3 per BUILD_PLAN.md. Phase 0 stubs
one fixed ActionCard so the frontend action-card UI has something real to render against.

`safe_window_hours` is always a range, never a point estimate — CLAUDE.md glossary: "Safe
evacuation window ... Never call this 'time to landslide' — we do not predict exact timing."
"""
from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


class EvacuationRoute(BaseModel):
    village_id: str
    shelter_id: str
    shelter_name: str
    geometry: dict  # GeoJSON LineString
    distance_m: float = Field(ge=0.0)
    est_walk_minutes: int = Field(ge=0)
    avoided_roads: list[str] = Field(default_factory=list)
    shelter_capacity_ok: bool


class ActionCard(BaseModel):
    alert_id: str
    village_id: str
    stage: Literal["GREEN", "YELLOW", "ORANGE", "RED"]
    headline: str
    reason_plain: str
    shelter_name: str
    route: EvacuationRoute | None = None
    roads_to_avoid: list[str] = Field(default_factory=list)
    what_to_carry: list[str] = Field(default_factory=list)
    contact: str
    issued_at: datetime
    valid_until: datetime
    safe_window_hours: tuple[float, float] | None = None  # range, never a point estimate
    translations: dict[str, str] = Field(default_factory=dict)  # lang code -> text
    audio_urls: dict[str, str] = Field(default_factory=dict)
