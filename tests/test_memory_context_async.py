import asyncio
from pathlib import Path

import app


def test_build_memory_context_async_uses_to_thread(monkeypatch) -> None:
    called: dict[str, object] = {}

    async def fake_to_thread(func, *args, **kwargs):  # type: ignore[no-untyped-def]
        called["func"] = func
        called["args"] = args
        called["kwargs"] = kwargs
        return "mock-memory-context"

    monkeypatch.setattr(app.asyncio, "to_thread", fake_to_thread)

    result = asyncio.run(app.build_memory_context_async(Path("D:/develop/test"), 50))
    assert result == "mock-memory-context"
    assert called["func"] is app.build_memory_context
    assert called["args"] == (Path("D:/develop/test"), 50)
