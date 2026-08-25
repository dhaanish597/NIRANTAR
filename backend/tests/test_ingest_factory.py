"""Contract test for ingest/factory.py."""
from __future__ import annotations

import pytest

from app.core.clock import LiveClock, ScenarioClock
from app.ingest.factory import UnknownScenarioError, build_clock_and_source, load_scenario_or_raise
from app.ingest.live.stub_source import StubLiveSource
from app.ingest.replay.scenario_source import ScenarioSource
from app.schemas.mode import ModeState, RunMode


def test_load_scenario_or_raise_finds_the_smoke_fixture():
    scenario = load_scenario_or_raise("_smoke")
    assert scenario.id == "_smoke"


def test_load_scenario_or_raise_raises_for_unknown_id():
    with pytest.raises(UnknownScenarioError):
        load_scenario_or_raise("does-not-exist")


def test_live_mode_builds_live_clock_and_stub_source():
    state = ModeState(mode=RunMode.LIVE, scenario_id=None, scenario_time=None)
    clock, source = build_clock_and_source(state)
    assert isinstance(clock, LiveClock)
    assert isinstance(source, StubLiveSource)


def test_replay_mode_builds_scenario_clock_and_scenario_source():
    state = ModeState(mode=RunMode.REPLAY, scenario_id="_smoke", scenario_time=None)
    clock, source = build_clock_and_source(state, realtime=False)
    assert isinstance(clock, ScenarioClock)
    assert isinstance(source, ScenarioSource)
    assert source.realtime is False


def test_replay_mode_without_scenario_id_raises():
    state = ModeState(mode=RunMode.REPLAY, scenario_id=None, scenario_time=None)
    with pytest.raises(ValueError):
        build_clock_and_source(state)


def test_replay_mode_uses_mode_states_speed_factor_when_set():
    state = ModeState(mode=RunMode.REPLAY, scenario_id="_smoke", scenario_time=None, speed_factor=42.0)
    clock, _source = build_clock_and_source(state, realtime=False)
    assert clock.speed_factor == 42.0


def test_replay_mode_unknown_scenario_propagates():
    state = ModeState(mode=RunMode.REPLAY, scenario_id="nope", scenario_time=None)
    with pytest.raises(UnknownScenarioError):
        build_clock_and_source(state)
