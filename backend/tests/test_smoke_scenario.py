"""THE non-negotiable Phase 0 end-to-end test (BUILD_PLAN.md task 0.14 / CLAUDE.md session
brief). Do not delete. Drives data/scenarios/_smoke.json through the real ingest → pipeline path
and proves the whole vertical slice actually works, not just its parts in isolation.

This is what `make demo-check` runs (see Makefile) and is meant to keep working forever as the
CI smoke test, even after Phase 1+ replaces every stub stage with a real one — a scenario replay
completing end to end through Pipeline is the invariant that must never break.

A later session (1) wired pipeline.py to the real risk/impact/decision modules and (2) remapped
_smoke.json's 9 cell_ids from the Phase 0 stub convention onto 9 REAL cells.gpkg cells — each one
a real village's actual nearest analysis cell (see pipeline.py's module docstring and grid.ts's
REMAPPED_REAL_CELL_POSITIONS for the full rationale/mapping). So this file's assertions changed
from "the Phase 0 stub formula" to "the real pipeline, driving real villages" — same invariant
(a full scenario replay produces a real, dramatic, end-to-end escalation), different mechanism.
Requires real Aizawl static data (gitignored — see test_pipeline.py's own HAS_REAL_AIZAWL_DATA
note); skipped, not faked, when it's absent.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from app.ingest.replay.scenario_source import ScenarioSource, build_scenario_clock, load_scenario
from app.pipeline import Pipeline
from app.schemas.mode import RunMode

SMOKE_PATH = Path(__file__).resolve().parents[2] / "data" / "scenarios" / "_smoke.json"

_REPO_ROOT = Path(__file__).resolve().parents[2]
HAS_REAL_AIZAWL_DATA = (
    (_REPO_ROOT / "data" / "static" / "aizawl" / "cells.gpkg").is_file()
    and (_REPO_ROOT / "data" / "static" / "aizawl" / "exposure.gpkg").is_file()
    and (_REPO_ROOT / "data" / "osm" / "aizawl_graph.pkl").is_file()
)

# Tuirini — a real village, real name, in exposure.gpkg — whose real nearest analysis cell
# (aizawl_054_046) is one of the 9 cells the scenario's uniform rain ramp now drives directly
# (grid.ts's REMAPPED_REAL_CELL_POSITIONS, "was aizawl_423"). Tracking one specific, known real
# village (rather than `tick.priorities[0]`, whose order depends on exposure.gpkg iteration order
# and is not a stable index once there are many real villages, not one synthetic one) is what lets
# these tests assert something precise about the real pipeline. Chosen specifically because its
# real terrain-only ML baseline (~0.07 at zero rainfall — the lowest of the 9 remapped cells; see
# the cell-id migration commit for how this was checked) is low enough that the exceedance-driven
# rain ramp, not a high terrain floor, is what actually produces the GREEN->RED arc below — a
# village like Durtlang (aizawl_040_026), whose terrain-only baseline is already ~0.70, would
# start at ORANGE regardless of rain and couldn't demonstrate the full range.
TRACKED_VILLAGE_ID = "v_12249036273"


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


def _tracked_priority(tick):
    return next((p for p in tick.priorities if p.village_id == TRACKED_VILLAGE_ID), None)


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


@pytest.mark.skipif(not HAS_REAL_AIZAWL_DATA, reason="requires real Aizawl static data")
async def test_cell_risks_rise_with_the_scenarios_rain_ramp_and_use_the_real_model():
    """Proves risk/, impact/, and ingest/replay/ are wired correctly together against REAL data,
    not just individually correct: p_fail must trend upward as the scenario's rain ramp rises, and
    at least one cell must be a genuine `xgb_terrain_v1` ML prediction, not just the threshold-only
    fallback — all 9 remapped cells have real, valid terrain (verified when the mapping was built),
    so the real model is exercised, not bypassed."""
    ticks, _pipeline = await run_smoke_scenario()

    max_p_fails = [max(r.p_fail for r in tick.cell_risks) for tick in ticks]
    assert max_p_fails[0] < max_p_fails[-1]
    assert max_p_fails == sorted(max_p_fails), "the ramp is monotonic; risk must not go backwards"

    model_versions = {r.model_version for tick in ticks for r in tick.cell_risks}
    assert any(v != "threshold_only_v1" for v in model_versions), (
        "expected at least one real ML-matched cell (all 9 remapped cells have valid terrain); "
        f"got only {model_versions} — the cell-id remapping may have broken"
    )


async def _run_smoke_scenario_tracking_stage_per_tick() -> list[str]:
    """Like `run_smoke_scenario()`, but records TRACKED_VILLAGE_ID's escalation stage
    immediately after each tick — `EscalationStateMachine.current_stage()` returns LIVE state, so
    reading it in a separate loop after `run_smoke_scenario()` has already produced every tick
    would read the same final (post-scenario) stage 10 times over, not a per-tick history. This
    was a real bug caught here, not assumed."""
    scenario = load_scenario(SMOKE_PATH)
    clock = build_scenario_clock(scenario)
    source = ScenarioSource(scenario, clock, realtime=False)
    pipeline = Pipeline()

    stages = []
    async for frame in source.frames():
        pipeline.process(frame, mode=RunMode.REPLAY, scenario_id=scenario.id)
        stages.append(pipeline.escalation.current_stage(TRACKED_VILLAGE_ID))
    return stages


@pytest.mark.skipif(not HAS_REAL_AIZAWL_DATA, reason="requires real Aizawl static data")
async def test_escalation_arc_rises_from_green_to_red_over_the_scenario():
    """Proves the smoke scenario is actually dramatic enough to demo: a real, named village must
    pass through every named stage (CLAUDE.md §4), not just flip once."""
    stages = await _run_smoke_scenario_tracking_stage_per_tick()

    assert stages[0] in ("GREEN", "YELLOW")  # first tick's rain_1h=0.25mm is mild, not zero
    assert stages[-1] == "RED"
    assert "ORANGE" in stages


@pytest.mark.skipif(not HAS_REAL_AIZAWL_DATA, reason="requires real Aizawl static data")
async def test_action_cards_appear_once_the_tracked_village_reaches_orange():
    """`build_action_card` fires on any tick the tracked village is ORANGE/RED (pipeline.py builds
    one every alert-worthy tick, not only on the transition tick — see pipeline.py's decision-stage
    loop), so once the escalation arc test above confirms this village reaches RED, at least one
    real card for it must exist somewhere in the run."""
    ticks, _pipeline = await run_smoke_scenario()

    all_card_village_ids = {c.village_id for tick in ticks for c in tick.new_action_cards}
    assert TRACKED_VILLAGE_ID in all_card_village_ids, (
        "expected the tracked village to receive at least one action card once it reached "
        "ORANGE/RED over the course of the scenario"
    )


@pytest.mark.skipif(not HAS_REAL_AIZAWL_DATA, reason="requires real Aizawl static data")
async def test_every_tick_writes_at_least_the_ai_flagged_audit_event_and_the_chain_is_unbroken():
    """Every tick writes exactly one AI_FLAGGED event (Phase 0's original invariant), PLUS
    whatever real ESCALATED events real villages' stage transitions produced this tick (task 3.2)
    — multiple real villages sharing the same uniform rain ramp can genuinely transition on the
    same tick, so "exactly one event per tick" is no longer the right assertion; "AI_FLAGGED is
    always first, and the hash chain is unbroken across the WHOLE run" still is."""
    ticks, pipeline = await run_smoke_scenario()
    for tick in ticks:
        assert len(tick.new_audit_events) >= 1
        assert tick.new_audit_events[0].kind == "AI_FLAGGED"

    events = pipeline.audit_log.events
    assert len(events) >= 10  # at least the 10 AI_FLAGGED events, plus any real ESCALATED ones
    for prev_event, event in zip(events, events[1:]):
        assert event.prev_hash == prev_event.hash


@pytest.mark.skipif(not HAS_REAL_AIZAWL_DATA, reason="requires real Aizawl static data")
async def test_replaying_the_smoke_scenario_twice_is_byte_identical():
    """Determinism (CLAUDE.md rule 13), proven at full pipeline scope, not just ingest scope."""
    ticks_a, _ = await run_smoke_scenario()
    ticks_b, _ = await run_smoke_scenario()
    assert [t.model_dump_json() for t in ticks_a] == [t.model_dump_json() for t in ticks_b]
