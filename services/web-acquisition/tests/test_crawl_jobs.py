import asyncio
import hashlib

import pytest
from aiohttp.test_utils import TestClient, TestServer
from conftest import Reply

from web_acquisition.api import create_app
from web_acquisition.fetcher import Credentials
from web_acquisition.models import AcquisitionError, CrawlPolicy

HTML = {"Content-Type": "text/html"}


def graph():
    return {
        "/a": Reply(
            body=b'<a href="/b">B</a><a href="/d">D</a><a href="/a#x">same</a>',
            headers=HTML,
            delay=0.005,
        ),
        "/b": Reply(
            body=b'<a href="/c">C</a><img src="/logo.png">logo</img>', headers=HTML, delay=0.02
        ),
        "/c": Reply(body=b"shared"),
        "/d": Reply(body=b"shared"),
        "/logo.png": Reply(body=b"not filtered", headers={"Content-Type": "image/png"}),
    }


@pytest.mark.parametrize("max_pages", [100, 3])
async def test_parallelism_preserves_recursive_semantics(harness, max_pages):
    reference = None
    for concurrency in (1, 2, 4, 8):
        manager, _server, _transport, _root = await harness(graph())
        job = manager.submit(
            ["http://web.example/a"],
            CrawlPolicy(
                robots_mode="ignore",
                host_interval=0,
                max_depth=3,
                max_pages=max_pages,
                concurrency=concurrency,
                per_host_concurrency=4,
            ),
        )
        result = await manager.wait(job.job_id)
        assert result.status == "completed"
        rows = manager.repository.resources(job.job_id)
        semantic = {
            (r.canonical_url, r.status, r.depth, r.sha256, r.rejection_reason) for r in rows
        }
        assert reference is None or reference == semantic
        reference = semantic
        if max_pages == 100:
            assert len([r for r in rows if r.status == "acquired"]) == 5
            assert result.metrics["duplicate_content"] == 1
            assert result.metrics["duplicate_urls"] == 1
            assert len(manager.repository.artifacts(job.job_id)) == 4
            assert any(r.canonical_url.endswith("/c") and r.depth == 2 for r in rows)
            assert any(
                r.canonical_url.endswith("/logo.png") and r.status == "acquired" for r in rows
            )


async def test_duplicate_urls_content_and_provenance(harness):
    manager, _server, _transport, root = await harness(graph())
    job = manager.submit(
        ["http://web.example/a"], CrawlPolicy(robots_mode="ignore", host_interval=0, max_depth=3)
    )
    await manager.wait(job.job_id)
    rows = manager.repository.resources(job.job_id)
    c, d = (
        next(r for r in rows if r.final_url.endswith("/c")),
        next(r for r in rows if r.final_url.endswith("/d")),
    )
    assert c.artifact_id == d.artifact_id == "sha256:" + hashlib.sha256(b"shared").hexdigest()
    assert c.parent_resource_id and c.parent_url.endswith("/b") and c.discovery_method == "html_a"
    attempts = manager.repository.attempts(job.job_id)
    assert any(a.resource_id == c.resource_id and a.requested_url.endswith("/c") for a in attempts)
    assert (root / "artifacts" / f"sha256/{c.sha256[:2]}/{c.sha256[2:]}").read_bytes() == b"shared"
    assert not list((root / "artifacts/.pending").iterdir())


async def test_unique_artifact_cap_allows_duplicate_references(harness):
    manager, _server, _transport, _root = await harness(
        {"/a": Reply(body=b"same"), "/b": Reply(body=b"same")}
    )
    job = manager.submit(
        ["http://web.example/a", "http://web.example/b"],
        CrawlPolicy(robots_mode="ignore", host_interval=0, max_artifacts=1),
    )
    result = await manager.wait(job.job_id)
    assert result.metrics["duplicate_content"] == 1
    assert len(manager.repository.artifacts(job.job_id)) == 1
    assert all(r.status == "acquired" for r in manager.repository.resources(job.job_id))


