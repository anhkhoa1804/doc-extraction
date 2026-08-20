"""Structural disagreement analysis between backends.

The question this answers is *not* "which backend is better" — there is no
ground truth for this corpus, and inventing an aggregate quality score would
manufacture confidence we have not earned. The question is **"where do two
systems disagree about the same page?"**, because disagreement is a cheap,
unsupervised pointer at the pages worth a human's attention.

Everything here is descriptive and symmetric. A large delta is a flag to go
look, not a verdict on either side.

Metrics
-------
``element_count_delta`` / ``table_count_delta``
    Raw structural divergence per page.

``text_similarity``
    Character-level similarity (difflib ratio) of each page's concatenated
    text in reading order. Low similarity with similar text *lengths*
    usually means an encoding/OCR disagreement; low similarity with very
    different lengths usually means one side missed content.

``bbox_match_rate`` / ``mean_matched_iou``
    Greedy IoU matching of element boxes between two backends. Answers
    "did both systems find the same regions?" separately from "did they
    read them the same way?".

``reading_order_correlation``
    Spearman-style rank correlation over elements matched by IoU. Near 1.0
    means both systems ordered the shared regions the same way; low or
    negative values point at a genuine reading-order dispute — one of the
    named research interests for this project.
"""
from __future__ import annotations

from difflib import SequenceMatcher
from typing import Any

from doc_extraction.schemas.document import Document
from doc_extraction.schemas.element import BBox, Element
from doc_extraction.schemas.page import Page

# Two boxes are considered "the same region" above this IoU. Deliberately
# permissive: we are looking for corresponding regions across systems that
# segment differently, not measuring localization accuracy.
_MATCH_IOU = 0.5


def page_text(page: Page) -> str:
    """Concatenate a page's text in reading order.

    Table content is included via each table element's cells. Without this a
    spreadsheet page — whose entire content lives in `Page.tables`, not in
    element `.text` — would measure as zero characters, which reads as
    "extraction found nothing" when in fact it found everything.
    """
    order = page.reading_order or [e.id for e in page.elements]
    parts: list[str] = []
    for element_id in order:
        element = page.element_by_id(element_id)
        if element is None:
            continue
        if element.text:
            parts.append(element.text)
        elif element.table_id:
            table = page.table_by_id(element.table_id)
            if table is not None:
                parts.extend(" ".join(c for c in row if c) for row in table.to_grid())
    return "\n".join(parts)


def _boxed_elements(page: Page) -> list[Element]:
    return [e for e in page.elements if e.bbox is not None]


def match_elements(left: list[Element], right: list[Element]) -> list[tuple[int, int, float]]:
    """Greedy highest-IoU-first matching between two element lists.

    Returns (left_index, right_index, iou) triples. Greedy rather than
    optimal (Hungarian) matching: deterministic, O(n*m), and adequate for
    flagging disagreement — we are not scoring detection accuracy.
    """
    candidates: list[tuple[float, int, int]] = []
    for i, le in enumerate(left):
        for j, re_ in enumerate(right):
            assert le.bbox is not None and re_.bbox is not None
            iou = le.bbox.iou(re_.bbox)
            if iou >= _MATCH_IOU:
                candidates.append((iou, i, j))
    # Sort by IoU desc, then indices asc so the result is fully deterministic
    # even when several pairs tie.
    candidates.sort(key=lambda t: (-t[0], t[1], t[2]))

    used_left: set[int] = set()
    used_right: set[int] = set()
    matches: list[tuple[int, int, float]] = []
    for iou, i, j in candidates:
        if i in used_left or j in used_right:
            continue
        used_left.add(i)
        used_right.add(j)
        matches.append((i, j, iou))
    return matches


