"""Resource limits for one extraction run.

The guard is deliberately local to a run.  It protects work that this
process owns (input preflight, container inspection, page iteration and
raster allocation) without pretending that a library model call can always
be interrupted safely in-process.
"""
from __future__ import annotations

import stat
import time
import zipfile
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass, field
from pathlib import Path

import pymupdf
from PIL import Image
from pydantic import BaseModel, ConfigDict, Field

MiB = 1024 * 1024


class ExtractionLimits(BaseModel):
    """Safe default limits for one source document.

    Values are deployment configuration, not parser heuristics.  ``None`` is
    deliberately not accepted: an operator that needs a larger workload must
    explicitly provide a larger positive value rather than accidentally
    disabling a guard.
    """

    model_config = ConfigDict(frozen=True)

    max_input_bytes: int = Field(default=100 * MiB, gt=0)
    max_document_units: int = Field(default=100, gt=0)
    max_runtime_seconds: float = Field(default=300.0, gt=0)
    max_temp_bytes: int = Field(default=512 * MiB, gt=0)
    max_archive_members: int = Field(default=10_000, gt=0)
    max_archive_uncompressed_bytes: int = Field(default=250 * MiB, gt=0)
    max_archive_compression_ratio: float = Field(default=100.0, gt=1.0)
    max_image_pixels: int = Field(default=40_000_000, gt=0)


class ResourceLimitExceeded(RuntimeError):
    """A deterministic, structured hard resource-policy violation."""

    def __init__(self, limit_name: str, limit: float, actual: float, detail: str) -> None:
        self.limit_name = limit_name
        self.limit = limit
        self.actual = actual
        self.detail = detail
        super().__init__(f"resource limit {limit_name} exceeded: {actual} > {limit} ({detail})")

    def as_dict(self) -> dict[str, int | float | str]:
        return {
            "limit_name": self.limit_name,
            "limit": self.limit,
            "actual": self.actual,
            "detail": self.detail,
        }


@dataclass
class ResourceGuard:
    """Cooperative run budget shared by all pipeline stages for one input."""

    limits: ExtractionLimits
    clock: Callable[[], float] = time.monotonic
    started_at: float = field(init=False)
    _reserved_temp_bytes: int = field(default=0, init=False)

    def __post_init__(self) -> None:
        self.started_at = self.clock()

    def check_runtime(self, boundary: str) -> None:
        elapsed = self.clock() - self.started_at
        if elapsed > self.limits.max_runtime_seconds:
            raise ResourceLimitExceeded(
                "max_runtime_seconds",
                self.limits.max_runtime_seconds,
                elapsed,
                f"cooperative deadline reached at {boundary}",
            )

    def remaining_runtime_seconds(self) -> float:
        return max(0.0, self.limits.max_runtime_seconds - (self.clock() - self.started_at))

    def reserve_raster(self, width: int, height: int, boundary: str) -> None:
        pixels = width * height
        if pixels > self.limits.max_image_pixels:
            raise ResourceLimitExceeded(
                "max_image_pixels", self.limits.max_image_pixels, pixels, f"{boundary}: {width}x{height}"
            )
        # PNG serialization cannot exceed a four-byte raster plus its modest
        # line/metadata overhead for the RGB/RGBA images produced here.  A
        # one-MiB margin makes the reservation conservative before disk write.
        reservation = pixels * 4 + MiB
        projected = self._reserved_temp_bytes + reservation
        if projected > self.limits.max_temp_bytes:
            raise ResourceLimitExceeded(
                "max_temp_bytes", self.limits.max_temp_bytes, projected, f"{boundary}: raster reservation"
            )
        self._reserved_temp_bytes = projected


_ACTIVE_GUARD: ContextVar[ResourceGuard | None] = ContextVar("doc_extraction_resource_guard", default=None)


