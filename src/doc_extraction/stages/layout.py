"""Stage E — layout analysis.

Delegates to a configured `LayoutBackend` (default: Docling's layout model,
see backends/docling_backend.py). We deliberately do not hand-roll a layout
detector here — reusing a strong existing model instead of reimplementing
one is the whole premise of this project (see README).
"""
from __future__ import annotations

from pathlib import Path

from doc_extraction.pipelines.base import BackendUnavailableError, LayoutBackend, LayoutResult, PageInput
from doc_extraction.utils.logging import StageLogger, noop_stage
from doc_extraction.utils.serde import write_json


def run_layout(
    page: PageInput,
    backend: LayoutBackend,
    output_dir: Path,
    logger: StageLogger | None = None,
) -> LayoutResult:
    if not backend.is_available():
        raise BackendUnavailableError(
            f"layout backend '{backend.name}' is not available in this environment "
            f"— see docs/backends.md"
        )
    output_dir.mkdir(parents=True, exist_ok=True)
    ctx_manager = logger.stage("layout", backend.name, page=page.page_index) if logger else noop_stage()
    with ctx_manager as ctx:
        result = backend.analyze(page)
        out_path = output_dir / f"page-{page.page_index + 1:03d}.json"
        write_json(out_path, result)
        ctx.output_path = str(out_path)
        ctx.warnings = result.warnings
        ctx.metrics = {"num_regions": len(result.regions)}
    return result
