"""dissemination/channels.py — last-mile delivery channel adapters (BUILD_PLAN.md task 3.5).

CLAUDE.md is explicit: "For the demo these are simulated with realistic latency and a
delivery/ack rate; label them 'simulated channel' in the UI. Never imply we have live telecom
integration." Every channel class in this file is a SIMULATED CHANNEL: none of them opens a
socket, calls a telecom API, a push provider, or a BLE/Wi-Fi radio. Each `send()` call returns a
plausible, seeded-deterministic delivery/ack outcome per recipient so the DDMA console and audit
trail (BUILD_PLAN.md tasks 3.7/3.8) have real-shaped numbers to render — without a live network
dependency, which also keeps this off the demo's network-cable-unplugged critical path
(CLAUDE.md rule 10).

Determinism (CLAUDE.md rule 13): every simulated outcome is drawn from a `random.Random` instance
seeded deterministically from `(alert_id, channel_name)` — never the global `random` module,
never `time.time()`/`datetime.now()` (this file imports neither). The same `ActionCard` sent
through the same channel with the same recipient count produces byte-identical outcomes on every
run and every replay.

This module does not read a `Clock` and does not stamp wall-clock/scenario time onto its results
at all — callers that need a "sent at" / "delivered at" timestamp combine `ChannelSendResult` with
whatever `t` they already have from the tick (frame.t / clock.now()), by adding each
`RecipientOutcome.latency` to it. Keeping timestamps out of this module entirely is what keeps it
a pure, clock-free simulation (nothing here could violate CLAUDE.md rule 14 even by accident).
"""
from __future__ import annotations

import hashlib
import random
from datetime import timedelta
from typing import Protocol, runtime_checkable

from app.schemas.decision import ActionCard


def _seed_for(alert_id: str, channel_name: str) -> int:
    """Deterministic seed derived from (alert_id, channel_name) — same inputs, same seed, every
    time (CLAUDE.md rule 13). SHA-256 rather than Python's `hash()` because `hash()` on strings is
    randomized per-process (`PYTHONHASHSEED`) unless explicitly disabled — exactly the kind of
    hidden nondeterminism this project's determinism rule exists to rule out."""
    digest = hashlib.sha256(f"{alert_id}:{channel_name}".encode("utf-8")).digest()
    return int.from_bytes(digest[:8], "big") & 0x7FFF_FFFF_FFFF_FFFF


class RecipientOutcome:
    __slots__ = ("recipient_index", "delivered", "acknowledged", "latency")

    def __init__(
        self, recipient_index: int, delivered: bool, acknowledged: bool, latency: timedelta
    ) -> None:
        self.recipient_index = recipient_index
        self.delivered = delivered
        self.acknowledged = acknowledged
        self.latency = latency

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, RecipientOutcome):
            return NotImplemented
        return (
            self.recipient_index == other.recipient_index
            and self.delivered == other.delivered
            and self.acknowledged == other.acknowledged
            and self.latency == other.latency
        )

    def __repr__(self) -> str:  # pragma: no cover - debugging aid only
        return (
            f"RecipientOutcome(recipient_index={self.recipient_index}, "
            f"delivered={self.delivered}, acknowledged={self.acknowledged}, "
            f"latency={self.latency})"
        )


class ChannelSendResult:
    """The outcome of one SIMULATED channel send to `recipient_count` recipients."""

    def __init__(
        self,
        channel: str,
        alert_id: str,
        recipient_count: int,
        outcomes: tuple[RecipientOutcome, ...],
    ) -> None:
        self.channel = channel
        self.alert_id = alert_id
        self.recipient_count = recipient_count
        self.outcomes = outcomes

    @property
    def delivered_count(self) -> int:
        return sum(1 for o in self.outcomes if o.delivered)

    @property
    def acknowledged_count(self) -> int:
        return sum(1 for o in self.outcomes if o.acknowledged)

    @property
    def delivery_rate(self) -> float:
        return self.delivered_count / self.recipient_count if self.recipient_count else 0.0

    @property
    def ack_rate(self) -> float:
        return self.acknowledged_count / self.recipient_count if self.recipient_count else 0.0


@runtime_checkable
class Channel(Protocol):
    """The common interface every SIMULATED dissemination channel implements
    (BUILD_PLAN.md task 3.5)."""

    name: str

    def send(self, card: ActionCard, *, recipient_count: int) -> ChannelSendResult: ...


