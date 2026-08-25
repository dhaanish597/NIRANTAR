"""decision/escalation.py — the Green Watch -> Yellow Pre-Alert -> Orange Evacuation Ready ->
Red Evacuate Now state machine (BUILD_PLAN.md task 3.2, CLAUDE.md §4 domain glossary — use these
exact stage names, never invent alternates).

This module takes a `p_fail` trajectory (one value per tick, per entity — an entity is whatever
the caller keys risk by; BUILD_PLAN.md task 3.2 says "off a CellRisk/p_fail trajectory input", so
the natural key is `CellRisk.cell_id`, but `observe()` accepts any string key) and turns it into
stage transitions. It is a pure state machine over risk values: it does not import risk/model.py
or risk/thresholds.py, and it does not know or care whether `p_fail` came from the Phase 0 stub,
the real XGBoost model, or a synthetic test trajectory (docs/ARCHITECTURE.md §1 — nothing below
`risk/` branches on where a number came from, and this module does not even branch on *that*: it
just consumes floats).

--- Hysteresis choice (documented per BUILD_PLAN.md task 3.2's explicit requirement) ---

Upgrades are immediate and may skip stages: a p_fail spike from 0.1 straight to 0.9 fires RED the
same tick. We never delay escalating a genuine risk increase — a missed few minutes of lead time
costs more than an unnecessary yellow flicker, and CLAUDE.md's whole thesis is about lead time.

Downgrades use a hysteresis band: leaving a stage requires p_fail to fall not merely below that
stage's own entry threshold, but below (entry_threshold - downgrade_hysteresis_margin). Concretely,
with the config defaults (thresholds 0.25/0.5/0.75, margin 0.1): once at RED (entered at >= 0.75),
p_fail has to drop below 0.65 — not just below 0.75 — before the stage is allowed to drop. A value
oscillating between 0.70 and 0.80 around the RED boundary therefore stays latched at RED instead
of flapping RED/ORANGE every tick, which is what "so it doesn't flicker" (BUILD_PLAN.md task 3.2)
means in practice: a village-facing "Evacuate Now" card should not flip to "stand down" and back
on a single noisy rainfall reading.

The margin (0.1) is a full stage-width's worth of headroom smaller than the gap between adjacent
thresholds (0.25), chosen so it clearly suppresses boundary noise without requiring risk to nearly
halve before we ever downgrade. It is an engineering default, not a cited figure — tunable via
`config.EscalationConfig.downgrade_hysteresis_margin` (CLAUDE.md §4: thresholds must be tunable,
not hidden constants), and a candidate for the Phase 5 false-alarm-cost slider (BUILD_PLAN.md task
5.6) alongside the three entry thresholds themselves.

If a downgrade *is* allowed, it lands wherever the plain (non-hysteresis) thresholds say p_fail
now sits — so a genuine crash in risk (e.g. rain stops entirely) can drop more than one stage in a
single tick. Hysteresis exists to suppress boundary noise, not to slow-walk a real recovery.

--- Audit wiring ---

Every transition (up or down) emits one `AuditEvent` of kind `ESCALATED` via the existing
`audit/hash_chain.py` + `audit/log.py` (BUILD_PLAN.md's own framing for this task: "you're wiring
new producers into an existing sink, not building the sink itself"). `alert_id` is held stable as
`f"esc-{entity_id}"` for the entity's whole tracked lifetime, not reissued per transition — this
is what lets a future audit-trail view (BUILD_PLAN.md task 3.8) render one village's GREEN -> ...
-> RED history as a single chained timeline instead of N unrelated alerts.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Literal

from app.audit.log import AuditLog
from app.config import ESCALATION, EscalationConfig
from app.schemas.audit import AuditEvent
from app.schemas.risk import CellRisk

EscalationStage = Literal["GREEN", "YELLOW", "ORANGE", "RED"]

_STAGE_ORDER: tuple[EscalationStage, ...] = ("GREEN", "YELLOW", "ORANGE", "RED")

# Full glossary names (CLAUDE.md §4) for human-facing payloads/UI text. The schema Literal itself
# (ActionCard.stage in schemas/decision.py, and EscalationStage above) stays the short form — that
# is the wire contract other modules already depend on; this dict is purely presentational.
STAGE_LABELS: dict[EscalationStage, str] = {
    "GREEN": "Green Watch",
    "YELLOW": "Yellow Pre-Alert",
    "ORANGE": "Orange Evacuation Ready",
    "RED": "Red Evacuate Now",
}


def _rank(stage: EscalationStage) -> int:
    return _STAGE_ORDER.index(stage)


def stage_for_p_fail(p_fail: float, config: EscalationConfig) -> EscalationStage:
    """The stage implied by p_fail alone, with no memory of history. Used both for immediate
    upgrades and to compute where a *permitted* downgrade lands."""
    if p_fail >= config.red_threshold:
        return "RED"
    if p_fail >= config.orange_threshold:
        return "ORANGE"
    if p_fail >= config.yellow_threshold:
        return "YELLOW"
    return "GREEN"


def _entry_threshold(stage: EscalationStage, config: EscalationConfig) -> float | None:
    """The p_fail value at which `stage` is first entered — None for GREEN, which is the floor
    and therefore has nothing to be hysteresis-gated against."""
    return {
        "RED": config.red_threshold,
        "ORANGE": config.orange_threshold,
        "YELLOW": config.yellow_threshold,
        "GREEN": None,
    }[stage]


@dataclass(frozen=True)
class EscalationTransition:
    """One realized stage change for one entity, plus the audit event it produced."""

    entity_id: str
    t: datetime
    p_fail: float
    from_stage: EscalationStage
    to_stage: EscalationStage
    audit_event: AuditEvent


class EscalationStateMachine:
    """Stateful per-entity Green/Yellow/Orange/Red tracker. One instance tracks arbitrarily many
    entities (villages, cells — whatever key the caller uses), each with independent history.

    Deliberately NOT hard-wired to risk/model.py, impact/priority.py, or any specific producer of
    `p_fail` (BUILD_PLAN.md task 3.2: "test with synthetic/threshold-engine trajectories" — build
    and test this as a pure function/class taking risk values as input). Callers push values in
    via `observe()` / `observe_cell_risk()` / `step()`.
    """

    def __init__(
        self,
        config: EscalationConfig | None = None,
        *,
        audit_log: AuditLog | None = None,
    ) -> None:
        self.config = config or ESCALATION
        self.audit_log = audit_log if audit_log is not None else AuditLog()
        self._stage: dict[str, EscalationStage] = {}

    def current_stage(self, entity_id: str) -> EscalationStage:
        """GREEN if this entity has never been observed — that is the correct default state, not
        a missing-data error."""
        return self._stage.get(entity_id, "GREEN")

    def observe(self, entity_id: str, p_fail: float, t: datetime) -> EscalationTransition | None:
        """Feed one (entity, p_fail, timestamp) reading in. Returns the `EscalationTransition`
        (with its freshly-appended `ESCALATED` audit event) if the stage changed this call, or
        `None` if it held steady — including when a would-be downgrade was suppressed by the
        hysteresis band."""
        if not (0.0 <= p_fail <= 1.0):
            raise ValueError(f"p_fail must be in [0,1], got {p_fail}")

        current = self.current_stage(entity_id)
        raw = stage_for_p_fail(p_fail, self.config)

        if _rank(raw) > _rank(current):
            new_stage = raw  # upgrade: immediate, can skip stages
        elif _rank(raw) < _rank(current):
            threshold = _entry_threshold(current, self.config)
            # threshold is None only for GREEN, which can never be "current" here since raw<current
            # implies current is not the floor stage.
            assert threshold is not None
            if p_fail < threshold - self.config.downgrade_hysteresis_margin:
                new_stage = raw  # far enough below the band: downgrade allowed, lands at `raw`
            else:
                new_stage = current  # inside the hysteresis band: suppressed, no flicker
        else:
            new_stage = current

        self._stage[entity_id] = new_stage

        if new_stage == current:
            return None

        event = self.audit_log.append(
            event_id=f"evt-esc-{entity_id}-{t.isoformat()}",
            alert_id=f"esc-{entity_id}",
            kind="ESCALATED",
            actor="system",
            t=t,
            payload={
                "entity_id": entity_id,
                "p_fail": p_fail,
                "from_stage": current,
                "to_stage": new_stage,
                "from_label": STAGE_LABELS[current],
                "to_label": STAGE_LABELS[new_stage],
            },
        )
        return EscalationTransition(
            entity_id=entity_id,
            t=t,
            p_fail=p_fail,
            from_stage=current,
            to_stage=new_stage,
            audit_event=event,
        )

    def observe_cell_risk(self, risk: CellRisk, t: datetime) -> EscalationTransition | None:
        """Convenience wrapper matching BUILD_PLAN.md task 3.2's literal phrasing ("off a
        CellRisk/p_fail trajectory input") — keys the state machine by `risk.cell_id`."""
        return self.observe(risk.cell_id, risk.p_fail, t)

    def step(self, cell_risks: list[CellRisk], t: datetime) -> list[EscalationTransition]:
        """Process one tick's worth of `CellRisk` values at once. Returns only the transitions
        that actually happened this tick (cells whose stage held steady are omitted) — the shape
        a future pipeline wiring would want to fold into `TickResult.new_audit_events`."""
        transitions = []
        for risk in cell_risks:
            transition = self.observe_cell_risk(risk, t)
            if transition is not None:
                transitions.append(transition)
        return transitions
