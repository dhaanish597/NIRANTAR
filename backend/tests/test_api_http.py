"""Integration test for main.py: the FastAPI app, its REST routes, and /ws/ticks end to end
through real HTTP/WebSocket transport (BUILD_PLAN.md task 0.11)."""
from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.main import create_app

_REPO_ROOT = Path(__file__).resolve().parents[2]
HAS_REAL_AIZAWL_DATA = (
    (_REPO_ROOT / "data" / "static" / "aizawl" / "cells.gpkg").is_file()
    and (_REPO_ROOT / "data" / "static" / "aizawl" / "exposure.gpkg").is_file()
    and (_REPO_ROOT / "data" / "osm" / "aizawl_graph.pkl").is_file()
)


def make_client() -> TestClient:
    # realtime=False: replay ticks arrive instantly instead of on speed_factor real-time pacing.
    return TestClient(create_app(realtime=False))


def make_realtime_client() -> TestClient:
    # realtime=True: used only by the replay pause/resume/speed round-trip tests below. With
    # realtime=False, a fast scenario like `_smoke` can race to full completion (and auto-return
    # to LIVE) inside the background task's very first scheduled step, before a SEPARATE
    # follow-up HTTP request (e.g. POST /api/replay/pause) ever reaches the server — found by
    # actually hitting a spurious 409 here, not assumed. realtime=True paces frames with a real
    # (if short, given `_smoke`'s own speed_factor) delay, so mode reliably stays in REPLAY long
    # enough for an immediate follow-up request to land while still in REPLAY.
    return TestClient(create_app(realtime=True))


def test_healthz():
    with make_client() as client:
        response = client.get("/healthz")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_root_describes_api_and_citizen_reports():
    with make_client() as client:
        response = client.get("/")
    assert response.status_code == 200
    body = response.json()
    assert body["service"] == "NIRANTAR"
    assert body["citizen_reports"] == "/api/citizen-reports"


def test_get_state_starts_live():
    with make_client() as client:
        response = client.get("/api/state")
    assert response.status_code == 200
    assert response.json()["mode"] == "live"


def test_get_aoi_known():
    with make_client() as client:
        response = client.get("/api/aoi/aizawl")
    assert response.status_code == 200
    body = response.json()
    assert body["id"] == "aizawl"
    assert "center" in body


def test_get_aoi_unknown_is_404():
    with make_client() as client:
        response = client.get("/api/aoi/does-not-exist")
    assert response.status_code == 404


@pytest.mark.skipif(not HAS_REAL_AIZAWL_DATA, reason="requires built Aizawl static data")
def test_get_aoi_exposure_returns_real_villages():
    with make_client() as client:
        response = client.get("/api/aoi/aizawl/exposure")
    assert response.status_code == 200
    body = response.json()
    assert body["aoi_id"] == "aizawl"
    assert len(body["villages"]) > 0
    village = body["villages"][0]
    assert village["village_id"].startswith("v_")
    assert -90 <= village["lat"] <= 90
    assert -180 <= village["lon"] <= 180
    # Same id convention impact/priority.py and impact/isolation.py already use, so a tick's
    # SettlementPriority/VillageIsolation.village_id joins against this with no translation.
    assert village["village_id"] == f"v_{village['village_id'][2:]}"


def test_get_aoi_exposure_unknown_is_404():
    with make_client() as client:
        response = client.get("/api/aoi/does-not-exist/exposure")
    assert response.status_code == 404


def test_list_scenarios_includes_smoke():
    with make_client() as client:
        response = client.get("/api/scenarios")
    assert response.status_code == 200
    ids = [s["id"] for s in response.json()]
    assert "_smoke" in ids


def test_replay_start_switches_mode_to_replay():
    with make_client() as client:
        response = client.post("/api/replay/start", json={"scenario_id": "_smoke"})
    assert response.status_code == 200
    body = response.json()
    assert body["mode"] == "replay"
    assert body["scenario_id"] == "_smoke"


