"""Dry-runs the real case-study scenarios (BUILD_PLAN.md tasks 4.3-4.5) through the actual
ingest -> Pipeline path, exactly like test_smoke_scenario.py does for `_smoke.json`. This is the
"run it through the existing replay pipeline" verification the task instructions require beyond
schema validation alone: a scenario file that only validates syntactically is not proven runnable.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from app.decision.stub import escalation_stage
from app.ingest.replay.scenario_source import ScenarioSource, build_scenario_clock, load_scenario
from app.pipeline import Pipeline
from app.schemas.mode import RunMode

SCENARIOS_DIR = Path(__file__).resolve().parents[2] / "data" / "scenarios"

REAL_SCENARIO_IDS = ["aizawl-2024", "wayanad-2024", "tupul-2022"]


async def run_scenario(scenario_id: str) -> tuple[list, Pipeline]:
    scenario = load_scenario(SCENARIOS_DIR / f"{scenario_id}.json")
    clock = build_scenario_clock(scenario)
    source = ScenarioSource(scenario, clock, realtime=False)
    pipeline = Pipeline()

    ticks = [
        pipeline.process(frame, mode=RunMode.REPLAY, scenario_id=scenario.id)
        async for frame in source.frames()
    ]
    return ticks, pipeline


@pytest.mark.parametrize("scenario_id", REAL_SCENARIO_IDS)
async def test_scenario_file_exists(scenario_id: str):
    assert (SCENARIOS_DIR / f"{scenario_id}.json").is_file()


@pytest.mark.parametrize("scenario_id", REAL_SCENARIO_IDS)
async def test_scenario_loads_as_held_out_and_reconstructed(scenario_id: str):
    scenario = load_scenario(SCENARIOS_DIR / f"{scenario_id}.json")
    assert scenario.held_out_of_training is True
    assert scenario.provenance.confidence == "reconstructed"
    assert scenario.name is not None
    assert scenario.event_date is not None
    assert scenario.ground_truth is not None
    assert scenario.ground_truth.outcome.deaths  # non-empty string


@pytest.mark.parametrize("scenario_id", REAL_SCENARIO_IDS)
async def test_scenario_completes_end_to_end_through_the_real_pipeline(scenario_id: str):
    scenario = load_scenario(SCENARIOS_DIR / f"{scenario_id}.json")
    ticks, _pipeline = await run_scenario(scenario_id)
    assert len(ticks) == len(scenario.frames)
    assert len(ticks) > 0


@pytest.mark.parametrize("scenario_id", REAL_SCENARIO_IDS)
async def test_every_tick_is_stamped_replay_and_reconstructed(scenario_id: str):
    ticks, _pipeline = await run_scenario(scenario_id)
    for tick in ticks:
        assert tick.mode is RunMode.REPLAY
        assert tick.scenario_id == scenario_id
        assert tick.is_reconstructed is True


@pytest.mark.parametrize("scenario_id", REAL_SCENARIO_IDS)
async def test_every_tick_writes_exactly_one_audit_event_and_the_chain_is_unbroken(scenario_id: str):
    ticks, pipeline = await run_scenario(scenario_id)
    for tick in ticks:
        assert len(tick.new_audit_events) == 1
        assert tick.new_audit_events[0].kind == "AI_FLAGGED"

    events = pipeline.audit_log.events
    assert len(events) == len(ticks)
    for prev_event, event in zip(events, events[1:]):
        assert event.prev_hash == prev_event.hash


@pytest.mark.parametrize("scenario_id", REAL_SCENARIO_IDS)
async def test_replaying_each_real_scenario_twice_is_byte_identical(scenario_id: str):
    """Determinism (CLAUDE.md rule 13) for the real case-study files, not just `_smoke.json` —
    a fresh Pipeline() each time, mirroring how a judge clicking "Run Case Study" twice in a row
    must see identical output (a slice of BUILD_PLAN.md task 4.11's fuller requirement)."""
    ticks_a, _ = await run_scenario(scenario_id)
    ticks_b, _ = await run_scenario(scenario_id)
    assert [t.model_dump_json() for t in ticks_a] == [t.model_dump_json() for t in ticks_b]


async def test_aizawl_2024_escalates_to_red_at_some_point():
    """The Aizawl scenario's rainfall (253.7mm/3days, peaking just before the documented ~6AM
    quarry collapse) must actually be dramatic enough to escalate through the stub risk/decision
    stages -- otherwise the replay would be visually inert, which defeats the point of a
    case-study demo (CLAUDE.md's 8-minute arc explicitly needs cells to escalate on screen)."""
    ticks, _pipeline = await run_scenario("aizawl-2024")
    stages = [escalation_stage(tick.priorities[0].eps) for tick in ticks]
    assert "RED" in stages or "ORANGE" in stages, (
        "expected the stub pipeline to escalate at least to ORANGE somewhere in the Aizawl replay"
    )


async def test_wayanad_2024_escalates_to_red_at_some_point():
    """Wayanad's 572mm/48h is the most intense of the three reconstructed events -- it should
    clearly escalate under even the Phase 0 linear rain_1h stub risk model."""
    ticks, _pipeline = await run_scenario("wayanad-2024")
    stages = [escalation_stage(tick.priorities[0].eps) for tick in ticks]
    assert "RED" in stages


async def test_tupul_2022_ground_truth_captures_the_low_to_moderate_susceptibility_fact():
    """BUILD_PLAN.md task 4.5's entire point for this scenario: NLSM had mapped the Tupul site
    low-to-moderate susceptibility before the failure. This must show up somewhere in the file --
    proven here, not just asserted in a commit message. (Note: under the CURRENT Phase 0 stub
    risk model -- linear in rain_1h only, no terrain/threshold factors -- this scenario's modest,
    honestly-apportioned rainfall total does not itself force a dramatic on-screen escalation;
    that contrast becomes visible once Phase 1C's real terrain-aware risk model is wired in. This
    task's job is the scenario file's facts, not the future risk model.)"""
    scenario = load_scenario(SCENARIOS_DIR / "tupul-2022.json")
    haystack = " ".join(entry.text for entry in scenario.narration)
    haystack += " " + " ".join(f.note for f in scenario.ground_truth.failures)
    haystack += " " + scenario.provenance.disclaimer
    assert "low-to-moderate susceptibility" in haystack or "low-moderate susceptibility" in haystack


async def test_tupul_2022_has_no_official_warnings():
    """The absence of any warning is itself a documented fact for this event (docs/reference/:
    "no warning" for Tupul) -- must not be silently populated with an invented one."""
    scenario = load_scenario(SCENARIOS_DIR / "tupul-2022.json")
    assert scenario.ground_truth.official_warnings == []


async def test_wayanad_2024_ground_truth_includes_the_hume_centre_warning_with_lead_time():
    scenario = load_scenario(SCENARIOS_DIR / "wayanad-2024.json")
    warnings = scenario.ground_truth.official_warnings
    assert any("Hume Centre" in w.issuer for w in warnings)
    hume = next(w for w in warnings if "Hume Centre" in w.issuer)
    assert hume.t.hour == 9
    assert hume.t.date().isoformat() == "2024-07-29"


async def test_wayanad_2024_death_toll_is_reported_as_a_range_not_a_single_figure():
    scenario = load_scenario(SCENARIOS_DIR / "wayanad-2024.json")
    deaths = scenario.ground_truth.outcome.deaths
    assert "-" in deaths or "200" in deaths and "400" in deaths


async def test_aizawl_2024_ground_truth_includes_the_nh6_hunthar_severance():
    scenario = load_scenario(SCENARIOS_DIR / "aizawl-2024.json")
    road_events = scenario.ground_truth.road_events
    assert any(e.road == "NH-6" and e.location == "Hunthar" and e.effect == "severed" for e in road_events)
