from dataclasses import replace

from fastapi.testclient import TestClient

import app


def _cfg(monkeypatch, tmp_path) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.setattr(app, "CHATLOG_TARGETS_FILE", tmp_path / "targets.json")
    monkeypatch.setattr(app, "CHATLOG_STATE_DB", tmp_path / "state.db")
    monkeypatch.setattr(
        app,
        "RUNTIME_CONFIG",
        replace(app.RUNTIME_CONFIG, chatlog_enabled=True, chatlog_webhook_token="top-secret"),
    )


def test_chatlog_targets_crud(monkeypatch, tmp_path) -> None:
    _cfg(monkeypatch, tmp_path)
    client = TestClient(app.app)
    up = client.post(
        "/api/integrations/chatlog/targets/upsert",
        json={
            "talker": "48651409135@chatroom",
            "group_type": "learning",
            "importance": 5,
            "default_memory_bucket": "10_Growth",
        },
    )
    assert up.status_code == 200
    assert up.json()["item"]["group_type"] == "learning"

    listed = client.get("/api/integrations/chatlog/targets")
    assert listed.status_code == 200
    assert len(listed.json()["items"]) == 1

    deleted = client.delete("/api/integrations/chatlog/targets/48651409135@chatroom")
    assert deleted.status_code == 200
    assert deleted.json()["removed"] is True


def test_notification_group_drops_non_important_message(monkeypatch, tmp_path) -> None:
    _cfg(monkeypatch, tmp_path)
    client = TestClient(app.app)
    client.post(
        "/api/integrations/chatlog/targets/upsert",
        json={
            "talker": "48651409135@chatroom",
            "group_type": "notification",
        },
    )
    resp = client.post(
        "/api/integrations/chatlog/webhook",
        headers={"X-Webhook-Token": "top-secret"},
        json={
            "talker": "48651409135@chatroom",
            "messages": [
                {"seq": 999, "time": "2026-02-18T10:00:00+08:00", "content": "大家好呀"}
            ],
        },
    )
    assert resp.status_code == 200
    assert resp.json()["accepted"] == 0
