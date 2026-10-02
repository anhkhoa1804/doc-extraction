"""The committed local replay corpus drives the real crawl execution path."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from conftest import Reply

from web_acquisition.models import CrawlPolicy

REPLAY = (
    Path(__file__).resolve().parents[3]
    / "benchmarks"
    / "manifests"
    / "web-acquisition-replay.json"
)


def _routes(case: dict[str, object]) -> dict[str, Reply]:
    routes: dict[str, Reply] = {}
    for route in case["routes"]:  # type: ignore[index]
        assert isinstance(route, dict)
        headers: dict[str, str] = {}
        if "content_type" in route:
            headers["Content-Type"] = str(route["content_type"])
        if "location" in route:
            headers["Location"] = str(route["location"])
        routes[str(route["path"])] = Reply(
            body=str(route.get("body", "")).encode(),
            status=int(route.get("status", 200)),
            headers=headers,
        )
    return routes


@pytest.mark.parametrize("concurrency", [1, 2, 4, 8])
async def test_replay_bfs_case_is_deterministic(harness, concurrency):
    corpus = json.loads(REPLAY.read_text(encoding="utf-8"))
    case = next(item for item in corpus["cases"] if item["case_id"] == "bfs-duplicate-content")
    manager, _server, _transport, _root = await harness(_routes(case))
    job = manager.submit(
        case["seeds"],
        CrawlPolicy(
            robots_mode="ignore",
            host_interval=0,
            concurrency=concurrency,
            per_host_concurrency=4,
        ),
    )
    await manager.wait(job.job_id)
    acquired = sorted(
        resource.final_url.removeprefix("http://web.example")
        for resource in manager.repository.resources(job.job_id)
        if resource.status == "acquired" and resource.final_url
    )
    assert acquired == case["expected_acquired"]
