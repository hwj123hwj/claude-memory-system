from fastapi.testclient import TestClient

import app


def test_feishu_webhook_challenge() -> None:
    client = TestClient(app.app)
    response = client.post("/api/feishu/webhook", json={"challenge": "abc123"})
    assert response.status_code == 200
    assert response.json() == {"challenge": "abc123"}


def test_feishu_webhook_text_event(monkeypatch) -> None:
    client = TestClient(app.app)

    called: dict[str, str] = {}

    async def fake_run_agent(prompt: str, conversation_id: str, force_new_client: bool):  # type: ignore[no-untyped-def]
        called["prompt"] = prompt
        called["conversation_id"] = conversation_id
        called["force_new_client"] = str(force_new_client)
        return "mock-reply", "logs/mock.jsonl"

    async def fake_send_text(*, receive_id: str, text: str, receive_id_type: str = "chat_id"):  # type: ignore[no-untyped-def]
        called["receive_id"] = receive_id
        called["text"] = text
        called["receive_id_type"] = receive_id_type
        return {"ok": True}

    monkeypatch.setattr(app, "run_agent", fake_run_agent)
    monkeypatch.setattr(app, "send_feishu_text", fake_send_text)

    payload = {
        "event": {
            "sender": {"sender_type": "user"},
            "message": {
                "chat_id": "oc_test_chat",
                "message_type": "text",
                "content": "{\"text\":\"你好，帮我看下记忆系统\"}",
            },
        }
    }
    response = client.post("/api/feishu/webhook", json=payload)
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
    assert called["prompt"] == "你好，帮我看下记忆系统"
    assert called["conversation_id"] == "feishu:oc_test_chat"
    assert called["receive_id"] == "oc_test_chat"
    assert called["text"] == "mock-reply"
