"""Controlled wire servers, not a production allow-private switch.

The injected transport maps a validated PUBLIC test IP to this loopback
server and projects its peer address. Production StreamTransport has no such
mapping. All policy/DNS/redirect/header/body/TLS logic still runs unchanged.
"""

from __future__ import annotations

import asyncio
import ssl
import time
from dataclasses import dataclass, field
from typing import cast

import pytest
import trustme

from web_acquisition.fetcher import StreamTransport
from web_acquisition.jobs import JobManager
from web_acquisition.policy import Resolver
from web_acquisition.repository import SQLiteRepository
from web_acquisition.storage import FileArtifactStore

PUBLIC = "93.184.216.34"


class FixtureResolver(Resolver):
    def __init__(self, responses=None):
        self.responses = list(responses or [[PUBLIC]])
        self.calls = []

    async def resolve(self, host, port):
        self.calls.append((host, port))
        return self.responses.pop(0) if len(self.responses) > 1 else self.responses[0]


class PeerProjection:
    def __init__(self, writer, address):
        self.writer = writer
        self.address = address

    def get_extra_info(self, name):
        return (self.address, 80) if name == "peername" else self.writer.get_extra_info(name)

    def __getattr__(self, name):
        return getattr(self.writer, name)


class FixtureTransport(StreamTransport):
    def __init__(self, server, ca=None):
        self.server = server
        self.ca = ca
        self.calls = []

    async def connect(self, address, port, host, context, limit):
        assert address == PUBLIC
        self.calls.append((address, port, host, context is not None))
        if context and self.ca:
            self.ca.configure_trust(context)
        reader, writer = await asyncio.open_connection(
            "127.0.0.1",
            self.server.port,
            ssl=context,
            server_hostname=host if context else None,
            limit=limit,
        )
        return reader, cast(asyncio.StreamWriter, PeerProjection(writer, address))


@dataclass
class Reply:
    body: bytes = b"content"
    status: int = 200
    headers: dict[str, str] = field(default_factory=lambda: {"Content-Type": "text/plain"})
    raw: bytes | None = None
    stall: bool = False
    delay: float = 0
    auto_length: bool = True

    def wire(self):
        if self.raw is not None:
            return self.raw
        headers = dict(self.headers)
        if self.auto_length:
            headers.setdefault("Content-Length", str(len(self.body)))
        return (
            f"HTTP/1.1 {self.status} OK\r\n"
            + "".join(f"{k}: {v}\r\n" for k, v in headers.items())
            + "\r\n"
        ).encode() + self.body


class WireServer:
    def __init__(self, routes, context=None):
        self.routes = routes
        self.context = context
        self.requests = []
        self.tasks = set()
        self.connections = 0
        self.max_connections = 0
        self.block = asyncio.Event()
        self.started = asyncio.Event()

    async def start(self):
        self.listener = await asyncio.start_server(self.handle, "127.0.0.1", 0, ssl=self.context)
        self.port = self.listener.sockets[0].getsockname()[1]
        return self

    async def handle(self, reader, writer):
        task = asyncio.current_task()
        self.tasks.add(task)
        self.connections += 1
        self.max_connections = max(self.max_connections, self.connections)
        try:
            header = await asyncio.wait_for(reader.readuntil(b"\r\n\r\n"), 3)
            target = header.split(b" ", 2)[1].decode()
            self.requests.append((target, header, time.monotonic()))
            self.started.set()
            reply = self.routes.get(target, Reply(status=404, body=b""))
            if isinstance(reply, list):
                reply = reply.pop(0) if len(reply) > 1 else reply[0]
            if reply.stall:
                await self.block.wait()
            if reply.delay:
                await asyncio.sleep(reply.delay)
            writer.write(reply.wire())
            await writer.drain()
        except (OSError, asyncio.IncompleteReadError, TimeoutError):
            pass
        finally:
            writer.close()
            try:
                await writer.wait_closed()
            except OSError:
                pass
            self.tasks.discard(task)
            self.connections -= 1

    async def close(self):
        self.listener.close()
        for task in list(self.tasks):
            task.cancel()
        await asyncio.gather(*self.tasks, return_exceptions=True)
        await self.listener.wait_closed()


@pytest.fixture
async def harness(tmp_path):
    managers, stores, repositories, servers = [], [], [], []

    async def create(routes, resolver=None, *, tls=False, certificate_host="web.example"):
        ca = trustme.CA() if tls else None
        context = None
        if ca:
            context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
            ca.issue_cert(certificate_host).configure_cert(context)
        server = await WireServer(routes, context).start()
        root = tmp_path / str(len(stores))
        store = FileArtifactStore(root / "artifacts")
        repository = SQLiteRepository(root / "db" / "metadata.sqlite")
        transport = FixtureTransport(server, ca)
        manager = JobManager(
            repository, store, resolver=resolver or FixtureResolver(), transport=transport
        )
        stores.append(store)
        repositories.append(repository)
        servers.append(server)
        managers.append(manager)
        return manager, server, transport, root

    yield create
    for manager in managers:
        await manager.close()
    for server in servers:
        await server.close()
    for store in stores:
        store.close()
    for repository in repositories:
        repository.close()