def _rank_correlation(pairs: list[tuple[int, int]]) -> float | None:
    """Spearman rank correlation over (left_position, right_position) pairs.

    Returns None when there are fewer than 3 pairs (undefined / meaningless)
    or when either side has zero rank variance.
    """
    n = len(pairs)
    if n < 3:
        return None
    left_order = sorted(range(n), key=lambda k: pairs[k][0])
    right_order = sorted(range(n), key=lambda k: pairs[k][1])
    left_rank = [0] * n
    right_rank = [0] * n
    for rank, idx in enumerate(left_order):
        left_rank[idx] = rank
    for rank, idx in enumerate(right_order):
        right_rank[idx] = rank

    d_squared = sum((left_rank[k] - right_rank[k]) ** 2 for k in range(n))
    denominator = n * (n * n - 1)
    if denominator == 0:
        return None
    return 1.0 - (6.0 * d_squared) / denominator


def compare_pages(left: Page, right: Page) -> dict[str, Any]:
    left_boxed = _boxed_elements(left)
    right_boxed = _boxed_elements(right)
    matches = match_elements(left_boxed, right_boxed)

    matchable = min(len(left_boxed), len(right_boxed))
    bbox_match_rate = (len(matches) / matchable) if matchable else None
    mean_iou = (sum(m[2] for m in matches) / len(matches)) if matches else None

    order_pairs: list[tuple[int, int]] = []
    left_order = {eid: i for i, eid in enumerate(left.reading_order or [e.id for e in left.elements])}
    right_order = {eid: i for i, eid in enumerate(right.reading_order or [e.id for e in right.elements])}
    for i, j, _iou in matches:
        li = left_order.get(left_boxed[i].id)
        ri = right_order.get(right_boxed[j].id)
        if li is not None and ri is not None:
            order_pairs.append((li, ri))

    left_text = page_text(left)
    right_text = page_text(right)
    text_similarity = SequenceMatcher(None, left_text, right_text).ratio() if (left_text or right_text) else 1.0

    return {
        "page_index": left.index,
        "left_elements": len(left.elements),
        "right_elements": len(right.elements),
        "element_count_delta": len(left.elements) - len(right.elements),
        "left_tables": len(left.tables),
        "right_tables": len(right.tables),
        "table_count_delta": len(left.tables) - len(right.tables),
        "left_text_chars": len(left_text),
        "right_text_chars": len(right_text),
        "text_similarity": round(text_similarity, 4),
        "matched_elements": len(matches),
        "bbox_match_rate": round(bbox_match_rate, 4) if bbox_match_rate is not None else None,
        "mean_matched_iou": round(mean_iou, 4) if mean_iou is not None else None,
        "reading_order_correlation": (
            round(c, 4) if (c := _rank_correlation(order_pairs)) is not None else None
        ),
    }


def compare_documents(left_name: str, left: Document, right_name: str, right: Document) -> dict[str, Any]:
    """Pairwise comparison of two backends' output for the same input."""
    n_pages = min(len(left.pages), len(right.pages))
    per_page = [compare_pages(left.pages[i], right.pages[i]) for i in range(n_pages)]

    return {
        "left": left_name,
        "right": right_name,
        "page_count_delta": len(left.pages) - len(right.pages),
        "left_pages": len(left.pages),
        "right_pages": len(right.pages),
        "compared_pages": n_pages,
        "total_element_count_delta": sum(p["element_count_delta"] for p in per_page),
        "total_table_count_delta": sum(p["table_count_delta"] for p in per_page),
        "mean_text_similarity": (
            round(sum(p["text_similarity"] for p in per_page) / len(per_page), 4) if per_page else None
        ),
        "pages": per_page,
    }


def all_pairwise(documents: dict[str, Document | None]) -> list[dict[str, Any]]:
    """Every unordered pair of successfully-converted backends."""
    names = [n for n, d in documents.items() if d is not None]
    results: list[dict[str, Any]] = []
    for i in range(len(names)):
        for j in range(i + 1, len(names)):
            left_name, right_name = names[i], names[j]
            left, right = documents[left_name], documents[right_name]
            assert left is not None and right is not None
            results.append(compare_documents(left_name, left, right_name, right))
    return results
