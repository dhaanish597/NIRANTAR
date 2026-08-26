"""decision/action_card.py — BUILD_PLAN.md task 3.3: the village-facing `ActionCard` artifact.

Assembles a schema-valid `ActionCard` (backend/app/schemas/decision.py) from the outputs of the
other Phase 3 modules already built this same pass — it computes NONE of the underlying risk
itself:

  - `stage`: delegated to `decision/escalation.py`'s real `EscalationStateMachine` (task 3.2) —
    this module NEVER re-derives GREEN/YELLOW/ORANGE/RED cutoffs itself (that was Phase 0's
    `decision/stub.py`'s job, which this supersedes). `build_action_card()` takes an already-
    resolved `EscalationStage` as a plain argument so it stays a pure function testable without a
    live state machine; `build_action_card_from_escalation()` right below it is the "call it,
    don't reimplement" convenience wrapper that actually drives an `EscalationStateMachine`.
  - `route` / `shelter_name` / `roads_to_avoid`: `decision/routing.py`'s `EvacuationRoute`
    (task 3.1) — this module does not compute a route, it only reads one.
  - `safe_window_hours`: `decision/window.py`'s `SafeWindowEstimate.hours` (task 2.6) — passed
    straight through; NEVER re-labelled as anything but a range (CLAUDE.md's "never time to
    landslide" rule, already enforced structurally in window.py itself).
  - `issued_at` / `valid_until`: both derived from a REQUIRED caller-supplied `now: datetime`
    (rule 14 — `datetime.now()` is banned outside `core/clock.py`; a real pipeline caller passes
    `clock.now()`, tests pass a fixed timestamp).
  - `alert_id`: deterministic (`f"card-{village_id}-{now.isoformat()}"`), never `uuid.uuid4()`
    (CLAUDE.md rule 13 — unseeded randomness anywhere breaks replay determinism), same pattern
    `decision/escalation.py`'s own `alert_id=f"esc-{entity_id}"` and `pipeline.py`'s
    `event_id=f"evt-{aoi_id}-{t.isoformat()}"` already use.

REASON_PLAIN: composed from the stage's human label (`decision/escalation.py`'s `STAGE_LABELS` —
reused, not duplicated) plus, when available, the top attribution(s) from `risk/explain.py`'s SHAP
output (task 1.18) rendered in that module's own plain-language style
(`Attribution.plain_language` + `Attribution.display_pct`) — e.g. "Orange Evacuation Ready:
modelled failure probability 62% for the slopes above this village, driven mainly by 72-hour
rainfall (+38%) and average slope (26°) (+21%)." When no attributions are supplied (a cell with no
real terrain match, or a caller that hasn't wired risk/explain.py in yet), falls back to a
still-honest, non-fabricated generic sentence naming just the stage and the raw p_fail — never
invents a driver that wasn't actually supplied.

WHAT TO CARRY / WHO TO CALL — both explicit, documented placeholders (task 3.3's own wording: "a
short static list is fine — document it's a general checklist, not scenario-specific" /
"a placeholder contact string is fine, documented as such"):
  - `config.WHAT_TO_CARRY_CHECKLIST`: a general emergency-evacuation checklist, not sourced from
    docs/reference/ and not claimed to be scenario-specific.
  - `config.ACTION_CARD_CONTACT_PLACEHOLDER`: an explicit, self-labelling placeholder string.
    CLAUDE.md gives no real DDMA phone number anywhere and this module does not invent one.

Pure function over already-computed inputs — no LIVE/REPLAY awareness (CLAUDE.md §2), no file I/O,
no pipeline wiring (that is explicitly a separate, later task, not this one).
"""
from __future__ import annotations

from datetime import datetime, timedelta

from app.config import (
    ACTION_CARD_CONTACT_PLACEHOLDER,
    ACTION_CARD_VALID_FOR_HOURS,
    WHAT_TO_CARRY_CHECKLIST,
)
from app.decision.escalation import STAGE_LABELS, EscalationStage, EscalationStateMachine
from app.decision.window import SafeWindowEstimate
from app.schemas.decision import ActionCard, EvacuationRoute
from app.schemas.risk import Attribution

_HEADLINES: dict[EscalationStage, str] = {
    "GREEN": "Monitor — No Action Needed",
    "YELLOW": "Prepare to Evacuate",
    "ORANGE": "Evacuation Ready",
    "RED": "Evacuate Now",
}

