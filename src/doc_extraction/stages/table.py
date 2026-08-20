"""Stage G — table detection / structure recognition, run separately from
general layout so table backends (e.g. Table Transformer) can be swapped or
compared independently of whichever backend handled layout/OCR.
"""
from __future__ import annotations

from pathlib import Path

from doc_extraction.pipelines.base import BackendUnavailableError, PageInput, Region, TableBackend, TableResult
from doc_extraction.utils.logging import StageLogger, noop_stage
from doc_extraction.utils.serde import write_json


def run_table(
    page: PageInput,
    regions: list[Region],
    backend: TableBackend,
    output_dir: Path,
    logger: StageLogger | None = None,
) -> TableResult:
    if not backend.is_available():
        raise BackendUnavailableError(
            f"table backend '{backend.name}' is not available in this environment "
            f"— see docs/backends.md"
        )
    output_dir.mkdir(parents=True, exist_ok=True)
    ctx_manager = logger.stage("table", backend.name, page=page.page_index) if logger else noop_stage()
    with ctx_manager as ctx:
        result = backend.extract(page, regions)
        out_path = output_dir / f"page-{page.page_index + 1:03d}.json"
        write_json(out_path, result)
        ctx.output_path = str(out_path)
        ctx.warnings = result.warnings
        ctx.metrics = {
            "num_tables": len(result.tables),
            "num_cells": sum(len(t.cells) for t in result.tables),
        }
    return result