@contextmanager
def active_resource_guard(guard: ResourceGuard) -> Iterator[None]:
    """Expose the remaining deadline to subprocess-backed backends only."""
    token = _ACTIVE_GUARD.set(guard)
    try:
        yield
    finally:
        _ACTIVE_GUARD.reset(token)


def current_subprocess_timeout() -> float | None:
    """Return a positive timeout for a child process, if a run is active."""
    guard = _ACTIVE_GUARD.get()
    if guard is None:
        return None
    guard.check_runtime("before subprocess invocation")
    return guard.remaining_runtime_seconds()


def _is_unsafe_archive_member(info: zipfile.ZipInfo) -> bool:
    name = info.filename.replace("\\", "/")
    parts = [part for part in name.split("/") if part]
    mode = info.external_attr >> 16
    return name.startswith("/") or ".." in parts or stat.S_ISLNK(mode)


def _check_archive(path: Path, limits: ExtractionLimits) -> set[str]:
    with zipfile.ZipFile(path) as archive:
        names: set[str] = set()
        total_uncompressed = 0
        for member_count, info in enumerate(archive.infolist(), start=1):
            if member_count > limits.max_archive_members:
                raise ResourceLimitExceeded(
                    "max_archive_members", limits.max_archive_members, member_count, "ZIP central directory"
                )
            if _is_unsafe_archive_member(info):
                raise ResourceLimitExceeded("archive_member_path", 0, 1, f"unsafe ZIP member: {info.filename!r}")
            total_uncompressed += info.file_size
            if total_uncompressed > limits.max_archive_uncompressed_bytes:
                raise ResourceLimitExceeded(
                    "max_archive_uncompressed_bytes",
                    limits.max_archive_uncompressed_bytes,
                    total_uncompressed,
                    "ZIP declared uncompressed size",
                )
            if info.file_size and info.compress_size:
                ratio = info.file_size / info.compress_size
                if ratio > limits.max_archive_compression_ratio:
                    raise ResourceLimitExceeded(
                        "max_archive_compression_ratio",
                        limits.max_archive_compression_ratio,
                        ratio,
                        f"ZIP member {info.filename!r}",
                    )
            names.add(info.filename)
        return names


def _count_ooxml_units(names: set[str]) -> int:
    if "word/document.xml" in names:
        return 1
    if "xl/workbook.xml" in names:
        return len([name for name in names if name.startswith("xl/worksheets/") and name.endswith(".xml")])
    if "ppt/presentation.xml" in names:
        return len([name for name in names if name.startswith("ppt/slides/slide") and name.endswith(".xml")])
    return 0


def preflight_input(path: Path, limits: ExtractionLimits, guard: ResourceGuard) -> None:
    """Reject oversized/container-bomb inputs before route or parser work."""
    if not path.is_file():
        raise ValueError(f"input is not a regular file: {path}")
    size = path.stat().st_size
    if size > limits.max_input_bytes:
        raise ResourceLimitExceeded("max_input_bytes", limits.max_input_bytes, size, "input file size")
    guard.check_runtime("input preflight")

    with path.open("rb") as source:
        header = source.read(8)
    if header.startswith(b"%PDF"):
        document = pymupdf.open(path)
        try:
            units = document.page_count
        finally:
            document.close()
    elif header[:2] == b"PK":
        try:
            units = _count_ooxml_units(_check_archive(path, limits))
        except zipfile.BadZipFile as exc:
            raise ValueError(f"invalid ZIP container: {path.name}") from exc
    else:
        units = 0
        try:
            with Image.open(path) as image:
                guard.reserve_raster(image.width, image.height, "input image")
                units = 1
        except (Image.UnidentifiedImageError, OSError):
            # The dispatcher gives the format-specific unsupported/malformed
            # error later.  Do not reinterpret arbitrary files as images.
            pass

    if units > limits.max_document_units:
        raise ResourceLimitExceeded(
            "max_document_units", limits.max_document_units, units, "PDF pages or OOXML logical units"
        )
    guard.check_runtime("input preflight completion")
