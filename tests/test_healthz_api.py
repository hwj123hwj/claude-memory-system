import json
from dataclasses import replace
from datetime import datetime, timedelta, timezone

from fastapi.testclient import TestClient

import app


def test_healthz_without_bridge_heartbeat(monkeypatch, tmp_path) -> None:
    monkeypatch.setattr(app, "RUNTIME_CONFIG", replace(app.RUNTIME_CONFIG, chatlog_enabled=False))
    heartbeat = tmp_path / "heartbeat.json"
    monkeypatch.setattr(app, "BRIDGE_HEARTBEAT_FILE", heartbeat)
    client = TestClient(app.app)
    response = client.get("/healthz")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
    assert data["backend"] == "ok"
    assert data["bridge"]["status"] == "unknown"
    assert "chatlog" in data
    assert data["chatlog"]["enabled"] is False


def test_healthz_with_fresh_bridge_heartbeat(monkeypatch, tmp_path) -> None:
    monkeypatch.setattr(app, "RUNTIME_CONFIG", replace(app.RUNTIME_CONFIG, chatlog_enabled=False))
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
    assert "chatlog" in data


def test_healthz_with_stale_bridge_heartbeat(monkeypatch, tmp_path) -> None:
    monkeypatch.setattr(app, "RUNTIME_CONFIG", replace(app.RUNTIME_CONFIG, chatlog_enabled=False))
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
    assert "chatlog" in data


def test_healthz_degraded_on_backfill_error_streak(monkeypatch, tmp_path) -> None:
    monkeypatch.setattr(
        app,
        "RUNTIME_CONFIG",
        replace(
            app.RUNTIME_CONFIG,
            chatlog_enabled=True,
            chatlog_backfill_consecutive_error_threshold=2,
        ),
    )
    monkeypatch.setitem(app.CHATLOG_RUNTIME, "backfill_consecutive_error_runs", 3)
    monkeypatch.setitem(app.CHATLOG_RUNTIME, "webhook_accepted_total", 0)
    monkeypatch.setitem(app.CHATLOG_RUNTIME, "webhook_deduped_total", 0)
    heartbeat = tmp_path / "heartbeat.json"
    monkeypatch.setattr(app, "BRIDGE_HEARTBEAT_FILE", heartbeat)
    client = TestClient(app.app)

    response = client.get("/healthz")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "degraded"
    assert data["chatlog"]["signals"]["backfill_error_alert"] is True


def test_healthz_degraded_on_dedup_ratio_alert(monkeypatch, tmp_path) -> None:
    monkeypatch.setattr(
        app,
        "RUNTIME_CONFIG",
        replace(
            app.RUNTIME_CONFIG,
            chatlog_enabled=True,
            chatlog_webhook_dedup_ratio_threshold=0.6,
            chatlog_webhook_dedup_min_total=10,
        ),
    )
    monkeypatch.setitem(app.CHATLOG_RUNTIME, "backfill_consecutive_error_runs", 0)
    monkeypatch.setitem(app.CHATLOG_RUNTIME, "webhook_accepted_total", 2)
    monkeypatch.setitem(app.CHATLOG_RUNTIME, "webhook_deduped_total", 18)
    heartbeat = tmp_path / "heartbeat.json"
    monkeypatch.setattr(app, "BRIDGE_HEARTBEAT_FILE", heartbeat)
    client = TestClient(app.app)

    response = client.get("/healthz")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "degraded"
    assert data["chatlog"]["signals"]["webhook_dedup_alert"] is True
