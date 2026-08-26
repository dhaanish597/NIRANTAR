"""audit/producers.py — BUILD_PLAN.md task 3.6(a): real producer functions for the two audit
event kinds this session's Phase 3 work newly introduces a natural source for.

`decision/escalation.py`'s `EscalationStateMachine` (task 3.2, prior session) already appends real
`ESCALATED` events straight into an `AuditLog` — that producer already exists and is not
duplicated here. `pipeline.py`'s `AI_FLAGGED` producer (Phase 0) likewise already exists. What was
still missing, per task 3.6's own wording, is a real producer path for the two events that sit
between "AI flagged it" and "it escalated further": a DDMA officer's human-in-the-loop decision
(`DDMA_APPROVED` — or `STOOD_DOWN` for a rejection, the schema's own name for "no action"), and
the simulated channels (`dissemination/channels.py`, task 3.5) actually sending an `ActionCard`
out (`DISSEMINATED`).

Both functions below are real, standalone, testable producers over the same
`audit/hash_chain.py` + `audit/log.py` machinery every other stage already uses — CALLABLE, not
yet CALLED from `pipeline.py` (wiring producers into the live pipeline is a separate, later task,
explicitly out of this session's scope; see BUILD_PLAN.md task 3.6's own framing: "you're wiring
new producers into an existing sink, not building the sink itself" — the same phrase
`decision/escalation.py`'s own docstring already quotes for its ESCALATED producer).

SCOPE NOTE (updated, task 3.10 session): `DELIVERED` is still deliberately NOT given a producer
here — in a fully real deployment it is an asynchronous delivery-confirmation callback from a
telecom/push provider, and this project's channels are simulated (task 3.5) precisely so no such
callback exists to wire. Adding a producer for an event with no real trigger anywhere in this
codebase would be exactly the kind of fabrication CLAUDE.md's honesty rules ban.

`VILLAGE_ACKNOWLEDGED` **now has a real producer** (`record_village_acknowledged`, below) — its
real trigger, the citizen-facing "I have evacuated" button (BUILD_PLAN.md task 3.10, Village
View), now exists (`frontend/src/components/VillageView.tsx`) and calls
`POST /api/village/acknowledge` (`api/routes.py`), which calls this function.
"""
from __future__ import annotations

from datetime import datetime
from typing import Literal

from app.audit.log import AuditLog
from app.dissemination.channels import ChannelSendResult
from app.schemas.audit import AuditEvent
from app.schemas.decision import ActionCard

DdmaDecision = Literal["approved", "modified", "rejected"]


def record_ddma_decision(
    audit_log: AuditLog,
    *,
    action_card: ActionCard,
    officer_id: str,
    t: datetime,
    decision: DdmaDecision = "approved",
    notes: str = "",
) -> AuditEvent:
    """CLAUDE.md's human-in-the-loop rule, made real: this is the one function in the whole
    decision/dissemination stack whose `actor` is ever a human (`"ddma:{officer_id}"`, matching
    `AuditEvent.actor`'s own documented convention), because a DDMA officer approving/modifying/
    rejecting an AI recommendation is precisely the accountable human action CLAUDE.md §1's thesis
    ("no accountable chain from a bulletin to an actual evacuation") says this whole product exists
    to create.

    `decision="approved"` or `"modified"` both append a `DDMA_APPROVED` event (a modification is
    still an approval-to-proceed, just with officer-supplied changes — recorded in `notes`, not a
    second event kind the schema doesn't have). `decision="rejected"` appends `STOOD_DOWN` instead
    — the schema's own name for "no action taken on this alert."

    `input_hash` (via `AuditLog.append`) is computed over the actual `ActionCard` content the
    officer approved/rejected — the payload includes `action_card.alert_id`/`.stage`/`.village_id`
    so a later audit read can see exactly what was approved, not just that *something* was.
    """
    kind = "STOOD_DOWN" if decision == "rejected" else "DDMA_APPROVED"
    return audit_log.append(
        event_id=f"evt-ddma-{action_card.alert_id}-{t.isoformat()}",
        alert_id=action_card.alert_id,
        kind=kind,
        actor=f"ddma:{officer_id}",
        t=t,
        payload={
            "decision": decision,
            "notes": notes,
            "village_id": action_card.village_id,
            "stage": action_card.stage,
            "headline": action_card.headline,
        },
    )


