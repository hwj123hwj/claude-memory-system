from pathlib import Path

from runtime_config import RuntimeConfig, load_runtime_config


def _clear_sdk_env(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    for key in (
        "CLAUDE_MODEL",
        "PERMISSION_MODE",
        "ANTHROPIC_BASE_URL",
        "ANTHROPIC_AUTH_TOKEN",
        "ANTHROPIC_API_KEY",
        "CLAUDE_API_KEY",
    ):
        monkeypatch.delenv(key, raising=False)


def test_runtime_config_defaults_when_env_missing(tmp_path: Path, monkeypatch) -> None:
    _clear_sdk_env(monkeypatch)
    cfg = load_runtime_config(tmp_path / ".env")
    assert cfg == RuntimeConfig(
        max_turns=30,
        stale_client_delay_seconds=20,
        memory_index_max_entries=50,
        agent_run_timeout_seconds=180,
        chatlog_enabled=False,
        chatlog_base_url="",
        chatlog_webhook_token="",
        chatlog_backfill_interval_seconds=300,
        chatlog_monitored_talkers=(
            "wxid_cfz3t4h22px722",
            "48651409135@chatroom",
        ),
        chatlog_backfill_bootstrap_days=1,
        chatlog_backfill_consecutive_error_threshold=3,
        chatlog_webhook_dedup_ratio_threshold=0.8,
        chatlog_webhook_dedup_min_total=20,
        feishu_app_id="",
        feishu_app_secret="",
        feishu_encrypt_key="",
        feishu_verification_token="",
        feishu_agent_timeout_seconds=120,
        feishu_max_reply_chars=1500,
        claude_model="",
        permission_mode="default",
        anthropic_base_url="",
        anthropic_auth_token="",
        anthropic_api_key="",
    )


def test_runtime_config_reads_values_from_env_file(tmp_path: Path, monkeypatch) -> None:
    _clear_sdk_env(monkeypatch)
    env_path = tmp_path / ".env"
    env_path.write_text(
        "MAX_TURNS=45\nSTALE_CLIENT_DELAY_SECONDS=12\nMEMORY_INDEX_MAX_ENTRIES=42\nAGENT_RUN_TIMEOUT_SECONDS=240\nCHATLOG_ENABLED=true\nCHATLOG_BASE_URL=http://127.0.0.1:5030\nCHATLOG_WEBHOOK_TOKEN=chatlog_token\nCHATLOG_BACKFILL_INTERVAL_SECONDS=600\nCHATLOG_MONITORED_TALKERS=wxid_a,123@chatroom\nCHATLOG_BACKFILL_BOOTSTRAP_DAYS=3\nCHATLOG_BACKFILL_CONSECUTIVE_ERROR_THRESHOLD=5\nCHATLOG_WEBHOOK_DEDUP_RATIO_THRESHOLD=0.9\nCHATLOG_WEBHOOK_DEDUP_MIN_TOTAL=50\nFEISHU_APP_ID=cli_x\nFEISHU_APP_SECRET=sec_y\nFEISHU_ENCRYPT_KEY=enc_k\nFEISHU_VERIFICATION_TOKEN=vtok\nFEISHU_AGENT_TIMEOUT_SECONDS=90\nFEISHU_MAX_REPLY_CHARS=1800\nCLAUDE_MODEL=claude-3-5-sonnet-20241022\nPERMISSION_MODE=bypassPermissions\nANTHROPIC_BASE_URL=https://api.example.com\nANTHROPIC_AUTH_TOKEN=custom-token\nANTHROPIC_API_KEY=sk-test\n",
        encoding="utf-8",
    )
    cfg = load_runtime_config(env_path)
    assert cfg.max_turns == 45
    assert cfg.stale_client_delay_seconds == 12
    assert cfg.memory_index_max_entries == 42
    assert cfg.agent_run_timeout_seconds == 240
    assert cfg.chatlog_enabled is True
    assert cfg.chatlog_base_url == "http://127.0.0.1:5030"
    assert cfg.chatlog_webhook_token == "chatlog_token"
    assert cfg.chatlog_backfill_interval_seconds == 600
    assert cfg.chatlog_monitored_talkers == ("wxid_a", "123@chatroom")
    assert cfg.chatlog_backfill_bootstrap_days == 3
    assert cfg.chatlog_backfill_consecutive_error_threshold == 5
    assert cfg.chatlog_webhook_dedup_ratio_threshold == 0.9
    assert cfg.chatlog_webhook_dedup_min_total == 50
    assert cfg.feishu_app_id == "cli_x"
    assert cfg.feishu_app_secret == "sec_y"
    assert cfg.feishu_encrypt_key == "enc_k"
    assert cfg.feishu_verification_token == "vtok"
    assert cfg.feishu_agent_timeout_seconds == 90
    assert cfg.feishu_max_reply_chars == 1800
    assert cfg.claude_model == "claude-3-5-sonnet-20241022"
    assert cfg.permission_mode == "bypassPermissions"
    assert cfg.anthropic_base_url == "https://api.example.com"
    assert cfg.anthropic_auth_token == "custom-token"
    assert cfg.anthropic_api_key == "sk-test"


def test_runtime_config_falls_back_for_invalid_values(tmp_path: Path, monkeypatch) -> None:
    _clear_sdk_env(monkeypatch)
    env_path = tmp_path / ".env"
    env_path.write_text(
        "MAX_TURNS=abc\nSTALE_CLIENT_DELAY_SECONDS=-3\nMEMORY_INDEX_MAX_ENTRIES=0\nAGENT_RUN_TIMEOUT_SECONDS=0\nCHATLOG_ENABLED=not-a-bool\nCHATLOG_BACKFILL_INTERVAL_SECONDS=0\nCHATLOG_BACKFILL_BOOTSTRAP_DAYS=0\nCHATLOG_MONITORED_TALKERS=,,\nCHATLOG_BACKFILL_CONSECUTIVE_ERROR_THRESHOLD=0\nCHATLOG_WEBHOOK_DEDUP_RATIO_THRESHOLD=abc\nCHATLOG_WEBHOOK_DEDUP_MIN_TOTAL=-1\nFEISHU_AGENT_TIMEOUT_SECONDS=0\nFEISHU_MAX_REPLY_CHARS=0\n",
        encoding="utf-8",
    )
    cfg = load_runtime_config(env_path)
    assert cfg.max_turns == 30
    assert cfg.stale_client_delay_seconds == 20
    assert cfg.memory_index_max_entries == 50
    assert cfg.agent_run_timeout_seconds == 180
    assert cfg.chatlog_enabled is False
    assert cfg.chatlog_backfill_interval_seconds == 300
    assert cfg.chatlog_monitored_talkers == (
        "wxid_cfz3t4h22px722",
        "48651409135@chatroom",
    )
    assert cfg.chatlog_backfill_bootstrap_days == 1
    assert cfg.chatlog_backfill_consecutive_error_threshold == 3
    assert cfg.chatlog_webhook_dedup_ratio_threshold == 0.8
    assert cfg.chatlog_webhook_dedup_min_total == 20
    assert cfg.feishu_agent_timeout_seconds == 120
    assert cfg.feishu_max_reply_chars == 1500


def test_runtime_config_maps_claude_api_key_to_anthropic_api_key(tmp_path: Path, monkeypatch) -> None:
    _clear_sdk_env(monkeypatch)
    env_path = tmp_path / ".env"
    env_path.write_text(
        "CLAUDE_API_KEY=sk-compat\n",
        encoding="utf-8",
    )
    cfg = load_runtime_config(env_path)
    assert cfg.anthropic_api_key == "sk-compat"


def test_runtime_config_invalid_permission_mode_uses_default(tmp_path: Path, monkeypatch) -> None:
    _clear_sdk_env(monkeypatch)
    env_path = tmp_path / ".env"
    env_path.write_text(
        "PERMISSION_MODE=invalid_mode\n",
        encoding="utf-8",
    )
    cfg = load_runtime_config(env_path)
    assert cfg.permission_mode == "default"
