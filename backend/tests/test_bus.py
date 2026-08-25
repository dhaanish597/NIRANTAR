"""Contract test for core/bus.py."""
from __future__ import annotations

import asyncio

import pytest

from app.core.bus import Bus, Topic


async def test_publish_before_any_subscriber_is_dropped_silently():
    bus = Bus()
    await bus.publish(Topic.TICK, {"hello": "world"})  # no subscribers yet — must not raise


async def test_single_subscriber_receives_published_message():
    bus = Bus()
    async with bus.subscribe(Topic.TICK) as queue:
        await bus.publish(Topic.TICK, {"t": 1})
        message = await asyncio.wait_for(queue.get(), timeout=1.0)
    assert message == {"t": 1}


async def test_multiple_subscribers_on_same_topic_all_receive():
    bus = Bus()
    async with bus.subscribe(Topic.MODE) as q1, bus.subscribe(Topic.MODE) as q2:
        await bus.publish(Topic.MODE, "state-1")
        m1 = await asyncio.wait_for(q1.get(), timeout=1.0)
        m2 = await asyncio.wait_for(q2.get(), timeout=1.0)
    assert m1 == m2 == "state-1"


async def test_subscribers_on_different_topics_are_isolated():
    bus = Bus()
    async with bus.subscribe(Topic.RISK) as risk_q, bus.subscribe(Topic.AUDIT) as audit_q:
        await bus.publish(Topic.RISK, "risk-event")
        risk_msg = await asyncio.wait_for(risk_q.get(), timeout=1.0)
        assert audit_q.empty()
    assert risk_msg == "risk-event"


async def test_unsubscribe_on_context_exit_stops_delivery():
    bus = Bus()
    assert bus.subscriber_count(Topic.DECISION) == 0
    async with bus.subscribe(Topic.DECISION) as queue:
        assert bus.subscriber_count(Topic.DECISION) == 1
    assert bus.subscriber_count(Topic.DECISION) == 0
    # publishing after the subscriber left must not raise, and nothing should land in `queue`
    await bus.publish(Topic.DECISION, "too-late")
    assert queue.empty()
