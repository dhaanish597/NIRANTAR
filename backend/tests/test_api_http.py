"""Integration test for main.py: the FastAPI app, its REST routes, and /ws/ticks end to end
through real HTTP/WebSocket transport (BUILD_PLAN.md task 0.11)."""
from __future__ import annotations

from fastapi.testclient import TestClient

from app.main import create_app


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


def test_ws_ticks_eventually_shows_the_full_escalation_arc():
    """Proves the browser-facing path (not just the pipeline-level test) sees the same rising
    p_fail arc that test_smoke_scenario.py proves at the pipeline level."""
    with make_client() as client:
        with client.websocket_connect("/ws/ticks") as ws:
            client.post("/api/replay/start", json={"scenario_id": "_smoke"})
            stages_seen = set()
            for _ in range(10):
                message = ws.receive_json()
                if message["scenario_id"] == "_smoke" and message["priorities"]:
                    eps = message["priorities"][0]["eps"]
                    if eps >= 0.75:
                        stages_seen.add("RED")
                    elif eps >= 0.5:
                        stages_seen.add("ORANGE")

    assert "RED" in stages_seen
    assert "ORANGE" in stages_seen