def test_replay_start_unknown_scenario_is_404():
    with make_client() as client:
        response = client.post("/api/replay/start", json={"scenario_id": "does-not-exist"})
    assert response.status_code == 404


def test_replay_stop_returns_to_live():
    with make_client() as client:
        client.post("/api/replay/start", json={"scenario_id": "_smoke"})
        response = client.post("/api/replay/stop")
    assert response.status_code == 200
    assert response.json()["mode"] == "live"


def test_ws_ticks_streams_at_least_one_tick_after_replay_start():
    with make_client() as client:
        with client.websocket_connect("/ws/ticks") as ws:
            client.post("/api/replay/start", json={"scenario_id": "_smoke"})
            message = ws.receive_json()

    assert "t" in message
    assert "cell_risks" in message
    assert "new_audit_events" in message


def test_replay_pause_while_live_returns_409():
    with make_client() as client:
        response = client.post("/api/replay/pause")
    assert response.status_code == 409


def test_replay_resume_while_live_returns_409():
    with make_client() as client:
        response = client.post("/api/replay/resume")
    assert response.status_code == 409


def test_replay_speed_while_live_returns_409():
    with make_client() as client:
        response = client.post("/api/replay/speed", json={"speed_factor": 10.0})
    assert response.status_code == 409


def test_replay_pause_and_resume_round_trip_over_http():
    with make_realtime_client() as client:
        client.post("/api/replay/start", json={"scenario_id": "_smoke"})

        pause_response = client.post("/api/replay/pause")
        assert pause_response.status_code == 200
        assert pause_response.json()["paused"] is True

        resume_response = client.post("/api/replay/resume")
        assert resume_response.status_code == 200
        assert resume_response.json()["paused"] is False


def test_replay_speed_updates_mode_state_over_http():
    with make_realtime_client() as client:
        client.post("/api/replay/start", json={"scenario_id": "_smoke"})
        response = client.post("/api/replay/speed", json={"speed_factor": 99.0})
    assert response.status_code == 200
    assert response.json()["speed_factor"] == 99.0


def test_replay_speed_rejects_non_positive_factor_with_422():
    with make_realtime_client() as client:
        client.post("/api/replay/start", json={"scenario_id": "_smoke"})
        response = client.post("/api/replay/speed", json={"speed_factor": -1.0})
    assert response.status_code == 422


def test_get_audit_trail_for_unknown_alert_id_returns_empty_list_not_404():
    with make_client() as client:
        response = client.get("/api/audit/no-such-alert")
    assert response.status_code == 200
    assert response.json() == []


def test_get_audit_trail_returns_the_real_chain_for_a_live_ai_flagged_alert():
    with make_client() as client:
        with client.websocket_connect("/ws/ticks") as ws:
            message = ws.receive_json()
        alert_id = message["new_audit_events"][0]["alert_id"]

        response = client.get(f"/api/audit/{alert_id}")

    assert response.status_code == 200
    events = response.json()
    assert len(events) >= 1
    assert events[0]["kind"] == "AI_FLAGGED"
    assert events[0]["alert_id"] == alert_id
    # The hash chain fields travel over the wire too — this is meant to be verifiable, not just
    # a flat event dump.
    assert "hash" in events[0] and "prev_hash" in events[0]


def _sample_action_card(alert_id: str = "alert-v1-test") -> dict:
    # Matches app.schemas.decision.ActionCard's required fields exactly (see
    # backend/tests/test_audit_producers.py::make_card for the Python-side equivalent).
    return {
        "alert_id": alert_id,
        "village_id": "v1",
        "stage": "RED",
        "headline": "Evacuate Now",
        "reason_plain": "test reason",
        "shelter_name": "Test Shelter",
        "route": None,
        "roads_to_avoid": ["NH6"],
        "what_to_carry": ["ID"],
        "contact": "placeholder",
        "issued_at": "2026-05-28T03:20:00+00:00",
        "valid_until": "2026-05-28T09:20:00+00:00",
        "safe_window_hours": [0.0, 1.0],
        "translations": {},
        "audio_urls": {},
    }


