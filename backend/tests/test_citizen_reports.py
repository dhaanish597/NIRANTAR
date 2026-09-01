from __future__ import annotations

import base64
import struct
import zlib

from fastapi.testclient import TestClient

from app.main import create_app


def _png_data_url(width: int = 640, height: int = 480) -> str:
    def chunk(kind: bytes, data: bytes) -> bytes:
        return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data) & 0xFFFFFFFF)

    raw = b"".join(b"\x00" + b"\x78\x8c\x54" * width for _ in range(height))
    png = (
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0))
        + chunk(b"IDAT", zlib.compress(raw))
        + chunk(b"IEND", b"")
    )
    return "data:image/png;base64," + base64.b64encode(png).decode("ascii")


def _payload(**overrides) -> dict:
    payload = {
        "aoi_id": "aizawl",
        "category": "Blocked road",
        "description": "Large debris has blocked the road and traffic cannot pass.",
        "lat": 23.7307,
        "lon": 92.7173,
        "accuracy_m": 12.0,
        "image_data_url": _png_data_url(),
    }
    payload.update(overrides)
    return payload


def test_citizen_report_runs_all_seven_agents_and_persists(tmp_path):
    app = create_app(realtime=False, citizen_report_data_dir=tmp_path)
    with TestClient(app) as client:
        app.state.app_state.citizen_report_workflow.api_key = None
        response = client.post("/api/citizen-reports", json=_payload())
        listing = client.get("/api/citizen-reports?aoi_id=aizawl")

    assert response.status_code == 201
    body = response.json()
    assert body["category"] == "Blocked road"
    assert body["classification_source"] == "fallback"
    assert body["quality_score"] > 0.5
    assert [trace["step_name"] for trace in body["agent_traces"]] == [
        "Ingestion",
        "Classification",
        "Dedup",
        "Hotspot",
        "Forecast",
        "Urgency",
        "Recommendation",
    ]
    assert listing.status_code == 200
    assert [report["id"] for report in listing.json()] == [body["id"]]


def test_second_nearby_report_is_marked_as_duplicate(tmp_path):
    app = create_app(realtime=False, citizen_report_data_dir=tmp_path)
    with TestClient(app) as client:
        app.state.app_state.citizen_report_workflow.api_key = None
        first = client.post("/api/citizen-reports", json=_payload()).json()
        second = client.post(
            "/api/citizen-reports",
            json=_payload(lat=23.7310, lon=92.7175),
        ).json()

    assert second["duplicate_of"] == first["id"]
    assert second["hotspot_count"] == 2


def test_officer_can_update_report_status_and_retrieve_image(tmp_path):
    app = create_app(realtime=False, citizen_report_data_dir=tmp_path)
    with TestClient(app) as client:
        app.state.app_state.citizen_report_workflow.api_key = None
        report = client.post("/api/citizen-reports", json=_payload()).json()
        update = client.patch(
            f"/api/citizen-reports/{report['id']}/status",
            json={"status": "in_review", "officer_id": "ddma-demo", "notes": "Field team assigned"},
        )
        image = client.get(report["image_url"])

    assert update.status_code == 200
    assert update.json()["status"] == "in_review"
    assert update.json()["officer_notes"] == "Field team assigned"
    assert image.status_code == 200
    assert image.headers["content-type"].startswith("image/png")
    assert image.content.startswith(b"\x89PNG")


def test_invalid_photo_is_rejected_but_valid_out_of_aoi_report_is_retained(tmp_path):
    app = create_app(realtime=False, citizen_report_data_dir=tmp_path)
    with TestClient(app) as client:
        invalid_image = client.post(
            "/api/citizen-reports",
            json=_payload(image_data_url="data:image/png;base64,bm90LWEtcG5n"),
        )
        outside = client.post(
            "/api/citizen-reports",
            json=_payload(lat=28.61, lon=77.20),
        )

    assert invalid_image.status_code == 400
    assert "does not match" in invalid_image.json()["detail"]
    assert outside.status_code == 201
    assert "outside" in outside.json()["agent_traces"][0]["detail"]
