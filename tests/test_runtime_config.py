from pathlib import Path

from runtime_config import RuntimeConfig, load_runtime_config


def test_runtime_config_defaults_when_env_missing(tmp_path: Path) -> None:
    cfg = load_runtime_config(tmp_path / ".env")
    assert cfg == RuntimeConfig(max_turns=30, stale_client_delay_seconds=20)


def test_runtime_config_reads_values_from_env_file(tmp_path: Path) -> None:
    env_path = tmp_path / ".env"
    env_path.write_text(
        "MAX_TURNS=45\nSTALE_CLIENT_DELAY_SECONDS=12\n",
        encoding="utf-8",
    )
    cfg = load_runtime_config(env_path)
    assert cfg.max_turns == 45
    assert cfg.stale_client_delay_seconds == 12


def test_runtime_config_falls_back_for_invalid_values(tmp_path: Path) -> None:
    env_path = tmp_path / ".env"
    env_path.write_text(
        "MAX_TURNS=abc\nSTALE_CLIENT_DELAY_SECONDS=-3\n",
        encoding="utf-8",
    )
    cfg = load_runtime_config(env_path)
    assert cfg.max_turns == 30
    assert cfg.stale_client_delay_seconds == 20
