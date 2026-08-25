"""Audit contract. See docs/ARCHITECTURE.md §4.6.

audit/ is the only writer of the hash chain (`prev_hash` -> `hash`), even though every pipeline
stage emits events onto the bus that end up here. Phase 0 writes one AI_FLAGGED event per tick so
the audit trail is real, not mocked, from day one (BUILD_PLAN.md Phase 0 DoD).
"""
from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel


class AuditEvent(BaseModel):
    event_id: str
    alert_id: str
    kind: Literal[
        "AI_FLAGGED",
        "DDMA_APPROVED",
        "DISSEMINATED",
        "DELIVERED",
        "VILLAGE_ACKNOWLEDGED",
        "ESCALATED",
        "STOOD_DOWN",
    ]
    actor: str  # "system" | "ddma:officer_id" | "village:id"
    t: datetime
    payload: dict
    input_hash: str
    prev_hash: str  # hash chain
    hash: str
