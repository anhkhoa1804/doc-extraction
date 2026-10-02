"""Job-scoped per-origin robots cache; robots never overrides network security."""

from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass
from urllib.robotparser import RobotFileParser

from .fetcher import HttpFetcher
from .models import AcquisitionError, JobBudgetExceeded, Resource
from .urls import origin


@dataclass
class Rules:
    parser: RobotFileParser | None
    allow: bool
    delay: float
    expires: float
    reason: str | None = None


class RobotsCache:
    def __init__(self, fetcher: HttpFetcher):
        self.fetcher = fetcher
        self.entries: dict[str, Rules] = {}
        self.locks: dict[str, asyncio.Lock] = {}

    async def authorize(self, url: str, resource: Resource) -> float:
        policy = self.fetcher.job.policy
        if policy.robots_mode == "ignore":
            return 0
        key = origin(url)
        async with self.locks.setdefault(key, asyncio.Lock()):
            rules = self.entries.get(key)
            if rules is None or rules.expires < time.monotonic():
                rules = await self._load(key, resource)
                self.entries[key] = rules
        if rules.reason:
            self.fetcher.job.metrics["robots_" + rules.reason] = (
                self.fetcher.job.metrics.get("robots_" + rules.reason, 0) + 1
            )
        if not rules.allow or (rules.parser and not rules.parser.can_fetch(policy.user_agent, url)):
            raise AcquisitionError("blocked_by_robots")
        return rules.delay

    async def _load(self, key: str, resource: Resource) -> Rules:
        expires = time.monotonic() + 300
        policy = self.fetcher.job.policy
        try:
            result = await self.fetcher.fetch(
                key + "/robots.txt", resource, robots=True, maximum=256 * 1024
            )
            try:
                if result.status in (404, 410):
                    return Rules(None, True, 0, expires, "not_found")
                if result.status in (401, 403):
                    return Rules(None, False, 0, expires, "denied")
                if not 200 <= result.status < 300:
                    raise AcquisitionError("unavailable")
                text = result.body.read_bounded(256 * 1024).decode("utf-8", errors="strict")
            finally:
                result.body.discard()
            active = [line.split("#", 1)[0].strip() for line in text.splitlines()]
            if any(active) and not any(line.lower().startswith("user-agent:") for line in active):
                raise AcquisitionError("malformed")
            parser = RobotFileParser()
            parser.parse(text.splitlines())
            delay = float(parser.crawl_delay(policy.user_agent) or 0)
            rate = parser.request_rate(policy.user_agent)
            if rate and rate.requests:
                delay = max(delay, rate.seconds / rate.requests)
            if delay > 60:
                return Rules(parser, False, delay, expires, "delay_limit")
            return Rules(parser, True, delay, expires)
        except JobBudgetExceeded:
            raise
        except (AcquisitionError, UnicodeError) as exc:
            if isinstance(exc, AcquisitionError) and exc.code in (
                "ssrf_blocked",
                "outside_scope",
                "egress_port_or_scheme",
                "peer_address_mismatch",
            ):
                raise
            return Rules(
                None,
                policy.robots_failure == "allow",
                0,
                expires,
                exc.code if isinstance(exc, AcquisitionError) else "malformed",
            )
