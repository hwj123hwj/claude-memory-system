from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


INDEX_FILE_NAME = "_index.json"
INDEX_EXCLUDE_NAMES = {"_index.json", "_index.yaml"}
SYSTEM_DOC_EXCLUDE_NAMES = {"MEMORY_SCHEMA.md", "README.md"}
ALLOWED_SUFFIXES = {".md", ".yaml", ".yml"}


def _parse_frontmatter(text: str) -> dict[str, Any]:
    if not text.startswith("---\n"):
        return {}
    lines = text.splitlines()
    if len(lines) < 3:
        return {}

    data: dict[str, Any] = {}
    i = 1
    while i < len(lines):
        line = lines[i].strip()
        if line == "---":
            break
        if ":" in line:
            key, raw_value = line.split(":", 1)
            key = key.strip()
            value = raw_value.strip()
            if value.startswith("[") and value.endswith("]"):
                inner = value[1:-1].strip()
                if not inner:
                    data[key] = []
                else:
                    data[key] = [x.strip() for x in inner.split(",")]
            else:
                data[key] = value
        i += 1
    return data


def _extract_summary(text: str, max_chars: int = 160) -> str:
    body = text
    if text.startswith("---\n"):
        pos = text.find("\n---", 4)
        if pos != -1:
            body = text[pos + 4 :]
    lines = [x.strip() for x in body.splitlines() if x.strip()]
    if not lines:
        return ""
    merged = " ".join(lines)
    if len(merged) <= max_chars:
        return merged
    return merged[: max_chars - 6].rstrip() + " [已截断]"


def _iter_memory_files(memory_root: Path) -> list[Path]:
    files = []
    for path in memory_root.rglob("*"):
        if not path.is_file():
            continue
        if path.name in INDEX_EXCLUDE_NAMES:
            continue
        if path.name in SYSTEM_DOC_EXCLUDE_NAMES:
            continue
        if path.suffix.lower() not in ALLOWED_SUFFIXES:
            continue
        files.append(path)
    files.sort(key=lambda p: p.stat().st_mtime, reverse=True)
    return files


def build_index_data(root: Path) -> dict[str, Any]:
    memory_root = root / "memory"
    memory_root.mkdir(parents=True, exist_ok=True)
    files = _iter_memory_files(memory_root)

    rows: list[dict[str, Any]] = []
    for path in files:
        text = path.read_text(encoding="utf-8", errors="ignore")
        fm = _parse_frontmatter(text)
        stat = path.stat()
        rows.append(
            {
                "path": str(path.relative_to(root)).replace("\\", "/"),
                "title": fm.get("title", path.stem),
                "type": fm.get("type", ""),
                "tags": fm.get("tags", []),
                "updated_at": fm.get("updated_at", ""),
                "mtime": datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc).isoformat(),
                "size": stat.st_size,
                "summary": _extract_summary(text),
            }
        )

    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "memory_root": str(memory_root),
        "file_count": len(rows),
        "files": rows,
    }


def write_memory_index(root: Path) -> Path:
    data = build_index_data(root)
    index_path = root / "memory" / INDEX_FILE_NAME
    index_path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    return index_path


