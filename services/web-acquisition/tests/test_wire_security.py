import gzip
import ssl

import pytest
from conftest import PUBLIC, FixtureResolver, Reply

from web_acquisition.models import CrawlPolicy


async def fetch_case(harness, reply, **kwargs):
    manager, server, transport, root = await harness({"/": reply})
    policy = CrawlPolicy(robots_mode="ignore", max_retries=0, host_interval=0, **kwargs)
    job = manager.submit(["http://web.example/"], policy)
    await manager.wait(job.job_id)
    resource = manager.repository.resources(job.job_id)[0]
    assert not list((root / "artifacts/.pending").iterdir())
    return resource, manager, server, transport, root, job


@pytest.mark.parametrize(
    "seed", ["http://127.0.0.1/", "http://10.0.0.1/", "http://169.254.169.254/", "http://[::1]/"]
)
async def test_literal_ssrf_no_connection(harness, seed):
    manager, _server, transport, _root = await harness({})
    job = manager.submit([seed], CrawlPolicy(robots_mode="ignore"))
    await manager.wait(job.job_id)
    assert manager.repository.resources(job.job_id)[0].rejection_reason == "ssrf_blocked"
    assert not transport.calls


@pytest.mark.parametrize(
    "host,addresses",
    [("localhost", ["127.0.0.1"]), ("web.example", ["10.0.0.1"]), ("web.example", [PUBLIC, "::1"])],
)
async def test_dns_ssrf_no_connection(harness, host, addresses):
    manager, _server, transport, _root = await harness({}, FixtureResolver([addresses]))
    job = manager.submit([f"http://{host}/"], CrawlPolicy(robots_mode="ignore", max_retries=0))
    await manager.wait(job.job_id)
    assert manager.repository.resources(job.job_id)[0].rejection_reason == "ssrf_blocked"
    assert not transport.calls


async def test_public_to_private_redirect_never_connects(harness):
    manager, _server, transport, root = await harness(
        {"/": Reply(status=302, body=b"", headers={"Location": "http://127.0.0.1/"})}
    )
    job = manager.submit(
        ["http://web.example/"],
        CrawlPolicy(
            same_origin=False,
            allowed_hosts=("web.example", "127.0.0.1"),
            robots_mode="ignore",
            host_interval=0,
        ),
    )
    await manager.wait(job.job_id)
    assert manager.repository.resources(job.job_id)[0].rejection_reason == "ssrf_blocked"
    assert len(transport.calls) == 1
    assert not manager.repository.artifacts(job.job_id)
    assert not list((root / "artifacts/.pending").iterdir())


async def test_dns_rebinding_revalidated_at_next_hop(harness):
    resolver = FixtureResolver([[PUBLIC], ["127.0.0.1"]])
    manager, _server, transport, _root = await harness(
        {"/": Reply(status=302, body=b"", headers={"Location": "/next"})}, resolver
    )
    job = manager.submit(
        ["http://web.example/"], CrawlPolicy(robots_mode="ignore", host_interval=0)
    )
    await manager.wait(job.job_id)
    assert manager.repository.resources(job.job_id)[0].rejection_reason == "ssrf_blocked"
    assert len(transport.calls) == 1
    assert len(resolver.calls) == 2


async def test_disallowed_host_redirect(harness):
    resource, _manager, _server, transport, _root, _job = await fetch_case(
        harness, Reply(status=302, body=b"", headers={"Location": "http://other.example/"})
    )
    assert resource.rejection_reason == "outside_scope"
    assert len(transport.calls) == 1


async def test_multiple_redirect_hops_and_final_identity(harness):
    manager, _server, transport, _root = await harness(
        {
            "/": Reply(status=302, body=b"", headers={"Location": "/b"}),
            "/b": Reply(status=307, body=b"", headers={"Location": "/c"}),
            "/c": Reply(body=b"final"),
        }
    )
    job = manager.submit(
        ["http://web.example/"], CrawlPolicy(robots_mode="ignore", host_interval=0)
    )
    await manager.wait(job.job_id)
    resource = manager.repository.resources(job.job_id)[0]
    assert resource.status == "acquired"
    assert resource.source_url.endswith("/") and resource.final_url.endswith("/c")
    assert len(transport.calls) == 3
    assert [a.redirect_hop for a in manager.repository.attempts(job.job_id)] == [0, 1, 2]


