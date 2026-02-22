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
    chatlog_enabled: bool = False
    chatlog_base_url: str = ""
    chatlog_webhook_token: str = ""
    chatlog_backfill_interval_seconds: int = 300
    chatlog_monitored_talkers: tuple[str, ...] = (
        "wxid_cfz3t4h22px722",
        "48651409135@chatroom",
    )
    chatlog_backfill_bootstrap_days: int = 1
    chatlog_backfill_consecutive_error_threshold: int = 3
    chatlog_webhook_dedup_ratio_threshold: float = 0.8
    chatlog_webhook_dedup_min_total: int = 20
    feishu_app_id: str = ""
    feishu_app_secret: str = ""
    feishu_encrypt_key: str = ""
    feishu_verification_token: str = ""
    feishu_agent_timeout_seconds: int = 120
    feishu_max_reply_chars: int = 1500


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


def _parse_bool(raw: str | None, default: bool) -> bool:
    if raw is None:
        return default
    normalized = raw.strip().lower()
    if normalized in {"1", "true", "yes", "on"}:
        return True
    if normalized in {"0", "false", "no", "off"}:
        return False
    return default


def _parse_csv(raw: str | None, default: tuple[str, ...]) -> tuple[str, ...]:
    if raw is None:
        return default
    items = tuple(x.strip() for x in raw.split(",") if x.strip())
    return items or default


def _parse_ratio(raw: str | None, default: float) -> float:
    if raw is None:
        return default
    try:
        value = float(raw)
    except (TypeError, ValueError):
        return default
    if value < 0 or value > 1:
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
    chatlog_enabled_raw = os.getenv("CHATLOG_ENABLED", file_env.get("CHATLOG_ENABLED"))
    chatlog_base_url = os.getenv("CHATLOG_BASE_URL", file_env.get("CHATLOG_BASE_URL", ""))
    chatlog_webhook_token = os.getenv(
        "CHATLOG_WEBHOOK_TOKEN",
        file_env.get("CHATLOG_WEBHOOK_TOKEN", ""),
    )
    chatlog_backfill_interval_raw = os.getenv(
        "CHATLOG_BACKFILL_INTERVAL_SECONDS",
        file_env.get("CHATLOG_BACKFILL_INTERVAL_SECONDS"),
    )
    chatlog_monitored_talkers_raw = os.getenv(
        "CHATLOG_MONITORED_TALKERS",
        file_env.get("CHATLOG_MONITORED_TALKERS"),
    )
    chatlog_backfill_bootstrap_days_raw = os.getenv(
        "CHATLOG_BACKFILL_BOOTSTRAP_DAYS",
        file_env.get("CHATLOG_BACKFILL_BOOTSTRAP_DAYS"),
    )
    chatlog_backfill_error_threshold_raw = os.getenv(
        "CHATLOG_BACKFILL_CONSECUTIVE_ERROR_THRESHOLD",
        file_env.get("CHATLOG_BACKFILL_CONSECUTIVE_ERROR_THRESHOLD"),
    )
    chatlog_dedup_ratio_threshold_raw = os.getenv(
        "CHATLOG_WEBHOOK_DEDUP_RATIO_THRESHOLD",
        file_env.get("CHATLOG_WEBHOOK_DEDUP_RATIO_THRESHOLD"),
    )
    chatlog_dedup_min_total_raw = os.getenv(
        "CHATLOG_WEBHOOK_DEDUP_MIN_TOTAL",
        file_env.get("CHATLOG_WEBHOOK_DEDUP_MIN_TOTAL"),
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
    feishu_max_reply_chars_raw = os.getenv(
        "FEISHU_MAX_REPLY_CHARS",
        file_env.get("FEISHU_MAX_REPLY_CHARS"),
    )
    return RuntimeConfig(
        max_turns=_parse_positive_int(max_turns_raw, 30),
        stale_client_delay_seconds=_parse_positive_int(stale_delay_raw, 20),
        memory_index_max_entries=_parse_positive_int(memory_index_max_entries_raw, 50),
        agent_run_timeout_seconds=_parse_positive_int(agent_run_timeout_raw, 180),
        chatlog_enabled=_parse_bool(chatlog_enabled_raw, False),
        chatlog_base_url=chatlog_base_url,
        chatlog_webhook_token=chatlog_webhook_token,
        chatlog_backfill_interval_seconds=_parse_positive_int(
            chatlog_backfill_interval_raw,
            300,
        ),
        chatlog_monitored_talkers=_parse_csv(
            chatlog_monitored_talkers_raw,
            ("wxid_cfz3t4h22px722", "48651409135@chatroom"),
        ),
        chatlog_backfill_bootstrap_days=_parse_positive_int(
            chatlog_backfill_bootstrap_days_raw,
            1,
        ),
        chatlog_backfill_consecutive_error_threshold=_parse_positive_int(
            chatlog_backfill_error_threshold_raw,
            3,
        ),
        chatlog_webhook_dedup_ratio_threshold=_parse_ratio(
            chatlog_dedup_ratio_threshold_raw,
            0.8,
        ),
        chatlog_webhook_dedup_min_total=_parse_positive_int(
            chatlog_dedup_min_total_raw,
            20,
        ),
        feishu_app_id=feishu_app_id,
        feishu_app_secret=feishu_app_secret,
        feishu_encrypt_key=feishu_encrypt_key,
        feishu_verification_token=feishu_verification_token,
        feishu_agent_timeout_seconds=_parse_positive_int(feishu_agent_timeout_raw, 120),
        feishu_max_reply_chars=_parse_positive_int(feishu_max_reply_chars_raw, 1500),
    )
