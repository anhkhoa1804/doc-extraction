"""Stage H (part 2) / Step I — assembly & export.

Takes whatever a route produced (native office/PDF elements, or scanned-page
layout+OCR+table results) as a list of `Page`s, computes reading order for
any page that doesn't already have one, wraps everything in the canonical
`Document`, and writes both machine-readable JSON and a human-readable
Markdown export.
"""
from __future__ import annotations

from pathlib import Path

from doc_extraction.schemas.document import Document, RunMetadata
from doc_extraction.schemas.page import Page
from doc_extraction.stages.reading_order import ORDER_STRATEGY, compute_reading_order
from doc_extraction.utils.logging import StageLogger, noop_stage
from doc_extraction.utils.serde import write_json


def assemble_document(
    document_id: str,
    metadata: RunMetadata,
    pages: list[Page],
    output_dir: Path,
    logger: StageLogger | None = None,
) -> Document:
    assembled_dir = output_dir / "assembled"
    final_dir = output_dir / "final"

    ctx_manager = logger.stage("reading_order", ORDER_STRATEGY) if logger else noop_stage()
    with ctx_manager as ctx:
        total_ordered = 0
        for page in pages:
            if not page.reading_order:
                # Pass the real page width so column detection is scaled to
                # the page rather than to the extent of the elements found.
                page.reading_order = compute_reading_order(
                    page.elements, page_width=page.width or None
                )
            total_ordered += len(page.reading_order)
        ctx.metrics = {
            "num_pages": len(pages),
            "num_elements_ordered": total_ordered,
            "strategy": ORDER_STRATEGY,
        }

    document = Document(document_id=document_id, metadata=metadata, pages=pages)

    ctx_manager = logger.stage("assemble", "doc_extraction") if logger else noop_stage()
    with ctx_manager as ctx:
        for page in pages:
            write_json(assembled_dir / f"page-{page.index + 1:03d}.json", page)

        doc_json_path = final_dir / "document.json"
        doc_md_path = final_dir / "document.md"
        write_json(doc_json_path, document)
        doc_md_path.parent.mkdir(parents=True, exist_ok=True)
        doc_md_path.write_text(document.to_markdown(), encoding="utf-8")

        ctx.output_path = str(doc_json_path)
        ctx.metrics = {
            "num_pages": len(pages),
            "num_elements": sum(len(p.elements) for p in pages),
            "num_tables": sum(len(p.tables) for p in pages),
        }

    write_json(output_dir / "metadata.json", metadata)

    return document
