"""Background.drain waits bounded: what it cannot wait for is cancelled, never awaited without a bound."""

import asyncio
import time

import pytest

from nlab.api.background import Background

pytestmark = pytest.mark.anyio


async def test_drain_waits_for_work_that_finishes():
    background = Background()
    done: list[int] = []

    async def quick() -> None:
        await asyncio.sleep(0.05)
        done.append(1)

    background.spawn(quick())
    await asyncio.wait_for(background.drain(timeout=5), timeout=10)
    assert done == [1]


async def test_drain_cancels_what_it_cannot_wait_for():
    background = Background()
    cleaned: list[str] = []

    async def forever() -> None:
        try:
            await asyncio.sleep(3600)
        finally:
            cleaned.append("cancelled")

    background.spawn(forever())
    started = time.monotonic()
    with pytest.raises(TimeoutError):
        await asyncio.wait_for(background.drain(timeout=0.2), timeout=5)  # bounded twice over
    assert time.monotonic() - started < 3
    assert cleaned == ["cancelled"]
