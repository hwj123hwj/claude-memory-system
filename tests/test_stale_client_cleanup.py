import asyncio

from stale_client_cleanup import schedule_stale_client_cleanup


class _DummyClient:
    def __init__(self) -> None:
        self.disconnected = False

    async def disconnect(self) -> None:
        self.disconnected = True


async def _no_wait(_: float) -> None:
    await asyncio.sleep(0)


def test_cleanup_disconnects_and_clears_clients() -> None:
    clients = [_DummyClient(), _DummyClient()]
    cleaned = asyncio.run(
        schedule_stale_client_cleanup(clients, delay_seconds=20, sleep_func=_no_wait)
    )
    assert cleaned == 2
    assert clients == []