class _SimulatedChannelBase:
    """Shared seeded latency/delivery/ack simulation. Subclasses only fix a channel's profile
    (name + latency bounds + rates) — every subclass in this file is a SIMULATED CHANNEL; nothing
    here ever contacts a real network, gateway, or handset (CLAUDE.md — "never imply we have live
    telecom integration")."""

    def __init__(
        self,
        name: str,
        *,
        min_latency_seconds: float,
        max_latency_seconds: float,
        delivery_rate: float,
        ack_rate_given_delivered: float,
    ) -> None:
        if min_latency_seconds < 0 or max_latency_seconds < min_latency_seconds:
            raise ValueError("invalid latency bounds")
        if not (0.0 <= delivery_rate <= 1.0) or not (0.0 <= ack_rate_given_delivered <= 1.0):
            raise ValueError("rates must be in [0,1]")
        self.name = name
        self.min_latency_seconds = min_latency_seconds
        self.max_latency_seconds = max_latency_seconds
        self.delivery_rate = delivery_rate
        self.ack_rate_given_delivered = ack_rate_given_delivered

    def send(self, card: ActionCard, *, recipient_count: int) -> ChannelSendResult:
        if recipient_count < 0:
            raise ValueError("recipient_count must be >= 0")

        rng = random.Random(_seed_for(card.alert_id, self.name))
        outcomes = []
        for i in range(recipient_count):
            delivered = rng.random() < self.delivery_rate
            acknowledged = delivered and rng.random() < self.ack_rate_given_delivered
            latency = timedelta(
                seconds=rng.uniform(self.min_latency_seconds, self.max_latency_seconds)
            )
            outcomes.append(
                RecipientOutcome(
                    recipient_index=i,
                    delivered=delivered,
                    acknowledged=acknowledged,
                    latency=latency,
                )
            )
        return ChannelSendResult(
            channel=self.name,
            alert_id=card.alert_id,
            recipient_count=recipient_count,
            outcomes=tuple(outcomes),
        )


class CellBroadcastChannel(_SimulatedChannelBase):
    """SIMULATED cell-broadcast channel — models the C-DOT Cell Broadcast rail SACHET already
    fans alerts out over (docs/reference/SIH26001_Technical_Architecture_Reference.md). Highest
    reach and near-instant per real-world cell broadcast characteristics (no SIM registration or
    app install needed, delivered to every compatible handset in the affected cell). CAP/cell
    broadcast is one-way by design; the "acknowledged" rate modelled here stands in for a
    follow-up channel (e.g. a paired SMS prompt) some deployments use to capture a response, not
    a literal per-handset ack in the cell-broadcast protocol itself."""

    def __init__(self) -> None:
        super().__init__(
            "cell_broadcast",
            min_latency_seconds=2.0,
            max_latency_seconds=15.0,
            delivery_rate=0.97,
            ack_rate_given_delivered=0.55,
        )


class SmsChannel(_SimulatedChannelBase):
    """SIMULATED SMS channel — models a telecom SMS gateway hop off SACHET. Slower and less
    reliable than cell broadcast (queuing, handset off/out-of-range) but supports a real two-way
    acknowledgement SMS back."""

    def __init__(self) -> None:
        super().__init__(
            "sms",
            min_latency_seconds=5.0,
            max_latency_seconds=120.0,
            delivery_rate=0.90,
            ack_rate_given_delivered=0.40,
        )


class PushChannel(_SimulatedChannelBase):
    """SIMULATED mobile push-notification channel — models the offline-capable PWA
    (BUILD_PLAN.md Phase 5) receiving a push while online. Fast when it lands, but the lowest
    delivery rate of the four: requires the app installed, notifications permitted, and (unlike
    cell broadcast) a live data connection at send time."""

    def __init__(self) -> None:
        super().__init__(
            "push",
            min_latency_seconds=1.0,
            max_latency_seconds=20.0,
            delivery_rate=0.75,
            ack_rate_given_delivered=0.60,
        )


class MeshChannel(_SimulatedChannelBase):
    """SIMULATED BLE/Wi-Fi Direct phone-to-phone store-and-forward mesh (BUILD_PLAN.md task 5.5)
    for the ~1,841 NER villages with no mobile coverage (CLAUDE.md §1). By design the slowest and
    least reliable of the four: propagation depends on how many hops and how much phone-to-phone
    movement happens before every device in range has relayed the alert onward — this is the
    entire reason it is modelled with the widest latency spread and the lowest delivery rate,
    not an oversight."""

    def __init__(self) -> None:
        super().__init__(
            "mesh",
            min_latency_seconds=60.0,
            max_latency_seconds=1800.0,
            delivery_rate=0.60,
            ack_rate_given_delivered=0.30,
        )


ALL_CHANNELS: dict[str, type[_SimulatedChannelBase]] = {
    "cell_broadcast": CellBroadcastChannel,
    "sms": SmsChannel,
    "push": PushChannel,
    "mesh": MeshChannel,
}
