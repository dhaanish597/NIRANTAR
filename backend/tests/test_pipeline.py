"""Contract test for pipeline.py — single-frame behavior. The full multi-frame smoke scenario
lives in test_smoke_scenario.py (BUILD_PLAN.md task 0.14)."""
from __future__ import annotations

from app.pipeline import Pipeline
from app.schemas.ingest import CellObservation, ObservationFrame
from app.schemas.mode import RunMode

T = "2025-01-01T00:00:00+05:30"


def make_frame(rain_1h: float = 5.0) -> ObservationFrame:
    return ObservationFrame(
        t=T,
        aoi_id="aizawl",
        cells=[
            CellObservation(
                cell_id="c1", rain_1h=rain_1h, rain_6h=0.0, rain_24h=0.0, rain_72h=0.0,
                antecedent_7d=0.0, antecedent_15d=0.0, antecedent_30d=0.0,
                soil_moisture=None, insar_velocity_mm_yr=None,
                source="test", is_reconstructed=True,
            )
        ],
        provenance={},
    )


def test_process_returns_a_tick_result_stamped_with_mode_and_scenario_id():
    pipeline = Pipeline()
    tick = pipeline.process(make_frame(), mode=RunMode.REPLAY, scenario_id="_smoke")
    assert tick.mode is RunMode.REPLAY
    assert tick.scenario_id == "_smoke"
    assert tick.aoi_id == "aizawl"
    assert tick.is_reconstructed is True


def test_process_always_produces_exactly_one_audit_event():
    pipeline = Pipeline()
    tick = pipeline.process(make_frame(), mode=RunMode.LIVE)
    assert len(tick.new_audit_events) == 1
    assert tick.new_audit_events[0].kind == "AI_FLAGGED"


def test_low_rain_produces_no_action_card():
    pipeline = Pipeline()
    tick = pipeline.process(make_frame(rain_1h=1.0), mode=RunMode.LIVE)
    assert tick.new_action_cards == []


def test_high_rain_produces_an_action_card():
    pipeline = Pipeline()
    tick = pipeline.process(make_frame(rain_1h=29.0), mode=RunMode.LIVE)
    assert len(tick.new_action_cards) == 1
    assert tick.new_action_cards[0].stage == "RED"


def test_audit_hash_chain_accumulates_across_multiple_ticks():
    pipeline = Pipeline()
    pipeline.process(make_frame(rain_1h=2.0), mode=RunMode.LIVE)
    pipeline.process(make_frame(rain_1h=5.0), mode=RunMode.LIVE)
    events = pipeline.audit_log.events
    assert len(events) == 2
    assert events[1].prev_hash == events[0].hash
