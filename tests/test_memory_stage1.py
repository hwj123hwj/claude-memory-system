from pathlib import Path

from memory_stage1 import (
    MEMORY_BUCKETS,
    build_frontmatter,
    create_inbox_note,
    ensure_memory_layout,
)


def test_ensure_memory_layout_creates_buckets(tmp_path: Path) -> None:
    root = tmp_path / "ws"
    root.mkdir()
    ensure_memory_layout(root)

    for bucket in MEMORY_BUCKETS:
        assert (root / "memory" / bucket).exists()


def test_build_frontmatter_has_required_keys() -> None:
    fm = build_frontmatter(
        title="test",
        memory_type="inbox",
        tags=["a", "b"],
        source="chat",
    )
    assert "type: inbox" in fm
    assert "tags: [a, b]" in fm
    assert "source: chat" in fm
    assert "updated_at:" in fm
    assert "confidence: medium" in fm


def test_create_inbox_note_writes_file_under_00_inbox(tmp_path: Path) -> None:
    root = tmp_path / "ws"
    root.mkdir()
    ensure_memory_layout(root)

    note = create_inbox_note(
        root=root,
        content="today note",
        title="daily_capture",
        tags=["journal"],
        source="chat",
    )

    assert note.exists()
    assert "memory/00_Inbox" in note.as_posix()
    text = note.read_text(encoding="utf-8")
    assert text.startswith("---\n")
    assert "today note" in text

