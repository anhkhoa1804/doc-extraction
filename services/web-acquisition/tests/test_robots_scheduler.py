"""End-to-end robots and host scheduler behavior through the crawl engine."""

from __future__ import annotations

import asyncio

import pytest
from conftest import Reply

from web_acquisition.models import CrawlPolicy
from web_acquisition.scheduler import Scheduler


@pytest.mark.parametrize(
    "robots,expected",
    [
        (b"User-agent: *\nAllow: /\n", "acquired"),
        (b"User-agent: *\nDisallow: /private\n", "failed"),
    ],
)
async def test_robots_allow_and_disallow_through_job(harness, robots, expected):
    manager, server, _transport, _root = await harness(
        {"/robots.txt": Reply(body=robots), "/private": Reply(body=b"document")}
    )
    job = manager.submit(["http://web.example/private"], CrawlPolicy(host_interval=0))
    await manager.wait(job.job_id)
    resource = manager.repository.resources(job.job_id)[0]
    assert resource.status == expected
    if expected == "failed":
        assert resource.rejection_reason == "blocked_by_robots"
        assert [target for target, _, _ in server.requests] == ["/robots.txt"]
    else:
        assert [target for target, _, _ in server.requests] == ["/robots.txt", "/private"]


@pytest.mark.parametrize(
    "reply,robots_failure,expected",
    [
        (Reply(status=404, body=b""), "deny", "acquired"),
        (Reply(status=500, body=b""), "deny", "failed"),
        (Reply(status=500, body=b""), "allow", "acquired"),
        (Reply(body=b"not a robots document"), "deny", "failed"),
    ],
)
async def test_robots_failure_policy_through_job(harness, reply, robots_failure, expected):
    manager, _server, _transport, _root = await harness(
        {"/robots.txt": reply, "/": Reply(body=b"document")}
    )
    job = manager.submit(
        ["http://web.example/"], CrawlPolicy(host_interval=0, robots_failure=robots_failure)
    )
    await manager.wait(job.job_id)
    resource = manager.repository.resources(job.job_id)[0]
    assert resource.status == expected
    if expected == "failed":
        assert resource.rejection_reason == "blocked_by_robots"


async def test_robots_timeout_denies_without_fetching_resource(harness):
    manager, server, _transport, _root = await harness(
        {"/robots.txt": Reply(stall=True), "/": Reply(body=b"document")}
    )
    job = manager.submit(
        ["http://web.example/"],
        CrawlPolicy(host_interval=0, robots_timeout=0.03, request_timeout=0.1),
    )
    await manager.wait(job.job_id)
    resource = manager.repository.resources(job.job_id)[0]
    assert resource.rejection_reason == "blocked_by_robots"
    assert all(target == "/robots.txt" for target, _, _ in server.requests)


async def test_robots_cache_is_per_origin_and_reused(harness):
    manager, server, _transport, _root = await harness(
        {
            "/robots.txt": Reply(body=b"User-agent: *\nAllow: /\n"),
            "/a": Reply(body=b"a"),
            "/b": Reply(body=b"b"),
        }
    )
    job = manager.submit(
        ["http://web.example/a", "http://web.example/b"], CrawlPolicy(host_interval=0)
    )
    await manager.wait(job.job_id)
    assert [target for target, _, _ in server.requests].count("/robots.txt") == 1
    assert all(resource.status == "acquired" for resource in manager.repository.resources(job.job_id))


async def test_robots_crawl_delay_applies_before_resource_fetch(harness):
    manager, _server, _transport, _root = await harness(
        {
            "/robots.txt": Reply(body=b"User-agent: *\nCrawl-delay: 1\nAllow: /\n"),
            "/": Reply(body=b"document"),
        }
    )
    clock = [0.0]

    async def advance(seconds: float) -> None:
        clock[0] += seconds

    manager.scheduler.clock = lambda: clock[0]
    manager.scheduler.sleep = advance
    job = manager.submit(["http://web.example/"], CrawlPolicy(host_interval=0))
    await manager.wait(job.job_id)
    assert manager.scheduler.last_request["web.example"] == 1.0


async def test_per_host_concurrency_and_cross_host_parallelism(harness):
    routes = {"/a": Reply(delay=0.04), "/b": Reply(delay=0.04)}
    manager, server, _transport, _root = await harness(routes)
    same_host = manager.submit(
        ["http://web.example/a", "http://web.example/b"],
        CrawlPolicy(robots_mode="ignore", host_interval=0, concurrency=4, per_host_concurrency=1),
    )
    await manager.wait(same_host.job_id)
    assert server.max_connections == 1

    manager, server, _transport, _root = await harness(routes)
    multiple_hosts = manager.submit(
        ["http://web.example/a", "http://other.example/b"],
        CrawlPolicy(
            robots_mode="ignore",
            host_interval=0,
            concurrency=4,
            per_host_concurrency=1,
            same_origin=False,
            allowed_hosts=("web.example", "other.example"),
        ),
    )
    await manager.wait(multiple_hosts.job_id)
    assert server.max_connections >= 2


async def test_host_interval_is_enforced_in_actual_crawl(harness):
    manager, server, _transport, _root = await harness({"/a": Reply(), "/b": Reply()})
    job = manager.submit(
        ["http://web.example/a", "http://web.example/b"],
        CrawlPolicy(robots_mode="ignore", host_interval=0.03, concurrency=4, per_host_concurrency=4),
    )
    await manager.wait(job.job_id)
    starts = [timestamp for _, _, timestamp in server.requests]
    assert len(starts) == 2
    assert starts[1] - starts[0] >= 0.02


async def test_scheduler_global_concurrency_cap():
    scheduler = Scheduler(maximum=1)
    policy = CrawlPolicy(host_interval=0)
    entered = 0
    peak = 0
    release = asyncio.Event()

    async def work(host: str) -> None:
        nonlocal entered, peak
        async with scheduler.slot(host, policy):
            entered += 1
            peak = max(peak, entered)
            if entered == 1:
                await asyncio.sleep(0)
            release.set()
            await asyncio.sleep(0.01)
            entered -= 1

    await asyncio.gather(work("a.example"), work("b.example"))
    assert release.is_set()
    assert peak == 1
