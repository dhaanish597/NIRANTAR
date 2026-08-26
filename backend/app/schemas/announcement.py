"""Announcement contract — the wire shape CLAUDE.md's own Known Gaps section names: "nothing yet
chains an approval to an actual channel send." `POST /api/announcements` (api/announcements.py)
is that chain; this is what it returns, consumed identically by the Government Announce workspace
and the Citizen Announcement tab, and mirrored by hand in frontend/src/types/schemas.ts.
"""
from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel


class ChannelResultSummary(BaseModel):
    channel: str
    recipient_count: int
    delivered_count: int
    acknowledged_count: int


class Announcement(BaseModel):
    id: str
    alert_id: str
    village_id: str
    stage: Literal["GREEN", "YELLOW", "ORANGE", "RED"]
    message: str
    language: str = "en"
    issued_by: str
    issued_at: datetime
    channel_results: list[ChannelResultSummary]
    cap_xml: str
