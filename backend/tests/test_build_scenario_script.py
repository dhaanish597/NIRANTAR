"""Contract test for scripts/build_scenario.py (BUILD_PLAN.md task 4.2).

Loaded via importlib from its file path, same convention as test_validate_scenario_script.py.
"""
from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT_PATH = REPO_ROOT / "scripts" / "build_scenario.py"


def _load_build_scenario():
    spec = importlib.util.spec_from_file_location("build_scenario", SCRIPT_PATH)
    module = importlib.util.module_from_spec(spec)
    sys.modules["build_scenario"] = module
    spec.loader.exec_module(module)
    return module


bs = _load_build_scenario()


class TestAlternatingBlockHyetograph:
    def test_blocks_sum_to_the_published_total(self):
        blocks = bs.alternating_block_hyetograph(total_mm=253.7, n_steps=67, peak_index=53)
        assert sum(blocks) == pytest.approx(253.7, rel=1e-9)

    def test_peak_index_gets_the_single_largest_block(self):
        blocks = bs.alternating_block_hyetograph(total_mm=100.0, n_steps=20, peak_index=15)
        assert blocks[15] == max(blocks)

    def test_peak_near_the_end_produces_a_monotonic_buildup_before_it(self):
        """This is the shape we actually rely on for the demo drama: a long, smooth,
        monotonically-rising ramp when the peak sits near the end of a much longer window."""
        blocks = bs.alternating_block_hyetograph(total_mm=253.7, n_steps=67, peak_index=53)
        ramp = blocks[:53]
        assert ramp == sorted(ramp)  # strictly non-decreasing up to the peak
        assert ramp[0] < ramp[-1]

    def test_rejects_out_of_range_peak_index(self):
        with pytest.raises(ValueError):
            bs.alternating_block_hyetograph(total_mm=10.0, n_steps=5, peak_index=5)

    def test_rejects_non_positive_n_steps(self):
        with pytest.raises(ValueError):
            bs.alternating_block_hyetograph(total_mm=10.0, n_steps=0, peak_index=0)


class TestBuildScenarioDict:
    @pytest.mark.parametrize("scenario_id", ["aizawl-2024", "wayanad-2024", "tupul-2022"])
    def test_every_registered_event_builds_a_schema_valid_dict(self, scenario_id: str):
        spec = bs.EVENTS[scenario_id]
        data = bs.build_scenario_dict(spec)
        scenario = bs.ScenarioFile.model_validate(data)
        assert scenario.id == scenario_id
        assert scenario.held_out_of_training is True

    @pytest.mark.parametrize("scenario_id", ["aizawl-2024", "wayanad-2024", "tupul-2022"])
    def test_provenance_is_auto_populated_and_honest(self, scenario_id: str):
        spec = bs.EVENTS[scenario_id]
        data = bs.build_scenario_dict(spec)
        provenance = data["provenance"]
        assert provenance["confidence"] == "reconstructed"
        assert "Alternating Block Method" in provenance["method"]
        assert len(provenance["sources"]) > 0
        assert "reconstructed" in provenance["disclaimer"].lower()

    def test_aizawl_cell_totals_match_the_published_aggregate_up_to_the_multiplier(self):
        spec = bs.EVENTS["aizawl-2024"]
        data = bs.build_scenario_dict(spec)
        # Background cells (multiplier 0.90) should sum to 0.90 * the published 253.7mm total.
        background_cell = next(c for c in spec.cell_ids if c not in spec.hotspot_cell_ids)
        series = [
            next(c for c in frame["cells"] if c["cell_id"] == background_cell)["rain_1h"]
            for frame in data["frames"]
        ]
        assert sum(series) == pytest.approx(253.7 * bs.BACKGROUND_MULTIPLIER, rel=1e-2)

    def test_insar_velocity_is_null_throughout_every_event(self):
        for scenario_id in ("aizawl-2024", "wayanad-2024", "tupul-2022"):
            data = bs.build_scenario_dict(bs.EVENTS[scenario_id])
            for frame in data["frames"]:
                for cell in frame["cells"]:
                    assert cell["insar_velocity_mm_yr"] is None

    def test_soil_moisture_is_within_unit_range(self):
        for scenario_id in ("aizawl-2024", "wayanad-2024", "tupul-2022"):
            data = bs.build_scenario_dict(bs.EVENTS[scenario_id])
            for frame in data["frames"]:
                for cell in frame["cells"]:
                    assert 0.0 <= cell["soil_moisture"] <= 1.0


def test_main_writes_a_scenario_file(tmp_path: Path):
    exit_code = bs.main(["--id", "aizawl-2024", "--out-dir", str(tmp_path)])
    assert exit_code == 0
    out_path = tmp_path / "aizawl-2024.json"
    assert out_path.is_file()
    data = json.loads(out_path.read_text(encoding="utf-8"))
    assert data["id"] == "aizawl-2024"


def test_main_all_writes_every_registered_scenario(tmp_path: Path):
    exit_code = bs.main(["--all", "--out-dir", str(tmp_path)])
    assert exit_code == 0
    for scenario_id in bs.EVENTS:
        assert (tmp_path / f"{scenario_id}.json").is_file()
