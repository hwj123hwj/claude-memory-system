from __future__ import annotations

from datetime import datetime
from pathlib import Path
from uuid import uuid4

from memory_index import write_memory_index


MEMORY_BUCKETS = [
    "00_Inbox",
    "10_Growth",
    "20_Connections",
    "30_Wealth",
    "40_ProductMind",
    "_templates",
]


def ensure_memory_layout(root: Path) -> Path:
    memory_root = root / "memory"
    memory_root.mkdir(parents=True, exist_ok=True)
    for bucket in MEMORY_BUCKETS:
        (memory_root / bucket).mkdir(parents=True, exist_ok=True)
    write_memory_index(root)
    return memory_root


def build_frontmatter(
    *,
    title: str,
    memory_type: str,
    tags: list[str],
    source: str,
    confidence: str = "medium",
) -> str:
    now = datetime.now().isoformat(timespec="seconds")
    tags_str = ", ".join(tags)
    return (
        "---\n"
        f"title: {title}\n"
        f"type: {memory_type}\n"
        f"tags: [{tags_str}]\n"
        f"source: {source}\n"
        f"updated_at: {now}\n"
        f"confidence: {confidence}\n"
        "---\n"
    )


def create_inbox_note(
    *,
    root: Path,
    content: str,
    title: str = "capture",
    tags: list[str] | None = None,
    source: str = "chat",
) -> Path:
    memory_root = ensure_memory_layout(root)
    inbox = memory_root / "00_Inbox"

    ts = datetime.now().strftime("%Y%m%d-%H%M%S")
    file_name = f"{ts}-{uuid4().hex[:6]}-{title}.md"
    path = inbox / file_name

    frontmatter = build_frontmatter(
        title=title,
        memory_type="inbox",
        tags=tags or [],
        source=source,
    )
    path.write_text(f"{frontmatter}\n{content.strip()}\n", encoding="utf-8")
    write_memory_index(root)
    return path


def create_bucket_note(
    *,
    root: Path,
    bucket: str,
    title: str,
    content: str,
    tags: list[str] | None = None,
    source: str = "chat",
    memory_type: str = "note",
) -> Path:
    memory_root = ensure_memory_layout(root)
    if bucket not in MEMORY_BUCKETS:
        raise ValueError(f"Unknown bucket: {bucket}")
    folder = memory_root / bucket
    ts = datetime.now().strftime("%Y%m%d-%H%M%S")
    file_name = f"{ts}-{uuid4().hex[:6]}-{title}.md"
    path = folder / file_name
    frontmatter = build_frontmatter(
        title=title,
        memory_type=memory_type,
        tags=tags or [],
        source=source,
    )
    path.write_text(f"{frontmatter}\n{content.strip()}\n", encoding="utf-8")
    write_memory_index(root)
    return path
