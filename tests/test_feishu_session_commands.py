import asyncio

import feishu_ws_bridge as bridge_mod


def test_handle_text_async_routes_clear_command_to_agent(monkeypatch) -> None:
    sent: list[str] = []
    calls: list[tuple[str, str, bool]] = []

    async def fake_run_agent(prompt: str, conversation_id: str, force_new_client: bool):  # type: ignore[no-untyped-def]
        calls.append((prompt, conversation_id, force_new_client))
        return "cleared", "logs/mock.jsonl"

    monkeypatch.setattr(bridge_mod, "run_agent", fake_run_agent)

    bridge = bridge_mod.FeishuWSBridge(app_id="x", app_secret="y", agent_timeout_seconds=3)
    bridge._send_text = lambda chat_id, text: sent.append(text)  # type: ignore[method-assign]

    asyncio.run(bridge._handle_text_async("oc_chat", "/clear"))

    assert calls == [("/clear", "feishu:oc_chat", False)]
    assert sent == ["cleared"]


def test_follow_up_messages_keep_same_conversation_id(monkeypatch) -> None:
    calls: list[str] = []

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

    assert calls == ["feishu:oc_chat", "feishu:oc_chat", "feishu:oc_chat"]


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

    assert calls == [("/compact", "feishu:oc_chat", False)]
    assert sent == ["compacted"]
