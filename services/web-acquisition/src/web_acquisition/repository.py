"""Persistence port. Crawl algorithms never contain SQL."""

from __future__ import annotations

import os
import sqlite3
import stat
from pathlib import Path
from typing import Protocol

from .models import Artifact, CrawlJob, Discovery, FetchAttempt, Resource
from .storage import private_directory


class Repository(Protocol):
    def save_job(self, job: CrawlJob) -> None: ...
    def get_job(self, job_id: str) -> CrawlJob: ...
    def save_resource(self, resource: Resource) -> None: ...
    def save_discovery(self, discovery: Discovery) -> None: ...
    def save_attempt(self, attempt: FetchAttempt) -> None: ...
    def publish(self, artifact: Artifact, resource: Resource) -> None: ...
    def resources(self, job_id: str, offset: int = 0, limit: int = 100) -> list[Resource]: ...
    def discoveries(self, job_id: str, offset: int = 0, limit: int = 100) -> list[Discovery]: ...
    def attempts(self, job_id: str, offset: int = 0, limit: int = 100) -> list[FetchAttempt]: ...
    def artifacts(self, job_id: str, offset: int = 0, limit: int = 100) -> list[Artifact]: ...


class SQLiteRepository:
    """Single-process local implementation; service-owned directory required.

    Cross-process worker leasing/migrations/PostgreSQL are separate adapters,
    not assumptions embedded in the engine.
    """

    def __init__(self, path: Path):
        fd = private_directory(path.parent)
        try:
            try:
                existing = os.stat(path.name, dir_fd=fd, follow_symlinks=False)
                if not stat.S_ISREG(existing.st_mode) or existing.st_nlink != 1:
                    raise ValueError("unsafe_database_path")
            except FileNotFoundError:
                descriptor = os.open(
                    path.name,
                    os.O_CREAT | os.O_EXCL | os.O_WRONLY | os.O_NOFOLLOW,
                    0o600,
                    dir_fd=fd,
                )
                os.close(descriptor)
            if stat.S_IMODE(os.fstat(fd).st_mode) & 0o077:
                raise ValueError("database directory must be private (0700)")
        finally:
            os.close(fd)
        self.connection = sqlite3.connect(path, timeout=5)
        self.connection.execute("PRAGMA foreign_keys=ON")
        self.connection.execute("PRAGMA journal_mode=WAL")
        self.connection.executescript("""
            CREATE TABLE IF NOT EXISTS jobs(id TEXT PRIMARY KEY, payload TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS resources(
                id TEXT PRIMARY KEY, job TEXT REFERENCES jobs(id), key TEXT NOT NULL,
                payload TEXT NOT NULL, UNIQUE(job,key));
            CREATE TABLE IF NOT EXISTS discoveries(
                id TEXT PRIMARY KEY, job TEXT REFERENCES jobs(id), payload TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS attempts(
                id TEXT PRIMARY KEY, job TEXT REFERENCES jobs(id), payload TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS artifacts(id TEXT PRIMARY KEY, payload TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS acquisitions(
                resource TEXT PRIMARY KEY REFERENCES resources(id), artifact TEXT REFERENCES artifacts(id));
            CREATE INDEX IF NOT EXISTS resources_job ON resources(job);
            CREATE INDEX IF NOT EXISTS discoveries_job ON discoveries(job);
            CREATE INDEX IF NOT EXISTS attempts_job ON attempts(job);
        """)
        # Execution URLs/secrets are deliberately not persisted. Do not
        # pretend a crashed process-local job can transparently resume.
        for row in self.connection.execute("SELECT payload FROM jobs").fetchall():
            job = CrawlJob.model_validate_json(row[0])
            if job.status in ("queued", "running"):
                from .models import JobStatus, now

                job.status = JobStatus.FAILED
                job.error_summary = "worker_interrupted"
                job.finished_at = now()
                self.save_job(job)

    def save_job(self, job: CrawlJob) -> None:
        with self.connection:
            self.connection.execute(
                "INSERT INTO jobs VALUES (?,?) ON CONFLICT(id) DO UPDATE SET payload=excluded.payload",
                (job.job_id, job.model_dump_json()),
            )

    def get_job(self, job_id: str) -> CrawlJob:
        row = self.connection.execute("SELECT payload FROM jobs WHERE id=?", (job_id,)).fetchone()
        if row is None:
            raise KeyError(job_id)
        return CrawlJob.model_validate_json(row[0])

    def save_resource(self, resource: Resource) -> None:
        with self.connection:
            self.connection.execute(
                "INSERT INTO resources VALUES (?,?,?,?) ON CONFLICT(id) DO UPDATE SET payload=excluded.payload",
                (
                    resource.resource_id,
                    resource.job_id,
                    resource.url_key,
                    resource.model_dump_json(),
                ),
            )

    def save_discovery(self, discovery: Discovery) -> None:
        with self.connection:
            self.connection.execute(
                "INSERT INTO discoveries VALUES (?,?,?)",
                (discovery.discovery_id, discovery.job_id, discovery.model_dump_json()),
            )

    def save_attempt(self, attempt: FetchAttempt) -> None:
        with self.connection:
            self.connection.execute(
                "INSERT INTO attempts VALUES (?,?,?) ON CONFLICT(id) DO UPDATE SET payload=excluded.payload",
                (attempt.attempt_id, attempt.job_id, attempt.model_dump_json()),
            )

    def publish(self, artifact: Artifact, resource: Resource) -> None:
        # Blob publication precedes this atomic metadata transaction. A
        # crash may leave a complete unreferenced blob, never a partial one.
        with self.connection:
            self.connection.execute(
                "INSERT INTO artifacts VALUES (?,?) ON CONFLICT(id) DO NOTHING",
                (artifact.artifact_id, artifact.model_dump_json()),
            )
            self.connection.execute(
                "UPDATE resources SET payload=? WHERE id=?",
                (resource.model_dump_json(), resource.resource_id),
            )
            self.connection.execute(
                "INSERT INTO acquisitions VALUES (?,?)",
                (resource.resource_id, artifact.artifact_id),
            )

    def resources(self, job_id: str, offset: int = 0, limit: int = 100) -> list[Resource]:
        rows = self.connection.execute(
            "SELECT payload FROM resources WHERE job=? ORDER BY rowid LIMIT ? OFFSET ?",
            (job_id, min(limit, 1000), offset),
        )
        return [Resource.model_validate_json(row[0]) for row in rows]

    def discoveries(self, job_id: str, offset: int = 0, limit: int = 100) -> list[Discovery]:
        rows = self.connection.execute(
            "SELECT payload FROM discoveries WHERE job=? ORDER BY rowid LIMIT ? OFFSET ?",
            (job_id, min(limit, 1000), offset),
        )
        return [Discovery.model_validate_json(row[0]) for row in rows]

    def attempts(self, job_id: str, offset: int = 0, limit: int = 100) -> list[FetchAttempt]:
        rows = self.connection.execute(
            "SELECT payload FROM attempts WHERE job=? ORDER BY rowid LIMIT ? OFFSET ?",
            (job_id, min(limit, 1000), offset),
        )
        return [FetchAttempt.model_validate_json(row[0]) for row in rows]

    def artifacts(self, job_id: str, offset: int = 0, limit: int = 100) -> list[Artifact]:
        rows = self.connection.execute(
            "SELECT DISTINCT a.payload FROM artifacts a JOIN acquisitions x ON x.artifact=a.id JOIN resources r ON r.id=x.resource WHERE r.job=? ORDER BY a.id LIMIT ? OFFSET ?",
            (job_id, min(limit, 1000), offset),
        )
        return [Artifact.model_validate_json(row[0]) for row in rows]

    def close(self) -> None:
        self.connection.close()
