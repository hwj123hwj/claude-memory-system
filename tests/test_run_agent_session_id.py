from dataclasses import replace

import app


class _QuickClient:
    def __init__(self) -> None:
        self.captured_session_id: str | None = None

    async def query(self, prompt: str, session_id: str = "default") -> None:
        _ = prompt
        self.captured_session_id = session_id

    async def receive_response(self):  # type: ignore[no-untyped-def]
        if False:
            yield None


def test_run_agent_passes_conversation_id_to_sdk_query(monkeypatch) -> None:
    client = _QuickClient()

    async def fake_build_memory_context_async(root, max_entries):  # type: ignore[no-untyped-def]
        _ = root
        _ = max_entries
        return "ctx"

    async def fake_get_client(force_new: bool = False):  # type: ignore[no-untyped-def]
        _ = force_new
        return client

    monkeypatch.setattr(app, "build_memory_context_async", fake_build_memory_context_async)
    monkeypatch.setattr(app, "get_client", fake_get_client)
    monkeypatch.setattr(
        app,
        "RUNTIME_CONFIG",
        replace(app.RUNTIME_CONFIG, agent_run_timeout_seconds=3),
    )

    import asyncio

    asyncio.run(app.run_agent("hello", "cid-42", False))
    assert client.captured_session_id == "cid-42"
