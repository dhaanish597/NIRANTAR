"""api/announcements.py — the real dissemination trigger CLAUDE.md's Known Gaps section names:
"nothing yet chains an approval to an actual channel send." `create_announcement()` is that
chain: approve (if not already decided), send through every real simulated channel, record the
real DISSEMINATED audit event, build the real CAP 1.2 XML, and return the result.
`backend/app/api/routes.py` wires the two thin REST handlers that call into this module — the
same split `api/whatif.py`/`routes.py` already establish.
"""
from __future__ import annotations

from pydantic import BaseModel, Field

from app.audit.log import AuditLog
from app.audit.producers import record_ddma_decision, record_dissemination
from app.core.clock import LiveClock
from app.dissemination.cap import build_cap_alert
from app.dissemination.channels import CellBroadcastChannel, Channel, MeshChannel, PushChannel, SmsChannel
from app.schemas.announcement import Announcement, ChannelResultSummary
from app.schemas.decision import ActionCard

CHANNELS: list[Channel] = [CellBroadcastChannel(), SmsChannel(), PushChannel(), MeshChannel()]


class AnnouncementRequest(BaseModel):
    action_card: ActionCard
    officer_id: str
    recipient_count: int = Field(ge=0)
    message: str | None = None
    language: str = "en"


def create_announcement(
    body: AnnouncementRequest, *, audit_log: AuditLog, announcements: list[Announcement]
) -> Announcement:
    t = LiveClock().now()
    card = body.action_card

    already_decided = any(
        event.kind in ("DDMA_APPROVED", "STOOD_DOWN")
        for event in audit_log.for_alert(card.alert_id)
    )
    if not already_decided:
        record_ddma_decision(
            audit_log,
            action_card=card,
            officer_id=body.officer_id,
            t=t,
            decision="approved",
            notes="Approved via Announce workspace",
        )

    channel_results = [
        channel.send(card, recipient_count=body.recipient_count) for channel in CHANNELS
    ]
    record_dissemination(audit_log, action_card=card, channel_results=channel_results, t=t)
    cap_xml = build_cap_alert(card)

    announcement = Announcement(
        id=f"ann-{card.alert_id}-{t.isoformat()}",
        alert_id=card.alert_id,
        village_id=card.village_id,
        stage=card.stage,
        message=body.message or card.reason_plain,
        language=body.language,
        issued_by=body.officer_id,
        issued_at=t,
        channel_results=[
            ChannelResultSummary(
                channel=result.channel,
                recipient_count=result.recipient_count,
                delivered_count=result.delivered_count,
                acknowledged_count=result.acknowledged_count,
            )
            for result in channel_results
        ],
        cap_xml=cap_xml.decode("utf-8"),
    )
    announcements.append(announcement)
    return announcement


def list_announcements(announcements: list[Announcement]) -> list[Announcement]:
    return list(reversed(announcements))
