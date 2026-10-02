"""CLI uses exactly the service job runner and egress policy."""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import os
from pathlib import Path

from aiohttp import web

from .api import create_app
from .jobs import JobManager
from .models import AcquisitionError, CrawlPolicy
from .repository import SQLiteRepository
from .storage import FileArtifactStore


async def crawl(
    args: argparse.Namespace, repository: SQLiteRepository, store: FileArtifactStore
) -> int:
    manager = JobManager(repository, store)
    try:
        policy = CrawlPolicy(
            max_depth=args.max_depth,
            max_pages=args.max_pages,
            max_total_bytes=args.max_bytes,
            max_response_bytes=args.max_response_bytes,
            allowed_hosts=tuple(args.allowed_host),
            allowed_domains=tuple(args.allowed_domain),
            same_origin=not args.cross_origin,
            include_subdomains=args.include_subdomains,
            concurrency=args.concurrency,
            request_timeout=args.timeout,
            robots_mode=args.robots_mode,
        )
        job = manager.submit(args.seeds, policy)
        try:
            result = await manager.wait(job.job_id)
        except asyncio.CancelledError:
            await manager.cancel(job.job_id)
            raise
        print(json.dumps(result.model_dump(mode="json"), sort_keys=True))
        return (
            0 if result.status == "completed" and result.metrics.get("resources_fetched", 0) else 1
        )
    finally:
        await manager.close()


def main() -> int:
    parser = argparse.ArgumentParser(prog="crawler")
    commands = parser.add_subparsers(dest="command", required=True)
    run = commands.add_parser("crawl")
    run.add_argument("seeds", nargs="+")
    run.add_argument("--max-depth", type=int, default=2)
    run.add_argument("--max-pages", type=int, default=100)
    run.add_argument("--max-bytes", type=int, default=256 * 1024**2)
    run.add_argument("--max-response-bytes", type=int, default=16 * 1024**2)
    run.add_argument("--allowed-host", action="append", default=[])
    run.add_argument("--allowed-domain", action="append", default=[])
    run.add_argument("--cross-origin", action="store_true")
    run.add_argument("--include-subdomains", action="store_true")
    run.add_argument("--concurrency", type=int, default=4)
    run.add_argument("--timeout", type=float, default=30)
    run.add_argument("--robots-mode", choices=["obey", "ignore"], default="obey")
    server = commands.add_parser("serve")
    server.add_argument("--host", default="127.0.0.1")
    server.add_argument("--port", type=int, default=8080)
    for command in (run, server):
        command.add_argument("--database", type=Path, default=Path("state/metadata.sqlite"))
        command.add_argument("--output", type=Path, default=Path("state/artifacts"))
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    repository = SQLiteRepository(args.database)
    store = FileArtifactStore(args.output)
    try:
        if args.command == "serve":
            token = os.environ.get("WEB_ACQUISITION_API_TOKEN", "")
            manager = JobManager(repository, store)
            web.run_app(create_app(manager, token), host=args.host, port=args.port, access_log=None)
            return 0
        return asyncio.run(crawl(args, repository, store))
    except (AcquisitionError, ValueError):
        print(json.dumps({"error": "invalid_request_or_configuration"}))
        return 2
    finally:
        store.close()
        repository.close()
