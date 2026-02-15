from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any


async def schedule_stale_client_cleanup(
    stale_clients: list[Any],
    delay_seconds: int,
    sleep_func: Callable[[float], Awaitable[None]],
) -> int:
    await sleep_func(delay_seconds)
    cleaned = 0
    while stale_clients:
        client = stale_clients.pop(0)
        try:
            await client.disconnect()
        except Exception:
            pass
        cleaned += 1
    return cleaned