@pytest.mark.parametrize(
    "reply,reason",
    [
        (Reply(body=b"x", headers={"Content-Length": "1000"}), "too_large"),
        (Reply(body=b"x" * 100, auto_length=False), "too_large"),
        (
            Reply(
                raw=b"HTTP/1.1 200 OK\r\nTransfer-Encoding: chunked\r\n\r\n64\r\n"
                + b"x" * 100
                + b"\r\n0\r\n\r\n"
            ),
            "too_large",
        ),
        (
            Reply(body=gzip.compress(b"x" * 10000), headers={"Content-Encoding": "gzip"}),
            "too_large",
        ),
        (Reply(body=b"short", headers={"Content-Length": "50"}), "malformed_response"),
        (
            Reply(
                raw=b"HTTP/1.1 200 OK\r\nContent-Length: 1\r\nTransfer-Encoding: chunked\r\n\r\n0\r\n\r\n"
            ),
            "ambiguous_response_framing",
        ),
    ],
)
async def test_bounded_and_malformed_bodies(harness, reply, reason):
    resource, manager, _server, _transport, _root, job = await fetch_case(
        harness, reply, max_response_bytes=64
    )
    assert resource.rejection_reason == reason
    assert not manager.repository.artifacts(job.job_id)


async def test_headers_limited_before_body(harness):
    resource, _manager, _server, _transport, _root, _job = await fetch_case(
        harness, Reply(headers={"Large": "x" * 5000}), max_headers_size=256
    )
    assert resource.rejection_reason == "headers_limit"


async def test_stalled_request_timeout_cleanup(harness):
    resource, manager, _server, _transport, _root, job = await fetch_case(
        harness, Reply(stall=True), read_timeout=0.03, request_timeout=0.1
    )
    assert "timeout" in resource.rejection_reason
    assert not manager.repository.artifacts(job.job_id)
    assert manager.repository.attempts(job.job_id)[0].status == "failed"


async def test_small_gzip_has_decoded_content_identity(harness):
    resource, manager, _server, _transport, _root, job = await fetch_case(
        harness,
        Reply(body=gzip.compress(b"decoded"), headers={"Content-Encoding": "gzip"}),
        max_response_bytes=128,
    )
    import hashlib

    assert resource.sha256 == hashlib.sha256(b"decoded").hexdigest()
    assert resource.content_encoding == "gzip"
    assert manager.repository.artifacts(job.job_id)[0].size_bytes == 7


async def test_tls_hostname_verification_rejects_wrong_certificate(harness):
    manager, _server, _transport, _root = await harness(
        {"/": Reply()}, tls=True, certificate_host="wrong.example"
    )
    job = manager.submit(["https://web.example/"], CrawlPolicy(robots_mode="ignore", max_retries=0))
    await manager.wait(job.job_id)
    assert manager.repository.resources(job.job_id)[0].rejection_reason == "tls_error"
    assert not manager.repository.artifacts(job.job_id)


def test_tls_verification_cannot_be_disabled():
    from web_acquisition.fetcher import HttpFetcher
    from web_acquisition.models import CrawlJob
    from web_acquisition.policy import PolicyEngine
    from web_acquisition.scheduler import ByteBudget, Scheduler

    context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
    context.check_hostname = False
    context.verify_mode = ssl.CERT_NONE
    policy = CrawlPolicy()
    job = CrawlJob(seed_urls=["https://web.example/"], policy=policy)
    with pytest.raises(ValueError, match="cannot be disabled"):
        HttpFetcher(
            job,
            PolicyEngine(policy, job.seed_urls),
            None,
            None,
            Scheduler(),
            ByteBudget(100),
            context=context,
        )
