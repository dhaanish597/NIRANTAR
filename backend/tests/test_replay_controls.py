"""Contract test for AppState.pause_replay()/resume_replay()/set_replay_speed() — this session's
"small connected gap" (BUILD_PLAN.md task 4.7's REST follow-up, named in task 4.9's own frontend
code comment). Same bus-subscribe-before-triggering pattern tests/test_api_state.py already
establishes.

TIMING NOTE (found by actually running this, not assumed): with `realtime=False`, none of
`ScenarioSource.frames()`'s per-frame work (`pipeline.process`, `bus.publish` on an unbounded
`asyncio.Queue`, `mode.update_scenario_time`) contains a genuine `asyncio` suspension point, so
once the background tick task starts stepping it runs the ENTIRE `_smoke` replay (all 10 frames,
including the automatic return-to-LIVE) to completion in one uninterrupted step, before the event
loop ever gets a chance to wake a test coroutine blocked on `queue.get()` — by the time a
`realtime=False` test observes its first REPLAY tick, the real backend state has often already
moved past REPLAY back to LIVE. Two different strategies are used below depending on what a test
needs to prove:
  - Tests that only need to observe pause/resume/speed-change EFFECTS with nothing already in
    flight call `pause_replay()`/`set_replay_speed()` immediately after `start_replay()` returns
    and BEFORE the first `queue.get()` — since `start_replay()` and `pause_replay()` themselves
    also never hit a real suspension point when nothing is subscribed to the MODE topic, this
    reliably pauses the scenario before its background task has executed even its first line.
  - The one test that needs REAL in-flight ticks already produced before pausing
    (`test_pause_resume_do_not_reset_the_audit_log`) uses `realtime=True` instead, so frames are
    genuinely paced (`_smoke`'s own `default_speed_factor=3600` over a 60-minute frame interval —
    1 real second per frame) and a pause mid-stream is a real behavioural event, not a race.
"""
from __future__ import annotations

import asyncio

import pytest

from app.api.state import AppState
from app.core.bus import Topic
from app.core.mode import ModeError
from app.schemas.mode import RunMode

TIMEOUT = 2.0
SHORT_TIMEOUT = 0.3
MAX_DRAIN = 15


async def drain_until_mode(queue: asyncio.Queue, mode: RunMode, *, timeout: float = TIMEOUT):
    for _ in range(MAX_DRAIN):
        tick = await asyncio.wait_for(queue.get(), timeout=timeout)
        if tick.mode is mode:
            return tick
    raise AssertionError(f"no tick with mode={mode} seen within {MAX_DRAIN} ticks")


@pytest.fixture
async def app_state():
    state = AppState(realtime=False)
    try:
        yield state
    finally:
        await state.shutdown()


async def test_pause_while_live_raises_mode_error(app_state: AppState):
    app_state.start()
    with pytest.raises(ModeError):
        await app_state.pause_replay()


async def test_resume_while_live_raises_mode_error(app_state: AppState):
    app_state.start()
    with pytest.raises(ModeError):
        await app_state.resume_replay()


async def test_set_speed_while_live_raises_mode_error(app_state: AppState):
    app_state.start()
    with pytest.raises(ModeError):
        await app_state.set_replay_speed(10.0)


async def test_pause_before_any_frame_is_produced_prevents_any_tick_from_arriving(app_state: AppState):
    # Deliberately NOT calling app_state.start() first: doing so leaves a scheduled-but-not-yet-
    # run LIVE task around, and (found by actually hitting this) StubLiveSource paces itself with
    # its own internal suspension independent of `realtime` — so that stray LIVE task can slip out
    # a tick before the REPLAY task gets a chance to cancel it, defeating the very "nothing has
    # been produced yet" property this test wants to prove. Skipping start() avoids that race.
    async with app_state.bus.subscribe(Topic.TICK) as queue:
        await app_state.start_replay("_smoke")
        await app_state.pause_replay()  # before the background task has run at all — see module note
        assert app_state.mode.state.paused is True

        with pytest.raises(asyncio.TimeoutError):
            await asyncio.wait_for(queue.get(), timeout=SHORT_TIMEOUT)


async def test_resume_after_immediate_pause_lets_the_replay_proceed(app_state: AppState):
    async with app_state.bus.subscribe(Topic.TICK) as queue:
        await app_state.start_replay("_smoke")
        await app_state.pause_replay()
        await app_state.resume_replay()
        assert app_state.mode.state.paused is False

        tick = await drain_until_mode(queue, RunMode.REPLAY)
        assert tick.mode is RunMode.REPLAY


async def test_set_speed_updates_mode_state_and_the_live_scenario_clock(app_state: AppState):
    app_state.start()
    await app_state.start_replay("_smoke")
    await app_state.set_replay_speed(42.0)
    assert app_state.mode.state.speed_factor == 42.0
    # The exact same clock object frames()'s real-time pacing reads from must reflect the change
    # immediately (task 4.7's own documented "no restart needed" behaviour) — proving this isn't
    # just cosmetic on ModeState.
    assert app_state._current_source.clock.speed_factor == 42.0


async def test_set_speed_rejects_non_positive_factor(app_state: AppState):
    app_state.start()
    await app_state.start_replay("_smoke")
    with pytest.raises(ValueError):
        await app_state.set_replay_speed(0.0)


async def test_pause_resume_do_not_reset_the_audit_log():
    """Distinguishes pause/resume (this task) from restart (task 4.7's OWN reset behaviour,
    already tested in test_api_state.py) — pausing mid-replay must NOT wipe accumulated audit
    events the way starting a fresh replay does. Uses realtime=True so there genuinely are ticks
    already in flight before pause is called — see module docstring's TIMING NOTE for why
    realtime=False can't reliably prove a MID-replay pause."""
    state = AppState(realtime=True)
    try:
        async with state.bus.subscribe(Topic.TICK) as queue:
            await state.start_replay("_smoke")
            for _ in range(2):
                await drain_until_mode(queue, RunMode.REPLAY, timeout=5.0)

        events_before = len(state.pipeline.audit_log.events)
        assert events_before >= 2

        await state.pause_replay()
        assert state.mode.state.paused is True
        await state.resume_replay()
        assert state.mode.state.paused is False

        assert len(state.pipeline.audit_log.events) == events_before
    finally:
        await state.shutdown()
