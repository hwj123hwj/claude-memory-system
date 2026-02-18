from dataclasses import replace

from fastapi.testclient import TestClient

import app


def _configure_chatlog(monkeypatch, tmp_path) -> None:  # type: ignore[no-untyped-def]
    cfg = replace(app.RUNTIME_CONFIG, chatlog_enabled=True, chatlog_webhook_token="top-secret")
    app.RUNTIME_CONFIG = cfg
    monkeypatch.setattr(app, "CHATLOG_STATE_DB", tmp_path / "chatlog_state.db")
    monkeypatch.setattr(app, "CHATLOG_TARGETS_FILE", tmp_path / "targets.json")


def test_chatlog_webhook_rejects_missing_token(monkeypatch, tmp_path) -> None:
    _configure_chatlog(monkeypatch, tmp_path)
    client = TestClient(app.app)

    response = client.post(
        "/api/integrations/chatlog/webhook",
        json={"talker": "wxid_xxx", "messages": [{"content": "hi"}]},
    )
    assert response.status_code == 403


def test_chatlog_webhook_rejects_invalid_payload(monkeypatch, tmp_path) -> None:
    _configure_chatlog(monkeypatch, tmp_path)
    client = TestClient(app.app)

    response = client.post(
        "/api/integrations/chatlog/webhook",
        headers={"X-Webhook-Token": "top-secret"},
        json={"talker": "wxid_xxx", "messages": []},
    )
    assert response.status_code == 422


def test_chatlog_webhook_accepts_valid_payload(monkeypatch, tmp_path) -> None:
    _configure_chatlog(monkeypatch, tmp_path)
    client = TestClient(app.app)

    response = client.post(
        "/api/integrations/chatlog/webhook",
        headers={"X-Webhook-Token": "top-secret"},
        json={
            "talker": "123456@chatroom",
            "messages": [
                {"seq": 1, "time": "2026-02-18T10:00:00+08:00", "content": "hello"}
            ],
        },
    )
    assert response.status_code == 200
    data = response.json()
    assert data["ok"] is True
    assert data["talker"] == "123456@chatroom"
    assert data["accepted"] == 1
    assert data["mode"] == "group_digest"


def test_chatlog_webhook_deduplicates_replayed_message(monkeypatch, tmp_path) -> None:
    _configure_chatlog(monkeypatch, tmp_path)
    client = TestClient(app.app)

    payload = {
        "talker": "123456@chatroom",
        "messages": [
            {"seq": 10001, "time": "2026-02-18T10:00:00+08:00", "content": "hello"}
        ],
    }
    headers = {"X-Webhook-Token": "top-secret"}

    first = client.post("/api/integrations/chatlog/webhook", headers=headers, json=payload)
    second = client.post("/api/integrations/chatlog/webhook", headers=headers, json=payload)

    assert first.status_code == 200
    assert first.json()["accepted"] == 1
    assert second.status_code == 200
    assert second.json()["accepted"] == 0


def test_chatlog_webhook_persists_memory_note(monkeypatch, tmp_path) -> None:
    _configure_chatlog(monkeypatch, tmp_path)
    created: dict[str, object] = {}

    def fake_create_bucket_note(*, root, bucket, content, title, tags, source, memory_type):  # type: ignore[no-untyped-def]
        created["root"] = root
        created["bucket"] = bucket
        created["content"] = content
        created["title"] = title
        created["tags"] = tags
        created["source"] = source
        created["memory_type"] = memory_type
        return tmp_path / "note.md"

    monkeypatch.setattr(app, "create_bucket_note", fake_create_bucket_note)
    client = TestClient(app.app)
    response = client.post(
        "/api/integrations/chatlog/webhook",
        headers={"X-Webhook-Token": "top-secret"},
        json={
            "talker": "48651409135@chatroom",
            "messages": [
                {
                    "seq": 123,
                    "time": "2026-02-18T10:00:00+08:00",
                    "senderName": "hao",
                    "content": "test message",
                }
            ],
        },
    )
    assert response.status_code == 200
    assert created["source"] == "chatlog_webhook"
    assert created["bucket"] == "40_ProductMind"
    assert created["memory_type"] == "chatlog"
    assert "48651409135_chatroom" in str(created["title"])


def test_chatlog_webhook_contact_note_routes_to_connections(monkeypatch, tmp_path) -> None:
    _configure_chatlog(monkeypatch, tmp_path)
    created: dict[str, object] = {}

    def fake_create_bucket_note(*, root, bucket, content, title, tags, source, memory_type):  # type: ignore[no-untyped-def]
        created["bucket"] = bucket
        created["source"] = source
        return tmp_path / "note.md"

    monkeypatch.setattr(app, "create_bucket_note", fake_create_bucket_note)
    client = TestClient(app.app)
    response = client.post(
        "/api/integrations/chatlog/webhook",
        headers={"X-Webhook-Token": "top-secret"},
        json={
            "talker": "wxid_cfz3t4h22px722",
            "messages": [{"seq": 124, "time": "2026-02-18T10:01:00+08:00", "content": "hi"}],
        },
    )
    assert response.status_code == 200
    assert created["source"] == "chatlog_webhook"
    assert created["bucket"] == "20_Connections"


