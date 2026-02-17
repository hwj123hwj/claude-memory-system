import asyncio

import feishu_ws_bridge as bridge_mod


def test_same_chat_messages_are_processed_serially(monkeypatch) -> None:
    active = 0
    max_active = 0

    async def fake_run_agent(prompt: str, conversation_id: str, force_new_client: bool):  # type: ignore[no-untyped-def]
        nonlocal active
        nonlocal max_active
        active += 1
        max_active = max(max_active, active)
        await asyncio.sleep(0.05)
        active -= 1
        return f"ok:{prompt}", "logs/mock.jsonl"

    monkeypatch.setattr(bridge_mod, "run_agent", fake_run_agent)

    bridge = bridge_mod.FeishuWSBridge(app_id="x", app_secret="y", agent_timeout_seconds=3)
    bridge._send_text = lambda chat_id, text: None  # type: ignore[method-assign]

    async def run_both() -> None:
        await asyncio.gather(
            bridge._handle_text_serialized("oc_chat", "m1"),
            bridge._handle_text_serialized("oc_chat", "m2"),
        )

    asyncio.run(run_both())

    assert max_active == 1