# Stages this codebase treats as "worth a card" — matches decision/stub.py's own precedent
# (Phase 0's `_ALERT_WORTHY = frozenset({"ORANGE", "RED"})`), exposed here so a future caller
# deciding whether to ISSUE a card at all doesn't have to hardcode the set a second time.
ALERT_WORTHY_STAGES: frozenset[EscalationStage] = frozenset({"ORANGE", "RED"})

_NO_SHELTER_ROUTE_NAME = "No usable shelter route available — contact DDMA for guidance"


def _reason_plain(
    stage: EscalationStage, p_fail: float, attributions: list[Attribution] | None, *, top_n: int = 2
) -> str:
    stage_label = STAGE_LABELS[stage]
    if not attributions:
        return (
            f"{stage_label}: modelled failure probability {p_fail * 100:.0f}% for the slopes "
            "above this village."
        )
    top = sorted(attributions, key=lambda a: abs(a.contribution), reverse=True)[:top_n]
    drivers = ", ".join(f"{a.plain_language} ({a.display_pct:+.0f}%)" for a in top)
    return (
        f"{stage_label}: modelled failure probability {p_fail * 100:.0f}% for the slopes above "
        f"this village, driven mainly by {drivers}."
    )


def build_action_card(
    *,
    village_id: str,
    stage: EscalationStage,
    p_fail: float,
    now: datetime,
    attributions: list[Attribution] | None = None,
    route: EvacuationRoute | None = None,
    safe_window: SafeWindowEstimate | None = None,
    alert_id: str | None = None,
    valid_for: timedelta | None = None,
    contact: str = ACTION_CARD_CONTACT_PLACEHOLDER,
    what_to_carry: list[str] | None = None,
) -> ActionCard:
    """Builds one `ActionCard` for one village at one instant. Every dynamic input (`stage`,
    `p_fail`, `attributions`, `route`, `safe_window`) is supplied by the caller, already computed
    by this pass's other Phase 3 modules — see module docstring."""
    if not (0.0 <= p_fail <= 1.0):
        raise ValueError(f"p_fail must be in [0,1], got {p_fail}")

    resolved_alert_id = alert_id or f"card-{village_id}-{now.isoformat()}"
    resolved_valid_for = valid_for if valid_for is not None else timedelta(hours=ACTION_CARD_VALID_FOR_HOURS)

    if route is not None:
        shelter_name = route.shelter_name
        roads_to_avoid = list(route.avoided_roads)
    else:
        shelter_name = _NO_SHELTER_ROUTE_NAME
        roads_to_avoid = []

    return ActionCard(
        alert_id=resolved_alert_id,
        village_id=village_id,
        stage=stage,
        headline=_HEADLINES[stage],
        reason_plain=_reason_plain(stage, p_fail, attributions),
        shelter_name=shelter_name,
        route=route,
        roads_to_avoid=roads_to_avoid,
        what_to_carry=list(what_to_carry) if what_to_carry is not None else list(WHAT_TO_CARRY_CHECKLIST),
        contact=contact,
        issued_at=now,
        valid_until=now + resolved_valid_for,
        safe_window_hours=safe_window.hours if safe_window is not None else None,
        translations={},  # Phase 3.9 (IndicTrans2) — not this task's scope
        audio_urls={},  # Phase 3.9 (Indic-Parler-TTS) — not this task's scope
    )


def build_action_card_from_escalation(
    *,
    village_id: str,
    p_fail: float,
    now: datetime,
    escalation: EscalationStateMachine,
    entity_id: str | None = None,
    **kwargs,
) -> ActionCard:
    """The "call it, don't reimplement" entry point task 3.3 asks for: drives the REAL
    `EscalationStateMachine` (task 3.2) with this observation — `entity_id` defaults to
    `village_id` (the natural per-village key for a village-facing card; pass a distinct
    `entity_id` if the caller is keying escalation by cell instead) — and uses whatever stage the
    state machine reports as current AFTER that observation (which already applies task 3.2's own
    upgrade/hysteresis-downgrade rules), not a re-derived one. Every other keyword argument passes
    straight through to `build_action_card()`."""
    key = entity_id or village_id
    escalation.observe(key, p_fail, now)
    stage = escalation.current_stage(key)
    return build_action_card(village_id=village_id, stage=stage, p_fail=p_fail, now=now, **kwargs)
