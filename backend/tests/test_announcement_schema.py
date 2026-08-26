from __future__ import annotations

from app.schemas.announcement import Announcement, ChannelResultSummary


def test_announcement_round_trips_through_json():
    announcement = Announcement(
        id="ann-1",
        alert_id="alert-1",
        village_id="v1",
        stage="RED",
        message="Evacuate now",
        language="en",
        issued_by="officer-1",
        issued_at="2026-01-01T00:00:00+05:30",
        channel_results=[
            ChannelResultSummary(
                channel="sms", recipient_count=100, delivered_count=90, acknowledged_count=40
            )
        ],
        cap_xml="<alert></alert>",
    )
    restored = Announcement.model_validate_json(announcement.model_dump_json())
    assert restored == announcement
