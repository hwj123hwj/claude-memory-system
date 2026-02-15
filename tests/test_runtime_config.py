from pathlib import Path

from runtime_config import RuntimeConfig, load_runtime_config


def test_runtime_config_defaults_when_env_missing(tmp_path: Path) -> None:
    cfg = load_runtime_config(tmp_path / ".env")
    assert cfg == RuntimeConfig(
        max_turns=30,
        stale_client_delay_seconds=20,
        memory_index_max_entries=50,
        agent_run_timeout_seconds=180,
        feishu_app_id="",
        feishu_app_secret="",
        feishu_encrypt_key="",
        feishu_verification_token="",
        feishu_agent_timeout_seconds=120,
        feishu_max_reply_chars=1500,
    )


def test_runtime_config_reads_values_from_env_file(tmp_path: Path) -> None:
    env_path = tmp_path / ".env"
    env_path.write_text(
        "MAX_TURNS=45\nSTALE_CLIENT_DELAY_SECONDS=12\nMEMORY_INDEX_MAX_ENTRIES=42\nAGENT_RUN_TIMEOUT_SECONDS=240\nFEISHU_APP_ID=cli_x\nFEISHU_APP_SECRET=sec_y\nFEISHU_ENCRYPT_KEY=enc_k\nFEISHU_VERIFICATION_TOKEN=vtok\nFEISHU_AGENT_TIMEOUT_SECONDS=90\nFEISHU_MAX_REPLY_CHARS=1800\n",
        encoding="utf-8",
    )
    cfg = load_runtime_config(env_path)
    assert cfg.max_turns == 45
    assert cfg.stale_client_delay_seconds == 12
    assert cfg.memory_index_max_entries == 42
    assert cfg.agent_run_timeout_seconds == 240
    assert cfg.feishu_app_id == "cli_x"
    assert cfg.feishu_app_secret == "sec_y"
    assert cfg.feishu_encrypt_key == "enc_k"
    assert cfg.feishu_verification_token == "vtok"
    assert cfg.feishu_agent_timeout_seconds == 90
    assert cfg.feishu_max_reply_chars == 1800


def test_runtime_config_falls_back_for_invalid_values(tmp_path: Path) -> None:
    env_path = tmp_path / ".env"
    env_path.write_text(
        "MAX_TURNS=abc\nSTALE_CLIENT_DELAY_SECONDS=-3\nMEMORY_INDEX_MAX_ENTRIES=0\nAGENT_RUN_TIMEOUT_SECONDS=0\nFEISHU_AGENT_TIMEOUT_SECONDS=0\nFEISHU_MAX_REPLY_CHARS=0\n",
        encoding="utf-8",
    )
    cfg = load_runtime_config(env_path)
    assert cfg.max_turns == 30
    assert cfg.stale_client_delay_seconds == 20
    assert cfg.memory_index_max_entries == 50
    assert cfg.agent_run_timeout_seconds == 180
    assert cfg.feishu_agent_timeout_seconds == 120
    assert cfg.feishu_max_reply_chars == 1500
