"""Async HTTP/1.1 via h11, with literal-IP dialing and bounded wire input.

No proxies, automatic redirects, browser, shell, or document parser. TLS
always validates the original URL hostname, even though dialing uses an IP.
"""

from __future__ import annotations

import asyncio
import ipaddress
import ssl
import zlib
from collections.abc import Awaitable, Callable, Mapping
from dataclasses import dataclass, field
from types import MappingProxyType
from urllib.parse import urlsplit

import h11

from .models import AcquisitionError, CrawlJob, FetchAttempt, JobBudgetExceeded, Resource, now
from .policy import EgressPolicy, PolicyEngine, Resolver
from .repository import Repository
from .scheduler import ByteBudget, Scheduler
from .storage import ArtifactStore, Download
from .urls import display_url, origin, url_key


@dataclass(frozen=True, repr=False)
class Credentials:
    """Execution-only exact-HTTPS-origin headers. No cookie jar or persistence."""

    by_origin: Mapping[str, Mapping[str, str]] = field(default_factory=dict)

    def __post_init__(self) -> None:
        copied = {}
        for key, headers in self.by_origin.items():
            if not key.startswith("https://") or origin(key) != key:
                raise ValueError("credentials require an exact HTTPS origin")
            if any(name.lower() not in ("authorization", "cookie") for name in headers):
                raise ValueError("only Authorization and Cookie credentials are accepted")
            if sum(len(k) + len(v) for k, v in headers.items()) > 8192:
                raise ValueError("credentials exceed header budget")
            copied[key] = MappingProxyType(dict(headers))
        object.__setattr__(self, "by_origin", MappingProxyType(copied))

    def headers(self, url: str) -> list[tuple[str, str]]:
        return list(self.by_origin.get(origin(url), {}).items())


class StreamTransport:
    async def connect(
        self, address: str, port: int, host: str, context: ssl.SSLContext | None, limit: int
    ) -> tuple[asyncio.StreamReader, asyncio.StreamWriter]:
        return await asyncio.open_connection(
            address, port, ssl=context, server_hostname=host if context else None, limit=limit
        )


@dataclass
class FetchResult:
    url: str
    status: int
    media_type: str | None
    content_length: int | None
    content_encoding: str
    body: Download


class ResponseValidator:
    def validate(
        self, headers: Mapping[bytes, bytes], maximum: int
    ) -> tuple[int | None, str | None, str]:
        if b"content-length" in headers and b"transfer-encoding" in headers:
            raise AcquisitionError("ambiguous_response_framing")
        length = int(headers[b"content-length"]) if b"content-length" in headers else None
        if length is not None and length > maximum:
            raise AcquisitionError("too_large")
        media = (
            headers.get(b"content-type", b"")
            .decode("ascii", errors="replace")
            .split(";", 1)[0]
            .strip()
            .lower()
            or None
        )
        encoding = (
            headers.get(b"content-encoding", b"identity")
            .decode("ascii", errors="replace")
            .strip()
            .lower()
        )
        if encoding not in ("identity", "gzip", "deflate"):
            raise AcquisitionError("unsupported_content_encoding")
        return length, media, encoding


