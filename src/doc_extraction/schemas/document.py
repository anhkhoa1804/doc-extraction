from __future__ import annotations

from enum import Enum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, model_validator

from doc_extraction.schemas.element import ElementType
from doc_extraction.schemas.page import Page
from doc_extraction.schemas.version import SCHEMA_VERSION


class RunStatus(str, Enum):
    """Outcome of one extraction run at the canonical-document boundary."""

    SUCCESS = "success"
    SUCCESS_WITH_WARNINGS = "success_with_warnings"
    FAILED = "failed"


class RunMetadata(BaseModel):
    """Everything needed to reproduce/audit a single extraction run.

    Written verbatim to outputs/<document_id>/metadata.json.
    """

    model_config = ConfigDict(extra="forbid")

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
    # A successful document is never represented by an empty error list
    # alone: consumers can distinguish an unqualified result from a result
    # whose canonical content is valid but carries degradation warnings.
    status: RunStatus = RunStatus.SUCCESS
    errors: list[str] = Field(default_factory=list)
    # Present only for a hard resource-policy failure.  The stable keys make
    # the cause machine-readable without turning ordinary parser errors into
    # a guessed taxonomy.
    resource_violation: dict[str, int | float | str] | None = None
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
    model_config = ConfigDict(extra="forbid")

    schema_version: str = SCHEMA_VERSION
    document_id: str
    metadata: RunMetadata
    pages: list[Page] = Field(default_factory=list)
    assets: dict[str, str] = Field(default_factory=dict)  # name -> path, relative to output dir

    @model_validator(mode="after")
    def validate_public_document_boundary(self) -> Document:
        if self.schema_version != SCHEMA_VERSION:
            raise ValueError(
                f"unsupported canonical Document schema version {self.schema_version!r}; "
                f"this runtime supports {SCHEMA_VERSION!r}"
            )
        if self.metadata.status is RunStatus.FAILED:
            raise ValueError("failed extraction metadata cannot be published as a canonical Document")
        for position, page in enumerate(self.pages):
            if page.index != position:
                raise ValueError("Page.index must equal its zero-based position in Document.pages")
        return self

    def to_markdown(self) -> str:
        """Human-readable Markdown export for quick inspection (not a lossless format)."""
        lines: list[str] = [f"# {self.metadata.input_filename}", ""]
        for page in self.pages:
            lines.append(f"## Page {page.index + 1}")
            ordered_elements = page.elements_in_reading_order(require_complete=False)
            for element in ordered_elements:
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
            omitted_count = len(page.elements) - len(ordered_elements)
            if omitted_count:
                lines.append(
                    f"> {omitted_count} element(s) omitted from Markdown: no explicit reading-order entry."
                )
                lines.append("")
        return "\n".join(lines)