def test_ddma_decide_approved_appends_ddma_approved_and_is_visible_over_the_audit_endpoint():
    with make_client() as client:
        response = client.post(
            "/api/ddma/decide",
            json={
                "action_card": _sample_action_card(),
                "officer_id": "officer_placeholder",
                "decision": "approved",
            },
        )
    assert response.status_code == 200
    body = response.json()
    assert body["kind"] == "DDMA_APPROVED"
    assert body["actor"] == "ddma:officer_placeholder"
    assert body["alert_id"] == "alert-v1-test"
    assert "hash" in body and "prev_hash" in body


def test_ddma_decide_rejected_appends_stood_down_not_ddma_approved():
    with make_client() as client:
        response = client.post(
            "/api/ddma/decide",
            json={
                "action_card": _sample_action_card("alert-v1-reject"),
                "officer_id": "officer_placeholder",
                "decision": "rejected",
            },
        )
    assert response.status_code == 200
    assert response.json()["kind"] == "STOOD_DOWN"


def test_ddma_decide_missing_required_field_is_422():
    with make_client() as client:
        response = client.post("/api/ddma/decide", json={"action_card": _sample_action_card()})
    assert response.status_code == 422


def test_ddma_decide_then_get_audit_trail_returns_the_decision():
    with make_client() as client:
        card = _sample_action_card("alert-v1-roundtrip")
        client.post(
            "/api/ddma/decide",
            json={"action_card": card, "officer_id": "officer_placeholder", "decision": "approved"},
        )
        response = client.get(f"/api/audit/{card['alert_id']}")
    assert response.status_code == 200
    events = response.json()
    assert [e["kind"] for e in events] == ["DDMA_APPROVED"]


def test_village_acknowledge_appends_village_acknowledged_event():
    with make_client() as client:
        response = client.post(
            "/api/village/acknowledge",
            json={"alert_id": "alert-v1-ack", "village_id": "v1"},
        )
    assert response.status_code == 200
    body = response.json()
    assert body["kind"] == "VILLAGE_ACKNOWLEDGED"
    assert body["actor"] == "village:v1"
    assert body["alert_id"] == "alert-v1-ack"


def test_village_acknowledge_missing_field_is_422():
    with make_client() as client:
        response = client.post("/api/village/acknowledge", json={"alert_id": "alert-v1-ack"})
    assert response.status_code == 422


def test_village_acknowledge_then_get_audit_trail_shows_it_after_a_ddma_decision():
    """Proves DDMA_APPROVED and VILLAGE_ACKNOWLEDGED share one real, ordered, hash-chained
    history over HTTP for the same alert_id — the sequence the Audit Trail view (task 3.8)
    renders."""
    with make_client() as client:
        card = _sample_action_card("alert-v1-full-chain")
        client.post(
            "/api/ddma/decide",
            json={"action_card": card, "officer_id": "officer_placeholder", "decision": "approved"},
        )
        client.post(
            "/api/village/acknowledge",
            json={"alert_id": card["alert_id"], "village_id": card["village_id"]},
        )
        response = client.get(f"/api/audit/{card['alert_id']}")
    events = response.json()
    assert [e["kind"] for e in events] == ["DDMA_APPROVED", "VILLAGE_ACKNOWLEDGED"]
    assert events[1]["prev_hash"] == events[0]["hash"]


