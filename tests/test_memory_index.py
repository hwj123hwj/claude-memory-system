from pathlib import Path

from memory_index import build_index_data, write_memory_index


def test_write_memory_index_creates_index_file(tmp_path: Path) -> None:
    root = tmp_path / "ws"
    memory = root / "memory"
    (memory / "00_Inbox").mkdir(parents=True)
    note = memory / "00_Inbox" / "sample.md"
    note.write_text(
        "---\n"
        "title: sample\n"
        "type: inbox\n"
        "tags: [a, b]\n"
        "updated_at: 2026-02-15T10:00:00\n"
        "---\n\n"
        "hello world\n",
        encoding="utf-8",
    )

    index_path = write_memory_index(root)
    assert index_path.exists()
    assert index_path.name == "_index.json"
    text = index_path.read_text(encoding="utf-8")
    assert "sample.md" in text
    assert "hello world" in text


def test_build_index_data_excludes_index_file(tmp_path: Path) -> None:
    root = tmp_path / "ws"
    memory = root / "memory"
    (memory / "10_Growth").mkdir(parents=True)
    (memory / "_index.json").write_text("{}", encoding="utf-8")
    note = memory / "10_Growth" / "plan.md"
    note.write_text("# plan", encoding="utf-8")

    data = build_index_data(root)
    paths = [item["path"] for item in data["files"]]
    assert "memory/_index.json" not in paths
    assert "memory/10_Growth/plan.md" in paths


def test_build_index_data_excludes_legacy_index_yaml(tmp_path: Path) -> None:
    root = tmp_path / "ws"
    memory = root / "memory"
    (memory / "10_Growth").mkdir(parents=True)
    (memory / "_index.yaml").write_text("legacy", encoding="utf-8")
    (memory / "_index.json").write_text("{}", encoding="utf-8")
    note = memory / "10_Growth" / "plan.md"
    note.write_text("# plan", encoding="utf-8")

    data = build_index_data(root)
    paths = [item["path"] for item in data["files"]]
    assert "memory/_index.yaml" not in paths
    assert "memory/_index.json" not in paths
    assert "memory/10_Growth/plan.md" in paths


def test_build_index_data_excludes_system_docs(tmp_path: Path) -> None:
    root = tmp_path / "ws"
    memory = root / "memory"
    (memory / "10_Growth").mkdir(parents=True)
    (memory / "MEMORY_SCHEMA.md").write_text("# schema", encoding="utf-8")
    (memory / "README.md").write_text("# readme", encoding="utf-8")
    note = memory / "10_Growth" / "plan.md"
    note.write_text("# plan", encoding="utf-8")

    data = build_index_data(root)
    paths = [item["path"] for item in data["files"]]
    assert "memory/MEMORY_SCHEMA.md" not in paths
    assert "memory/README.md" not in paths
    assert "memory/10_Growth/plan.md" in paths
