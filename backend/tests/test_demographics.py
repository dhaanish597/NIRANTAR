from __future__ import annotations

from app.impact.demographics import simulate_demographics


def test_simulate_demographics_sums_to_population():
    d = simulate_demographics(1000)
    assert d.children + d.seniors + d.adults == 1000


def test_simulate_demographics_is_deterministic():
    assert simulate_demographics(2840) == simulate_demographics(2840)


def test_simulate_demographics_labels_source_simulated():
    assert simulate_demographics(500).source == "simulated"


def test_simulate_demographics_zero_population():
    d = simulate_demographics(0)
    assert d.children == 0
    assert d.seniors == 0
    assert d.adults == 0
    assert d.high_risk_households == 0
