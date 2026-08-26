"""BUILD_PLAN.md task 5.8 — the what-if rainfall simulator.

`app/api/whatif.py`'s pure logic (synthetic-frame construction, real cell_id loading) is fast and
tested directly. The full `/api/whatif/simulate` endpoint runs the ENTIRE real pipeline (ML
inference + SHAP + runout + road-graph + isolation + priority + escalation/action-cards) across
Aizawl's real 2,912-cell grid — a genuinely expensive real call (~15-20s measured locally, not
mocked), so this file keeps that to ONE comprehensive test rather than one expensive test per
assertion.
"""
from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.api.whatif import build_synthetic_frame, load_real_cell_ids
from app.core.clock import LiveClock
from app.main import create_app

REPO_ROOT = Path(__file__).resolve().parents[2]
HAS_REAL_AIZAWL_DATA = (
    (REPO_ROOT / "data" / "static" / "aizawl" / "cells.gpkg").is_file()
    and (REPO_ROOT / "data" / "static" / "aizawl" / "exposure.gpkg").is_file()
    and (REPO_ROOT / "data" / "osm" / "aizawl_graph.pkl").is_file()
)
HAS_TRAINED_MODEL = (
    (REPO_ROOT / "data" / "models" / "xgb_terrain_v1.json").is_file()
    and (REPO_ROOT / "data" / "models" / "model_metadata.json").is_file()
)


def make_client() -> TestClient:
    return TestClient(create_app(realtime=False))


# =================================================================================================
# Pure logic — fast
# =================================================================================================
@pytest.mark.skipif(not HAS_REAL_AIZAWL_DATA, reason="requires data/static/aizawl/cells.gpkg")
class TestBuildSyntheticFrame:
    def test_uses_real_cell_ids_from_cells_gpkg_not_a_fabricated_grid(self):
        frame = build_synthetic_frame("aizawl", 250.0, 12.0, t=LiveClock().now())
        real_ids = set(load_real_cell_ids("aizawl"))
        frame_ids = {obs.cell_id for obs in frame.cells}
        assert frame_ids == real_ids
        assert len(frame_ids) > 1000  # Aizawl's real grid is 2,912 cells — a sanity floor, not
        # a hardcoded exact count that would break the moment build_grid.py's own AOI bbox is
        # ever retuned (CLAUDE.md's own TODO(verify) on that bbox).

    def test_rainfall_math_is_uniform_intensity_correctly_accumulated(self):
        frame = build_synthetic_frame("aizawl", 250.0, 12.0, t=LiveClock().now())
        obs = frame.cells[0]
        # 250mm / 12h = ~20.83 mm/h constant intensity.
        assert obs.rain_1h == pytest.approx(250.0 / 12.0)
        assert obs.rain_6h == pytest.approx(250.0 / 12.0 * 6)
        # 24h/72h windows are both longer than the 12h event — capped at the real total, not
        # multiplied further (no rain fell after the event ended).
        assert obs.rain_24h == pytest.approx(250.0)
        assert obs.rain_72h == pytest.approx(250.0)

    def test_no_antecedent_wetness_fabricated_beyond_the_event_itself(self):
        frame = build_synthetic_frame("aizawl", 250.0, 12.0, t=LiveClock().now())
        obs = frame.cells[0]
        assert obs.antecedent_7d == pytest.approx(250.0)
        assert obs.antecedent_15d == pytest.approx(250.0)
        assert obs.antecedent_30d == pytest.approx(250.0)

    def test_every_cell_gets_the_identical_uniform_rainfall_profile(self):
        frame = build_synthetic_frame("aizawl", 100.0, 6.0, t=LiveClock().now())
        rain_1h_values = {obs.rain_1h for obs in frame.cells}
        assert rain_1h_values == {100.0 / 6.0}  # exactly one distinct value across all cells

    def test_soil_moisture_and_insar_are_left_absent_not_fabricated(self):
        frame = build_synthetic_frame("aizawl", 250.0, 12.0, t=LiveClock().now())
        assert all(obs.soil_moisture is None for obs in frame.cells)
        assert all(obs.insar_velocity_mm_yr is None for obs in frame.cells)

    def test_marked_as_reconstructed_never_a_live_observation(self):
        frame = build_synthetic_frame("aizawl", 250.0, 12.0, t=LiveClock().now())
        assert all(obs.is_reconstructed for obs in frame.cells)
        assert all(obs.source == "what_if_simulation" for obs in frame.cells)

    def test_unknown_aoi_raises_filenotfounderror_not_a_fabricated_grid(self):
        with pytest.raises(FileNotFoundError):
            build_synthetic_frame("nonexistent-aoi", 250.0, 12.0, t=LiveClock().now())

    def test_a_shorter_event_caps_longer_windows_at_the_real_total(self):
        # 50mm over just 2h -- the 6/24/72h windows should all equal 50mm (nothing fell outside
        # the 2h event), not extrapolate the 2h intensity across the whole window.
        frame = build_synthetic_frame("aizawl", 50.0, 2.0, t=LiveClock().now())
        obs = frame.cells[0]
        assert obs.rain_1h == pytest.approx(25.0)
        assert obs.rain_6h == pytest.approx(50.0)
        assert obs.rain_24h == pytest.approx(50.0)


