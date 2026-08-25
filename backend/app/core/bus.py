"""Minimal in-process async pub/sub. One topic per pipeline stage (BUILD_PLAN.md task 0.8).

Not a message broker — there's exactly one process, so this is just fan-out over asyncio.Queue
per subscriber. Used by core/mode.py to publish mode-change events, and by ws/ to fan tick
progress out to connected WebSocket clients.
"""
from __future__ import annotations

import asyncio
from collections import defaultdict
from contextlib import asynccontextmanager
from enum import Enum
from typing import Any, AsyncIterator


class Topic(str, Enum):
    """One topic per pipeline stage, per BUILD_PLAN.md task 0.8. See docs/ARCHITECTURE.md §2."""

    MODE = "mode"
    RISK = "risk"
    IMPACT = "impact"
    DECISION = "decision"
    DISSEMINATION = "dissemination"
    AUDIT = "audit"
    TICK = "tick"


class Bus:
    """Async pub/sub. Multiple subscribers per topic; each gets every message published to it."""

    def __init__(self) -> None:
        self._queues: dict[str, list[asyncio.Queue]] = defaultdict(list)

    async def publish(self, topic: Topic | str, message: Any) -> None:
        for queue in list(self._queues[str(topic)]):
            await queue.put(message)

    @asynccontextmanager
    async def subscribe(self, topic: Topic | str) -> AsyncIterator[asyncio.Queue]:
        """`async with bus.subscribe(Topic.TICK) as queue: msg = await queue.get()`"""
        queue: asyncio.Queue = asyncio.Queue()
        self._queues[str(topic)].append(queue)
        try:
            yield queue
        finally:
            self._queues[str(topic)].remove(queue)

    def subscriber_count(self, topic: Topic | str) -> int:
        return len(self._queues[str(topic)])
