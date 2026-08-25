"""Contract test for decision/stub.py."""
from __future__ import annotations

from datetime import datetime, timezone

from app.decision.stub import compute_action_cards, escalation_stage
from app.schemas.impact import SettlementPriority

T = datetime(2025, 1, 1, tzinfo=timezone.utc)


def make_priority(eps: float, village_id: str = "v1", tier: str = "P2") -> SettlementPriority:
    return SettlementPriority(village_id=village_id, eps=eps, tier=tier, components={})


def test_escalation_stage_boundaries():
    assert escalation_stage(0.0) == "GREEN"
    assert escalation_stage(0.24) == "GREEN"
    assert escalation_stage(0.25) == "YELLOW"
    assert escalation_stage(0.49) == "YELLOW"
    assert escalation_stage(0.5) == "ORANGE"
    assert escalation_stage(0.74) == "ORANGE"
    assert escalation_stage(0.75) == "RED"
    assert escalation_stage(1.0) == "RED"


def test_no_card_below_orange():
    assert compute_action_cards(T, [make_priority(0.1)]) == []
    assert compute_action_cards(T, [make_priority(0.4)]) == []


def test_card_issued_at_orange_and_red():
    orange_cards = compute_action_cards(T, [make_priority(0.6)])
    red_cards = compute_action_cards(T, [make_priority(0.9)])
    assert len(orange_cards) == 1 and orange_cards[0].stage == "ORANGE"
    assert len(red_cards) == 1 and red_cards[0].stage == "RED"


def test_safe_window_is_always_a_range_never_a_point():
    card = compute_action_cards(T, [make_priority(0.9)])[0]
    assert isinstance(card.safe_window_hours, tuple)
    assert len(card.safe_window_hours) == 2


def test_card_valid_until_is_after_issued_at():
    card = compute_action_cards(T, [make_priority(0.9)])[0]
    assert card.valid_until > card.issued_at


def test_one_card_per_alert_worthy_priority():
    cards = compute_action_cards(T, [make_priority(0.6, "v1"), make_priority(0.8, "v2")])
    assert len(cards) == 2
