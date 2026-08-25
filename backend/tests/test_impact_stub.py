"""Contract test for impact/stub.py."""
from __future__ import annotations

from app.impact.stub import (
    RUNOUT_TRIGGER_P_FAIL,
    SEVERANCE_P_BLOCKED,
    average_p_fail,
    compute_impact,
)
from app.schemas.risk import CellRisk


def make_risk(p_fail: float, cell_id: str = "c1") -> CellRisk:
    return CellRisk(
        cell_id=cell_id, p_fail=p_fail, threshold_exceedance=p_fail, confidence=0.5,
        attributions=[], model_version="test",
    )


def test_average_p_fail_of_empty_list_is_zero():
    assert average_p_fail([]) == 0.0


def test_average_p_fail_is_the_mean():
    assert average_p_fail([make_risk(0.2), make_risk(0.6)]) == 0.4


def test_low_risk_produces_no_runout_envelopes_and_p3_priority():
    envelopes, roads, villages, priorities = compute_impact([make_risk(0.1)])
    assert envelopes == []
    assert roads[0].severed is False
    assert villages[0].isolated_now is False
    assert priorities[0].tier == "P3"


def test_high_risk_above_runout_trigger_produces_an_envelope():
    envelopes, _roads, _villages, _priorities = compute_impact([make_risk(RUNOUT_TRIGGER_P_FAIL)])
    assert len(envelopes) == 1
    assert envelopes[0].source_cell_id == "c1"


def test_risk_at_or_above_severance_threshold_severs_the_road():
    envelopes, roads, villages, priorities = compute_impact([make_risk(SEVERANCE_P_BLOCKED)])
    assert roads[0].severed is True
    assert villages[0].isolated_now is True
    assert villages[0].alternate_route_exists is False
    assert priorities[0].tier == "P1"


def test_priority_components_sum_matches_p_fail_and_rii_by_construction():
    _e, _r, _v, priorities = compute_impact([make_risk(0.6)])
    assert priorities[0].components["p_fail"] == 0.6
    assert priorities[0].components["rii"] == 0.6
