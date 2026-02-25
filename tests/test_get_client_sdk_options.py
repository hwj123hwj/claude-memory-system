import asyncio
from dataclasses import replace

import app


class _FakeOptions:
    last_kwargs = None

    def __init__(self, **kwargs):  # type: ignore[no-untyped-def]
        _FakeOptions.last_kwargs = kwargs


class _FakeClient:
    def __init__(self, options=None):  # type: ignore[no-untyped-def]
        self.options = options
        self.connected = False

    async def connect(self) -> None:
        self.connected = True


def test_get_client_uses_runtime_sdk_options(monkeypatch) -> None:
    monkeypatch.setattr(app, "ClaudeAgentOptions", _FakeOptions)
    monkeypatch.setattr(app, "ClaudeSDKClient", _FakeClient)
    monkeypatch.setattr(
        app,
        "RUNTIME_CONFIG",
        replace(
            app.RUNTIME_CONFIG,
            claude_model="claude-3-5-sonnet-20241022",
            permission_mode="bypassPermissions",
            anthropic_base_url="https://api.example.com",
            anthropic_auth_token="custom-token",
            anthropic_api_key="sk-test",
        ),
    )
    monkeypatch.setattr(app, "CLIENT", None)
    monkeypatch.setattr(app, "STALE_CLIENTS", [])
    monkeypatch.setattr(app, "STALE_CLEANUP_TASK", None)

    client = asyncio.run(app.get_client(force_new=False))

    assert isinstance(client, _FakeClient)
    assert client.connected is True
    assert isinstance(_FakeOptions.last_kwargs, dict)
    kwargs = _FakeOptions.last_kwargs or {}
    assert kwargs.get("model") == "claude-3-5-sonnet-20241022"
    assert kwargs.get("permission_mode") == "bypassPermissions"
    assert kwargs.get("env", {}).get("ANTHROPIC_BASE_URL") == "https://api.example.com"
    assert kwargs.get("env", {}).get("ANTHROPIC_AUTH_TOKEN") == "custom-token"
    assert kwargs.get("env", {}).get("ANTHROPIC_API_KEY") == "sk-test"

