import json
from datetime import datetime, timedelta, timezone

from fastapi.testclient import TestClient

import app


def test_healthz_without_bridge_heartbeat(monkeypatch, tmp_path) -> None:
    heartbeat = tmp_path / "heartbeat.json"
    monkeypatch.setattr(app, "BRIDGE_HEARTBEAT_FILE", heartbeat)
    client = TestClient(app.app)
    response = client.get("/healthz")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
    assert data["backend"] == "ok"
    assert data["bridge"]["status"] == "unknown"


def test_healthz_with_fresh_bridge_heartbeat(monkeypatch, tmp_path) -> None:
    heartbeat = tmp_path / "heartbeat.json"
    now = datetime.now(timezone.utc)
    heartbeat.write_text(
        json.dumps({"ts": now.isoformat(), "event": "recv_text", "pid": 123}),
        encoding="utf-8",
    )
    monkeypatch.setattr(app, "BRIDGE_HEARTBEAT_FILE", heartbeat)
    monkeypatch.setattr(app, "BRIDGE_HEARTBEAT_STALE_SECONDS", 180)

    client = TestClient(app.app)
    response = client.get("/healthz")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
    assert data["bridge"]["status"] == "ok"
    assert data["bridge"]["event"] == "recv_text"
    assert isinstance(data["bridge"]["age_seconds"], int)


def test_healthz_with_stale_bridge_heartbeat(monkeypatch, tmp_path) -> None:
    heartbeat = tmp_path / "heartbeat.json"
    stale = datetime.now(timezone.utc) - timedelta(seconds=600)
    heartbeat.write_text(
        json.dumps({"ts": stale.isoformat(), "event": "started", "pid": 123}),
        encoding="utf-8",
    )
    monkeypatch.setattr(app, "BRIDGE_HEARTBEAT_FILE", heartbeat)
    monkeypatch.setattr(app, "BRIDGE_HEARTBEAT_STALE_SECONDS", 180)

    client = TestClient(app.app)
    response = client.get("/healthz")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "degraded"
    assert data["bridge"]["status"] == "stale"
