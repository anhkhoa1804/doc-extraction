"""Host-aware pacing shared across jobs; BFS frontier commits in URL order."""

from __future__ import annotations

import asyncio
import time
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager

from .models import CrawlPolicy, JobBudgetExceeded


class ByteBudget:
    def __init__(self, maximum: int):
        self.maximum = maximum
        self.used = 0
        self.received = 0
        self.decoded = 0

    def consume(self, count: int) -> None:
        self.received += count
        if self.used + count > self.maximum:
            raise JobBudgetExceeded("total_bytes_limit")
        self.used += count

    def consume_decoded(self, count: int) -> None:
        if self.decoded + count > self.maximum:
            raise JobBudgetExceeded("total_decoded_bytes_limit")
        self.decoded += count


class Scheduler:
    def __init__(
        self,
        maximum: int = 16,
        *,
        clock: Callable[[], float] = time.monotonic,
        sleep: Callable[[float], Awaitable[object]] = asyncio.sleep,
    ):
        self.global_slots = asyncio.Semaphore(maximum)
        self.clock = clock
        self.sleep = sleep
        self.host_locks: dict[str, asyncio.Lock] = {}
        self.next_request: dict[str, float] = {}
        self.last_request: dict[str, float] = {}
        self.host_slots: dict[str, asyncio.Semaphore] = {}

    @asynccontextmanager
    async def slot(
        self, host: str, policy: CrawlPolicy, *, delay: float = 0
    ) -> AsyncIterator[None]:
        slots = self.host_slots.setdefault(host, asyncio.Semaphore(4))
        async with slots, self.global_slots:
            lock = self.host_locks.setdefault(host, asyncio.Lock())
            async with lock:
                interval = max(policy.host_interval, delay)
                earliest = max(
                    self.next_request.get(host, 0),
                    self.last_request.get(host, 0) + interval,
                )
                wait = max(0.0, earliest - self.clock())
                await self.sleep(wait)
                started = self.clock()
                self.last_request[host] = started
                self.next_request[host] = started + interval
            yield
