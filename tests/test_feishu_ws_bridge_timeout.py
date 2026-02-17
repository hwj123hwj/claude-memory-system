import asyncio

import feishu_ws_bridge as bridge_mod


def test_handle_text_async_retries_with_new_client_after_timeout(monkeypatch) -> None:
    calls: list[bool] = []
    sent: list[str] = []

    async def fake_run_agent(prompt: str, conversation_id: str, force_new_client: bool):  # type: ignore[no-untyped-def]
        calls.append(force_new_client)
        if len(calls) == 1:
            await asyncio.sleep(1.2)
            return "late-reply", "logs/late.jsonl"
        return "retry-ok", "logs/retry.jsonl"

    monkeypatch.setattr(bridge_mod, "run_agent", fake_run_agent)

    bridge = bridge_mod.FeishuWSBridge(
        app_id="x",
        app_secret="y",
        agent_timeout_seconds=1,
    )
    bridge._send_text = lambda chat_id, text: sent.append(text)  # type: ignore[method-assign]

    asyncio.run(bridge._handle_text_async("oc_chat", "hello"))

    assert calls == [False, True]
    assert sent and sent[-1] == "retry-ok"
