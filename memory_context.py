from __future__ import annotations

from pathlib import Path


def is_memory_query(text: str) -> bool:
    lower = text.lower()
    return any(k in text for k in ("记忆", "个人记忆", "记忆系统")) or "memory" in lower


def build_memory_context(root: Path, max_files: int = 12, max_chars: int = 12000) -> str:
    memory_root = root / "memory"
    if not memory_root.exists() or not memory_root.is_dir():
        return f"memory 目录不存在：{memory_root}"

    files = sorted(
        [
            p
            for p in memory_root.rglob("*")
            if p.is_file() and p.suffix.lower() in {".md", ".yaml", ".yml"}
        ]
    )[:max_files]

    parts: list[str] = [f"memory 根目录：{memory_root}", "文件列表："]
    for p in files:
        parts.append(f"- {p.relative_to(root)}")

    used = 0
    for p in files:
        if used >= max_chars:
            break
        text = p.read_text(encoding="utf-8", errors="ignore")
        remain = max_chars - used
        snippet = text[:remain]
        used += len(snippet)
        parts.append(f"\n### {p.relative_to(root)}\n{snippet}")

    return "\n".join(parts)
