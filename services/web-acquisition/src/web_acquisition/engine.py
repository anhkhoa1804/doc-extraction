"""Acquisition orchestration; no SQL, document parsing, or downstream semantics."""

from __future__ import annotations

import asyncio
import json
import logging
from collections.abc import Sequence

from .discovery import LinkParser
from .fetcher import Credentials, FetchResult, HttpFetcher, StreamTransport
from .frontier import Frontier, FrontierItem
from .models import AcquisitionError, CrawlJob, Discovery, JobBudgetExceeded, Resource, now
from .policy import EgressPolicy, PolicyEngine, Resolver
from .repository import Repository
from .robots import RobotsCache
from .scheduler import ByteBudget, Scheduler
from .storage import ArtifactStore
from .urls import display_url, url_key

LOGGER = logging.getLogger("web_acquisition")


class CrawlEngine:
    def __init__(
        self,
        job: CrawlJob,
        seeds: Sequence[str],
        repository: Repository,
        store: ArtifactStore,
        scheduler: Scheduler,
        resolver: Resolver | None = None,
        transport: StreamTransport | None = None,
        credentials: Credentials | None = None,
        fetcher: HttpFetcher | None = None,
    ):
        self.job = job
        self.seeds = seeds
        self.repository = repository
        self.store = store
        self.policy = PolicyEngine(job.policy, seeds)
        self.budget = ByteBudget(job.policy.max_total_bytes)
        self.fetcher = fetcher or HttpFetcher(
            job,
            self.policy,
            repository,
            store,
            scheduler,
            self.budget,
            resolver,
            transport,
            credentials,
        )
        self.fetcher.authorize = RobotsCache(self.fetcher).authorize
        self.frontier = Frontier()
        self.resources: dict[str, Resource] = {}
        self.tasks: list[asyncio.Task[FetchResult | AcquisitionError]] = []
        self.results: list[FetchResult] = []
        self.artifact_ids: set[str] = set()
        self.fetch_count = 0

    def metric(self, key: str, count: int = 1) -> None:
        self.job.metrics[key] = self.job.metrics.get(key, 0) + count

    def discover(
        self,
        raw: str,
        parent: FrontierItem | None,
        depth: int,
        method: str,
        base: str | None = None,
    ) -> None:
        if self.job.metrics.get("discoveries", 0) >= self.job.policy.max_discoveries:
            self.metric("discovery_limit")
            return
        self.metric("discoveries")
        reason: str | None = None
        normalized: str | None = None
        try:
            normalized = self.policy.normalized(raw, base)
            self.policy.check(normalized)
            EgressPolicy().validate_url(normalized)
            if depth > self.job.policy.max_depth:
                raise AcquisitionError("depth_limit")
        except AcquisitionError as exc:
            reason = exc.code
        key = url_key(normalized if normalized is not None else raw)
        existing = self.resources.get(key)
        display = display_url(normalized) if normalized else "[rejected-url]"
        if existing is not None:
            reason = "duplicate"
            existing.last_seen_at = now()
            self.repository.save_resource(existing)
            self.metric("duplicate_urls")
        else:
            existing = Resource(
                job_id=self.job.job_id,
                url_key=key,
                source_url=display,
                canonical_url=display,
                parent_resource_id=parent.resource.resource_id if parent else None,
                parent_url=parent.resource.final_url if parent else None,
                depth=depth,
                discovery_method=method,
                status="rejected" if reason else "accepted",
                rejection_reason=reason,
            )
            self.resources[key] = existing
            self.repository.save_resource(existing)
            self.metric("resources_discovered")
            self.metric("resources_rejected" if reason else "resources_accepted")
            if not reason:
                assert normalized is not None
                self.frontier.push(FrontierItem(normalized, existing))
        self.repository.save_discovery(
            Discovery(
                job_id=self.job.job_id,
                resource_id=existing.resource_id,
                source_url=display,
                parent_resource_id=parent.resource.resource_id if parent else None,
                depth=depth,
                method=method,
                decision="rejected" if reason else "accepted",
                reason=reason,
            )
        )
        if reason:
            self.metric(reason)

    async def _fetch(
        self, item: FrontierItem, semaphore: asyncio.Semaphore
    ) -> FetchResult | AcquisitionError:
        async with semaphore:
            item.resource.status = "fetching"
            self.repository.save_resource(item.resource)
            try:
                result = await self.fetcher.fetch(item.url, item.resource)
                self.results.append(result)
                return result
            except JobBudgetExceeded:
                raise
            except AcquisitionError as exc:
                return exc

    async def run(self) -> None:
        for seed in sorted(self.seeds):
            self.discover(seed, None, 0, "seed")
        try:
            while level := self.frontier.pop_level():
                remaining = self.job.policy.max_pages - self.fetch_count
                selected = level[:remaining]
                for item in level[remaining:]:
                    item.resource.status = "rejected"
                    item.resource.rejection_reason = "page_limit"
                    self.repository.save_resource(item.resource)
                    self.metric("page_limit")
                if not selected:
                    break
                self.fetch_count += len(selected)
                semaphore = asyncio.Semaphore(self.job.policy.concurrency)
                self.tasks = [
                    asyncio.create_task(self._fetch(item, semaphore)) for item in selected
                ]
                outcomes = await asyncio.gather(*self.tasks)
                # Nothing from this level is published until all fetches
                # settle. A total-byte failure aborts the whole level,
                # rather than making admission depend on completion order.
                for item, outcome in zip(selected, outcomes, strict=True):
                    await asyncio.sleep(0)  # cancellation boundary before publication
                    if isinstance(outcome, AcquisitionError):
                        item.resource.status = "failed"
                        item.resource.rejection_reason = outcome.code
                        self.metric(outcome.code)
                        if "timeout" in outcome.code:
                            self.metric("timeouts")
                        self.repository.save_resource(item.resource)
                        continue
                    self._commit(item, outcome)
                self.results.clear()
                self.repository.save_job(self.job)
        finally:
            for task in self.tasks:
                if not task.done():
                    task.cancel()
            await asyncio.gather(*self.tasks, return_exceptions=True)
            for result in self.results:
                result.body.discard()
            for resource in self.resources.values():
                if resource.status in ("accepted", "fetching"):
                    resource.status = "cancelled"
                    resource.rejection_reason = "job_stopped"
                    self.repository.save_resource(resource)
            self.job.metrics["bytes_downloaded"] = self.budget.used
            self.job.metrics["wire_bytes_received"] = self.budget.received
            self.job.metrics["decoded_bytes"] = self.budget.decoded
            self.job.metrics["ssrf_blocks"] = self.job.metrics.get("ssrf_blocked", 0)
            self.job.metrics["robots_blocks"] = self.job.metrics.get("blocked_by_robots", 0)
            self.job.metrics["policy_blocks"] = sum(
                self.job.metrics.get(key, 0)
                for key in ("outside_scope", "policy_denied", "content_type_denied")
            )

    def _commit(self, item: FrontierItem, result: FetchResult) -> None:
        resource = item.resource
        resource.http_status = result.status
        resource.final_url = display_url(result.url)
        resource.content_type = result.media_type
        resource.content_length = result.content_length
        resource.content_encoding = result.content_encoding
        if not 200 <= result.status < 300:
            result.body.discard()
            resource.status = "failed"
            resource.rejection_reason = "http_" + str(result.status)
            self.metric("http_failures")
            self.repository.save_resource(resource)
            return
        parser: LinkParser | None = None
        if result.media_type in ("text/html", "application/xhtml+xml"):
            if result.body.size > self.job.policy.max_html_parse_size:
                resource.warnings.append("html_parse_limit")
                self.metric("html_parse_limit")
            else:
                parser = LinkParser(self.job.policy.max_links_per_page)
                parser.feed(
                    result.body.read_bounded(self.job.policy.max_html_parse_size).decode(
                        "utf-8", errors="replace"
                    )
                )
                parser.close()
                if parser.truncated:
                    resource.warnings.append("links_limit")
                    self.metric("links_limit")
        # The artifact cap controls new publications, including duplicate
        # response candidates, before atomic sealing.
        if (
            len(self.artifact_ids) >= self.job.policy.max_artifacts
            and "sha256:" + result.body.sha256 not in self.artifact_ids
        ):
            result.body.discard()
            resource.status = "rejected"
            resource.rejection_reason = "artifact_limit"
            self.metric("artifact_limit")
            self.repository.save_resource(resource)
            return
        artifact = result.body.seal()
        resource.status = "acquired"
        resource.artifact_id = artifact.artifact_id
        resource.sha256 = artifact.sha256
        if artifact.artifact_id in self.artifact_ids:
            self.metric("duplicate_content")
        else:
            self.artifact_ids.add(artifact.artifact_id)
            self.metric("artifacts_created")
        if parser and parser.canonical:
            try:
                canonical = self.policy.normalized(parser.canonical, result.url)
                resource.advertised_canonical_url = display_url(canonical)
            except AcquisitionError:
                resource.warnings.append("invalid_advertised_canonical")
        self.repository.publish(artifact, resource)
        self.metric("resources_fetched")
        LOGGER.info(
            json.dumps(
                {
                    "event": "acquired",
                    "job_id": self.job.job_id,
                    "resource_id": resource.resource_id,
                    "artifact_id": artifact.artifact_id,
                    "size_bytes": artifact.size_bytes,
                    "http_status": result.status,
                }
            )
        )
        if parser:
            for link in parser.links:
                self.discover(link.url, item, resource.depth + 1, link.method, result.url)
