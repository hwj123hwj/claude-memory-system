from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class RuntimeConfig:
    max_turns: int = 30
    stale_client_delay_seconds: int = 20
    memory_index_max_entries: int = 50
    agent_run_timeout_seconds: int = 180
    feishu_app_id: str = ""
    feishu_app_secret: str = ""
    feishu_encrypt_key: str = ""
    feishu_verification_token: str = ""
    feishu_agent_timeout_seconds: int = 120


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
    agent_run_timeout_raw = os.getenv(
        "AGENT_RUN_TIMEOUT_SECONDS",
        file_env.get("AGENT_RUN_TIMEOUT_SECONDS"),
    )
    feishu_app_id = os.getenv("FEISHU_APP_ID", file_env.get("FEISHU_APP_ID", ""))
    feishu_app_secret = os.getenv(
        "FEISHU_APP_SECRET",
        file_env.get("FEISHU_APP_SECRET", ""),
    )
    feishu_encrypt_key = os.getenv(
        "FEISHU_ENCRYPT_KEY",
        file_env.get("FEISHU_ENCRYPT_KEY", ""),
    )
    feishu_verification_token = os.getenv(
        "FEISHU_VERIFICATION_TOKEN",
        file_env.get("FEISHU_VERIFICATION_TOKEN", ""),
    )
    feishu_agent_timeout_raw = os.getenv(
        "FEISHU_AGENT_TIMEOUT_SECONDS",
        file_env.get("FEISHU_AGENT_TIMEOUT_SECONDS"),
    )
    return RuntimeConfig(
        max_turns=_parse_positive_int(max_turns_raw, 30),
        stale_client_delay_seconds=_parse_positive_int(stale_delay_raw, 20),
        memory_index_max_entries=_parse_positive_int(memory_index_max_entries_raw, 50),
        agent_run_timeout_seconds=_parse_positive_int(agent_run_timeout_raw, 180),
        feishu_app_id=feishu_app_id,
        feishu_app_secret=feishu_app_secret,
        feishu_encrypt_key=feishu_encrypt_key,
        feishu_verification_token=feishu_verification_token,
        feishu_agent_timeout_seconds=_parse_positive_int(feishu_agent_timeout_raw, 120),
    )
