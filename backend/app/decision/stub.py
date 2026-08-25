"""Phase 0 decision stub (BUILD_PLAN.md task 0.10). Fixed action card content, no real routing.
Real routing/escalation/action_card logic lands in Phase 3 (BUILD_PLAN.md §Phase 3 —
routing.py, escalation.py, action_card.py) and this file goes away.

The GREEN/YELLOW/ORANGE/RED thresholds below are Phase 0 placeholders, not the tuned,
UI-slider-controlled thresholds CLAUDE.md §4 describes living in config.py — that wiring is a
Phase 5 task (the false-alarm-cost slider). Introducing config.py now for numbers that are
themselves throwaway would just be clutter to clean up later.
"""
from __future__ import annotations

from datetime import datetime, timedelta
from typing import Literal

from app.schemas.decision import ActionCard
from app.schemas.impact import SettlementPriority

EscalationStage = Literal["GREEN", "YELLOW", "ORANGE", "RED"]

_ALERT_WORTHY: frozenset[EscalationStage] = frozenset({"ORANGE", "RED"})
_ACTION_CARD_VALID_FOR = timedelta(hours=6)


def escalation_stage(p_fail: float) -> EscalationStage:
    if p_fail >= 0.75:
        return "RED"
    if p_fail >= 0.5:
        return "ORANGE"
    if p_fail >= 0.25:
        return "YELLOW"
    return "GREEN"


def compute_action_cards(t: datetime, priorities: list[SettlementPriority]) -> list[ActionCard]:
    """One ActionCard per settlement currently at ORANGE or RED. GREEN/YELLOW villages get no
    card yet — matches BUILD_PLAN.md's escalation stages (CLAUDE.md §4): a card only fires once
    a village is at least "Evacuation Ready".
    """
    cards = []
    for priority in priorities:
        stage = escalation_stage(priority.eps)
        if stage not in _ALERT_WORTHY:
            continue
        cards.append(
            ActionCard(
                alert_id=f"alert-{priority.village_id}-{t.isoformat()}",
                village_id=priority.village_id,
                stage=stage,
                headline="Evacuate Now" if stage == "RED" else "Evacuation Ready",
                reason_plain=(
                    "Phase 0 stub reason: rising fabricated rainfall over this village's slopes."
                ),
                shelter_name="Stub Community Shelter",
                route=None,  # Phase 3: decision/routing.py
                roads_to_avoid=["NH-6 (stub)"],
                what_to_carry=["ID", "medicines", "torch", "drinking water"],
                contact="DDMA (stub contact)",
                issued_at=t,
                valid_until=t + _ACTION_CARD_VALID_FOR,
                safe_window_hours=(1.0, 4.0) if stage == "ORANGE" else (0.0, 1.0),
                translations={},
                audio_urls={},
            )
        )
    return cards