class HttpFetcher:
    def __init__(
        self,
        job: CrawlJob,
        policy: PolicyEngine,
        repository: Repository,
        store: ArtifactStore,
        scheduler: Scheduler,
        budget: ByteBudget,
        resolver: Resolver | None = None,
        transport: StreamTransport | None = None,
        credentials: Credentials | None = None,
        context: ssl.SSLContext | None = None,
    ):
        self.job = job
        self.policy = policy
        self.repository = repository
        self.store = store
        self.scheduler = scheduler
        self.budget = budget
        self.resolver = resolver or Resolver()
        self.transport = transport or StreamTransport()
        self.egress = EgressPolicy()
        self.credentials = credentials or Credentials()
        self.context = context or ssl.create_default_context()
        if self.context.verify_mode != ssl.CERT_REQUIRED or not self.context.check_hostname:
            raise ValueError("TLS verification cannot be disabled")
        self.validator = ResponseValidator()
        self.host_slots: dict[str, asyncio.Semaphore] = {}
        self.authorize: Callable[[str, Resource], Awaitable[float]] | None = None

    async def fetch(
        self,
        url: str,
        resource: Resource,
        *,
        robots: bool = False,
        maximum: int | None = None,
        delay: float = 0,
    ) -> FetchResult:
        policy = self.job.policy
        maximum = min(maximum or policy.max_response_bytes, policy.max_response_bytes)
        for retry in range(policy.max_retries + 1):
            current = url
            seen: set[str] = set()
            try:
                for hop in range(policy.max_redirects + 1):
                    if current in seen:
                        raise AcquisitionError("redirect_loop")
                    seen.add(current)
                    self.policy.check(current, robots=robots)
                    self.egress.validate_url(current)
                    if not robots and self.authorize is not None:
                        delay = await self.authorize(current, resource)
                    attempt = FetchAttempt(
                        job_id=self.job.job_id,
                        resource_id=resource.resource_id,
                        requested_url=display_url(current),
                        url_key=url_key(current),
                        retry=retry,
                        redirect_hop=hop,
                        purpose="robots" if robots else "resource",
                    )
                    result, location = await self._attempt(current, attempt, robots, maximum, delay)
                    if result.status in (301, 302, 303, 307, 308):
                        result.body.discard()
                        if not location:
                            raise AcquisitionError("redirect_without_location")
                        if hop == policy.max_redirects:
                            raise AcquisitionError("redirect_limit")
                        current = self.policy.normalized(location, current)
                        # A downgrade could leak an authenticated response's
                        # destination or tokens; credentials themselves are
                        # always scoped anew at each request.
                        if urlsplit(url).scheme == "https" and urlsplit(current).scheme != "https":
                            raise AcquisitionError("redirect_tls_downgrade")
                        continue
                    if result.status in (429, 502, 503, 504) and retry < policy.max_retries:
                        result.body.discard()
                        self.job.metrics["retries"] = self.job.metrics.get("retries", 0) + 1
                        await asyncio.sleep(min(2**retry * 0.1, 2.0))
                        break
                    return result
                else:
                    raise AcquisitionError("redirect_limit")
            except JobBudgetExceeded:
                raise
            except AcquisitionError as exc:
                if (
                    exc.code not in ("network_error", "request_timeout", "read_timeout")
                    or retry == policy.max_retries
                ):
                    raise
                self.job.metrics["retries"] = self.job.metrics.get("retries", 0) + 1
                await asyncio.sleep(min(2**retry * 0.1, 2.0))
        raise AcquisitionError("retry_exhausted")

    async def _attempt(
        self, url: str, attempt: FetchAttempt, robots: bool, maximum: int, delay: float
    ) -> tuple[FetchResult, str | None]:
        self.repository.save_attempt(attempt)
        try:
            self.policy.check(url, robots=robots)
            self.egress.validate_url(url)
            parts = urlsplit(url)
            host = str(parts.hostname)
            timeout = (
                min(self.job.policy.robots_timeout, self.job.policy.request_timeout)
                if robots
                else self.job.policy.request_timeout
            )
            slots = self.host_slots.setdefault(
                host, asyncio.Semaphore(self.job.policy.per_host_concurrency)
            )
            async with slots, self.scheduler.slot(host, self.job.policy, delay=delay):
                async with asyncio.timeout(timeout):
                    result, location = await self._request(url, attempt, maximum, robots)
            attempt.status = "received"
            self.job.metrics["http_" + str(result.status)] = (
                self.job.metrics.get("http_" + str(result.status), 0) + 1
            )
            return result, location
        except asyncio.CancelledError:
            attempt.status = "cancelled"
            attempt.error_code = "cancelled"
            raise
        except TimeoutError as exc:
            attempt.status = "failed"
            attempt.error_code = "request_timeout"
            raise AcquisitionError("request_timeout") from exc
        except ssl.SSLError as exc:
            attempt.status = "failed"
            attempt.error_code = "tls_error"
            raise AcquisitionError("tls_error") from exc
        except (OSError, h11.RemoteProtocolError, h11.LocalProtocolError) as exc:
            code = "malformed_response" if isinstance(exc, h11.ProtocolError) else "network_error"
            attempt.status = "failed"
            attempt.error_code = code
            raise AcquisitionError(code) from exc
        except AcquisitionError as exc:
            attempt.status = "failed"
            attempt.error_code = exc.code
            raise
        finally:
            attempt.finished_at = now()
            self.repository.save_attempt(attempt)

    async def _request(
        self, url: str, attempt: FetchAttempt, maximum: int, robots: bool
    ) -> tuple[FetchResult, str | None]:
        parts = urlsplit(url)
        host = str(parts.hostname)
        port = parts.port or (443 if parts.scheme == "https" else 80)
        policy = self.job.policy
        async with asyncio.timeout(policy.connect_timeout):
            try:
                addresses = [str(ipaddress.ip_address(host))]
            except ValueError:
                addresses = await self.resolver.resolve(host, port)
            self.egress.validate_resolved_addresses(addresses)
            attempt.resolved_addresses = addresses
            # Do not hand a hostname back to the socket layer (DNS rebinding).
            reader, writer = await self.transport.connect(
                addresses[0],
                port,
                host,
                self.context if parts.scheme == "https" else None,
                policy.max_headers_size,
            )
        body: Download | None = None
        completed: tuple[FetchResult, str | None] | None = None
        try:
            peer = writer.get_extra_info("peername")
            if not peer or ipaddress.ip_address(peer[0]) != ipaddress.ip_address(addresses[0]):
                raise AcquisitionError("peer_address_mismatch")
            self.egress.validate_resolved_addresses([peer[0]])
            connection = h11.Connection(
                h11.CLIENT, max_incomplete_event_size=policy.max_headers_size
            )
            target = parts.path + ("?" + parts.query if parts.query else "")
            headers = [
                ("Host", parts.netloc),
                ("User-Agent", policy.user_agent),
                ("Accept-Encoding", "identity"),
                ("Connection", "close"),
            ]
            headers.extend(self.credentials.headers(url))
            writer.write(connection.send(h11.Request(method="GET", target=target, headers=headers)))
            writer.write(connection.send(h11.EndOfMessage()))
            await writer.drain()
            header_count = 0
            for _ in range(6):
                try:
                    raw = await asyncio.wait_for(reader.readuntil(b"\r\n\r\n"), policy.read_timeout)
                except asyncio.LimitOverrunError as exc:
                    raise AcquisitionError("headers_limit") from exc
                except asyncio.IncompleteReadError as exc:
                    raise AcquisitionError("malformed_response") from exc
                header_count += len(raw)
                attempt.bytes_received += len(raw)
                self.budget.consume(len(raw))
                if header_count > policy.max_headers_size:
                    raise AcquisitionError("headers_limit")
                connection.receive_data(raw)
                event = connection.next_event()
                if isinstance(event, h11.Response):
                    break
                if not isinstance(event, h11.InformationalResponse) or event.status_code == 101:
                    raise AcquisitionError("unsupported_response")
            else:
                raise AcquisitionError("informational_response_limit")
            assert isinstance(event, h11.Response)
            attempt.http_status = event.status_code
            pairs = list(event.headers)
            if sum(name == b"location" for name, _ in pairs) > 1:
                raise AcquisitionError("ambiguous_redirect")
            response_headers = dict(pairs)
            length, media, encoding = self.validator.validate(response_headers, maximum)
            if (
                not robots
                and 200 <= event.status_code < 300
                and policy.allowed_content_types
                and media not in policy.allowed_content_types
            ):
                raise AcquisitionError("content_type_denied")
            location = response_headers.get(b"location")
            if location is not None:
                location_text = location.decode("utf-8", errors="strict")
            else:
                location_text = None
            body = self.store.begin(maximum)
            decoder = (
                zlib.decompressobj(16 + zlib.MAX_WBITS if encoding == "gzip" else zlib.MAX_WBITS)
                if encoding != "identity"
                else None
            )
            wire = 0
            while True:
                frame = connection.next_event()
                if frame is h11.NEED_DATA:
                    raw = await asyncio.wait_for(
                        reader.read(min(65536, policy.max_headers_size)), policy.read_timeout
                    )
                    wire += len(raw)
                    attempt.bytes_received += len(raw)
                    self.budget.consume(len(raw))
                    if wire > maximum + policy.max_headers_size:
                        raise AcquisitionError("too_large")
                    connection.receive_data(raw)
                elif isinstance(frame, h11.Data):
                    data = bytes(frame.data)
                    if decoder is not None:
                        data = decoder.decompress(data, maximum - body.size + 1)
                    self.budget.consume_decoded(len(data))
                    body.write(data)
                elif isinstance(frame, h11.EndOfMessage):
                    if decoder is not None and (not decoder.eof or decoder.unused_data):
                        raise AcquisitionError("malformed_compression")
                    if connection.trailing_data[0]:
                        raise AcquisitionError("unexpected_response_bytes")
                    if sum(len(k) + len(v) + 4 for k, v in frame.headers) > policy.max_headers_size:
                        raise AcquisitionError("headers_limit")
                    # Do not return from inside this block.  A task may be
                    # cancelled while ``writer.wait_closed`` runs below; in
                    # that case this pending file is still owned here and
                    # must be discarded rather than handed to the engine.
                    completed = (
                        FetchResult(url, event.status_code, media, length, encoding, body),
                        location_text,
                    )
                    break
                elif isinstance(frame, h11.ConnectionClosed):
                    raise AcquisitionError("partial_download")
                else:
                    raise AcquisitionError("malformed_response")
        except (zlib.error, UnicodeError) as exc:
            if body is not None:
                body.discard()
            raise AcquisitionError("malformed_response") from exc
        except BaseException:
            if body is not None:
                body.discard()
            raise
        finally:
            writer.close()
            # A slow TLS peer cannot keep shutdown alive after cancellation.
            # Crucially, cancellation here occurs before ``completed`` is
            # returned, so this function still owns the PendingBlob.
            try:
                await asyncio.wait_for(writer.wait_closed(), timeout=1)
            except asyncio.CancelledError:
                if body is not None:
                    body.discard()
                raise
            except (OSError, TimeoutError):
                pass
        if completed is None:
            raise AcquisitionError("malformed_response")
        return completed
