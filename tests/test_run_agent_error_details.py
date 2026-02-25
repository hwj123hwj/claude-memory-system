from dataclasses import replace

import app


class _FailingProcessError(RuntimeError):
    def __init__(self, message: str, stderr: bytes | str) -> None:
        super().__init__(message)
        self.stderr = stderr


class _FailingClient:
    async def query(self, prompt: str, session_id: str = "default") -> None:
        _ = prompt
        _ = session_id
        raise _FailingProcessError(
            "Command failed with exit code 1",
            b"Not logged in \xc2\xb7 Please run /login",
        )

    async def receive_response(self):  # type: ignore[no-untyped-def]
        if False:
            yield None


def test_run_agent_surfaces_process_stderr_details(monkeypatch) -> None:
    async def fake_build_memory_context_async(root, max_entries):  # type: ignore[no-untyped-def]
        _ = root
        _ = max_entries
        return "ctx"

    async def fake_get_client(force_new: bool = False):  # type: ignore[no-untyped-def]
        _ = force_new
        return _FailingClient()

    monkeypatch.setattr(app, "build_memory_context_async", fake_build_memory_context_async)
    monkeypatch.setattr(app, "get_client", fake_get_client)
    monkeypatch.setattr(
        app,
        "RUNTIME_CONFIG",
        replace(app.RUNTIME_CONFIG, agent_run_timeout_seconds=3),
    )

    import asyncio

    reply, _ = asyncio.run(app.run_agent("hello", "cid-err-1", False))
    assert "Claude Code call failed" in reply
    assert "Not logged in" in reply
