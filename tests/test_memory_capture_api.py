from pathlib import Path

from fastapi.testclient import TestClient

from app import app


def test_memory_capture_api_writes_inbox_file() -> None:
    client = TestClient(app)
    response = client.post(
        "/api/memory/capture",
        json={
            "title": "api_capture_test",
            "content": "capture from api test",
            "tags": ["test", "api"],
            "source": "pytest",
        },
    )
    assert response.status_code == 200

    data = response.json()
    path = Path(data["path"])
    assert path.exists()
    assert "memory/00_Inbox" in path.as_posix()

    content = path.read_text(encoding="utf-8")
    assert "capture from api test" in content
    assert "type: inbox" in content

    path.unlink(missing_ok=True)

