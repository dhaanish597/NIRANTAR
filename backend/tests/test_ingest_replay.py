"""Contract test for ingest/replay/scenario_source.py, exercised against the real
data/scenarios/_smoke.json fixture (BUILD_PLAN.md task 0.14 — used forever as the CI smoke test).
"""
from __future__ import annotations

import asyncio
from datetime import timedelta
from pathlib import Path

import pytest
from pydantic import ValidationError

from app.core.clock import ScenarioClock
from app.ingest.base import DataSource
from app.ingest.replay.scenario_source import (
    ScenarioSource,
    _merged_cell_observation,
    build_scenario_clock,
    load_scenario,
)
from app.schemas.scenario import ScenarioFile

SMOKE_PATH = Path(__file__).resolve().parents[2] / "data" / "scenarios" / "_smoke.json"


def test_smoke_fixture_exists():
    assert SMOKE_PATH.is_file(), f"expected {SMOKE_PATH} to exist (BUILD_PLAN.md task 0.14)"


def test_load_scenario_parses_the_smoke_fixture():
    scenario = load_scenario(SMOKE_PATH)
    assert scenario.id == "_smoke"
    assert scenario.aoi_id == "aizawl"
    assert scenario.held_out_of_training is False
    assert scenario.provenance.confidence == "fabricated"
    assert len(scenario.frames) == 10


def test_build_scenario_clock_matches_scenario_config():
    scenario = load_scenario(SMOKE_PATH)
    clock = build_scenario_clock(scenario)
    assert clock.start == scenario.clock.start
    assert clock.end == scenario.clock.end
    assert clock.speed_factor == scenario.clock.default_speed_factor


async def test_scenario_source_satisfies_data_source_protocol():
    scenario = load_scenario(SMOKE_PATH)
    clock = build_scenario_clock(scenario)
    source = ScenarioSource(scenario, clock, realtime=False)
    assert isinstance(source, DataSource)


async def test_scenario_source_yields_all_frames_with_rising_rainfall_non_realtime():
    scenario = load_scenario(SMOKE_PATH)
    clock = build_scenario_clock(scenario)
    source = ScenarioSource(scenario, clock, realtime=False)

    frames = [frame async for frame in source.frames()]

    assert len(frames) == 10
    assert [f.t for f in frames] == [sf.t for sf in scenario.frames]

    rain_1h_by_frame = [frame.cells[0].rain_1h for frame in frames]
    assert rain_1h_by_frame == sorted(rain_1h_by_frame)  # rises monotonically
    assert rain_1h_by_frame[0] < rain_1h_by_frame[-1]

    for frame in frames:
        assert frame.aoi_id == "aizawl"
        assert len(frame.cells) == 9
        for cell in frame.cells:
            assert cell.is_reconstructed is True
            assert cell.source == "scenario:_smoke"

    assert clock.finished is True


async def test_scenario_source_advances_the_clock_to_each_frame():
    scenario = load_scenario(SMOKE_PATH)
    clock = build_scenario_clock(scenario)
    source = ScenarioSource(scenario, clock, realtime=False)

    async for frame in source.frames():
        assert clock.now() == frame.t


async def test_replaying_twice_produces_byte_identical_frames():
    """A slice of the Phase 4 determinism requirement (BUILD_PLAN.md task 4.11), proven now
    while the machinery is small enough to be sure of."""
    scenario = load_scenario(SMOKE_PATH)

    clock_a = build_scenario_clock(scenario)
    frames_a = [f async for f in ScenarioSource(scenario, clock_a, realtime=False).frames()]

    clock_b = build_scenario_clock(scenario)
    frames_b = [f async for f in ScenarioSource(scenario, clock_b, realtime=False).frames()]

    assert [f.model_dump_json() for f in frames_a] == [f.model_dump_json() for f in frames_b]


def test_frame_provenance_is_flattened_to_str_str():
    scenario = load_scenario(SMOKE_PATH)
    clock = build_scenario_clock(scenario)
    source = ScenarioSource(scenario, clock, realtime=False)
    assert source._provenance == {
        "scenario_id": "_smoke",
        "confidence": "fabricated",
        "disclaimer": scenario.provenance.disclaimer,
    }


class TestMergedCellObservation:
    def test_cell_override_wins_over_default(self):
        obs = _merged_cell_observation(
            {"cell_id": "c1", "rain_1h": 99.0},
            {
                "rain_1h": 1.0, "rain_6h": 1.0, "rain_24h": 1.0, "rain_72h": 1.0,
                "antecedent_7d": 1.0, "antecedent_15d": 1.0, "antecedent_30d": 1.0,
            },
            scenario_id="test",
            frame_t="t0",
        )
        assert obs.rain_1h == 99.0
        assert obs.rain_6h == 1.0

    def test_missing_required_field_raises_with_helpful_message(self):
        with pytest.raises(ValueError, match="rain_1h"):
            _merged_cell_observation(
                {"cell_id": "c1"},
                {"rain_6h": 1.0, "rain_24h": 1.0, "rain_72h": 1.0, "antecedent_7d": 1.0,
                 "antecedent_15d": 1.0, "antecedent_30d": 1.0},
                scenario_id="test",
                frame_t="t0",
            )

    def test_missing_cell_id_raises(self):
        with pytest.raises(ValueError, match="cell_id"):
            _merged_cell_observation({}, {}, scenario_id="test", frame_t="t0")


