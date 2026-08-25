"""Application runtime state (BUILD_PLAN.md task 0.11): owns the bus, the mode machine, the
pipeline, and the background task that drives frames -> Pipeline.process -> bus for whichever
Clock/DataSource pair matches the current mode. Holds a ModeState and asks ingest/factory.py what
to do with it — never branches on mode itself (CLAUDE.md §2).

Concurrency note: `_restart_tick_task` captures mode_at_start / scenario_id_at_start / the
Clock+DataSource pair *synchronously*, at the moment of the transition — NOT inside `_run`'s
body. `asyncio.create_task` only schedules a task; it doesn't run it. If `_run` read
`self.mode.state` itself once it finally got to execute, a task created while LIVE could start
running only after a later `start_replay()` had already mutated `self.mode.state` to REPLAY —
reading the wrong mode for its entire run, and (with realtime=False, where nothing inside the
frame loop truly suspends) potentially completing before the task meant to cancel it even gets a
chance to. Capturing everything up front at transition time removes the ambiguity regardless of
when a task actually gets scheduled.
"""
from __future__ import annotations

import asyncio
import contextlib
import logging

from app.core.bus import Bus, Topic
from app.core.clock import Clock
from app.core.mode import ModeMachine
from app.ingest.base import DataSource
from app.ingest.factory import build_clock_and_source, load_scenario_or_raise
from app.pipeline import Pipeline
from app.schemas.mode import RunMode

logger = logging.getLogger(__name__)


class AppState:
    def __init__(self, *, realtime: bool = True):
        self.bus = Bus()
        self.mode = ModeMachine(self.bus)
        self.pipeline = Pipeline()
        self._realtime = realtime
        self._task: asyncio.Task | None = None

    def start(self) -> None:
        """Begin the LIVE stub tick stream. Call once, from inside a running event loop."""
        self._restart_tick_task()

    async def start_replay(self, scenario_id: str) -> None:
        scenario = load_scenario_or_raise(scenario_id)  # raises UnknownScenarioError if missing
        await self.mode.start_replay(
            scenario_id,
            speed_factor=scenario.clock.default_speed_factor,
            scenario_time=scenario.clock.start,
        )
        self._restart_tick_task()

    async def stop_replay(self) -> None:
        await self.mode.stop_replay()
        self._restart_tick_task()

    async def shutdown(self) -> None:
        if self._task is not None:
            self._task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._task

    def _restart_tick_task(self) -> None:
        """Synchronous by design (see module docstring) — no `await` anywhere in this method."""
        old_task = self._task
        mode_at_start = self.mode.state.mode
        scenario_id_at_start = self.mode.state.scenario_id
        clock, source = build_clock_and_source(self.mode.state, realtime=self._realtime)
        logger.info("tick loop starting: mode=%s scenario=%s", mode_at_start, scenario_id_at_start)

        new_task = asyncio.create_task(
            self._run(old_task, mode_at_start, scenario_id_at_start, clock, source)
        )
        self._task = new_task

    async def _run(
        self,
        old_task: asyncio.Task | None,
        mode_at_start: RunMode,
        scenario_id_at_start: str | None,
        clock: Clock,
        source: DataSource,
    ) -> None:
        if old_task is not None:
            old_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await old_task

        this_task = asyncio.current_task()

        async for frame in source.frames():
            tick = self.pipeline.process(frame, mode=mode_at_start, scenario_id=scenario_id_at_start)
            self.mode.update_scenario_time(tick.t)
            await self.bus.publish(Topic.TICK, tick)

        # Only reached if source.frames() ended naturally (a replay reaching its last frame) —
        # if this task was cancelled instead, the `async for` raises CancelledError and
        # everything below is skipped. The `self._task is this_task` guard additionally protects
        # against a stale, already-superseded task (one that finished before whoever was meant
        # to cancel it got a chance to) incorrectly firing a second, redundant mode transition.
        if mode_at_start is RunMode.REPLAY and self._task is this_task:
            logger.info("scenario %s finished; returning to LIVE", scenario_id_at_start)
            await self.mode.stop_replay()
            self._restart_tick_task()
