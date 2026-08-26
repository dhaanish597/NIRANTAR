from __future__ import annotations

from app.api.announcements import AnnouncementRequest, create_announcement, list_announcements
from app.audit.log import AuditLog
from app.schemas.decision import ActionCard


def _sample_card(alert_id: str = "alert-1") -> ActionCard:
    return ActionCard(
        alert_id=alert_id,
        village_id="v1",
        stage="RED",
        headline="Evacuate now",
        reason_plain="Heavy rainfall and slope movement",
        shelter_name="Community Hall",
        route=None,
        roads_to_avoid=[],
        what_to_carry=[],
        contact="108",
        issued_at="2026-01-01T00:00:00+05:30",
        valid_until="2026-01-02T00:00:00+05:30",
        safe_window_hours=None,
        translations={},
        audio_urls={},
    )


def test_create_announcement_sends_through_all_four_channels():
    audit_log = AuditLog()
    body = AnnouncementRequest(action_card=_sample_card(), officer_id="officer-1", recipient_count=1000)
    announcement = create_announcement(body, audit_log=audit_log, announcements=[])
    assert {r.channel for r in announcement.channel_results} == {
        "cell_broadcast",
        "sms",
        "push",
        "mesh",
    }
    assert len(announcement.cap_xml) > 0


def test_create_announcement_records_real_audit_events():
    audit_log = AuditLog()
    body = AnnouncementRequest(action_card=_sample_card(), officer_id="officer-1", recipient_count=10)
    announcement = create_announcement(body, audit_log=audit_log, announcements=[])
    kinds = [e.kind for e in audit_log.for_alert(announcement.alert_id)]
    assert "DDMA_APPROVED" in kinds
    assert "DISSEMINATED" in kinds


def test_create_announcement_does_not_double_approve():
    audit_log = AuditLog()
    card = _sample_card()
    create_announcement(
        AnnouncementRequest(action_card=card, officer_id="o", recipient_count=1),
        audit_log=audit_log,
        announcements=[],
    )
    create_announcement(
        AnnouncementRequest(action_card=card, officer_id="o", recipient_count=1),
        audit_log=audit_log,
        announcements=[],
    )
    approved = [e for e in audit_log.for_alert(card.alert_id) if e.kind == "DDMA_APPROVED"]
    assert len(approved) == 1


def test_create_announcement_defaults_message_to_reason_plain():
    audit_log = AuditLog()
    announcement = create_announcement(
        AnnouncementRequest(action_card=_sample_card(), officer_id="o", recipient_count=1),
        audit_log=audit_log,
        announcements=[],
    )
    assert announcement.message == "Heavy rainfall and slope movement"


def test_list_announcements_returns_newest_first():
    announcements: list = []
    audit_log = AuditLog()
    create_announcement(
        AnnouncementRequest(action_card=_sample_card("a1"), officer_id="o", recipient_count=1),
        audit_log=audit_log,
        announcements=announcements,
    )
    create_announcement(
        AnnouncementRequest(action_card=_sample_card("a2"), officer_id="o", recipient_count=1),
        audit_log=audit_log,
        announcements=announcements,
    )
    result = list_announcements(announcements)
    assert [a.alert_id for a in result] == ["a2", "a1"]
