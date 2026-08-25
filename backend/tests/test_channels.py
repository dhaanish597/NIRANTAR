"""Contract tests for dissemination/channels.py (BUILD_PLAN.md task 3.5)."""
from __future__ import annotations

from datetime import datetime, timezone

import pytest

from app.dissemination import channels as channels_mod
from app.dissemination.channels import (
    ALL_CHANNELS,
    CellBroadcastChannel,
    Channel,
    MeshChannel,
    PushChannel,
    RecipientOutcome,
    SmsChannel,
)
from app.schemas.decision import ActionCard

T0 = datetime(2026, 5, 28, 6, 0, tzinfo=timezone.utc)


def make_card(alert_id: str = "alert-v1-1") -> ActionCard:
    return ActionCard(
        alert_id=alert_id,
        village_id="v1",
        stage="RED",
        headline="Evacuate Now",
        reason_plain="Rising rainfall over saturated slopes.",
        shelter_name="Community Hall",
        route=None,
        roads_to_avoid=["NH-6"],
        what_to_carry=["ID", "water"],
        contact="DDMA Aizawl",
        issued_at=T0,
        valid_until=T0.replace(hour=12),
        safe_window_hours=(0.0, 1.0),
        translations={},
        audio_urls={},
    )


ALL_CHANNEL_CLASSES = [CellBroadcastChannel, SmsChannel, PushChannel, MeshChannel]


@pytest.mark.parametrize("cls", ALL_CHANNEL_CLASSES)
def test_channel_implements_common_protocol(cls):
    instance = cls()
    assert isinstance(instance, Channel)
    assert isinstance(instance.name, str) and instance.name


@pytest.mark.parametrize("cls", ALL_CHANNEL_CLASSES)
def test_channel_class_docstring_labels_itself_simulated(cls):
    """CLAUDE.md: "label them 'simulated channel' ... never imply we have live telecom
    integration." Enforce this mechanically, the same way test_no_wallclock.py enforces rule 14."""
    assert cls.__doc__ is not None
    assert "simulated" in cls.__doc__.lower()


def test_module_docstring_labels_everything_simulated():
    assert "simulated" in (channels_mod.__doc__ or "").lower()


@pytest.mark.parametrize("cls", ALL_CHANNEL_CLASSES)
def test_send_returns_one_outcome_per_recipient(cls):
    result = cls().send(make_card(), recipient_count=50)
    assert result.recipient_count == 50
    assert len(result.outcomes) == 50
    assert all(isinstance(o, RecipientOutcome) for o in result.outcomes)


@pytest.mark.parametrize("cls", ALL_CHANNEL_CLASSES)
def test_zero_recipients_is_valid_and_has_zero_rates(cls):
    result = cls().send(make_card(), recipient_count=0)
    assert result.outcomes == ()
    assert result.delivery_rate == 0.0
    assert result.ack_rate == 0.0


@pytest.mark.parametrize("cls", ALL_CHANNEL_CLASSES)
def test_negative_recipient_count_rejected(cls):
    with pytest.raises(ValueError):
        cls().send(make_card(), recipient_count=-1)


@pytest.mark.parametrize("cls", ALL_CHANNEL_CLASSES)
def test_acknowledged_implies_delivered(cls):
    result = cls().send(make_card(), recipient_count=500)
    assert all(o.delivered for o in result.outcomes if o.acknowledged)


@pytest.mark.parametrize("cls", ALL_CHANNEL_CLASSES)
def test_delivery_and_ack_counts_match_outcome_tally(cls):
    result = cls().send(make_card(), recipient_count=300)
    assert result.delivered_count == sum(1 for o in result.outcomes if o.delivered)
    assert result.acknowledged_count == sum(1 for o in result.outcomes if o.acknowledged)


@pytest.mark.parametrize("cls", ALL_CHANNEL_CLASSES)
def test_latency_within_configured_bounds(cls):
    instance = cls()
    result = instance.send(make_card(), recipient_count=200)
    for outcome in result.outcomes:
        seconds = outcome.latency.total_seconds()
        assert instance.min_latency_seconds <= seconds <= instance.max_latency_seconds


# --- determinism (CLAUDE.md rule 13) ------------------------------------------------------------


@pytest.mark.parametrize("cls", ALL_CHANNEL_CLASSES)
def test_same_card_and_recipient_count_is_byte_identical_across_runs(cls):
    card = make_card()
    result_a = cls().send(card, recipient_count=120)
    result_b = cls().send(card, recipient_count=120)
    assert result_a.outcomes == result_b.outcomes


@pytest.mark.parametrize("cls", ALL_CHANNEL_CLASSES)
def test_different_alert_ids_yield_different_outcomes(cls):
    result_a = cls().send(make_card("alert-A"), recipient_count=50)
    result_b = cls().send(make_card("alert-B"), recipient_count=50)
    assert result_a.outcomes != result_b.outcomes


def test_seed_is_independent_of_global_random_state():
    """Perturbing the global `random` module must not change our seeded outcome — proves we never
    fall back to the global RNG."""
    import random as global_random

    card = make_card()
    global_random.seed(1)
    first = CellBroadcastChannel().send(card, recipient_count=40)
    global_random.seed(999999)
    second = CellBroadcastChannel().send(card, recipient_count=40)
    assert first.outcomes == second.outcomes


# --- channel profile sanity (design intent, not just implementation accident) --------------------


def test_mesh_channel_is_slowest_and_least_reliable_by_design():
    mesh = MeshChannel()
    others = [CellBroadcastChannel(), SmsChannel(), PushChannel()]
    for other in others:
        assert mesh.max_latency_seconds > other.max_latency_seconds
        assert mesh.delivery_rate <= other.delivery_rate


def test_cell_broadcast_has_highest_delivery_rate():
    cb = CellBroadcastChannel()
    for other in [SmsChannel(), PushChannel(), MeshChannel()]:
        assert cb.delivery_rate >= other.delivery_rate


def test_invalid_latency_bounds_rejected():
    with pytest.raises(ValueError):
        channels_mod._SimulatedChannelBase(
            "bad", min_latency_seconds=10.0, max_latency_seconds=5.0,
            delivery_rate=0.5, ack_rate_given_delivered=0.5,
        )


def test_invalid_rate_rejected():
    with pytest.raises(ValueError):
        channels_mod._SimulatedChannelBase(
            "bad", min_latency_seconds=1.0, max_latency_seconds=5.0,
            delivery_rate=1.5, ack_rate_given_delivered=0.5,
        )


def test_all_channels_registry_matches_the_four_required_classes():
    assert set(ALL_CHANNELS) == {"cell_broadcast", "sms", "push", "mesh"}
    assert ALL_CHANNELS["cell_broadcast"] is CellBroadcastChannel
    assert ALL_CHANNELS["sms"] is SmsChannel
    assert ALL_CHANNELS["push"] is PushChannel
    assert ALL_CHANNELS["mesh"] is MeshChannel
