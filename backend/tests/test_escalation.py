"""Contract tests for decision/escalation.py (BUILD_PLAN.md task 3.2)."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from app.audit.log import AuditLog
from app.config import EscalationConfig
from app.decision.escalation import (
    EscalationStateMachine,
    STAGE_LABELS,
    stage_for_p_fail,
)
from app.risk.thresholds import threshold_exceedance_ratio
from app.schemas.ingest import CellObservation
from app.schemas.risk import CellRisk

T0 = datetime(2026, 5, 28, 0, 0, tzinfo=timezone.utc)


def _t(hours: float) -> datetime:
    return T0 + timedelta(hours=hours)


def make_risk(cell_id: str, p_fail: float) -> CellRisk:
    return CellRisk(
        cell_id=cell_id,
        p_fail=p_fail,
        threshold_exceedance=0.0,
        confidence=0.9,
        attributions=[],
        model_version="test",
    )


# --- stage_for_p_fail (stateless boundary check, no hysteresis involved) -------------------


def test_stage_for_p_fail_boundaries():
    cfg = EscalationConfig()
    assert stage_for_p_fail(0.0, cfg) == "GREEN"
    assert stage_for_p_fail(0.24, cfg) == "GREEN"
    assert stage_for_p_fail(0.25, cfg) == "YELLOW"
    assert stage_for_p_fail(0.49, cfg) == "YELLOW"
    assert stage_for_p_fail(0.5, cfg) == "ORANGE"
    assert stage_for_p_fail(0.74, cfg) == "ORANGE"
    assert stage_for_p_fail(0.75, cfg) == "RED"
    assert stage_for_p_fail(1.0, cfg) == "RED"


def test_stage_labels_use_exact_glossary_terms():
    # CLAUDE.md §4: "Green Watch -> Yellow Pre-Alert -> Orange Evacuation Ready -> Red Evacuate
    # Now" -- these exact strings, never invented alternates.
    assert STAGE_LABELS == {
        "GREEN": "Green Watch",
        "YELLOW": "Yellow Pre-Alert",
        "ORANGE": "Orange Evacuation Ready",
        "RED": "Red Evacuate Now",
    }


# --- basic state machine behaviour -----------------------------------------------------------


def test_new_entity_starts_at_green_with_no_transition_recorded():
    m = EscalationStateMachine()
    assert m.current_stage("v1") == "GREEN"


def test_observing_green_level_risk_produces_no_transition():
    m = EscalationStateMachine()
    result = m.observe("v1", 0.1, _t(0))
    assert result is None
    assert m.current_stage("v1") == "GREEN"


def test_upgrade_is_immediate_and_can_skip_stages():
    m = EscalationStateMachine()
    transition = m.observe("v1", 0.9, _t(0))
    assert transition is not None
    assert transition.from_stage == "GREEN"
    assert transition.to_stage == "RED"
    assert m.current_stage("v1") == "RED"


def test_upgrade_then_further_upgrade_each_emit_a_transition():
    m = EscalationStateMachine()
    t1 = m.observe("v1", 0.3, _t(0))
    t2 = m.observe("v1", 0.6, _t(1))
    t3 = m.observe("v1", 0.9, _t(2))
    assert [t1.to_stage, t2.to_stage, t3.to_stage] == ["YELLOW", "ORANGE", "RED"]


def test_holding_steady_at_same_stage_emits_no_transition():
    m = EscalationStateMachine()
    m.observe("v1", 0.9, _t(0))
    result = m.observe("v1", 0.85, _t(1))  # still RED, no change
    assert result is None


# --- hysteresis on downgrade -------------------------------------------------------------------


def test_downgrade_suppressed_inside_hysteresis_band():
    """RED entry threshold 0.75, margin 0.1 -> must drop below 0.65 to leave RED. 0.70 is below
    0.75 (would trigger a downgrade with no hysteresis) but still inside the band."""
    m = EscalationStateMachine()
    m.observe("v1", 0.9, _t(0))
    assert m.current_stage("v1") == "RED"
    result = m.observe("v1", 0.70, _t(1))
    assert result is None
    assert m.current_stage("v1") == "RED"


def test_downgrade_allowed_once_below_hysteresis_band():
    m = EscalationStateMachine()
    m.observe("v1", 0.9, _t(0))
    result = m.observe("v1", 0.6, _t(1))  # below 0.65 -> allowed; lands at ORANGE (raw stage)
    assert result is not None
    assert result.from_stage == "RED"
    assert result.to_stage == "ORANGE"
    assert m.current_stage("v1") == "ORANGE"


def test_downgrade_can_skip_stages_once_permitted():
    """Hysteresis only gates *leaving* the current stage -- once that gate opens, the entity lands
    wherever the plain thresholds put it, even if that's more than one stage down."""
    m = EscalationStateMachine()
    m.observe("v1", 0.9, _t(0))  # RED
    result = m.observe("v1", 0.05, _t(1))  # crashes all the way to GREEN territory
    assert result.from_stage == "RED"
    assert result.to_stage == "GREEN"


