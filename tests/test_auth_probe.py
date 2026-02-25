import asyncio

import app


class _InitMessage:
    subtype = "init"
    data = {
        "apiKeySource": "none",
        "model": "claude-sonnet-4-5-20250929",
    }


class _ResultMessage:
    pass


class _FakeClient:
    def __init__(self) -> None:
        self.prompt: str | None = None
        self.session_id: str | None = None

    async def query(self, prompt: str, session_id: str = "default") -> None:
        self.prompt = prompt
        self.session_id = session_id

    async def receive_response(self):  # type: ignore[no-untyped-def]
        yield _InitMessage()
        yield _ResultMessage()


def test_probe_auth_context_reads_api_key_source(monkeypatch) -> None:
    client = _FakeClient()

    async def fake_get_client(force_new: bool = False):  # type: ignore[no-untyped-def]
        _ = force_new
        return client

    monkeypatch.setattr(app, "get_client", fake_get_client)

    result = asyncio.run(app.probe_auth_context())
    assert result["api_key_source"] == "none"
    assert result["model"] == "claude-sonnet-4-5-20250929"
    assert client.session_id == "auth-probe"
