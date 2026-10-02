"""Process-local job lifecycle, bounded admission, cancellation and shutdown."""

from __future__ import annotations

import asyncio
import json
import logging
from collections.abc import Sequence

from .engine import CrawlEngine
from .fetcher import Credentials, StreamTransport
from .models import AcquisitionError, CrawlJob, CrawlPolicy, JobStatus, now
from .policy import Resolver
from .repository import Repository
from .scheduler import Scheduler
from .storage import ArtifactStore
from .urls import display_url, normalize

LOGGER = logging.getLogger("web_acquisition")


class JobManager:
    def __init__(
        self,
        repository: Repository,
        store: ArtifactStore,
        *,
        max_active: int = 2,
        max_pending: int = 32,
        resolver: Resolver | None = None,
        transport: StreamTransport | None = None,
    ):
        self.repository = repository
        self.store = store
        self.active = asyncio.Semaphore(max_active)
        self.max_pending = max_pending
        self.tasks: dict[str, asyncio.Task[None]] = {}
        self.scheduler = Scheduler()
        self.resolver = resolver
        self.transport = transport
        self.closed = False

    def submit(
        self, seeds: Sequence[str], policy: CrawlPolicy, credentials: Credentials | None = None
    ) -> CrawlJob:
        if self.closed or len(self.tasks) >= self.max_pending:
            raise AcquisitionError("job_admission_limit")
        if not 1 <= len(seeds) <= 16:
            raise AcquisitionError("seed_limit")
        normalized = [
            normalize(
                seed,
                query_mode=policy.query_mode,
                collapse_slashes=policy.collapse_slashes,
                max_length=policy.max_url_length,
            )
            for seed in seeds
        ]
        job = CrawlJob(seed_urls=[display_url(seed) for seed in normalized], policy=policy)
        self.repository.save_job(job)
        task = asyncio.create_task(self._execute(job, normalized, credentials))
        self.tasks[job.job_id] = task
        task.add_done_callback(lambda _task: self.tasks.pop(job.job_id, None))
        return job

    async def _execute(
        self, job: CrawlJob, seeds: Sequence[str], credentials: Credentials | None
    ) -> None:
        try:
            async with self.active:
                job.status = JobStatus.RUNNING
                job.started_at = now()
                self.repository.save_job(job)
                engine = CrawlEngine(
                    job,
                    seeds,
                    self.repository,
                    self.store,
                    self.scheduler,
                    self.resolver,
                    self.transport,
                    credentials,
                )
                async with asyncio.timeout(job.policy.job_timeout):
                    await engine.run()
                job.status = JobStatus.COMPLETED
        except asyncio.CancelledError:
            job.status = JobStatus.CANCELLED
        except TimeoutError:
            job.status = JobStatus.FAILED
            job.error_summary = "job_timeout"
        except AcquisitionError as exc:
            job.status = JobStatus.FAILED
            job.error_summary = exc.code
        except Exception:  # noqa: BLE001 - stable payload-free diagnostic at job boundary
            # Arbitrary parser/network/library messages may embed source
            # tokens. Only a stable code is published/logged.
            job.status = JobStatus.FAILED
            job.error_summary = "internal_error"
        finally:
            job.finished_at = now()
            self.repository.save_job(job)
            LOGGER.info(
                json.dumps(
                    {
                        "event": "job_finished",
                        "job_id": job.job_id,
                        "status": job.status,
                        "metrics": job.metrics,
                        "error_code": job.error_summary,
                    }
                )
            )

    async def wait(self, job_id: str) -> CrawlJob:
        task = self.tasks.get(job_id)
        if task is not None:
            await task
        return self.repository.get_job(job_id)

    async def cancel(self, job_id: str) -> CrawlJob:
        task = self.tasks.get(job_id)
        if task is not None:
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)
        job = self.repository.get_job(job_id)
        # A task cancelled before its first turn never reaches its finally.
        if job.status in (JobStatus.QUEUED, JobStatus.RUNNING):
            job.status = JobStatus.CANCELLED
            job.finished_at = now()
            self.repository.save_job(job)
        return job

    async def close(self) -> None:
        self.closed = True
        for job_id in list(self.tasks):
            await self.cancel(job_id)
