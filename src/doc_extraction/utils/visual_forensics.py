"""Opt-in, bounded observations, NOT canonical extraction evidence.

None means unobserved. Component calls are not underlying model calls; in
particular Docling's OCR adapter projects an already cached conversion.
No source text, pixels, paths or arbitrary object reprs are kept. The metadata
timestamp is copied only to bind an artifact to the correct extraction run.
"""
from __future__ import annotations

import json
from collections import Counter
from collections.abc import Callable
from functools import wraps
from pathlib import Path
from typing import Any

from doc_extraction.utils.safe_io import write_text

MAX_PAGES = 100
MAX_REGIONS = 128
MAX_LABELS = 32
MAX_TOKENS = 4096
MAX_BYTES = 256 * 1024


def _observational(method: Callable[..., None]) -> Callable[..., None]:
    """Malformed optional observations must not change extraction errors."""
    @wraps(method)
    def wrapped(self: Any, *args: Any, **kwargs: Any) -> None:
        try:
            method(self, *args, **kwargs)
        except Exception:  # noqa: BLE001 - never replace the actual pipeline exception
            self.observation_failed = True
            if hasattr(self, "data"):
                self.data["observation_failed"] = True
    return wrapped


def safe_name(value: str) -> str:
    return "".join(c for c in value[:64] if c.isalnum() or c in "_-.+") or "unknown"


def label_counts(regions: list[Any]) -> dict[str, Any]:
    counts: Counter[str] = Counter()
    omitted = 0
    for region in regions:
        label = safe_name(region.label)
        if label not in counts and len(counts) >= MAX_LABELS:
            omitted += 1
        else:
            counts[label] += 1
    return {"counts": dict(sorted(counts.items())), "omitted_regions": omitted}


class VisualPageTrace:
    def __init__(self, index: int, width: int, height: int, route: str) -> None:
        self.data: dict[str, Any] = {
            "page_index": index,
            "route": safe_name(route),
            "input_dimensions": [width, height],
            # Opening the rendered image succeeded; this does not certify
            # raster fidelity or claim the upstream renderer was instrumented.
            "rendered_image_opened": True,
            "layout": {"component_calls": 0, "state": "not_reached", "regions": None, "labels": None},
            "ocr": {"component_calls": 0, "state": "not_reached", "projected_tokens": None,
                    "model_invocations": None, "target_regions": None, "raw_tokens": None,
                    "tokens_by_region": None},
            "formula": {"regions": None, "model_invocations": None, "text_results": None},
            "table": {"component_calls": 0, "state": "not_reached", "regions": None,
                      "tables": None, "text_cells": None, "backend_tables": None},
            "canonical": None,
            "serialization": None,
            "dependency": None,
        }

    @_observational
    def invoked(self, stage: str, backend: str) -> None:
        self.data[stage]["component_calls"] += 1
        self.data[stage]["state"] = "invoked"
        self.data[stage]["backend"] = safe_name(backend)

    @_observational
    def unavailable(self, stage: str) -> None:
        self.data[stage]["state"] = "backend_unavailable"

    @_observational
    def failed(self, stage: str, exc: Exception) -> None:
        self.data[stage]["state"] = "failed"
        self.data[stage]["exception_type"] = safe_name(type(exc).__name__)

    @_observational
    def layout_result(self, result: Any) -> None:
        self.data["layout"].update(state="returned", regions=len(result.regions),
                                    labels=label_counts(result.regions), warnings_count=len(result.warnings))
        self.data["formula"]["regions"] = sum(r.label.lower() == "formula" for r in result.regions)
        self.data["table"]["regions"] = sum(r.label.lower() == "table" for r in result.regions)

    @_observational
    def ocr_result(self, result: Any, regions: list[Any]) -> None:
        rows = []
        for index, region in enumerate(regions[:MAX_REGIONS]):
            box = region.bbox
            rows.append({"region_index": index, "label": safe_name(region.label), "tokens": sum(
                box.x0 <= (t.bbox.x0 + t.bbox.x1) / 2 <= box.x1
                and box.y0 <= (t.bbox.y0 + t.bbox.y1) / 2 <= box.y1
                for t in result.tokens[:MAX_TOKENS]
            )})
        self.data["ocr"].update(
            state="returned", projected_tokens=len(result.tokens), warnings_count=len(result.warnings),
            tokens_by_region=rows, region_counts_truncated=len(regions) > MAX_REGIONS,
            token_counts_truncated=len(result.tokens) > MAX_TOKENS,
            assignment="nonexclusive_token_center_containment",
        )

    def observe_dependency(self, backend: Any, page: Any) -> None:
        observer = getattr(backend, "visual_forensic_snapshot", None)
        if observer is None:
            return
        try:
            # Only the built-in observer's bounded aggregate structure is used.
            snapshot = observer(page)
            # Whitelist scalars; never persist arbitrary backend content,
            # paths or object reprs, even from an unexpected observer.
            allowed = {
                "ocr_enabled", "formula_enrichment_enabled", "languages_truncated",
                "public_items_examined", "public_items_with_text", "public_items_truncated",
                "public_text_items_without_geometry", "formula_items_with_text",
                "public_table_text_cells", "public_table_text_cells_without_geometry",
                "public_table_cells_examined", "public_table_cells_truncated",
                "retained_ocr_cells",
                "retained_layout_clusters", "retained_layout_cells_with_text", "retained_formula_cells_with_text",
                "retained_layout_truncated",
            }
            if snapshot is not None:
                clean = {k: v for k, v in snapshot.items() if k in allowed
                         and (v is None or isinstance(v, (bool, int)))}
                for key in ("backend", "ocr_backend", "retained_ocr_cells_scope", "retained_layout_scope"):
                    if isinstance(snapshot.get(key), str):
                        clean[key] = safe_name(snapshot[key])
                for key in ("configured_ocr_languages", "requested_ocr_languages"):
                    languages = snapshot.get(key)
                    clean[key] = ([safe_name(x) for x in languages[:32] if isinstance(x, str)]
                                  if isinstance(languages, list) else None)
                self.data["dependency"] = clean
            if snapshot is not None:
                self.data["formula"]["text_results"] = clean.get("formula_items_with_text")
        except Exception:  # noqa: BLE001 - optional observations must not change extraction
            self.data["dependency_observation_failed"] = True

    @_observational
    def canonical_page(self, page: Any) -> None:
        self.data["canonical"] = {
            "elements": len(page.elements),
            "text_bearing": sum(bool(e.text and e.text.strip()) for e in page.elements),
            "null_text": sum(e.text is None for e in page.elements),
            "formula": sum(e.type.value == "formula" for e in page.elements),
            "warnings_count": len(page.notes),
            "source_route": safe_name(page.source_route) if page.source_route else None,
            "source_backend": safe_name(page.source_backend) if page.source_backend else None,
        }
        self.data["table"].update(tables=len(page.tables), text_cells=sum(
            bool(c.text and c.text.strip()) for t in page.tables for c in t.cells
        ))

    @_observational
    def table_result(self, result: Any) -> None:
        self.data["table"].update(
            state="returned", backend_tables=len(result.tables), warnings_count=len(result.warnings),
        )


