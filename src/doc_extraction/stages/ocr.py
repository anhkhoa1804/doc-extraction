"""Stage F — OCR, run only for pages that actually need it (scanned PDFs,
raw images). Delegates to a configured `OCRBackend` (default: Docling's
bundled OCR engine).
"""
from __future__ import annotations

from pathlib import Path

from doc_extraction.pipelines.base import BackendUnavailableError, OCRBackend, OCRResult, PageInput
from doc_extraction.utils.logging import StageLogger, noop_stage
from doc_extraction.utils.serde import write_json


def run_ocr(
    page: PageInput,
    backend: OCRBackend,
    output_dir: Path,
    logger: StageLogger | None = None,
) -> OCRResult:
    if not backend.is_available():
        raise BackendUnavailableError(
            f"OCR backend '{backend.name}' is not available in this environment "
            f"— see docs/backends.md"
        )
    output_dir.mkdir(parents=True, exist_ok=True)
    ctx_manager = logger.stage("ocr", backend.name, page=page.page_index) if logger else noop_stage()
    with ctx_manager as ctx:
        result = backend.recognize(page)
        out_path = output_dir / f"page-{page.page_index + 1:03d}.json"
        write_json(out_path, result)
        ctx.output_path = str(out_path)
        ctx.warnings = result.warnings
        confidences = [t.confidence for t in result.tokens if t.confidence is not None]
        ctx.metrics = {
            "num_tokens": len(result.tokens),
            "mean_confidence": (sum(confidences) / len(confidences)) if confidences else None,
        }
    return result
