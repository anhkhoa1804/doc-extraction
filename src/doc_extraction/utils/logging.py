"""Structured, append-only per-document stage logging.

Every pipeline stage should wrap its work in `StageLogger.stage(...)`. Each
call appends one JSON record to outputs/<document_id>/logs/pipeline.jsonl
with document/page/stage/backend/runtime/device/status/warnings/output_path,
and — when supplied — lightweight metrics (region counts, OCR token counts,
table cell counts, confidence, image resolution, ...). Exceptions are logged
as failures and always re-raised: this module never swallows an error.
"""
from __future__ import annotations

import json
import logging
import sys
import time
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


@contextmanager
def noop_stage() -> Iterator["StageContext"]:
    """Drop-in replacement for `StageLogger.stage(...)` when no logger is
    available, so call sites never need an `if logger` branch."""
    yield StageContext()


@dataclass
class StageContext:
    """Mutable handle yielded by `StageLogger.stage(...)`.

    Stage implementations populate this while they work; it's flushed to the
    log record when the `with` block exits (success or failure).
    """

    warnings: list[str] = field(default_factory=list)
    metrics: dict[str, Any] = field(default_factory=dict)
    output_path: str | None = None


class StageLogger:
    """Per-document stage logger.

    `device` is a property of the *run*, not of an individual stage call, so
    it is set once here and stamped onto every record. It used to default to
    "cpu" on each `log_event`/`stage` call with no call site ever passing it,
    which meant a full CUDA run produced logs claiming `device: "cpu"` —
    silently wrong provenance in the pipeline's primary observability
    artifact. An explicit per-call `device=` still overrides, for the rare
    stage that genuinely runs somewhere else than the rest of the run.
    """

    def __init__(self, document_id: str, log_dir: Path, device: str = "cpu") -> None:
        self.document_id = document_id
        self.device = device
        self.log_dir = Path(log_dir)
        self.log_dir.mkdir(parents=True, exist_ok=True)
        self._jsonl_path = self.log_dir / "pipeline.jsonl"

        self._logger = logging.getLogger(f"doc_extraction.{document_id}")
        self._logger.setLevel(logging.INFO)
        self._logger.propagate = False
        if not self._logger.handlers:
            handler = logging.StreamHandler(sys.stderr)
            handler.setFormatter(
                logging.Formatter("%(asctime)s [%(levelname)s] %(message)s", "%H:%M:%S")
            )
            self._logger.addHandler(handler)

    def log_event(
        self,
        *,
        stage: str,
        backend: str,
        status: str,
        runtime_seconds: float | None = None,
        device: str | None = None,
        page: int | None = None,
        output_path: str | None = None,
        warnings: list[str] | None = None,
        error: str | None = None,
        metrics: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        record = {
            "timestamp": _now_iso(),
            "document": self.document_id,
            "page": page,
            "stage": stage,
            "backend": backend,
            "status": status,
            "runtime_seconds": runtime_seconds,
            "device": device if device is not None else self.device,
            "output_path": output_path,
            "warnings": warnings or [],
            "error": error,
            "metrics": metrics or {},
        }
        with open(self._jsonl_path, "a", encoding="utf-8") as f:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")

        level = logging.ERROR if status == "failure" else logging.INFO
        page_str = f" page={page}" if page is not None else ""
        self._logger.log(
            level,
            f"[{self.document_id}] {stage} backend={backend}{page_str} "
            f"status={status} runtime={runtime_seconds}",
        )
        return record

    @contextmanager
    def stage(
        self, stage: str, backend: str, page: int | None = None, device: str | None = None
    ) -> Iterator[StageContext]:
        ctx = StageContext()
        start = time.perf_counter()
        try:
            yield ctx
        except Exception as exc:
            runtime = time.perf_counter() - start
            self.log_event(
                stage=stage,
                backend=backend,
                status="failure",
                runtime_seconds=runtime,
                device=device,
                page=page,
                output_path=ctx.output_path,
                warnings=ctx.warnings,
                error=f"{type(exc).__name__}: {exc}",
                metrics=ctx.metrics,
            )
            raise
        else:
            runtime = time.perf_counter() - start
            self.log_event(
                stage=stage,
                backend=backend,
                status="success",
                runtime_seconds=runtime,
                device=device,
                page=page,
                output_path=ctx.output_path,
                warnings=ctx.warnings,
                metrics=ctx.metrics,
            )
