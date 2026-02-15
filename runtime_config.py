from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class RuntimeConfig:
    max_turns: int = 30
    stale_client_delay_seconds: int = 20
    memory_index_max_entries: int = 50


def _parse_env_file(path: Path) -> dict[str, str]:
    if not path.exists():
        return {}

    result: dict[str, str] = {}
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        result[key.strip()] = value.strip().strip("\"'")
    return result


def _parse_positive_int(raw: str | None, default: int) -> int:
    if raw is None:
        return default
    try:
        value = int(raw)
    except (TypeError, ValueError):
        return default
    if value <= 0:
        return default
    return value


def load_runtime_config(env_file: Path) -> RuntimeConfig:
    file_env = _parse_env_file(env_file)
    max_turns_raw = os.getenv("MAX_TURNS", file_env.get("MAX_TURNS"))
    stale_delay_raw = os.getenv(
        "STALE_CLIENT_DELAY_SECONDS",
        file_env.get("STALE_CLIENT_DELAY_SECONDS"),
    )
    memory_index_max_entries_raw = os.getenv(
        "MEMORY_INDEX_MAX_ENTRIES",
        file_env.get("MEMORY_INDEX_MAX_ENTRIES"),
    )
    return RuntimeConfig(
        max_turns=_parse_positive_int(max_turns_raw, 30),
        stale_client_delay_seconds=_parse_positive_int(stale_delay_raw, 20),
        memory_index_max_entries=_parse_positive_int(memory_index_max_entries_raw, 50),
    )