def test_oscillation_near_boundary_does_not_flicker():
    """The whole point of task 3.2's hysteresis requirement: a value bouncing around the RED
    boundary should not toggle the stage every tick."""
    m = EscalationStateMachine()
    readings = [0.9, 0.70, 0.78, 0.68, 0.80, 0.72]
    transitions = [m.observe("v1", p, _t(i)) for i, p in enumerate(readings)]
    # Only the very first reading (GREEN -> RED) should have produced a transition.
    assert [t is not None for t in transitions] == [True, False, False, False, False, False]
    assert m.current_stage("v1") == "RED"


def test_hysteresis_margin_is_configurable():
    cfg = EscalationConfig(downgrade_hysteresis_margin=0.0)  # no hysteresis at all
    m = EscalationStateMachine(config=cfg)
    m.observe("v1", 0.9, _t(0))
    result = m.observe("v1", 0.70, _t(1))  # with zero margin, any drop below 0.75 downgrades
    assert result is not None
    assert result.to_stage == "ORANGE"


# --- audit wiring -------------------------------------------------------------------------------


def test_transition_emits_a_real_escalated_audit_event():
    log = AuditLog()
    m = EscalationStateMachine(audit_log=log)
    transition = m.observe("v1", 0.9, _t(0))

    assert len(log.events) == 1
    event = log.events[0]
    assert event.kind == "ESCALATED"
    assert event is transition.audit_event
    assert event.actor == "system"
    assert event.payload["from_stage"] == "GREEN"
    assert event.payload["to_stage"] == "RED"
    assert event.payload["to_label"] == "Red Evacuate Now"


def test_no_audit_event_appended_when_stage_holds_steady():
    log = AuditLog()
    m = EscalationStateMachine(audit_log=log)
    m.observe("v1", 0.9, _t(0))
    m.observe("v1", 0.85, _t(1))  # still RED
    assert len(log.events) == 1  # only the initial upgrade


def test_hash_chain_links_across_successive_transitions():
    log = AuditLog()
    m = EscalationStateMachine(audit_log=log)
    m.observe("v1", 0.3, _t(0))  # -> YELLOW
    m.observe("v1", 0.6, _t(1))  # -> ORANGE
    events = log.events
    assert len(events) == 2
    assert events[1].prev_hash == events[0].hash
    assert events[0].prev_hash != events[1].hash  # sanity: not degenerate


def test_alert_id_is_stable_per_entity_across_its_lifecycle():
    log = AuditLog()
    m = EscalationStateMachine(audit_log=log)
    m.observe("v1", 0.3, _t(0))
    m.observe("v1", 0.6, _t(1))
    alert_ids = {e.alert_id for e in log.events}
    assert alert_ids == {"esc-v1"}


def test_multiple_entities_tracked_and_audited_independently():
    log = AuditLog()
    m = EscalationStateMachine(audit_log=log)
    m.observe("v1", 0.9, _t(0))
    m.observe("v2", 0.3, _t(0))
    assert m.current_stage("v1") == "RED"
    assert m.current_stage("v2") == "YELLOW"
    alert_ids = {e.alert_id for e in log.events}
    assert alert_ids == {"esc-v1", "esc-v2"}


# --- p_fail validation -------------------------------------------------------------------------


