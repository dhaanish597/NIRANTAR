"""Contract test for audit/hash_chain.py and audit/log.py."""
from __future__ import annotations

from datetime import datetime, timezone

from app.audit.hash_chain import GENESIS_HASH, chain_hash, hash_payload
from app.audit.log import AuditLog

T = datetime(2025, 1, 1, tzinfo=timezone.utc)


def test_hash_payload_is_deterministic_regardless_of_key_order():
    a = hash_payload({"x": 1, "y": 2})
    b = hash_payload({"y": 2, "x": 1})
    assert a == b


def test_hash_payload_differs_for_different_payloads():
    assert hash_payload({"x": 1}) != hash_payload({"x": 2})


def test_chain_hash_is_deterministic():
    h1 = chain_hash("prev", "input", event_id="e1", kind="AI_FLAGGED")
    h2 = chain_hash("prev", "input", event_id="e1", kind="AI_FLAGGED")
    assert h1 == h2


def test_chain_hash_changes_if_prev_hash_changes():
    h1 = chain_hash("prev-a", "input", event_id="e1", kind="AI_FLAGGED")
    h2 = chain_hash("prev-b", "input", event_id="e1", kind="AI_FLAGGED")
    assert h1 != h2


class TestAuditLog:
    def test_first_event_chains_from_genesis(self):
        log = AuditLog()
        event = log.append(
            event_id="e1", alert_id="a1", kind="AI_FLAGGED", actor="system", t=T, payload={"x": 1}
        )
        assert event.prev_hash == GENESIS_HASH
        assert log.last_hash == event.hash

    def test_second_event_chains_from_first(self):
        log = AuditLog()
        e1 = log.append(
            event_id="e1", alert_id="a1", kind="AI_FLAGGED", actor="system", t=T, payload={"x": 1}
        )
        e2 = log.append(
            event_id="e2", alert_id="a1", kind="DDMA_APPROVED", actor="ddma:1", t=T, payload={"x": 2}
        )
        assert e2.prev_hash == e1.hash
        assert e1.hash != e2.hash

    def test_events_property_returns_a_copy(self):
        log = AuditLog()
        log.append(event_id="e1", alert_id="a1", kind="AI_FLAGGED", actor="system", t=T, payload={})
        events = log.events
        events.append("not a real event")  # mutating the returned list...
        assert len(log.events) == 1  # ...must not affect the log's internal state

    def test_for_alert_filters_by_alert_id(self):
        log = AuditLog()
        log.append(event_id="e1", alert_id="a1", kind="AI_FLAGGED", actor="system", t=T, payload={})
        log.append(event_id="e2", alert_id="a2", kind="AI_FLAGGED", actor="system", t=T, payload={})
        log.append(event_id="e3", alert_id="a1", kind="ESCALATED", actor="system", t=T, payload={})
        assert [e.event_id for e in log.for_alert("a1")] == ["e1", "e3"]

    def test_full_chain_is_internally_consistent(self):
        log = AuditLog()
        for i in range(5):
            log.append(
                event_id=f"e{i}", alert_id="a1", kind="AI_FLAGGED", actor="system", t=T,
                payload={"i": i},
            )
        events = log.events
        prev = GENESIS_HASH
        for event in events:
            assert event.prev_hash == prev
            expected_hash = chain_hash(
                event.prev_hash, event.input_hash, event_id=event.event_id, kind=event.kind
            )
            assert event.hash == expected_hash
            prev = event.hash
