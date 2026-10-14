"""In-process background tasks: turn scoring and debriefs. A restart loses running tasks; the session end scores
whatever is missing, so nothing depends on them surviving. The queue is bounded: at most `max_pending` tasks exist
and at most `max_concurrent` run at once, and refused work is closed without ever starting."""

import asyncio
import logging
from collections.abc import Coroutine
from typing import Any

logger = logging.getLogger(__name__)


class Background:
    def __init__(self, max_concurrent: int = 8, max_pending: int = 64) -> None:
        self._max_pending = max_pending
        self._slots = asyncio.Semaphore(max_concurrent)
        self._tasks: set[asyncio.Task[None]] = set()

    def spawn(self, work: Coroutine[Any, Any, None]) -> bool:
        """False when the queue is full: the work never starts (and is never billed)."""
        if len(self._tasks) >= self._max_pending:
            work.close()
            logger.warning("Background work refused: %d tasks already pending", self._max_pending)
            return False
        task = asyncio.create_task(self._run(work))
        self._tasks.add(task)
        task.add_done_callback(self._finished)
        return True

    async def _run(self, work: Coroutine[Any, Any, None]) -> None:
        async with self._slots:
            await work

    def _finished(self, task: asyncio.Task[None]) -> None:
        self._tasks.discard(task)
        if not task.cancelled() and task.exception() is not None:
            # the exception text may carry provider output or user content: log the type only (production log policy)
            logger.error("Background task failed (%s)", type(task.exception()).__name__)

    async def drain(self, timeout: float = 30) -> None:
        """Waits until no task is left (tasks may start others), at most `timeout` seconds in total. What is left
        then is cancelled (its shielded cleanup still runs, bounded) and TimeoutError is raised: drain never waits
        without a bound, even for a task that is slow to cancel."""
        loop = asyncio.get_running_loop()
        deadline = loop.time() + timeout
        while self._tasks and (left := deadline - loop.time()) > 0:
            await asyncio.wait(set(self._tasks), timeout=left)  # returns at the deadline and cancels nothing
        if self._tasks:
            for task in list(self._tasks):
                task.cancel()
            await asyncio.wait(set(self._tasks), timeout=5)  # let shielded cleanup writes land; still bounded
            raise TimeoutError("Background work did not finish within the timeout")
