"""The pipeline orchestrator (BUILD_PLAN.md task 0.10).

frame → risk → impact → decision → dissemination → audit, each stage a pure function over
schemas (docs/ARCHITECTURE.md §2). Phase 0: every stage past risk/ is a deterministic stub (see
risk/stub.py, impact/stub.py, decision/stub.py, dissemination/stub.py) — the pipe is real, the
water is fake. This file itself must never check `if mode == REPLAY` (CLAUDE.md §2) — `mode` and
`scenario_id` are passed in only to be stamped onto the outgoing TickResult, not branched on.
"""
from __future__ import annotations

from app.audit.log import AuditLog
from app.decision.stub import compute_action_cards
from app.dissemination.stub import disseminate
from app.impact.stub import compute_impact
from app.risk.stub import compute_cell_risks
from app.schemas.ingest import ObservationFrame
from app.schemas.mode import RunMode
from app.schemas.tick import TickResult


class Pipeline:
    """Holds the one piece of state the stage functions themselves can't own: the audit hash
    chain, which must thread its `prev_hash` from one tick to the next."""

    def __init__(self, *, audit_log: AuditLog | None = None):
        self.audit_log = audit_log or AuditLog()

    def process(
        self, frame: ObservationFrame, *, mode: RunMode, scenario_id: str | None = None
    ) -> TickResult:
        cell_risks = compute_cell_risks(frame)
        # RunoutEnvelope (first return value) has no field on TickResult yet — see the NOTE in
        # impact/stub.py. Computed for completeness; not broadcast in Phase 0.
        _envelopes, road_risks, isolations, priorities = compute_impact(cell_risks)
        action_cards = compute_action_cards(frame.t, priorities)
        action_cards = disseminate(action_cards)

        # Deterministic, not uuid4() — CLAUDE.md rule 13 bans unseeded randomness anywhere in
        # the pipeline, precisely so two replays of the same scenario are byte-identical.
        audit_event = self.audit_log.append(
            event_id=f"evt-{frame.aoi_id}-{frame.t.isoformat()}",
            alert_id=f"tick-{frame.aoi_id}-{frame.t.isoformat()}",
            kind="AI_FLAGGED",
            actor="system",
            t=frame.t,
            payload={
                "aoi_id": frame.aoi_id,
                "cell_count": len(frame.cells),
                "max_p_fail": max((r.p_fail for r in cell_risks), default=0.0),
                "action_cards_issued": len(action_cards),
            },
        )

        return TickResult(
            t=frame.t,
            mode=mode,
            scenario_id=scenario_id,
            aoi_id=frame.aoi_id,
            cell_risks=cell_risks,
            road_risks=road_risks,
            isolations=isolations,
            priorities=priorities,
            new_action_cards=action_cards,
            new_audit_events=[audit_event],
            is_reconstructed=any(c.is_reconstructed for c in frame.cells),
        )
