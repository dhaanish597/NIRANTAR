"""Contract test for api/state.py's AppState — the background tick loop, independent of HTTP.
Uses realtime=False throughout so replay ticks arrive instantly instead of on speed_factor pacing.

Every test subscribes to the bus *before* triggering the action that produces the tick it cares
about — the bus has no replay buffer for late subscribers (core/bus.py), so triggering first and
subscribing after is a real race: a tick can be published and dropped before anyone's listening.
`drain_until_mode` (rather than asserting on the very first item) additionally tolerates a
harmless leftover tick from whatever mode was active before the action under test — e.g. one
straggler LIVE tick published by the previous run before it's cancelled.
"""
from __future__ import annotations

import asyncio

import pytest

from app.api.state import AppState
from app.audit.hash_chain import GENESIS_HASH
from app.core.bus import Topic
from app.ingest.factory import UnknownScenarioError
from app.schemas.mode import RunMode
from app.schemas.tick import TickResult

TIMEOUT = 2.0
MAX_DRAIN = 15


async def drain_until_mode(queue: asyncio.Queue, mode: RunMode) -> TickResult:
    for _ in range(MAX_DRAIN):
        tick = await asyncio.wait_for(queue.get(), timeout=TIMEOUT)
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


async def test_starts_in_live_mode_and_produces_live_ticks(app_state: AppState):
    assert app_state.mode.state.mode is RunMode.LIVE
    async with app_state.bus.subscribe(Topic.TICK) as queue:
        app_state.start()
        tick = await drain_until_mode(queue, RunMode.LIVE)
    assert tick.is_reconstructed is False


async def test_start_replay_switches_to_replay_ticks(app_state: AppState):
    app_state.start()
    async with app_state.bus.subscribe(Topic.TICK) as queue:
        await app_state.start_replay("_smoke")
        assert app_state.mode.state.mode is RunMode.REPLAY
        tick = await drain_until_mode(queue, RunMode.REPLAY)
    assert tick.scenario_id == "_smoke"
    assert tick.is_reconstructed is True


async def test_start_replay_with_unknown_scenario_raises_and_leaves_mode_unchanged(
    app_state: AppState,
):
    app_state.start()
    with pytest.raises(UnknownScenarioError):
        await app_state.start_replay("does-not-exist")
    assert app_state.mode.state.mode is RunMode.LIVE


async def test_stop_replay_returns_to_live(app_state: AppState):
    app_state.start()
    await app_state.start_replay("_smoke")
    async with app_state.bus.subscribe(Topic.TICK) as queue:
        # Drain past any tail of REPLAY ticks still in flight before proving stop_replay's
        # effect — we want the LIVE tick that comes *after* stop_replay, not a stray earlier one.
        for _ in range(MAX_DRAIN):
            tick = await asyncio.wait_for(queue.get(), timeout=TIMEOUT)
            if tick.mode is RunMode.REPLAY:
                break
        await app_state.stop_replay()
        assert app_state.mode.state.mode is RunMode.LIVE
        tick = await drain_until_mode(queue, RunMode.LIVE)
    assert tick.mode is RunMode.LIVE


async def test_replay_reaching_its_end_returns_to_live_automatically(app_state: AppState):
    app_state.start()
    async with app_state.bus.subscribe(Topic.TICK) as queue:
        await app_state.start_replay("_smoke")

        seen_replay = False
        seen_live_after_replay = False
        for _ in range(MAX_DRAIN):
            tick = await asyncio.wait_for(queue.get(), timeout=TIMEOUT)
            if tick.mode is RunMode.REPLAY:
                seen_replay = True
            elif seen_replay and tick.mode is RunMode.LIVE:
                seen_live_after_replay = True
                break

    assert seen_replay, "expected to observe at least one REPLAY tick"
    assert seen_live_after_replay, "expected replay to auto-return to LIVE after its last frame"
    assert app_state.mode.state.mode is RunMode.LIVE


async def test_restarting_a_replay_fully_resets_the_audit_log_with_no_residue(app_state: AppState):
    """BUILD_PLAN.md task 4.7: "Restart must fully reset downstream state — no residue from the
    previous run." A judge clicking "Run Case Study" a second time (same scenario or a different
    one) must not see the first run's audit hash chain bleeding into the second — otherwise two
    identical replays wouldn't produce identical TickResults, a real determinism violation
    (CLAUDE.md rule 13), not just a cosmetic one."""
    app_state.start()
    await app_state.start_replay("_smoke")
    async with app_state.bus.subscribe(Topic.TICK) as queue:
        seen = 0
        for _ in range(MAX_DRAIN):
            tick = await asyncio.wait_for(queue.get(), timeout=TIMEOUT)
            if tick.mode is RunMode.REPLAY:
                seen += 1
                if seen >= 3:
                    break
        assert seen >= 3, "expected at least 3 REPLAY ticks before restarting"

    events_before_restart = len(app_state.pipeline.audit_log.events)
    assert events_before_restart >= 3

    # Restart the SAME scenario — this is exactly what a second "Run Case Study" click does.
    await app_state.start_replay("_smoke")
    assert app_state.pipeline.audit_log.events == []
    assert app_state.pipeline.audit_log.last_hash == GENESIS_HASH

    async with app_state.bus.subscribe(Topic.TICK) as queue:
        first_tick_after_restart = await drain_until_mode(queue, RunMode.REPLAY)
    # The very first audit event of the new run must chain from the genesis hash, not from
    # wherever the previous run's chain left off.
    assert first_tick_after_restart.new_audit_events[0].prev_hash == GENESIS_HASH


async def test_shutdown_cancels_the_background_task_cleanly():
    state = AppState(realtime=False)
    state.start()
    await state.shutdown()
    assert state._task.cancelled() or state._task.done()
