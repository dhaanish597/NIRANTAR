"""In-memory append-only hash-chained event log (BUILD_PLAN.md task 3.6, Phase 0 subset).

Phase 0 needs a *real* hash chain, not a mock, so the audit trail on screen is trustworthy from
day one (BUILD_PLAN.md Phase 0 DoD: "an audit entry is written"). It just isn't backed by
Postgres yet — that's Phase 1+. An in-process list is enough to prove the mechanism now and to
back `GET /api/audit/{alert_id}` (task 3.6) once persistence exists.
"""
from __future__ import annotations

from datetime import datetime

from app.audit.hash_chain import GENESIS_HASH, chain_hash, hash_payload
from app.schemas.audit import AuditEvent


class AuditLog:
    def __init__(self) -> None:
        self._events: list[AuditEvent] = []
        self._last_hash: str = GENESIS_HASH

    @property
    def events(self) -> list[AuditEvent]:
        return list(self._events)

    @property
    def last_hash(self) -> str:
        return self._last_hash

    def append(
        self,
        *,
        event_id: str,
        alert_id: str,
        kind: str,
        actor: str,
        t: datetime,
        payload: dict,
    ) -> AuditEvent:
        input_hash = hash_payload(payload)
        prev_hash = self._last_hash
        event_hash = chain_hash(prev_hash, input_hash, event_id=event_id, kind=kind)
        event = AuditEvent(
            event_id=event_id,
            alert_id=alert_id,
            kind=kind,
            actor=actor,
            t=t,
            payload=payload,
            input_hash=input_hash,
            prev_hash=prev_hash,
            hash=event_hash,
        )
        self._events.append(event)
        self._last_hash = event_hash
        return event

    def for_alert(self, alert_id: str) -> list[AuditEvent]:
        """Backs the future `GET /api/audit/{alert_id}` (task 3.6)."""
        return [e for e in self._events if e.alert_id == alert_id]