async def test_byte_cutoff_aborts_entire_level_independent_of_parallelism(harness):
    routes = {
        "/a": Reply(body=b'<a href="/b">B</a><a href="/c">C</a>', headers=HTML),
        "/b": Reply(body=b"x" * 80),
        "/c": Reply(body=b"y" * 80),
    }
    reference = None
    for concurrency in (1, 2, 4, 8):
        manager, _server, _transport, root = await harness(routes)
        job = manager.submit(
            ["http://web.example/a"],
            CrawlPolicy(
                robots_mode="ignore",
                host_interval=0,
                concurrency=concurrency,
                per_host_concurrency=4,
                max_total_bytes=250,
            ),
        )
        result = await manager.wait(job.job_id)
        assert result.status == "failed" and result.error_summary == "total_bytes_limit"
        acquired = {
            r.canonical_url
            for r in manager.repository.resources(job.job_id)
            if r.status == "acquired"
        }
        assert reference is None or reference == acquired
        reference = acquired
        assert acquired == {"http://web.example/a"}
        assert not list((root / "artifacts/.pending").iterdir())
        assert result.metrics["bytes_downloaded"] <= 250


@pytest.mark.parametrize(
    "limit", ["max_links_per_page", "max_discoveries", "max_depth", "max_html_parse_size"]
)
async def test_graph_and_parser_limits_are_explicit(harness, limit):
    settings = {
        "max_links_per_page": 1,
        "max_discoveries": 1,
        "max_depth": 0,
        "max_html_parse_size": 1,
    }
    manager, _server, _transport, _root = await harness(graph())
    job = manager.submit(
        ["http://web.example/a"],
        CrawlPolicy(robots_mode="ignore", host_interval=0, **{limit: settings[limit]}),
    )
    result = await manager.wait(job.job_id)
    code = {
        "max_links_per_page": "links_limit",
        "max_discoveries": "discovery_limit",
        "max_depth": "depth_limit",
        "max_html_parse_size": "html_parse_limit",
    }[limit]
    assert result.metrics.get(code, 0) > 0


async def test_canonical_hint_is_not_authority(harness):
    manager, _server, _transport, _root = await harness(
        {"/": Reply(body=b'<link rel="canonical" href="http://evil.example/other">', headers=HTML)}
    )
    job = manager.submit(
        ["http://web.example/"], CrawlPolicy(robots_mode="ignore", host_interval=0)
    )
    await manager.wait(job.job_id)
    seed = manager.repository.resources(job.job_id)[0]
    assert seed.canonical_url == seed.final_url == "http://web.example/"
    assert seed.advertised_canonical_url == "http://evil.example/other"
    assert manager.repository.resources(job.job_id)[1].rejection_reason == "outside_scope"


async def test_cancellation_fetch_cleans_pending_and_http_tasks(harness):
    manager, server, _transport, root = await harness({"/": Reply(stall=True)})
    job = manager.submit(
        ["http://web.example/"], CrawlPolicy(robots_mode="ignore", host_interval=0)
    )
    await asyncio.wait_for(server.started.wait(), 2)
    result = await manager.cancel(job.job_id)
    assert result.status == "cancelled"
    assert not manager.tasks
    assert not manager.repository.artifacts(job.job_id)
    assert not list((root / "artifacts/.pending").iterdir())
    assert manager.repository.attempts(job.job_id)[0].status == "cancelled"


async def test_queued_cancellation_does_not_start_fetch(harness):
    manager, _server, transport, _root = await harness({})
    job = manager.submit(["http://web.example/"], CrawlPolicy(robots_mode="ignore"))
    assert (await manager.cancel(job.job_id)).status == "cancelled"
    assert not transport.calls


async def test_cancellation_during_discovery_stops_frontier_and_publication(harness, monkeypatch):
    from web_acquisition.engine import CrawlEngine

    discover = CrawlEngine.discover

    def cancel_on_child(self, raw, parent, depth, method, base=None):
        discover(self, raw, parent, depth, method, base)
        if depth == 1:
            asyncio.current_task().cancel()

    monkeypatch.setattr(CrawlEngine, "discover", cancel_on_child)
    manager, server, _transport, root = await harness(graph())
    job = manager.submit(
        ["http://web.example/a"], CrawlPolicy(robots_mode="ignore", host_interval=0)
    )
    result = await manager.wait(job.job_id)
    assert result.status == "cancelled"
    assert [r[0] for r in server.requests] == ["/a"]
    assert len(manager.repository.artifacts(job.job_id)) == 1
    assert not list((root / "artifacts/.pending").iterdir())


async def test_cancellation_between_stream_write_and_publication(harness, monkeypatch):
    from web_acquisition.storage import PendingBlob

    write = PendingBlob.write

    def cancel_after_chunk(self, data):
        write(self, data)
        asyncio.current_task().cancel()

    monkeypatch.setattr(PendingBlob, "write", cancel_after_chunk)
    manager, _server, _transport, root = await harness({"/": Reply()})
    job = manager.submit(
        ["http://web.example/"], CrawlPolicy(robots_mode="ignore", host_interval=0)
    )
    await manager.wait(job.job_id)
    assert not manager.repository.artifacts(job.job_id)
    assert not list((root / "artifacts/.pending").iterdir())