def test_chatlog_webhook_group_learning_routes_to_growth(monkeypatch, tmp_path) -> None:
    _configure_chatlog(monkeypatch, tmp_path)
    app.ChatlogTargetStore(app.CHATLOG_TARGETS_FILE).upsert_target(
        "48651409135@chatroom",
        {"group_type": "learning", "capture_policy": "hybrid"},
    )
    created: dict[str, object] = {}

    def fake_create_bucket_note(*, root, bucket, content, title, tags, source, memory_type):  # type: ignore[no-untyped-def]
        created["bucket"] = bucket
        return tmp_path / "note.md"

    monkeypatch.setattr(app, "create_bucket_note", fake_create_bucket_note)
    client = TestClient(app.app)
    response = client.post(
        "/api/integrations/chatlog/webhook",
        headers={"X-Webhook-Token": "top-secret"},
        json={
            "talker": "48651409135@chatroom",
            "messages": [{"seq": 125, "time": "2026-02-18T10:01:00+08:00", "content": "deadline for learning docs"}],
        },
    )
    assert response.status_code == 200
    assert created["bucket"] == "10_Growth"


def test_chatlog_webhook_group_filters_by_important_people(monkeypatch, tmp_path) -> None:
    _configure_chatlog(monkeypatch, tmp_path)
    app.ChatlogTargetStore(app.CHATLOG_TARGETS_FILE).upsert_target(
        "48651409135@chatroom",
        {"group_type": "info_gap", "important_people": ["VIP"], "capture_policy": "hybrid"},
    )
    client = TestClient(app.app)

    not_important = client.post(
        "/api/integrations/chatlog/webhook",
        headers={"X-Webhook-Token": "top-secret"},
        json={
            "talker": "48651409135@chatroom",
            "messages": [
                {
                    "seq": 2001,
                    "time": "2026-02-18T10:10:00+08:00",
                    "senderName": "random",
                    "content": "hello everyone",
                }
            ],
        },
    )
    assert not_important.status_code == 200
    assert not_important.json()["accepted"] == 0

    important_person = client.post(
        "/api/integrations/chatlog/webhook",
        headers={"X-Webhook-Token": "top-secret"},
        json={
            "talker": "48651409135@chatroom",
            "messages": [
                {
                    "seq": 2002,
                    "time": "2026-02-18T10:11:00+08:00",
                    "senderName": "VIP",
                    "content": "I want to add context",
                }
            ],
        },
    )
    assert important_person.status_code == 200
    assert important_person.json()["accepted"] == 1


def test_chatlog_webhook_group_summary_only_skips_raw_messages(monkeypatch, tmp_path) -> None:
    _configure_chatlog(monkeypatch, tmp_path)
    app.ChatlogTargetStore(app.CHATLOG_TARGETS_FILE).upsert_target(
        "48651409135@chatroom",
        {"group_type": "learning", "capture_policy": "summary_only"},
    )
    client = TestClient(app.app)

    response = client.post(
        "/api/integrations/chatlog/webhook",
        headers={"X-Webhook-Token": "top-secret"},
        json={
            "talker": "48651409135@chatroom",
            "messages": [
                {
                    "seq": 3001,
                    "time": "2026-02-18T10:20:00+08:00",
                    "senderName": "A",
                    "content": "normal update",
                }
            ],
        },
    )
    assert response.status_code == 200
    assert response.json()["accepted"] == 0


def test_chatlog_webhook_group_key_events_only_accepts_high_value(monkeypatch, tmp_path) -> None:
    _configure_chatlog(monkeypatch, tmp_path)
    app.ChatlogTargetStore(app.CHATLOG_TARGETS_FILE).upsert_target(
        "48651409135@chatroom",
        {"group_type": "info_gap", "capture_policy": "key_events"},
    )
    client = TestClient(app.app)

    skipped = client.post(
        "/api/integrations/chatlog/webhook",
        headers={"X-Webhook-Token": "top-secret"},
        json={
            "talker": "48651409135@chatroom",
            "messages": [
                {"seq": 3101, "time": "2026-02-18T10:21:00+08:00", "senderName": "A", "content": "hello"}
            ],
        },
    )
    accepted = client.post(
        "/api/integrations/chatlog/webhook",
        headers={"X-Webhook-Token": "top-secret"},
        json={
            "talker": "48651409135@chatroom",
            "messages": [
                {
                    "seq": 3102,
                    "time": "2026-02-18T10:22:00+08:00",
                    "senderName": "A",
                    "content": "deadline tomorrow",
                }
            ],
        },
    )
    assert skipped.status_code == 200
    assert skipped.json()["accepted"] == 0
    assert accepted.status_code == 200
    assert accepted.json()["accepted"] == 1


def test_chatlog_webhook_group_hybrid_accepts_people_or_events(monkeypatch, tmp_path) -> None:
    _configure_chatlog(monkeypatch, tmp_path)
    app.ChatlogTargetStore(app.CHATLOG_TARGETS_FILE).upsert_target(
        "48651409135@chatroom",
        {"group_type": "info_gap", "capture_policy": "hybrid", "important_people": ["VIP"]},
    )
    client = TestClient(app.app)

    by_person = client.post(
        "/api/integrations/chatlog/webhook",
        headers={"X-Webhook-Token": "top-secret"},
        json={
            "talker": "48651409135@chatroom",
            "messages": [
                {"seq": 3201, "time": "2026-02-18T10:23:00+08:00", "senderName": "VIP", "content": "routine"}
            ],
        },
    )
    by_event = client.post(
        "/api/integrations/chatlog/webhook",
        headers={"X-Webhook-Token": "top-secret"},
        json={
            "talker": "48651409135@chatroom",
            "messages": [
                {"seq": 3202, "time": "2026-02-18T10:24:00+08:00", "senderName": "A", "content": "deadline soon"}
            ],
        },
    )
    assert by_person.status_code == 200
    assert by_person.json()["accepted"] == 1
    assert by_event.status_code == 200
    assert by_event.json()["accepted"] == 1