class VisualForensics:
    """Run-local recorder. Bounded, best-effort, secure atomic publication."""

    def __init__(self, output_dir: Path, *, input_sha256: str | None = None) -> None:
        self.path = output_dir / "diagnostics" / "classic_visual_trace.json"
        self.pages: dict[int, VisualPageTrace] = {}
        self.omitted_pages = 0
        self.persistence_failed = False
        self.input_sha256 = input_sha256

    def page(self, index: int, width: int, height: int, route: str) -> VisualPageTrace | None:
        if len(self.pages) >= MAX_PAGES and index not in self.pages:
            self.omitted_pages += 1
            return None
        trace = VisualPageTrace(index, width, height, route)
        self.pages[index] = trace
        return trace

    @_observational
    def assembled(self, document: Any, markdown: str) -> None:
        for page in document.pages:
            if page.index in self.pages:
                self.pages[page.index].canonical_page(page)
                ordered = page.elements_in_reading_order(require_complete=False)
                self.pages[page.index].data["serialization"] = {
                    "scope": "canonical_document_export",
                    "ordered_elements": len(ordered),
                    "ordered_text_bearing": sum(bool(e.text and e.text.strip()) for e in ordered),
                    "omitted_text_bearing": sum(bool(e.text and e.text.strip()) for e in page.elements
                                                if e.id not in page.reading_order),
                }
        # Document export includes headings/metadata; nonempty export is NOT
        # evidence that page content survived. Record it separately.
        self.export = {"markdown_bytes": len(markdown.encode("utf-8")), "scope": "canonical_document_export"}

    @_observational
    def outcome(self, metadata: Any) -> None:
        self.run = {"status": metadata.status.value, "warnings_count": len(metadata.warnings),
                    "errors_count": len(metadata.errors), "metadata_timestamp": metadata.timestamp[:64]}

    def persist(self) -> None:
        payload: dict[str, Any] = {
            "format": "classic-visual-forensics-v1", "pages": [],
            "bounds": {"pages": MAX_PAGES, "regions": MAX_REGIONS, "labels": MAX_LABELS,
                       "tokens_examined_per_region": MAX_TOKENS, "bytes": MAX_BYTES},
            "omitted_pages": self.omitted_pages,
            "export": getattr(self, "export", None),
            "run": getattr(self, "run", None),
            "input_sha256": self.input_sha256,
            "observation_failed": getattr(self, "observation_failed", False),
        }
        try:
            for index in sorted(self.pages):
                payload["pages"].append(self.pages[index].data)
                if len(json.dumps(payload, ensure_ascii=True, sort_keys=True).encode()) > MAX_BYTES - 128:
                    payload["pages"].pop()
                    payload["omitted_pages"] += len(self.pages) - len(payload["pages"])
                    break
            text = json.dumps(payload, ensure_ascii=True, sort_keys=True, indent=None) + "\n"
            if len(text.encode()) > MAX_BYTES:
                self.persistence_failed = True
                return
            write_text(self.path, text)
        except (OSError, ValueError, TypeError):
            # Never obscure an original backend error or change the result
            # solely because this optional diagnostic could not be written.
            self.persistence_failed = True


def summarize_traces(records: list[dict[str, Any]]) -> dict[str, int]:
    """Observable patterns, not root-cause labels or quality metrics."""
    counts: Counter[str] = Counter()
    for record in records:
        for page in record["pages"]:
            counts["pages"] += 1
            layout, ocr = page["layout"], page["ocr"]
            canonical, table = page["canonical"], page["table"]
            dep = page.get("dependency") or {}
            if layout["regions"] and page["formula"]["regions"] == layout["regions"] and ocr["projected_tokens"] == 0:
                counts["formula_only_zero_projected_ocr"] += 1
            if page["formula"]["regions"] and dep.get("formula_enrichment_enabled") is False:
                counts["formula_regions_enrichment_disabled"] += 1
            if canonical and ocr["projected_tokens"] and canonical["text_bearing"] == 0 and table["text_cells"] == 0:
                counts["projected_ocr_without_canonical_text"] += 1
            if canonical and ocr["projected_tokens"] == 0 and canonical["warnings_count"] == 0:
                counts["zero_projected_ocr_no_page_warning"] += 1
    return dict(sorted(counts.items()))