async def test_retry_metadata_and_no_retry_on_404(harness):
    manager, server, _transport, _root = await harness(
        {"/a": [Reply(status=503, body=b""), Reply(body=b"ok")], "/b": Reply(status=404, body=b"")}
    )
    job = manager.submit(
        ["http://web.example/a", "http://web.example/b"],
        CrawlPolicy(robots_mode="ignore", host_interval=0, max_retries=1),
    )
    result = await manager.wait(job.job_id)
    assert result.metrics["retries"] == 1
    assert len([r for r in server.requests if r[0] == "/b"]) == 1
    assert [
        a.retry for a in manager.repository.attempts(job.job_id) if a.requested_url.endswith("/a")
    ] == [0, 1]


async def test_credentials_job_origin_isolation_and_no_metadata_or_log_leak(harness, caplog):
    manager, server, _transport, root = await harness(
        {
            "/a?token=url-secret": Reply(
                status=302, body=b"", headers={"Location": "https://other.example/b"}
            ),
            "/b": Reply(body=b"ok"),
            "/c": Reply(body=b"ok", headers={"Set-Cookie": "sid=cookie-secret"}),
        },
        tls=True,
    )
    # The test CA must validate both fixture hostnames on the same server.
    manager.transport.ca.issue_cert("web.example", "other.example").configure_cert(server.context)
    policy = CrawlPolicy(
        robots_mode="ignore",
        host_interval=0,
        same_origin=False,
        allowed_hosts=("web.example", "other.example"),
    )
    credentials = Credentials(
        {
            "https://web.example": {
                "Authorization": "Bearer auth-secret",
                "Cookie": "sid=initial-secret",
            }
        }
    )
    first = manager.submit(["https://web.example/a?token=url-secret"], policy, credentials)
    second = manager.submit(["https://web.example/c"], policy)
    await asyncio.gather(manager.wait(first.job_id), manager.wait(second.job_id))
    assert b"auth-secret" in next(
        header for target, header, _ in server.requests if target.startswith("/a")
    )
    assert all(
        b"auth-secret" not in header and b"initial-secret" not in header
        for target, header, _ in server.requests
        if target in ("/b", "/c")
    )
    persisted = b"".join(path.read_bytes() for path in (root / "db").iterdir())
    for secret in (b"auth-secret", b"initial-secret", b"cookie-secret", b"url-secret"):
        assert secret not in persisted
        assert secret.decode() not in caplog.text
    assert "auth-secret" not in repr(credentials)


async def test_api_job_endpoints_return_before_crawl_and_cancel(harness):
    manager, server, _transport, _root = await harness({"/": Reply(stall=True)})
    token = "x" * 32
    async with TestClient(TestServer(create_app(manager, token))) as client:
        assert (await client.post("/crawl", json={"seeds": ["http://web.example/"]})).status == 401
        headers = {"Authorization": "Bearer " + token}
        response = await client.post(
            "/crawl",
            headers=headers,
            json={
                "seeds": ["http://web.example/"],
                "policy": {"robots_mode": "ignore", "host_interval": 0},
            },
        )
        assert response.status == 202
        job_id = (await response.json())["job_id"]
        await asyncio.wait_for(server.started.wait(), 2)
        assert (await (await client.get(f"/crawl/{job_id}", headers=headers)).json())[
            "status"
        ] == "running"
        for kind in ("resources", "artifacts", "discoveries", "attempts"):
            assert (await client.get(f"/crawl/{job_id}/{kind}", headers=headers)).status == 200
        assert (await (await client.post(f"/crawl/{job_id}/cancel", headers=headers)).json())[
            "status"
        ] == "cancelled"
        invalid = await client.post(
            "/crawl", headers=headers, json={"seeds": ["http://user:secret@web.example/"]}
        )
        assert invalid.status == 400 and "secret" not in await invalid.text()
        assert not manager.tasks


async def test_admission_limit(harness):
    manager, _server, _transport, _root = await harness({})
    manager.max_pending = 1
    manager.submit(["http://web.example/"], CrawlPolicy(robots_mode="ignore"))
    with pytest.raises(AcquisitionError, match="job_admission_limit"):
        manager.submit(["http://web.example/"], CrawlPolicy())