def test_ws_ticks_eventually_shows_the_full_escalation_arc():
    """Proves the browser-facing path (not just the pipeline-level test) sees the same rising
    p_fail arc that test_smoke_scenario.py proves at the pipeline level.

    Reads `new_action_cards[*].stage` directly (the real escalation stage string an ActionCard
    carries) rather than inferring a stage from `priorities[0].eps` — EPS is now a genuine
    weighted composite (p_fail/population/RII/shelter, task 2.5), not a stand-in for p_fail, so an
    eps>=0.75 threshold no longer means "RED" the way it did against Phase 0's stub pipeline
    (where a single fake village's eps was p_fail verbatim). Requires real Aizawl static data
    (gitignored) for real villages to exist at all — skipped, not faked, when it's absent, same
    pattern as test_smoke_scenario.py's own HAS_REAL_AIZAWL_DATA."""
    if not HAS_REAL_AIZAWL_DATA:
        pytest.skip("requires real Aizawl static data")

    with make_client() as client:
        with client.websocket_connect("/ws/ticks") as ws:
            client.post("/api/replay/start", json={"scenario_id": "_smoke"})
            stages_seen = set()
            for _ in range(10):
                message = ws.receive_json()
                if message["scenario_id"] == "_smoke":
                    for card in message["new_action_cards"]:
                        stages_seen.add(card["stage"])

    assert "RED" in stages_seen
    assert "ORANGE" in stages_seen


import json


def _sample_announcement_card(alert_id: str = "alert-1") -> dict:
    # Named distinctly from the pre-existing `_sample_action_card` above (default alert_id
    # "alert-v1-test") — reusing that name here would shadow it at module scope (Python resolves
    # a bare name from the module's global namespace at CALL time, not at each test's definition
    # site), silently changing the default alert_id every earlier test in this file that calls
    # `_sample_action_card()` with no argument. Caught for real: this collision broke
    # test_ddma_decide_approved_appends_ddma_approved_and_is_visible_over_the_audit_endpoint's
    # `alert_id == "alert-v1-test"` assertion before this rename.
    return {
        "alert_id": alert_id,
        "village_id": "v1",
        "stage": "RED",
        "headline": "Evacuate now",
        "reason_plain": "Heavy rainfall and slope movement",
        "shelter_name": "Community Hall",
        "route": None,
        "roads_to_avoid": [],
        "what_to_carry": [],
        "contact": "108",
        "issued_at": "2026-01-01T00:00:00+05:30",
        "valid_until": "2026-01-02T00:00:00+05:30",
        "safe_window_hours": None,
        "translations": {},
        "audio_urls": {},
    }


def test_post_announcement_dispatches_and_records_audit():
    with make_client() as client:
        card = _sample_announcement_card()
        response = client.post(
            "/api/announcements",
            json={"action_card": card, "officer_id": "officer-1", "recipient_count": 500},
        )
        assert response.status_code == 200
        body = response.json()
        assert {r["channel"] for r in body["channel_results"]} == {
            "cell_broadcast",
            "sms",
            "push",
            "mesh",
        }

        audit_response = client.get(f"/api/audit/{card['alert_id']}")
        kinds = [e["kind"] for e in audit_response.json()]
        assert "DDMA_APPROVED" in kinds
        assert "DISSEMINATED" in kinds


def test_get_announcements_lists_newest_first():
    with make_client() as client:
        client.post(
            "/api/announcements",
            json={
                "action_card": _sample_announcement_card("a1"),
                "officer_id": "o",
                "recipient_count": 1,
            },
        )
        client.post(
            "/api/announcements",
            json={
                "action_card": _sample_announcement_card("a2"),
                "officer_id": "o",
                "recipient_count": 1,
            },
        )
        response = client.get("/api/announcements")
        ids = [a["alert_id"] for a in response.json()]
    assert ids == ["a2", "a1"]


def test_announcement_is_broadcast_over_ws_ticks():
    with make_client() as client:
        card = _sample_announcement_card()
        with client.websocket_connect("/ws/ticks") as ws:
            client.post(
                "/api/announcements",
                json={"action_card": card, "officer_id": "o", "recipient_count": 1},
            )
            for _ in range(20):
                message = json.loads(ws.receive_text())
                if message.get("type") == "announcement":
                    assert message["data"]["alert_id"] == card["alert_id"]
                    break
            else:
                pytest.fail("no announcement message received over /ws/ticks")
