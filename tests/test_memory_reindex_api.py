from pathlib import Path

from fastapi.testclient import TestClient

from app import app


def test_memory_reindex_api_rebuilds_index() -> None:
    client = TestClient(app)
    response = client.post("/api/memory/reindex")
    assert response.status_code == 200

    data = response.json()
    index_path = Path(data["path"])
    assert index_path.exists()
    assert index_path.name == "_index.json"
    assert data["message"] == "记忆索引已重建。"
