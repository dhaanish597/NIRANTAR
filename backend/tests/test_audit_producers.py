"""Contract test for audit/producers.py (BUILD_PLAN.md task 3.6(a))."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from app.audit.hash_chain import GENESIS_HASH, chain_hash
from app.audit.log import AuditLog
from app.audit.producers import (
    record_ddma_decision,
    record_dissemination,
    record_village_acknowledged,
)
from app.dissemination.channels import CellBroadcastChannel, SmsChannel
from app.schemas.decision import ActionCard

T = datetime(2026, 5, 28, 3, 20, tzinfo=timezone.utc)


def make_card(alert_id="alert-v1-1") -> ActionCard:
    return ActionCard(
        alert_id=alert_id,
        village_id="v1",
        stage="RED",
        headline="Evacuate Now",
        reason_plain="test reason",
        shelter_name="Test Shelter",
        route=None,
        roads_to_avoid=["NH6"],
        what_to_carry=["ID"],
        contact="placeholder",
        issued_at=T,
        valid_until=T + timedelta(hours=6),
        safe_window_hours=(0.0, 1.0),
        translations={},
        audio_urls={},
    )


class TestRecordDdmaDecision:
    def test_approved_appends_ddma_approved_event(self):
        log = AuditLog()
        card = make_card()
        event = record_ddma_decision(log, action_card=card, officer_id="officer_42", t=T, decision="approved")
        assert event.kind == "DDMA_APPROVED"
        assert event.alert_id == card.alert_id
        assert event.actor == "ddma:officer_42"
        assert log.for_alert(card.alert_id) == [event]

    def test_modified_also_appends_ddma_approved_with_notes_recorded(self):
        log = AuditLog()
        card = make_card()
        event = record_ddma_decision(
            log, action_card=card, officer_id="officer_1", t=T, decision="modified",
            notes="changed shelter to a closer one",
        )
        assert event.kind == "DDMA_APPROVED"
        assert event.payload["decision"] == "modified"
        assert event.payload["notes"] == "changed shelter to a closer one"

    def test_rejected_appends_stood_down_not_ddma_approved(self):
        log = AuditLog()
        card = make_card()
        event = record_ddma_decision(log, action_card=card, officer_id="officer_2", t=T, decision="rejected")
        assert event.kind == "STOOD_DOWN"

    def test_actor_is_human_not_system(self):
        log = AuditLog()
        card = make_card()
        event = record_ddma_decision(log, action_card=card, officer_id="officer_9", t=T)
        assert event.actor.startswith("ddma:")
        assert event.actor != "system"

    def test_payload_captures_what_was_approved(self):
        log = AuditLog()
        card = make_card()
        event = record_ddma_decision(log, action_card=card, officer_id="officer_1", t=T)
        assert event.payload["village_id"] == "v1"
        assert event.payload["stage"] == "RED"

    def test_hash_chains_from_genesis_for_first_event(self):
        log = AuditLog()
        card = make_card()
        event = record_ddma_decision(log, action_card=card, officer_id="officer_1", t=T)
        assert event.prev_hash == GENESIS_HASH
        expected = chain_hash(GENESIS_HASH, event.input_hash, event_id=event.event_id, kind=event.kind)
        assert event.hash == expected

    def test_deterministic_given_same_inputs(self):
        card = make_card()
        log_a = AuditLog()
        log_b = AuditLog()
        event_a = record_ddma_decision(log_a, action_card=card, officer_id="officer_1", t=T)
        event_b = record_ddma_decision(log_b, action_card=card, officer_id="officer_1", t=T)
        assert event_a.hash == event_b.hash
        assert event_a.event_id == event_b.event_id


class TestRecordDissemination:
    def test_appends_disseminated_event_with_system_actor(self):
        log = AuditLog()
        card = make_card()
        results = [CellBroadcastChannel().send(card, recipient_count=100)]
        event = record_dissemination(log, action_card=card, channel_results=results, t=T)
        assert event.kind == "DISSEMINATED"
        assert event.actor == "system"
        assert event.alert_id == card.alert_id

    def test_payload_totals_match_the_real_channel_send_results(self):
        log = AuditLog()
        card = make_card()
        cell = CellBroadcastChannel().send(card, recipient_count=1000)
        sms = SmsChannel().send(card, recipient_count=20)
        event = record_dissemination(log, action_card=card, channel_results=[cell, sms], t=T)

        assert event.payload["total_recipients"] == 1020
        assert event.payload["total_delivered"] == cell.delivered_count + sms.delivered_count
        assert event.payload["total_acknowledged"] == cell.acknowledged_count + sms.acknowledged_count
        assert set(event.payload["channels"]) == {"cell_broadcast", "sms"}
        assert event.payload["per_channel"]["cell_broadcast"]["recipient_count"] == 1000

    def test_no_channels_used_produces_zero_totals_not_an_error(self):
        log = AuditLog()
        card = make_card()
        event = record_dissemination(log, action_card=card, channel_results=[], t=T)
        assert event.payload["total_recipients"] == 0
        assert event.payload["channels"] == []

    def test_deterministic_given_the_same_seeded_channel_results(self):
        card = make_card()
        results_a = [CellBroadcastChannel().send(card, recipient_count=500)]
        results_b = [CellBroadcastChannel().send(card, recipient_count=500)]
        log_a, log_b = AuditLog(), AuditLog()
        event_a = record_dissemination(log_a, action_card=card, channel_results=results_a, t=T)
        event_b = record_dissemination(log_b, action_card=card, channel_results=results_b, t=T)
        assert event_a.hash == event_b.hash


class TestRecordVillageAcknowledged:
    def test_appends_village_acknowledged_event(self):
        log = AuditLog()
        event = record_village_acknowledged(log, alert_id="alert-v1-1", village_id="v1", t=T)
        assert event.kind == "VILLAGE_ACKNOWLEDGED"
        assert event.alert_id == "alert-v1-1"
        assert log.for_alert("alert-v1-1") == [event]

    def test_actor_is_village_not_system_or_ddma(self):
        log = AuditLog()
        event = record_village_acknowledged(log, alert_id="alert-v1-1", village_id="v1", t=T)
        assert event.actor == "village:v1"

    def test_payload_records_village_id(self):
        log = AuditLog()
        event = record_village_acknowledged(log, alert_id="alert-v1-1", village_id="v1", t=T)
        assert event.payload["village_id"] == "v1"

    def test_hash_chains_from_genesis_for_first_event(self):
        log = AuditLog()
        event = record_village_acknowledged(log, alert_id="alert-v1-1", village_id="v1", t=T)
        assert event.prev_hash == GENESIS_HASH
        expected = chain_hash(GENESIS_HASH, event.input_hash, event_id=event.event_id, kind=event.kind)
        assert event.hash == expected

    def test_deterministic_given_same_inputs(self):
        log_a, log_b = AuditLog(), AuditLog()
        event_a = record_village_acknowledged(log_a, alert_id="alert-v1-1", village_id="v1", t=T)
        event_b = record_village_acknowledged(log_b, alert_id="alert-v1-1", village_id="v1", t=T)
        assert event_a.hash == event_b.hash
        assert event_a.event_id == event_b.event_id


class TestFullChainAcrossProducers:
    """Proves ESCALATED (decision/escalation.py) + DDMA_APPROVED + DISSEMINATED all chain
    correctly into ONE shared AuditLog, exactly the "full event chain" GET /api/audit/{alert_id}
    (task 3.6(b)) is meant to expose."""

    def test_escalated_ddma_approved_and_disseminated_share_one_consistent_hash_chain(self):
        from app.decision.escalation import EscalationStateMachine

        log = AuditLog()
        escalation = EscalationStateMachine(audit_log=log)
        card = make_card(alert_id="esc-v1")  # matches escalation.py's alert_id convention

        transition = escalation.observe("v1", 0.9, T)
        assert transition is not None

        approval_event = record_ddma_decision(
            log, action_card=card, officer_id="officer_1", t=T + timedelta(minutes=5)
        )
        results = [CellBroadcastChannel().send(card, recipient_count=50)]
        dissem_event = record_dissemination(
            log, action_card=card, channel_results=results, t=T + timedelta(minutes=6)
        )

        events = log.events
        assert [e.kind for e in events] == ["ESCALATED", "DDMA_APPROVED", "DISSEMINATED"]
        # Full-log hash chain is internally consistent end to end, regardless of which producer
        # function appended which event.
        prev = GENESIS_HASH
        for event in events:
            assert event.prev_hash == prev
            prev = event.hash

        alert_chain = log.for_alert("esc-v1")
        assert [e.kind for e in alert_chain] == ["ESCALATED", "DDMA_APPROVED", "DISSEMINATED"]
        assert approval_event in alert_chain
        assert dissem_event in alert_chain

    def test_full_chain_including_village_acknowledged_is_the_complete_glossary_sequence(self):
        """CLAUDE.md's audit-trail glossary entry: AI Flagged -> DDMA Approved -> Disseminated ->
        Village Acknowledged. AI_FLAGGED itself is produced by pipeline.py (not exercised here,
        same as the test above) — this proves the three producer-function-driven events plus the
        task-3.10 VILLAGE_ACKNOWLEDGED event chain together correctly."""
        log = AuditLog()
        card = make_card(alert_id="alert-v1-full")

        approval_event = record_ddma_decision(log, action_card=card, officer_id="officer_1", t=T)
        results = [CellBroadcastChannel().send(card, recipient_count=10)]
        dissem_event = record_dissemination(
            log, action_card=card, channel_results=results, t=T + timedelta(minutes=1)
        )
        ack_event = record_village_acknowledged(
            log, alert_id=card.alert_id, village_id=card.village_id, t=T + timedelta(minutes=10)
        )

        alert_chain = log.for_alert("alert-v1-full")
        assert [e.kind for e in alert_chain] == ["DDMA_APPROVED", "DISSEMINATED", "VILLAGE_ACKNOWLEDGED"]
        prev = GENESIS_HASH
        for event in alert_chain:
            assert event.prev_hash == prev
            prev = event.hash
        assert approval_event in alert_chain
        assert dissem_event in alert_chain
        assert ack_event in alert_chain