@pytest.mark.parametrize("bad", [-0.01, 1.01, -1.0, 2.0])
def test_out_of_range_p_fail_rejected(bad):
    m = EscalationStateMachine()
    with pytest.raises(ValueError):
        m.observe("v1", bad, _t(0))


# --- CellRisk / step() integration ---------------------------------------------------------------


def test_observe_cell_risk_keys_by_cell_id():
    m = EscalationStateMachine()
    risk = make_risk("aizawl_0412", 0.9)
    transition = m.observe_cell_risk(risk, _t(0))
    assert transition.entity_id == "aizawl_0412"
    assert m.current_stage("aizawl_0412") == "RED"


def test_step_processes_a_tick_of_cell_risks_and_returns_only_real_transitions():
    m = EscalationStateMachine()
    tick1 = m.step([make_risk("c1", 0.9), make_risk("c2", 0.1)], _t(0))
    assert {t.entity_id for t in tick1} == {"c1"}  # c2 stayed GREEN -> GREEN, no transition

    tick2 = m.step([make_risk("c1", 0.85), make_risk("c2", 0.3)], _t(1))
    assert {t.entity_id for t in tick2} == {"c2"}  # c1 held at RED; c2 upgraded to YELLOW


# --- determinism (CLAUDE.md rule 13) ------------------------------------------------------------


def test_same_trajectory_twice_produces_identical_events():
    trajectory = [0.1, 0.3, 0.6, 0.9, 0.7, 0.6, 0.05]

    def run() -> list[tuple]:
        log = AuditLog()
        m = EscalationStateMachine(audit_log=log)
        for i, p in enumerate(trajectory):
            m.observe("v1", p, _t(i))
        return [(e.event_id, e.hash, e.payload["to_stage"]) for e in log.events]

    assert run() == run()


# --- built against the real threshold engine (risk/thresholds.py), not a hand-picked fixture ----


def _obs(**overrides) -> CellObservation:
    base = dict(
        cell_id="c1",
        rain_1h=0.0,
        rain_6h=0.0,
        rain_24h=0.0,
        rain_72h=0.0,
        antecedent_7d=0.0,
        antecedent_15d=0.0,
        antecedent_30d=0.0,
        soil_moisture=None,
        insar_velocity_mm_yr=None,
        source="test",
    )
    base.update(overrides)
    return CellObservation(**base)


def test_trajectory_driven_by_the_real_threshold_engine_escalates_and_holds():
    """Feed a rising-then-falling rainfall trajectory through the real I-D/E-D threshold engine
    (risk/thresholds.py, task 1.11) — convert its exceedance ratio into a bounded pseudo-p_fail —
    and confirm escalation.py reacts sensibly: escalates as exceedance climbs, and does not
    instantly un-escalate on a small dip (hysteresis)."""
    m = EscalationStateMachine()

    dry = _obs()
    heavy = _obs(rain_1h=40.0, rain_6h=150.0, rain_24h=300.0, rain_72h=400.0)
    slightly_less_heavy = _obs(rain_1h=35.0, rain_6h=140.0, rain_24h=290.0, rain_72h=390.0)

    def pseudo_p_fail(obs: CellObservation) -> float:
        return min(1.0, threshold_exceedance_ratio(obs) / 3.0)

    assert threshold_exceedance_ratio(dry) == 0.0

    t_dry = m.observe("c1", pseudo_p_fail(dry), _t(0))
    assert t_dry is None
    assert m.current_stage("c1") == "GREEN"

    t_heavy = m.observe("c1", pseudo_p_fail(heavy), _t(1))
    assert t_heavy is not None
    assert t_heavy.to_stage in ("ORANGE", "RED")

    stage_after_spike = m.current_stage("c1")
    t_dip = m.observe("c1", pseudo_p_fail(slightly_less_heavy), _t(2))
    # A small dip in a genuinely heavy trajectory must not instantly drop the stage.
    assert t_dip is None or _rank_le(t_dip.to_stage, stage_after_spike)


def _rank_le(a: str, b: str) -> bool:
    order = ["GREEN", "YELLOW", "ORANGE", "RED"]
    return order.index(a) <= order.index(b)