# =================================================================================================
# Full endpoint — real HTTP, real pipeline, expensive (ONE comprehensive test)
# =================================================================================================
@pytest.mark.skipif(
    not (HAS_REAL_AIZAWL_DATA and HAS_TRAINED_MODEL),
    reason="requires real Aizawl static data + a trained model artifact",
)
def test_whatif_endpoint_full_real_run():
    # ~15-20s measured locally against the real 2,912-cell Aizawl grid — this is not a
    # mocked/stubbed run. `realtime=False` means the app's own background LIVE stub tick loop
    # (AppState.start(), started unconditionally by create_app's lifespan) keeps appending its
    # OWN real AI_FLAGGED events to app_state.pipeline.audit_log throughout this test's ~20s
    # window — so isolation below is checked by identity (this what-if run's own specific
    # alert_id/event hashes must be absent from the real log), not by a fragile "total event
    # count didn't change" snapshot, which that concurrent background activity would break.
    with make_client() as client:
        app_state = client.app.state.app_state

        response = client.post(
            "/api/whatif/simulate",
            json={"aoi_id": "aizawl", "rainfall_mm": 250.0, "duration_hours": 12.0},
        )

        assert response.status_code == 200
        body = response.json()
        whatif_alert_id = body["tick"]["new_audit_events"][0]["alert_id"]
        whatif_event_hashes = {e["hash"] for e in body["tick"]["new_audit_events"]}

        # Checked INSIDE the `with` block, same live app_state instance the request just ran
        # against — this what-if run's own alert_id/event hashes must never appear in the real,
        # live audit log it deliberately never touched.
        assert app_state.pipeline.audit_log.for_alert(whatif_alert_id) == []
        real_hashes = {e.hash for e in app_state.pipeline.audit_log.events}
        assert whatif_event_hashes.isdisjoint(real_hashes)

    # --- request/assumptions echoed back honestly ---
    assert body["request"] == {"aoi_id": "aizawl", "rainfall_mm": 250.0, "duration_hours": 12.0}
    assert len(body["assumptions"]) >= 3
    assert any("uniform" in a.lower() for a in body["assumptions"])
    assert body["cell_count"] > 1000

    # --- real ML model actually fired (task 1.17), not just the threshold fallback ---
    tick = body["tick"]
    assert len(tick["cell_risks"]) == body["cell_count"]
    model_versions = {r["model_version"] for r in tick["cell_risks"]}
    assert "xgb-terrain-v1" in model_versions
    assert all(0.0 <= r["p_fail"] <= 1.0 for r in tick["cell_risks"])

    # --- the impact/decision chain genuinely ran (task 2.x/3.x wiring, not a stub) ---
    assert len(tick["road_risks"]) > 0
    assert len(tick["isolations"]) > 0
    assert len(tick["priorities"]) > 0
    # 250mm/12h is far beyond the published I-D/E-D thresholds for every cell -- a real,
    # extreme-but-legitimate result, not an arbitrary assertion.
    assert len(tick["new_action_cards"]) > 0


def test_whatif_endpoint_unknown_aoi_is_404():
    with make_client() as client:
        response = client.post(
            "/api/whatif/simulate",
            json={"aoi_id": "not-a-real-aoi", "rainfall_mm": 100.0, "duration_hours": 6.0},
        )
    assert response.status_code == 404


def test_whatif_endpoint_aoi_with_no_static_data_is_404_not_a_silent_empty_result():
    # wayanad/tupul are registered in config.AOIS (so get_aoi succeeds) but have no
    # data/static/<aoi>/cells.gpkg built yet -- confirmed by the same repo-layout check every
    # other AOI-scoped test in this codebase already makes.
    has_wayanad_data = (REPO_ROOT / "data" / "static" / "wayanad" / "cells.gpkg").is_file()
    if has_wayanad_data:
        pytest.skip("wayanad static data now exists — this AOI no longer demonstrates the gap")
    with make_client() as client:
        response = client.post(
            "/api/whatif/simulate",
            json={"aoi_id": "wayanad", "rainfall_mm": 100.0, "duration_hours": 6.0},
        )
    assert response.status_code == 404


@pytest.mark.parametrize(
    "payload",
    [
        {"aoi_id": "aizawl", "rainfall_mm": 0.0, "duration_hours": 6.0},
        {"aoi_id": "aizawl", "rainfall_mm": -5.0, "duration_hours": 6.0},
        {"aoi_id": "aizawl", "rainfall_mm": 100.0, "duration_hours": 0.0},
        {"aoi_id": "aizawl", "rainfall_mm": 100.0, "duration_hours": -1.0},
        {"aoi_id": "aizawl", "rainfall_mm": 5000.0, "duration_hours": 6.0},  # over the ceiling
    ],
)
def test_whatif_endpoint_rejects_invalid_input_with_422(payload):
    with make_client() as client:
        response = client.post("/api/whatif/simulate", json=payload)
    assert response.status_code == 422
