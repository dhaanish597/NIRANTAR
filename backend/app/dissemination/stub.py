"""Phase 0 dissemination stub (BUILD_PLAN.md task 0.10). Identity pass-through — no channel
adapters exist yet (Phase 3, BUILD_PLAN.md task 3.5: CellBroadcastChannel/SmsChannel/PushChannel/
MeshChannel, all simulated). This exists purely so the pipeline's stage chain (frame → risk →
impact → decision → dissemination → audit) is complete and callable end to end, per
docs/ARCHITECTURE.md §2.
"""
from __future__ import annotations

from app.schemas.decision import ActionCard


def disseminate(action_cards: list[ActionCard]) -> list[ActionCard]:
    """Phase 0: no-op. Returns the same cards unchanged, as if "queued for dissemination"."""
    return action_cards
