from dataclasses import replace

import app


class _CaptureClient:
    def __init__(self) -> None:
        self.prompt: str | None = None
        self.session_id: str | None = None

    async def query(self, prompt: str, session_id: str = "default") -> None:
        self.prompt = prompt
        self.session_id = session_id

    async def receive_response(self):  # type: ignore[no-untyped-def]
        if False:
            yield None


def test_run_agent_keeps_slash_command_raw_and_skips_memory_context(monkeypatch) -> None:
    client = _CaptureClient()

    async def should_not_build_memory_context(root, max_entries):  # type: ignore[no-untyped-def]
        raise AssertionError("memory context should be skipped for slash commands")

    async def fake_get_client(force_new: bool = False):  # type: ignore[no-untyped-def]
        _ = force_new
        return client

    monkeypatch.setattr(app, "build_memory_context_async", should_not_build_memory_context)
    monkeypatch.setattr(app, "get_client", fake_get_client)
    monkeypatch.setattr(
        app,
        "RUNTIME_CONFIG",
        replace(app.RUNTIME_CONFIG, agent_run_timeout_seconds=3),
    )

    import asyncio

    asyncio.run(app.run_agent("/compact", "cid-compact", False))
    assert client.prompt == "/compact"
    assert client.session_id == "cid-compact"
