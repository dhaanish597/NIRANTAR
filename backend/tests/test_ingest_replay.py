"""Contract test for ingest/replay/scenario_source.py, exercised against the real
data/scenarios/_smoke.json fixture (BUILD_PLAN.md task 0.14 — used forever as the CI smoke test).
"""
from __future__ import annotations

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
    assert scenario.provenance["confidence"] == "fabricated"
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
        "disclaimer": scenario.provenance["disclaimer"],
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
            provenance={"confidence": "fabricated"},
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
            provenance={"confidence": "fabricated"},
            clock={
                "start": "2025-01-01T00:00:00+05:30",
                "end": "2025-01-01T01:00:00+05:30",
                "frame_interval_minutes": 60,
                "default_speed_factor": 1.0,
            },
            frames=[],
        )