def test_scenario_file_rejects_end_before_start():
    with pytest.raises(ValidationError):
        ScenarioFile(
            id="bad",
            aoi_id="aizawl",
            held_out_of_training=False,
            provenance={"confidence": "fabricated", "method": "test fixture", "disclaimer": "test"},
            clock={
                "start": "2025-01-02T00:00:00+05:30",
                "end": "2025-01-01T00:00:00+05:30",
                "frame_interval_minutes": 60,
                "default_speed_factor": 1.0,
            },
            frames=[{"t": "2025-01-01T00:00:00+05:30", "cells": [], "defaults": {}}],
        )


def test_scenario_file_rejects_no_frames():
    with pytest.raises(ValidationError):
        ScenarioFile(
            id="bad",
            aoi_id="aizawl",
            held_out_of_training=False,
            provenance={"confidence": "fabricated", "method": "test fixture", "disclaimer": "test"},
            clock={
                "start": "2025-01-01T00:00:00+05:30",
                "end": "2025-01-01T01:00:00+05:30",
                "frame_interval_minutes": 60,
                "default_speed_factor": 1.0,
            },
            frames=[],
        )


class TestReplayControls:
    """BUILD_PLAN.md task 4.7: pause / resume / speed / scrub-to-timestamp / restart. Every
    control here must be safe to call from another task while `frames()` is actively iterating
    in a background task — mirroring how a browser's replay control bar would drive this."""

    def _fresh_source(self, *, realtime: bool = False) -> ScenarioSource:
        scenario = load_scenario(SMOKE_PATH)
        clock = build_scenario_clock(scenario)
        return ScenarioSource(scenario, clock, realtime=realtime)

    async def test_not_paused_by_default(self):
        source = self._fresh_source()
        assert source.paused is False

    async def test_pause_blocks_the_frame_stream_until_resumed(self):
        source = self._fresh_source()
        source.pause()
        assert source.paused is True

        gen = source.frames()
        task = asyncio.ensure_future(gen.__anext__())
        await asyncio.sleep(0)  # let the generator start and hit `await self._paused.wait()`
        assert not task.done(), "frames() should be blocked while paused"

        source.resume()
        assert source.paused is False
        frame = await asyncio.wait_for(task, timeout=1.0)
        assert frame.t == source.scenario.frames[0].t

    async def test_set_speed_mutates_the_clocks_speed_factor_directly(self):
        source = self._fresh_source()
        source.set_speed(42.0)
        assert source.clock.speed_factor == 42.0

    async def test_set_speed_rejects_non_positive(self):
        source = self._fresh_source()
        with pytest.raises(ValueError):
            source.set_speed(0.0)
        with pytest.raises(ValueError):
            source.set_speed(-5.0)

    async def test_realtime_source_responds_to_a_speed_change_made_mid_stream(self):
        """Proves set_speed() affects an already-running realtime consumer, not just the object's
        own attribute — the whole point of task 4.7's "speed" control."""
        source = self._fresh_source(realtime=True)
        source.set_speed(1_000_000.0)  # fast enough that any per-frame sleep is negligible

        async def _collect() -> list:
            return [f async for f in source.frames()]

        frames = await asyncio.wait_for(_collect(), timeout=2.0)
        assert len(frames) == 10

    async def test_seek_jumps_forward_to_the_exact_target_frame(self):
        source = self._fresh_source()
        gen = source.frames()
        first = await gen.__anext__()
        assert first.t == source.scenario.frames[0].t

        target = source.scenario.frames[5].t
        source.seek(target)
        jumped = await gen.__anext__()
        assert jumped.t == target
        assert source.clock.now() == target

    async def test_seek_to_a_timestamp_between_frames_lands_on_the_next_frame_at_or_after_it(self):
        source = self._fresh_source()
        gen = source.frames()
        await gen.__anext__()

        frame_2_t = source.scenario.frames[2].t
        frame_3_t = source.scenario.frames[3].t
        between = frame_2_t + (frame_3_t - frame_2_t) / 2
        source.seek(between)
        jumped = await gen.__anext__()
        assert jumped.t == frame_3_t

    async def test_seek_past_the_end_clamps_to_the_last_frame(self):
        source = self._fresh_source()
        gen = source.frames()
        await gen.__anext__()
        source.seek(source.scenario.clock.end + timedelta(days=1))
        jumped = await gen.__anext__()
        assert jumped.t == source.scenario.frames[-1].t
        with pytest.raises(StopAsyncIteration):
            await gen.__anext__()

    async def test_seek_backward_mid_stream_is_allowed_for_scrubbing(self):
        source = self._fresh_source()
        gen = source.frames()
        for _ in range(6):
            await gen.__anext__()  # now at frame index 5

        earlier_target = source.scenario.frames[1].t
        source.seek(earlier_target)
        jumped = await gen.__anext__()
        assert jumped.t == earlier_target
        assert source.clock.now() == earlier_target

    async def test_restart_replays_from_the_beginning_byte_identical_to_the_first_run(self):
        source = self._fresh_source()
        first_run = [f async for f in source.frames()]
        assert source.clock.finished is True

        source.restart()
        assert source.clock.now() == source.scenario.clock.start

        second_run = [f async for f in source.frames()]
        assert [f.model_dump_json() for f in first_run] == [f.model_dump_json() for f in second_run]

    async def test_restart_clears_pending_pause_and_seek_state(self):
        source = self._fresh_source()
        source.pause()
        source.seek(source.scenario.frames[3].t)

        source.restart()
        assert source.paused is False

        gen = source.frames()
        first = await asyncio.wait_for(gen.__anext__(), timeout=1.0)
        assert first.t == source.scenario.frames[0].t
