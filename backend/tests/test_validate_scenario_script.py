"""Contract test for scripts/validate_scenario.py (BUILD_PLAN.md task 4.1).

Loaded via importlib from its file path (mirrors tests/test_fetch_dem.py's convention) rather
than importing it as an installed package, since scripts/ is a folder of one-shot CLI tools, not
a Python package on this project's path. No geo/ingest dependency needed — this script only uses
Pydantic and stdlib.
"""
from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT_PATH = REPO_ROOT / "scripts" / "validate_scenario.py"
SMOKE_PATH = REPO_ROOT / "data" / "scenarios" / "_smoke.json"


def _load_validate_scenario():
    spec = importlib.util.spec_from_file_location("validate_scenario", SCRIPT_PATH)
    module = importlib.util.module_from_spec(spec)
    sys.modules["validate_scenario"] = module
    spec.loader.exec_module(module)
    return module


vs = _load_validate_scenario()


def _base_scenario_dict(**overrides) -> dict:
    """A minimal, otherwise-valid REAL (held-out) scenario dict, for tampering with in tests."""
    base = {
        "id": "test-scenario",
        "name": "Test Event",
        "event_date": "2024-01-01",
        "aoi_id": "aizawl",
        "hazard_type": "rainfall_triggered_shallow",
        "trigger": "test trigger",
        "held_out_of_training": True,
        "provenance": {
            "confidence": "reconstructed",
            "method": "test method",
            "sources": ["Test source"],
            "disclaimer": "test disclaimer",
        },
        "clock": {
            "start": "2024-01-01T00:00:00+05:30",
            "end": "2024-01-01T02:00:00+05:30",
            "frame_interval_minutes": 60,
            "default_speed_factor": 3600,
        },
        "frames": [
            {
                "t": "2024-01-01T00:00:00+05:30",
                "defaults": {
                    "rain_6h": 1.0, "rain_24h": 1.0, "rain_72h": 1.0,
                    "antecedent_7d": 1.0, "antecedent_15d": 1.0, "antecedent_30d": 1.0,
                },
                "cells": [{"cell_id": "c1", "rain_1h": 1.0}],
            },
            {
                "t": "2024-01-01T01:00:00+05:30",
                "defaults": {
                    "rain_6h": 1.0, "rain_24h": 1.0, "rain_72h": 1.0,
                    "antecedent_7d": 1.0, "antecedent_15d": 1.0, "antecedent_30d": 1.0,
                },
                "cells": [{"cell_id": "c1", "rain_1h": 2.0}],
            },
        ],
        "ground_truth": {
            "failures": [],
            "road_events": [],
            "official_warnings": [],
            "outcome": {"deaths": "1 (test)", "source_note": "test"},
        },
        "narration": [],
    }
    base.update(overrides)
    return base


def test_smoke_fixture_validates_clean():
    scenario = vs.load_and_validate(SMOKE_PATH)
    assert scenario.id == "_smoke"


def test_well_formed_real_scenario_validates_clean(tmp_path: Path):
    path = tmp_path / "test-scenario.json"
    path.write_text(json.dumps(_base_scenario_dict()), encoding="utf-8")
    scenario = vs.load_and_validate(path)
    assert scenario.id == "test-scenario"


def test_held_out_scenario_with_non_reconstructed_confidence_is_rejected(tmp_path: Path):
    data = _base_scenario_dict()
    data["provenance"]["confidence"] = "archived observation"
    path = tmp_path / "bad.json"
    path.write_text(json.dumps(data), encoding="utf-8")
    with pytest.raises(vs.ScenarioValidationError, match="reconstructed"):
        vs.load_and_validate(path)


def test_held_out_scenario_with_no_sources_is_rejected(tmp_path: Path):
    data = _base_scenario_dict()
    data["provenance"]["sources"] = []
    path = tmp_path / "bad.json"
    path.write_text(json.dumps(data), encoding="utf-8")
    with pytest.raises(vs.ScenarioValidationError, match="sources"):
        vs.load_and_validate(path)


def test_out_of_order_frames_are_rejected(tmp_path: Path):
    data = _base_scenario_dict()
    data["frames"] = [data["frames"][1], data["frames"][0]]  # swap to break ordering
    path = tmp_path / "bad.json"
    path.write_text(json.dumps(data), encoding="utf-8")
    with pytest.raises(vs.ScenarioValidationError, match="not strictly after"):
        vs.load_and_validate(path)


def test_frame_outside_clock_range_is_rejected(tmp_path: Path):
    data = _base_scenario_dict()
    data["frames"][0]["t"] = "2023-01-01T00:00:00+05:30"  # long before clock.start
    path = tmp_path / "bad.json"
    path.write_text(json.dumps(data), encoding="utf-8")
    with pytest.raises(vs.ScenarioValidationError, match="outside clock range"):
        vs.load_and_validate(path)


def test_cell_missing_required_field_is_rejected(tmp_path: Path):
    data = _base_scenario_dict()
    del data["frames"][0]["defaults"]["rain_6h"]  # neither default nor override now supplies it
    path = tmp_path / "bad.json"
    path.write_text(json.dumps(data), encoding="utf-8")
    with pytest.raises(vs.ScenarioValidationError, match="rain_6h"):
        vs.load_and_validate(path)


def test_held_out_scenario_missing_ground_truth_fails_schema_validation(tmp_path: Path):
    """This one is actually caught by the Pydantic schema itself (schemas/scenario.py's
    `_real_events_carry_full_metadata`), not by validate_scenario.py's own checks — proving the
    two layers compose rather than duplicate each other."""
    data = _base_scenario_dict()
    del data["ground_truth"]
    path = tmp_path / "bad.json"
    path.write_text(json.dumps(data), encoding="utf-8")
    with pytest.raises(vs.ScenarioValidationError, match="ground_truth"):
        vs.load_and_validate(path)


def test_main_returns_zero_for_the_real_scenarios_directory():
    assert vs.main([]) == 0


def test_main_returns_one_for_a_missing_scenario_id():
    assert vs.main(["does-not-exist"]) == 1


def test_main_returns_one_for_an_invalid_file(tmp_path: Path, capsys):
    data = _base_scenario_dict()
    data["provenance"]["confidence"] = "archived observation"
    path = tmp_path / "bad.json"
    path.write_text(json.dumps(data), encoding="utf-8")
    assert vs.main([str(path)]) == 1
    assert "FAIL" in capsys.readouterr().out
