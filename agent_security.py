from __future__ import annotations

from pathlib import Path
from typing import Any


PATH_HINT_KEYS = {
    "path",
    "file_path",
    "target_file",
    "new_file_path",
    "cwd",
    "directory",
}


def resolve_candidate_path(raw_path: str, root: Path) -> Path:
    candidate = Path(raw_path)
    if candidate.is_absolute():
        return candidate.resolve()
    return (root / candidate).resolve()


def _iter_candidate_paths(data: Any) -> list[str]:
    paths: list[str] = []
    if isinstance(data, dict):
        for key, value in data.items():
            if key in PATH_HINT_KEYS and isinstance(value, str):
                paths.append(value)
            else:
                paths.extend(_iter_candidate_paths(value))
    elif isinstance(data, list):
        for item in data:
            paths.extend(_iter_candidate_paths(item))
    return paths


def is_tool_input_within_root(input_data: dict[str, Any], root: Path) -> bool:
    root = root.resolve()
    for raw_path in _iter_candidate_paths(input_data):
        resolved = resolve_candidate_path(raw_path, root)
        if resolved != root and root not in resolved.parents:
            return False
    return True

