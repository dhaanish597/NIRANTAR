"""Contract test for pipeline.py — single-frame behavior. The full multi-frame smoke scenario
lives in test_smoke_scenario.py (BUILD_PLAN.md task 0.14).

A later session wired pipeline.py to the real risk/impact/decision modules (tasks 1.12-1.19,
2.1-2.6, 3.1-3.3, 3.6 — see pipeline.py's own module docstring for the full design). Requires
real Aizawl static data (data/static/aizawl/{cells,exposure}.gpkg, data/osm/aizawl_graph.pkl,
data/models/xgb_terrain_v1.json) — all gitignored, built by scripts/ + ml/train.py, not present in
a fresh checkout. Skipped here rather than faked, same pattern every other real-data integration
test in this suite already uses (see e.g. test_isolation_loader.py's HAS_REAL_EXPOSURE)."""
from __future__ import annotations

from pathlib import Path

import pytest

from app.pipeline import Pipeline
from app.schemas.ingest import CellObservation, ObservationFrame
from app.schemas.mode import RunMode

T = "2025-01-01T00:00:00+05:30"

_REPO_ROOT = Path(__file__).resolve().parents[2]
HAS_REAL_AIZAWL_DATA = (
    (_REPO_ROOT / "data" / "static" / "aizawl" / "cells.gpkg").is_file()
    and (_REPO_ROOT / "data" / "static" / "aizawl" / "exposure.gpkg").is_file()
    and (_REPO_ROOT / "data" / "osm" / "aizawl_graph.pkl").is_file()
)

# A real village (Durtlang, per exposure.gpkg) and the real cells.gpkg cell_id that is genuinely
# its nearest analysis cell (resolved once via impact/priority.py's own nearest-cell logic and
# fixed here — see this session's commit message for how it was derived, not invented).
REAL_VILLAGE_ID = "v_6202256842"
REAL_NEAREST_CELL_ID = "aizawl_040_026"


def make_frame(rain_1h: float = 5.0, cell_id: str = "c1") -> ObservationFrame:
    return ObservationFrame(
        t=T,
        aoi_id="aizawl",
        cells=[
            CellObservation(
                cell_id=cell_id, rain_1h=rain_1h, rain_6h=0.0, rain_24h=0.0, rain_72h=0.0,
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


@pytest.mark.skipif(
    not HAS_REAL_AIZAWL_DATA,
    reason="requires data/static/aizawl/{cells,exposure}.gpkg + data/osm/aizawl_graph.pkl",
)
def test_high_rain_on_a_real_villages_nearest_cell_produces_an_action_card():
    """Rain on `c1` (matching no real village's nearest cell) can never produce a card — action
    cards are driven by a real village's resolved p_fail (pipeline.py's own ruling 3: escalation
    is tracked per village, not per raw observed cell). Rain on the REAL cell that IS Durtlang's
    nearest analysis cell must."""
    pipeline = Pipeline()
    tick = pipeline.process(make_frame(rain_1h=29.0, cell_id=REAL_NEAREST_CELL_ID), mode=RunMode.LIVE)
    assert len(tick.new_action_cards) == 1
    assert tick.new_action_cards[0].stage == "RED"
    assert tick.new_action_cards[0].village_id == REAL_VILLAGE_ID


@pytest.mark.skipif(
    not HAS_REAL_AIZAWL_DATA,
    reason="requires data/static/aizawl/{cells,exposure}.gpkg + data/osm/aizawl_graph.pkl",
)
def test_high_rain_on_an_unmatched_cell_produces_no_action_card():
    pipeline = Pipeline()
    tick = pipeline.process(make_frame(rain_1h=29.0), mode=RunMode.LIVE)  # default cell_id="c1"
    # `c1` still gets a real (threshold-only) CellRisk — see pipeline.py's ruling 2 — but no real
    # village's nearest cell is "c1", so every real village's resolved p_fail stays 0.0 and none
    # of them escalate past GREEN.
    assert tick.cell_risks[0].p_fail == pytest.approx(1.0)
    assert tick.new_action_cards == []


def test_audit_hash_chain_accumulates_across_multiple_ticks():
    pipeline = Pipeline()
    pipeline.process(make_frame(rain_1h=2.0), mode=RunMode.LIVE)
    pipeline.process(make_frame(rain_1h=5.0), mode=RunMode.LIVE)
    events = pipeline.audit_log.events
    assert len(events) == 2
    assert events[1].prev_hash == events[0].hash
