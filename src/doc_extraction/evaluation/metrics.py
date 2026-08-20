"""Cheap, purely descriptive metrics over a Document.

Deliberately not a scored benchmark (spec §9: "the first purpose is failure
inspection", not scoring against ground truth we don't have). These are
counts and timings useful for spotting where a backend obviously
over/under-segments a page or silently produced nothing.
"""
from __future__ import annotations

from collections import Counter
from typing import Any

from doc_extraction.schemas.document import Document


def document_stats(document: Document) -> dict[str, Any]:
    element_type_counts: Counter[str] = Counter()
    total_text_chars = 0
    total_tables = 0
    total_table_cells = 0
    confidences: list[float] = []

    for page in document.pages:
        for element in page.elements:
            element_type_counts[element.type.value] += 1
            if element.text:
                total_text_chars += len(element.text)
            if element.confidence is not None:
                confidences.append(element.confidence)
        total_tables += len(page.tables)
        for table in page.tables:
            total_table_cells += len(table.cells)

    return {
        "num_pages": len(document.pages),
        "num_elements": sum(element_type_counts.values()),
        "element_type_counts": dict(element_type_counts),
        "num_tables": total_tables,
        "num_table_cells": total_table_cells,
        "total_text_chars": total_text_chars,
        "mean_confidence": (sum(confidences) / len(confidences)) if confidences else None,
        "runtime_seconds": document.metadata.runtime_seconds,
        "device": document.metadata.device,
        "errors": document.metadata.errors,
        "warnings": document.metadata.warnings,
    }
