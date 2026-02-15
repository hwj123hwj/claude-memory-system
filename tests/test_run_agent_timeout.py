from dataclasses import replace

import app


class _SlowClient:
    async def query(self, prompt: str) -> None:
        _ = prompt
        import asyncio

        await asyncio.sleep(1.2)

    async def receive_response(self):  # type: ignore[no-untyped-def]
        if False:
            yield None


def test_run_agent_returns_timeout_message(monkeypatch) -> None:
    async def fake_build_memory_context_async(root, max_entries):  # type: ignore[no-untyped-def]
        _ = root
        _ = max_entries
        return "ctx"

    async def fake_get_client(force_new: bool = False):  # type: ignore[no-untyped-def]
        _ = force_new
        return _SlowClient()

    monkeypatch.setattr(app, "build_memory_context_async", fake_build_memory_context_async)
    monkeypatch.setattr(app, "get_client", fake_get_client)
    monkeypatch.setattr(
        app,
        "RUNTIME_CONFIG",
        replace(app.RUNTIME_CONFIG, agent_run_timeout_seconds=1),
    )

    import asyncio

    reply, _ = asyncio.run(app.run_agent("hello", "cid-1", False))
    assert "执行超时" in reply
