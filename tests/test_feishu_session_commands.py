import asyncio
from pathlib import Path

import feishu_ws_bridge as bridge_mod


def _session_state_file(name: str) -> Path:
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
    assert "会话已清空" in sent[-1]
    if session_file.exists():
        session_file.unlink()


def test_clear_command_changes_follow_up_conversation_id(monkeypatch) -> None:
    calls: list[str] = []
    sent: list[str] = []

    session_file = _session_state_file("test_feishu_sessions_change.json")
    monkeypatch.setattr(bridge_mod, "CHAT_SESSION_STATE_FILE", session_file)

    async def fake_run_agent(prompt: str, conversation_id: str, force_new_client: bool):  # type: ignore[no-untyped-def]
        _ = (prompt, force_new_client)
        calls.append(conversation_id)
        return "ok", "logs/mock.jsonl"

    monkeypatch.setattr(bridge_mod, "run_agent", fake_run_agent)

    bridge = bridge_mod.FeishuWSBridge(app_id="x", app_secret="y", agent_timeout_seconds=3)
    bridge._send_text = lambda chat_id, text: sent.append(text)  # type: ignore[method-assign]

    asyncio.run(bridge._handle_text_async("oc_chat", "hello"))
    asyncio.run(bridge._handle_text_async("oc_chat", "/clear"))
    asyncio.run(bridge._handle_text_async("oc_chat", "hello again"))

    assert calls == ["feishu:oc_chat:v0", "feishu:oc_chat:v1"]
    assert any("会话已清空" in x for x in sent)
    if session_file.exists():
        session_file.unlink()


def test_handle_text_async_routes_compact_command_without_running_agent(monkeypatch) -> None:
    sent: list[str] = []

    async def should_not_run_agent(prompt: str, conversation_id: str, force_new_client: bool):  # type: ignore[no-untyped-def]
        raise AssertionError("run_agent should not be called for /compact")

    monkeypatch.setattr(bridge_mod, "run_agent", should_not_run_agent)

    bridge = bridge_mod.FeishuWSBridge(app_id="x", app_secret="y", agent_timeout_seconds=3)
    bridge._send_text = lambda chat_id, text: sent.append(text)  # type: ignore[method-assign]

    asyncio.run(bridge._handle_text_async("oc_chat", "/compact"))

    assert sent
    assert "/compact" in sent[-1]
