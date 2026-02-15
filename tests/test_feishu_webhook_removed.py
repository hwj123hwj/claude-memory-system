from fastapi.testclient import TestClient

import app


def test_feishu_webhook_route_removed() -> None:
    client = TestClient(app.app)
    response = client.post("/api/feishu/webhook", json={"challenge": "abc123"})
    assert response.status_code == 404
