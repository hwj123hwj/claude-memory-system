from pathlib import Path

from memory_context import build_memory_context, is_memory_query


def test_is_memory_query() -> None:
    assert is_memory_query("给我个人记忆概要") is True
    assert is_memory_query("show memory files") is True
    assert is_memory_query("列出当前目录") is False


def test_build_memory_context_includes_memory_paths() -> None:
    root = Path(__file__).resolve().parents[1]
    text = build_memory_context(root)
    normalized = text.replace("\\", "/")
    assert "memory/_index.json" in normalized
    assert "索引条目" in text
