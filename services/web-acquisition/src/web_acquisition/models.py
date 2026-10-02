"""Internal acquisition models, NOT an external KP/CDOI contract."""

from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum
from typing import Literal
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field


def now() -> str:
    return datetime.now(UTC).isoformat()


def identity() -> str:
    return uuid4().hex


class Model(BaseModel):
    model_config = ConfigDict(extra="forbid", validate_assignment=True, allow_inf_nan=False)


class CrawlPolicy(Model):
    model_config = ConfigDict(frozen=True, extra="forbid", allow_inf_nan=False)
    version: Literal["acquisition-policy/1"] = "acquisition-policy/1"
    allowed_schemes: tuple[Literal["http", "https"], ...] = ("https", "http")
    allowed_hosts: tuple[str, ...] = ()
    allowed_domains: tuple[str, ...] = ()
    include_subdomains: bool = False
    same_origin: bool = True
    allowed_path_prefixes: tuple[str, ...] = ()
    denied_path_globs: tuple[str, ...] = ()
    allowed_content_types: tuple[str, ...] = ()
    query_mode: Literal["preserve", "sort", "drop"] = "preserve"
    collapse_slashes: bool = False
    max_depth: int = Field(default=2, ge=0, le=20)
    max_pages: int = Field(default=100, ge=1, le=1000)
    max_response_bytes: int = Field(default=16 * 1024**2, ge=1, le=64 * 1024**2)
    max_total_bytes: int = Field(default=256 * 1024**2, ge=1, le=1024**3)
    max_artifacts: int = Field(default=100, ge=1, le=1000)
    concurrency: int = Field(default=4, ge=1, le=16)
    per_host_concurrency: int = Field(default=1, ge=1, le=4)
    host_interval: float = Field(default=1.0, ge=0, le=60)
    request_timeout: float = Field(default=30.0, gt=0, le=120)
    connect_timeout: float = Field(default=5.0, gt=0, le=30)
    read_timeout: float = Field(default=10.0, gt=0, le=60)
    job_timeout: float = Field(default=1800.0, gt=0, le=3600)
    max_redirects: int = Field(default=5, ge=0, le=10)
    max_retries: int = Field(default=2, ge=0, le=3)
    max_url_length: int = Field(default=4096, ge=64, le=8192)
    max_headers_size: int = Field(default=32768, ge=128, le=65536)
    max_html_parse_size: int = Field(default=1024**2, ge=1, le=4 * 1024**2)
    max_links_per_page: int = Field(default=1000, ge=1, le=5000)
    max_discoveries: int = Field(default=10000, ge=1, le=50000)
    robots_mode: Literal["obey", "ignore"] = "obey"
    robots_failure: Literal["deny", "allow"] = "deny"
    robots_timeout: float = Field(default=5.0, gt=0, le=30)
    user_agent: Literal["WebAcquisition/0.1"] = "WebAcquisition/0.1"


class JobStatus(StrEnum):
    QUEUED = "queued"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class CrawlJob(Model):
    job_id: str = Field(default_factory=identity)
    created_at: str = Field(default_factory=now)
    started_at: str | None = None
    finished_at: str | None = None
    status: JobStatus = JobStatus.QUEUED
    seed_urls: list[str]
    policy: CrawlPolicy
    metrics: dict[str, int] = Field(default_factory=dict)
    error_summary: str | None = None


class Resource(Model):
    resource_id: str = Field(default_factory=identity)
    job_id: str
    url_key: str
    source_url: str
    canonical_url: str
    parent_resource_id: str | None = None
    parent_url: str | None = None
    depth: int
    discovery_method: str
    status: str = "accepted"
    rejection_reason: str | None = None
    http_status: int | None = None
    final_url: str | None = None
    advertised_canonical_url: str | None = None
    content_type: str | None = None
    content_length: int | None = None
    content_encoding: str | None = None
    warnings: list[str] = Field(default_factory=list)
    artifact_id: str | None = None
    sha256: str | None = None
    first_seen_at: str = Field(default_factory=now)
    last_seen_at: str = Field(default_factory=now)


class Discovery(Model):
    discovery_id: str = Field(default_factory=identity)
    job_id: str
    resource_id: str | None
    source_url: str
    parent_resource_id: str | None
    depth: int
    method: str
    decision: str
    reason: str | None = None


class FetchAttempt(Model):
    attempt_id: str = Field(default_factory=identity)
    job_id: str
    resource_id: str
    purpose: Literal["resource", "robots"] = "resource"
    requested_url: str
    url_key: str
    retry: int
    redirect_hop: int
    started_at: str = Field(default_factory=now)
    finished_at: str | None = None
    status: str = "started"
    http_status: int | None = None
    resolved_addresses: list[str] = Field(default_factory=list)
    bytes_received: int = 0
    error_code: str | None = None


class Artifact(Model):
    model_config = ConfigDict(frozen=True, extra="forbid")
    artifact_id: str
    sha256: str
    storage_uri: str
    size_bytes: int
    created_at: str = Field(default_factory=now)


class AcquisitionError(Exception):
    """Stable, non-payload diagnostic code; never persist arbitrary exceptions."""

    def __init__(self, code: str):
        self.code = code
        super().__init__(code)


class JobBudgetExceeded(AcquisitionError):
    pass
