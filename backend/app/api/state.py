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
from pathlib import Path

from app.citizen_reports.store import CitizenReportStore
from app.citizen_reports.workflow import CitizenReportWorkflow
from app.config import (
    NVIDIA_API_KEY,
    NVIDIA_BASE_URL,
    NVIDIA_TIMEOUT_SECONDS,
    NVIDIA_VISION_MODEL,
)
from app.core.bus import Bus, Topic
from app.core.clock import Clock
from app.core.mode import ModeMachine
from app.ingest.base import DataSource
from app.ingest.factory import build_clock_and_source, load_scenario_or_raise
from app.pipeline import Pipeline
from app.schemas.announcement import Announcement
from app.schemas.mode import RunMode
from app.schemas.tick import TickResult
from app.commander.store import CommanderStore

logger = logging.getLogger(__name__)


class AppState:
    def __init__(self, *, realtime: bool = True, citizen_report_data_dir: Path | None = None):
        self.bus = Bus()
        self.mode = ModeMachine(self.bus)
        self.pipeline = Pipeline()
        self.latest_tick: TickResult | None = None
        self.commander_store = CommanderStore()
        report_root = citizen_report_data_dir or Path(__file__).resolve().parents[2] / "data" / "citizen_reports"
        self.citizen_report_store = CitizenReportStore(report_root)
        self.citizen_report_workflow = CitizenReportWorkflow(
            self.citizen_report_store,
            api_key=NVIDIA_API_KEY,
            model=NVIDIA_VISION_MODEL,
            base_url=NVIDIA_BASE_URL,
            timeout=NVIDIA_TIMEOUT_SECONDS,
        )
        # Real Announcements this session has dispatched (Task 3/4, Foundation sub-project).
        # Independent of replay state — an announcement made in LIVE mode stays visible even if a
        # replay starts afterwards, unlike self.pipeline (which IS reassigned on start_replay()).
        self.announcements: list[Announcement] = []
        self._realtime = realtime
        self._task: asyncio.Task | None = None
        # The currently in-flight DataSource — kept so pause()/resume()/set_speed() (BUILD_PLAN.md
        # task 4.7's replay controls, exposed over REST by this session's small connected gap) can
        # act on the SAME live ScenarioSource `_run`'s `async for frame in source.frames()` is
        # actually iterating, without restarting the tick task. Restarting via
        # `_restart_tick_task()` would call `build_clock_and_source()` again, which builds a BRAND
        # NEW ScenarioClock/ScenarioSource from the scenario's own start time — exactly the "no
        # residue" reset `start_replay()` deliberately wants on a genuine restart, but the WRONG
        # behaviour for a pause/resume/speed change, which must act on the replay already in
        # progress rather than silently rewinding it to frame zero.
        self._current_source: DataSource | None = None

    def start(self) -> None:
        """Begin the LIVE stub tick stream. Call once, from inside a running event loop."""
        self._restart_tick_task()

    async def pause_replay(self) -> None:
        """BUILD_PLAN.md task 4.7 / this session's small connected gap: pause the IN-PROGRESS
        replay. `self.mode.pause()` raises `ModeError` if not currently in REPLAY — that gate runs
        BEFORE touching `self._current_source`, so a LIVE-mode caller never reaches the source at
        all. `ScenarioSource.pause()` (task 4.7, already real) makes `frames()` block via its
        internal `asyncio.Event` before yielding the next frame, without ending iteration.
        """
        await self.mode.pause()
        if hasattr(self._current_source, "pause"):
            self._current_source.pause()

    async def resume_replay(self) -> None:
        await self.mode.resume()
        if hasattr(self._current_source, "resume"):
            self._current_source.resume()

    async def set_replay_speed(self, speed_factor: float) -> None:
        """Updates BOTH `ModeState.speed_factor` (`self.mode.set_speed` — what `GET /api/state`
        and the frontend's `modeState.speed_factor` display, per task 4.9's already-built control
        bar) AND the live `ScenarioSource`'s own clock (`ScenarioSource.set_speed`, task 4.7 —
        `frames()` re-reads `clock.speed_factor` fresh every iteration, so this takes effect on
        the very next frame's pacing, no restart needed). `self.mode.set_speed` raises `ModeError`/
        `ValueError` first (not in REPLAY / non-positive factor) before either is touched.
        """
        await self.mode.set_speed(speed_factor)
        if hasattr(self._current_source, "set_speed"):
            self._current_source.set_speed(speed_factor)

    async def start_replay(self, scenario_id: str) -> None:
        scenario = load_scenario_or_raise(scenario_id)  # raises UnknownScenarioError if missing
        await self.mode.start_replay(
            scenario_id,
            speed_factor=scenario.clock.default_speed_factor,
            scenario_time=scenario.clock.start,
        )
        # A fresh Pipeline (and therefore a fresh audit hash chain) every time — "Run Case Study"
        # must fully reset downstream state on restart (BUILD_PLAN.md task 4.7), whether this is
        # the very first replay, a restart of the same scenario, or a switch to a different one.
        # Without this, a second click would carry over the first run's audit_log.events and
        # prev_hash chain, so two identical replays would NOT produce identical TickResults —
        # a real determinism violation (CLAUDE.md rule 13), not just a cosmetic UI oddity.
        self.pipeline = Pipeline()
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
        # Captured synchronously for the exact same reason mode/clock/source are (see module
        # docstring): `start_replay()` (BUILD_PLAN.md task 4.7) reassigns `self.pipeline` to a
        # fresh Pipeline so a restarted replay's audit log has no residue from the previous run.
        # If `_run` read `self.pipeline` itself instead of a value captured at creation time, a
        # not-yet-cancelled OLD task could resume after that reassignment and write its leftover
        # frames into the NEW (freshly reset) Pipeline — contaminating the very audit log the
        # reset was meant to protect. Binding `pipeline` here, once, closes that race exactly the
        # way mode_at_start/scenario_id_at_start/clock/source already do.
        pipeline = self.pipeline
        # See the class docstring's note on `self._current_source`: this must point at the exact
        # `source` object `_run` below is about to iterate, so a pause()/resume()/set_speed() call
        # made from another coroutine while `_run` is mid-iteration reaches the right instance.
        self._current_source = source
        logger.info("tick loop starting: mode=%s scenario=%s", mode_at_start, scenario_id_at_start)

        new_task = asyncio.create_task(
            self._run(old_task, mode_at_start, scenario_id_at_start, clock, source, pipeline)
        )
        self._task = new_task

    async def _run(
        self,
        old_task: asyncio.Task | None,
        mode_at_start: RunMode,
        scenario_id_at_start: str | None,
        clock: Clock,
        source: DataSource,
        pipeline: Pipeline,
    ) -> None:
        if old_task is not None:
            old_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await old_task

        this_task = asyncio.current_task()

        async for frame in source.frames():
            tick = pipeline.process(frame, mode=mode_at_start, scenario_id=scenario_id_at_start)
            self.latest_tick = tick
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
