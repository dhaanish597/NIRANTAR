"""THE non-negotiable Phase 0 end-to-end test (BUILD_PLAN.md task 0.14 / CLAUDE.md session
brief). Do not delete. Drives data/scenarios/_smoke.json through the real ingest → pipeline path
and proves the whole vertical slice actually works, not just its parts in isolation.

This is what `make demo-check` runs (see Makefile) and is meant to keep working forever as the
CI smoke test, even after Phase 1+ replaces every stub stage with a real one — a scenario replay
completing end to end through Pipeline is the invariant that must never break.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from app.decision.stub import escalation_stage
from app.ingest.replay.scenario_source import ScenarioSource, build_scenario_clock, load_scenario
from app.pipeline import Pipeline
from app.risk.stub import RAIN_1H_SATURATION_MM
from app.schemas.mode import RunMode

SMOKE_PATH = Path(__file__).resolve().parents[2] / "data" / "scenarios" / "_smoke.json"


async def run_smoke_scenario() -> tuple[list, Pipeline]:
    scenario = load_scenario(SMOKE_PATH)
    clock = build_scenario_clock(scenario)
    source = ScenarioSource(scenario, clock, realtime=False)  # instant — CI shouldn't wait
    pipeline = Pipeline()

    ticks = [
        pipeline.process(frame, mode=RunMode.REPLAY, scenario_id=scenario.id)
        async for frame in source.frames()
    ]
    return ticks, pipeline


async def test_smoke_scenario_completes_end_to_end_with_ten_ticks():
    ticks, _pipeline = await run_smoke_scenario()
    assert len(ticks) == 10


async def test_every_tick_is_stamped_replay_and_reconstructed():
    ticks, _pipeline = await run_smoke_scenario()
    for tick in ticks:
        assert tick.mode is RunMode.REPLAY
        assert tick.scenario_id == "_smoke"
        assert tick.aoi_id == "aizawl"
        assert tick.is_reconstructed is True


async def test_p_fail_matches_the_fabricated_rain_1h_ramp_exactly():
    """Cross-checks the pipeline's actual output against what the stub formula should produce
    for each frame's rain_1h — proves risk/, impact/, and ingest/replay/ are wired correctly
    together, not just individually correct."""
    scenario = load_scenario(SMOKE_PATH)
    ticks, _pipeline = await run_smoke_scenario()

    for tick, frame in zip(ticks, scenario.frames):
        rain_1h = frame.cells[0]["rain_1h"]
        expected_p_fail = min(1.0, rain_1h / RAIN_1H_SATURATION_MM)
        assert tick.cell_risks[0].p_fail == expected_p_fail
        # Phase 0 impact stub sets village p_isolated / priority.eps to the average across all 9
        # cells. It equals expected_p_fail (every cell shares the same rain_1h) but via a
        # sum-then-divide-by-9 path, which can differ from a direct division in the last bit —
        # pytest.approx, not ==, is the correct tool here (this is float arithmetic, not a bug).
        assert tick.priorities[0].eps == pytest.approx(expected_p_fail)


async def test_escalation_arc_rises_from_green_to_red_over_the_scenario():
    """Proves the smoke scenario is actually dramatic enough to demo: it must pass through every
    named stage (CLAUDE.md §4), not just flip once."""
    ticks, _pipeline = await run_smoke_scenario()
    stages = [escalation_stage(tick.priorities[0].eps) for tick in ticks]

    assert stages[0] == "GREEN"
    assert stages[-1] == "RED"
    assert "ORANGE" in stages
    assert "YELLOW" in stages
    # non-decreasing: this fixture never de-escalates (CLAUDE.md's hysteresis-on-downgrade rule
    # for decision/escalation.py, task 3.2, doesn't apply to a monotonically rising fixture).
    order = {"GREEN": 0, "YELLOW": 1, "ORANGE": 2, "RED": 3}
    ranks = [order[s] for s in stages]
    assert ranks == sorted(ranks)


async def test_action_cards_appear_exactly_once_escalation_reaches_orange():
    ticks, _pipeline = await run_smoke_scenario()
    stages = [escalation_stage(tick.priorities[0].eps) for tick in ticks]
    card_counts = [len(tick.new_action_cards) for tick in ticks]

    for stage, count in zip(stages, card_counts):
        if stage in ("ORANGE", "RED"):
            assert count == 1
        else:
            assert count == 0

    assert sum(card_counts) >= 1, "the smoke scenario must produce at least one action card"


async def test_every_tick_writes_exactly_one_audit_event_and_the_chain_is_unbroken():
    ticks, pipeline = await run_smoke_scenario()
    for tick in ticks:
        assert len(tick.new_audit_events) == 1
        assert tick.new_audit_events[0].kind == "AI_FLAGGED"

    events = pipeline.audit_log.events
    assert len(events) == 10
    for prev_event, event in zip(events, events[1:]):
        assert event.prev_hash == prev_event.hash


async def test_replaying_the_smoke_scenario_twice_is_byte_identical():
    """Determinism (CLAUDE.md rule 13), proven at full pipeline scope, not just ingest scope."""
    ticks_a, _ = await run_smoke_scenario()
    ticks_b, _ = await run_smoke_scenario()
    assert [t.model_dump_json() for t in ticks_a] == [t.model_dump_json() for t in ticks_b]
