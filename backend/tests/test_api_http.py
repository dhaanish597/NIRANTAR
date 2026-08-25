"""Integration test for main.py: the FastAPI app, its REST routes, and /ws/ticks end to end
through real HTTP/WebSocket transport (BUILD_PLAN.md task 0.11)."""
from __future__ import annotations

from fastapi.testclient import TestClient

from app.main import create_app


def make_client() -> TestClient:
    # realtime=False: replay ticks arrive instantly instead of on speed_factor real-time pacing.
    return TestClient(create_app(realtime=False))


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
