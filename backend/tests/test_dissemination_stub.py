"""Contract test for dissemination/stub.py."""
from __future__ import annotations

from datetime import datetime, timezone

from app.dissemination.stub import disseminate
from app.schemas.decision import ActionCard


def make_card(alert_id: str) -> ActionCard:
    t = datetime(2025, 1, 1, tzinfo=timezone.utc)
    return ActionCard(
        alert_id=alert_id, village_id="v1", stage="RED", headline="x", reason_plain="x",
        shelter_name="x", route=None, roads_to_avoid=[], what_to_carry=[], contact="x",
        issued_at=t, valid_until=t, safe_window_hours=None, translations={}, audio_urls={},
    )


def test_disseminate_is_an_identity_pass_through():
    cards = [make_card("a"), make_card("b")]
    assert disseminate(cards) == cards


def test_disseminate_of_empty_list_is_empty():
    assert disseminate([]) == []
