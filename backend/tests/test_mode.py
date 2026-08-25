"""Contract test for core/mode.py."""
from __future__ import annotations

import asyncio
from datetime import datetime, timezone

import pytest

from app.core.bus import Bus, Topic
from app.core.mode import ModeError, ModeMachine
from app.schemas.mode import RunMode

UTC = timezone.utc


def make_machine() -> tuple[ModeMachine, Bus]:
    bus = Bus()
    return ModeMachine(bus), bus


async def test_starts_in_live_mode():
    machine, _ = make_machine()
    assert machine.state.mode is RunMode.LIVE
    assert machine.state.scenario_id is None


async def test_start_replay_enters_replay_with_scenario_id():
    machine, _ = make_machine()
    state = await machine.start_replay("_smoke", speed_factor=3600.0)
    assert state.mode is RunMode.REPLAY
    assert state.scenario_id == "_smoke"
    assert state.speed_factor == 3600.0
    assert state.paused is False


async def test_start_replay_rejects_non_positive_speed_factor():
    machine, _ = make_machine()
    with pytest.raises(ValueError):
        await machine.start_replay("_smoke", speed_factor=0.0)


async def test_pause_and_resume_toggle_paused_flag():
    machine, _ = make_machine()
    await machine.start_replay("_smoke")
    state = await machine.pause()
    assert state.paused is True
    state = await machine.resume()
    assert state.paused is False


async def test_pause_outside_replay_raises_mode_error():
    machine, _ = make_machine()
    with pytest.raises(ModeError):
        await machine.pause()


async def test_resume_outside_replay_raises_mode_error():
    machine, _ = make_machine()
    with pytest.raises(ModeError):
        await machine.resume()


async def test_set_speed_updates_speed_factor():
    machine, _ = make_machine()
    await machine.start_replay("_smoke", speed_factor=1.0)
    state = await machine.set_speed(60.0)
    assert state.speed_factor == 60.0


async def test_set_speed_outside_replay_raises():
    machine, _ = make_machine()
    with pytest.raises(ModeError):
        await machine.set_speed(60.0)


async def test_set_speed_rejects_non_positive():
    machine, _ = make_machine()
    await machine.start_replay("_smoke")
    with pytest.raises(ValueError):
        await machine.set_speed(-1.0)


async def test_stop_replay_returns_to_live_and_clears_scenario():
    machine, _ = make_machine()
    await machine.start_replay("_smoke")
    state = await machine.stop_replay()
    assert state.mode is RunMode.LIVE
    assert state.scenario_id is None
    assert state.paused is False


async def test_starting_a_new_scenario_while_replaying_switches_cleanly():
    machine, _ = make_machine()
    await machine.start_replay("_smoke")
    await machine.pause()
    state = await machine.start_replay("aizawl-2024")
    assert state.scenario_id == "aizawl-2024"
    assert state.paused is False  # switching scenarios resets pause state


async def test_update_scenario_time_only_applies_during_replay():
    machine, _ = make_machine()
    t = datetime(2024, 5, 28, 6, 0, tzinfo=UTC)
    state = machine.update_scenario_time(t)
    assert state.scenario_time is None  # ignored — we're in LIVE

    await machine.start_replay("_smoke")
    state = machine.update_scenario_time(t)
    assert state.scenario_time == t


async def test_transitions_publish_to_mode_topic():
    machine, bus = make_machine()
    async with bus.subscribe(Topic.MODE) as queue:
        await machine.start_replay("_smoke")
        published = await asyncio.wait_for(queue.get(), timeout=1.0)
        assert published.mode is RunMode.REPLAY

        await machine.pause()
        published = await asyncio.wait_for(queue.get(), timeout=1.0)
        assert published.paused is True


async def test_update_scenario_time_does_not_publish():
    machine, bus = make_machine()
    await machine.start_replay("_smoke")
    async with bus.subscribe(Topic.MODE) as queue:
        machine.update_scenario_time(datetime(2024, 5, 28, 6, 0, tzinfo=UTC))
        await asyncio.sleep(0)  # let any (unwanted) publish task settle
        assert queue.empty()