def record_dissemination(
    audit_log: AuditLog,
    *,
    action_card: ActionCard,
    channel_results: list[ChannelSendResult],
    t: datetime,
) -> AuditEvent:
    """Appends one `DISSEMINATED` event summarizing every SIMULATED channel send
    (`dissemination/channels.py`, task 3.5) a real dissemination flow for this `ActionCard` would
    have made. `actor="system"` — dissemination is not a human decision point (the human decision
    already happened, `record_ddma_decision` above); it is the mechanical act of pushing an
    already-approved card out over the (simulated) channels.

    The payload records exactly what CLAUDE.md's audit-trail example slide wants on screen
    (§10, beat 6 — "847/1,020 handsets acknowledged"): per-channel `recipient_count`/
    `delivered_count`/`acknowledged_count`, plus the same totals summed across every channel that
    was actually used. Real numbers from the real (seeded-deterministic) `ChannelSendResult`
    objects passed in — nothing here re-derives or approximates delivery/ack counts itself.
    """
    per_channel = {
        result.channel: {
            "recipient_count": result.recipient_count,
            "delivered_count": result.delivered_count,
            "acknowledged_count": result.acknowledged_count,
        }
        for result in channel_results
    }
    return audit_log.append(
        event_id=f"evt-dissem-{action_card.alert_id}-{t.isoformat()}",
        alert_id=action_card.alert_id,
        kind="DISSEMINATED",
        actor="system",
        t=t,
        payload={
            "village_id": action_card.village_id,
            "channels": sorted(per_channel),
            "per_channel": per_channel,
            "total_recipients": sum(r.recipient_count for r in channel_results),
            "total_delivered": sum(r.delivered_count for r in channel_results),
            "total_acknowledged": sum(r.acknowledged_count for r in channel_results),
        },
    )


def record_village_acknowledged(
    audit_log: AuditLog,
    *,
    alert_id: str,
    village_id: str,
    t: datetime,
) -> AuditEvent:
    """BUILD_PLAN.md task 3.10's "I have evacuated" button, made real: the citizen-facing
    acknowledgement that closes the AI Flagged -> DDMA Approved -> Disseminated -> Village
    Acknowledged chain CLAUDE.md's audit-trail glossary entry describes.

    `actor` is `"village:{village_id}"` — matching `AuditEvent.actor`'s own documented convention
    (`"system" | "ddma:officer_id" | "village:id"`). This is the second (and last) place in this
    whole stack where `actor` is ever a real, non-system party — the first being
    `record_ddma_decision` above, a DDMA officer; this one is the village itself, acting through
    whichever device rendered its Village View.

    No `ActionCard`/officer/channel object is required here — unlike `DDMA_APPROVED`/
    `DISSEMINATED`, a village acknowledgement is a bare fact ("this alert_id, this village,
    acknowledged, at this time"), not a decision about a payload. `alert_id` is caller-supplied
    (the `ActionCard.alert_id` the citizen's device already holds, received over `/ws/ticks`)
    rather than looked up server-side — same reasoning `record_ddma_decision`/`record_dissemination`
    already establish: this codebase has no server-side `ActionCard` store keyed by `alert_id`,
    so the caller (frontend) is the natural source of truth for which alert is being acknowledged.
    """
    return audit_log.append(
        event_id=f"evt-ack-{alert_id}-{t.isoformat()}",
        alert_id=alert_id,
        kind="VILLAGE_ACKNOWLEDGED",
        actor=f"village:{village_id}",
        t=t,
        payload={"village_id": village_id},
    )
