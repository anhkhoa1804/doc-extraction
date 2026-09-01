from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from doc_extraction.schemas.element import ElementType
from doc_extraction.schemas.page import Page
from doc_extraction.schemas.version import SCHEMA_VERSION


class RunMetadata(BaseModel):
    """Everything needed to reproduce/audit a single extraction run.

    Written verbatim to outputs/<document_id>/metadata.json.
    """

    input_filename: str
    input_path: str
    file_hash_sha256: str
    file_type: str  # e.g. "pdf", "docx", "xlsx", "image/png"
    route: str  # native_office | digital_pdf | scanned_pdf | image | unknown
    pipeline: str  # e.g. "baseline", "docling", "mineru", "paddleocr", "vlm"
    backend: str  # primary backend name used for this run
    model_versions: dict[str, str] = Field(default_factory=dict)
    config_snapshot: dict[str, Any] = Field(default_factory=dict)
    timestamp: str  # ISO 8601 UTC
    runtime_seconds: float | None = None
    device: str = "cpu"
    errors: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    # Route-decision evidence (ingest/dispatcher.py): why this file took the
    # route it did, including per-page text-quality signals for PDFs.
    route_reason: str | None = None
    text_profile: dict[str, Any] | None = None
    # How `device` was arrived at. Populated when config.device was "auto":
    # records the GPU state observed at selection time and the rule that
    # fired, so a result's device is explainable months later rather than
    # being an unexplained "cuda" or "cpu". None for an explicit device.
    device_decision: dict[str, Any] | None = None


class Document(BaseModel):
    # Version of the canonical IR this document was serialized with. See
    # schemas/version.py for the change history.
    schema_version: str = SCHEMA_VERSION
    document_id: str
    metadata: RunMetadata
    pages: list[Page] = Field(default_factory=list)
    assets: dict[str, str] = Field(default_factory=dict)  # name -> path, relative to output dir

    def to_markdown(self) -> str:
        """Human-readable Markdown export for quick inspection (not a lossless format)."""
        lines: list[str] = [f"# {self.metadata.input_filename}", ""]
        for page in self.pages:
            lines.append(f"## Page {page.index + 1}")
            order = page.reading_order or [e.id for e in page.elements]
            for element_id in order:
                element = page.element_by_id(element_id)
                if element is None:
                    continue
                if element.type == ElementType.TABLE and element.table_id:
                    table = page.table_by_id(element.table_id)
                    if table is not None:
                        lines.append(table.to_markdown())
                        lines.append("")
                        continue
                if element.type == ElementType.HEADING:
                    depth = min(max(element.level or 1, 1), 6)
                    lines.append(f"{'#' * (depth + 2)} {element.text or ''}")
                elif element.type == ElementType.LIST_ITEM:
                    lines.append(f"- {element.text or ''}")
                elif element.type == ElementType.IMAGE:
                    lines.append(f"![{element.source_id or 'image'}]({element.source_id or ''})")
                else:
                    if element.text:
                        lines.append(element.text)
                lines.append("")
        return "\n".join(lines)
