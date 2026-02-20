import asyncio
from pathlib import Path
import json

import feishu_ws_bridge as bridge_mod


def _session_state_file(name: str) -> Path:
    path = bridge_mod.LOG_DIR / name
    if path.exists():
        path.unlink()
    return path


def _log_probe_file(name: str) -> Path:
    path = bridge_mod.LOG_DIR / name
    if path.exists():
        path.unlink()
    return path


def test_handle_text_async_routes_clear_command_without_running_agent(monkeypatch) -> None:
    sent: list[str] = []
    session_file = _session_state_file("test_feishu_sessions_clear.json")
    monkeypatch.setattr(bridge_mod, "CHAT_SESSION_STATE_FILE", session_file)

    async def should_not_run_agent(prompt: str, conversation_id: str, force_new_client: bool):  # type: ignore[no-untyped-def]
        raise AssertionError("run_agent should not be called for /clear")

    monkeypatch.setattr(bridge_mod, "run_agent", should_not_run_agent)

    bridge = bridge_mod.FeishuWSBridge(app_id="x", app_secret="y", agent_timeout_seconds=3)
    bridge._send_text = lambda chat_id, text: sent.append(text)  # type: ignore[method-assign]

    asyncio.run(bridge._handle_text_async("oc_chat", "/clear"))

    assert sent
    assert ":v1" in sent[-1]
    if session_file.exists():
        session_file.unlink()


def test_clear_command_changes_follow_up_conversation_id(monkeypatch) -> None:
    calls: list[str] = []
    session_file = _session_state_file("test_feishu_sessions_change.json")
    monkeypatch.setattr(bridge_mod, "CHAT_SESSION_STATE_FILE", session_file)

    async def fake_run_agent(prompt: str, conversation_id: str, force_new_client: bool):  # type: ignore[no-untyped-def]
        _ = (prompt, force_new_client)
        calls.append(conversation_id)
        return "ok", "logs/mock.jsonl"

    monkeypatch.setattr(bridge_mod, "run_agent", fake_run_agent)

    bridge = bridge_mod.FeishuWSBridge(app_id="x", app_secret="y", agent_timeout_seconds=3)
    bridge._send_text = lambda chat_id, text: None  # type: ignore[method-assign]

    asyncio.run(bridge._handle_text_async("oc_chat", "hello"))
    asyncio.run(bridge._handle_text_async("oc_chat", "/clear"))
    asyncio.run(bridge._handle_text_async("oc_chat", "hello again"))

    assert calls == ["feishu:oc_chat:v0", "feishu:oc_chat:v1"]
    if session_file.exists():
        session_file.unlink()


def test_handle_text_async_routes_compact_command_to_agent(monkeypatch) -> None:
    sent: list[str] = []
    calls: list[tuple[str, str, bool]] = []

    async def fake_run_agent(prompt: str, conversation_id: str, force_new_client: bool):  # type: ignore[no-untyped-def]
        calls.append((prompt, conversation_id, force_new_client))
        return "compacted", "logs/mock.jsonl"

    monkeypatch.setattr(bridge_mod, "run_agent", fake_run_agent)

    bridge = bridge_mod.FeishuWSBridge(app_id="x", app_secret="y", agent_timeout_seconds=3)
    bridge._send_text = lambda chat_id, text: sent.append(text)  # type: ignore[method-assign]

    asyncio.run(bridge._handle_text_async("oc_chat", "/compact"))

    assert calls == [("/compact", "feishu:oc_chat:v0", False)]
    assert sent == ["compacted"]


def test_status_commands_reads_latest_init_slash_commands(monkeypatch) -> None:
    fake_log = _log_probe_file("chat-20260220-000000-aaaa1111.jsonl")
    line = {
        "event": "message",
        "type": "SystemMessage",
        "payload": {
            "subtype": "init",
            "data": {"slash_commands": ["compact", "context", "cost"]},
        },
    }
    fake_log.write_text(json.dumps(line, ensure_ascii=False) + "\n", encoding="utf-8")
    out = bridge_mod.handle_session_command("/status commands", "oc_chat")
    assert out is not None
    assert "compact" in out
    assert "context" in out
    if fake_log.exists():
        fake_log.unlink()


def test_status_commands_reports_when_unavailable(monkeypatch) -> None:
    probe = _log_probe_file("chat-20260220-000001-bbbb2222.jsonl")
    if probe.exists():
        probe.unlink()
    out = bridge_mod.handle_session_command("/status commands", "oc_chat")
    assert out is not None
    assert ("未发现" in out) or ("当前可用 slash_commands" in out)
