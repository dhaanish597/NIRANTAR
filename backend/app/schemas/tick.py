"""The WebSocket payload. See docs/ARCHITECTURE.md §4.7.

TickResult is the one object the frontend ever receives over /ws/ticks. It re-exports the types
from every other schema module — it does not duplicate them.
"""
from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field

from app.schemas.audit import AuditEvent
from app.schemas.decision import ActionCard
from app.schemas.impact import (
    RoadSegmentRisk,
    RunoutEnvelope,
    SettlementPriority,
    VillageIsolation,
)
from app.schemas.mode import RunMode
from app.schemas.risk import CellRisk


class TickResult(BaseModel):
    t: datetime
    mode: RunMode
    scenario_id: str | None = None
    aoi_id: str
    cell_risks: list[CellRisk] = Field(default_factory=list)
    # Runout envelopes reaching the frontend (BUILD_PLAN.md task 2.2/2.3 schema-change ruling):
    # CLAUDE.md §11 flagged this as an open gap since Phase 0 — impact/stub.py computed
    # RunoutEnvelope objects but had nowhere to put them on the wire. Resolved as a TickResult
    # field (not a separate REST/tile endpoint) to match the existing pattern of every other
    # impact/ output (road_risks, isolations, priorities) already being broadcast this way.
    runouts: list[RunoutEnvelope] = Field(default_factory=list)
    road_risks: list[RoadSegmentRisk] = Field(default_factory=list)
    isolations: list[VillageIsolation] = Field(default_factory=list)
    priorities: list[SettlementPriority] = Field(default_factory=list)
    new_action_cards: list[ActionCard] = Field(default_factory=list)
    new_audit_events: list[AuditEvent] = Field(default_factory=list)
    is_reconstructed: bool = False
