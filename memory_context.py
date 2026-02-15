from __future__ import annotations

import json
from pathlib import Path

from memory_index import INDEX_FILE_NAME, write_memory_index


def is_memory_query(text: str) -> bool:
    lower = text.lower()
    return any(k in text for k in ("记忆", "个人记忆", "记忆系统")) or "memory" in lower


def build_memory_context(root: Path, max_entries: int = 50) -> str:
    memory_root = root / "memory"
    if not memory_root.exists() or not memory_root.is_dir():
        return f"memory 目录不存在：{memory_root}"

    index_path = write_memory_index(root)
    raw = index_path.read_text(encoding="utf-8", errors="ignore")
    try:
        data = json.loads(raw)
    except Exception:
        return f"memory 索引解析失败：{index_path}"

    parts: list[str] = [
        f"memory 根目录：{memory_root}",
        f"索引文件：memory/{INDEX_FILE_NAME}",
        "索引条目：",
    ]
    files = data.get("files", [])
    for item in files[:max_entries]:
        path = item.get("path", "")
        title = item.get("title", "")
        memory_type = item.get("type", "")
        tags = item.get("tags", [])
        updated_at = item.get("updated_at", "")
        parts.append(
            f"- {path} | title={title} | type={memory_type} | tags={tags} | updated_at={updated_at}"
        )

    parts.append("说明：以上是 memory 索引。请先基于索引判断相关文件，再按需使用 Read 工具读取正文细节。")
    return "\n".join(parts)
