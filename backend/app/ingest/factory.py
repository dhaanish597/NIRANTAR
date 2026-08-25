"""Builds the (Clock, DataSource) pair for the current mode (BUILD_PLAN.md task 0.11).

This is the one place outside core/ allowed to branch on mode — CLAUDE.md §2 names `ingest/` as
one of the four places permitted to know which mode is active. Callers (api/state.py) pass a
ModeState through and get back a Clock + DataSource; they never branch on mode themselves.
"""
from __future__ import annotations

from pathlib import Path

from app.core.clock import Clock, LiveClock
from app.ingest.base import DataSource
from app.ingest.live.stub_source import StubLiveSource
from app.ingest.replay.scenario_source import ScenarioSource, build_scenario_clock, load_scenario
from app.schemas.mode import ModeState, RunMode
from app.schemas.scenario import ScenarioFile

SCENARIOS_DIR = Path(__file__).resolve().parents[3] / "data" / "scenarios"


class UnknownScenarioError(Exception):
    """No scenario file exists for the requested id."""


def scenario_path(scenario_id: str) -> Path:
    return SCENARIOS_DIR / f"{scenario_id}.json"


def load_scenario_or_raise(scenario_id: str) -> ScenarioFile:
    path = scenario_path(scenario_id)
    if not path.is_file():
        raise UnknownScenarioError(f"no scenario file for {scenario_id!r} (looked at {path})")
    return load_scenario(path)


def build_clock_and_source(
    mode_state: ModeState, *, realtime: bool = True
) -> tuple[Clock, DataSource]:
    if mode_state.mode is RunMode.LIVE:
        clock: Clock = LiveClock()
        # TODO(Phase 1): real AOI selection — Phase 0 only ever runs Aizawl.
        return clock, StubLiveSource(clock, aoi_id="aizawl")

    if mode_state.scenario_id is None:
        raise ValueError("REPLAY mode requires a scenario_id")

    scenario = load_scenario_or_raise(mode_state.scenario_id)
    scenario_clock = build_scenario_clock(scenario)
    if mode_state.speed_factor:
        scenario_clock.speed_factor = mode_state.speed_factor
    return scenario_clock, ScenarioSource(scenario, scenario_clock, realtime=realtime)
