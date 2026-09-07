"""Backend interfaces (spec §8) plus the small value types stages pass
between each other. Concrete implementations live in `backends/`; stages in
`stages/` orchestrate calls against whichever backend a config selects.

These Protocols are the whole point of the "modular, not a black box" design:
`doc_extraction compare` runs several `WholeDocumentBackend` implementations
over the same file, and the baseline pipeline's `stages/*.py` call
`LayoutBackend`/`OCRBackend`/`TableBackend` implementations independently, so
any one component can be swapped or studied in isolation.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Protocol, runtime_checkable

from doc_extraction.schemas.element import BBox, Element, ElementType
from doc_extraction.schemas.page import Page
from doc_extraction.schemas.table import Cell, Table
from doc_extraction.utils.logging import StageLogger

if TYPE_CHECKING:
    from doc_extraction.config import PipelineConfig
    from doc_extraction.schemas.document import Document


class BackendUnavailableError(RuntimeError):
    """Raised when a selected backend isn't installed/importable in this
    environment. Callers must handle this explicitly (log + skip, fall back
    to another backend, or fail the run) — it is never swallowed silently."""


@dataclass
class PageInput:
    """What a stage backend needs to operate on one page.

    A backend uses whichever inputs it needs and reports a warning when a
    required one is missing, rather than assuming: image-based backends need
    `image_path`, native PDF backends need `source_pdf_path`.
    """

    page_index: int  # 0-based
    width: float
    height: float
    image_path: Path | None = None  # rendered raster, when the stage needs pixels
    text: str | None = None  # extracted text layer, when available (digital PDFs)
    dpi: int | None = None
    source_pdf_path: Path | None = None  # original PDF, for native (non-raster) backends


@dataclass
class Region:
    bbox: BBox
    label: str
    confidence: float | None = None
    source_id: str | None = None


@dataclass
class LayoutResult:
    regions: list[Region] = field(default_factory=list)
    backend: str = ""
    warnings: list[str] = field(default_factory=list)


@dataclass
class OCRToken:
    text: str
    bbox: BBox
    confidence: float | None = None


@dataclass
class OCRResult:
    tokens: list[OCRToken] = field(default_factory=list)
    backend: str = ""
    warnings: list[str] = field(default_factory=list)


@dataclass
class TableResult:
    tables: list[Table] = field(default_factory=list)
    backend: str = ""
    warnings: list[str] = field(default_factory=list)
    # Source text runs considered for each table, keyed by table id, each
    # annotated with the cell it was assigned to. Carried so a quality gate
    # can judge cell text against the runs that produced it rather than
    # re-deriving them. Empty for backends that work from pixels.
    spans_by_table: dict[str, list[dict]] = field(default_factory=dict)


@runtime_checkable
class LayoutBackend(Protocol):
    name: str

    def is_available(self) -> bool: ...

    def analyze(self, page: PageInput) -> LayoutResult: ...


@runtime_checkable
class OCRBackend(Protocol):
    name: str

    def is_available(self) -> bool: ...

    def recognize(self, page: PageInput) -> OCRResult: ...


@runtime_checkable
class TableBackend(Protocol):
    name: str

    def is_available(self) -> bool: ...

    def extract(self, page: PageInput, regions: list[Region]) -> TableResult: ...


@runtime_checkable
class WholeDocumentBackend(Protocol):
    """Full end-to-end conversion used by `doc_extraction compare` — one
    library's own pipeline, adapted into the canonical IR."""

    name: str

    def is_available(self) -> bool: ...

    def convert(self, path: Path, config: "PipelineConfig") -> "Document": ...


# ---------------------------------------------------------------------------
# Shared scanned-page orchestration (Steps E-H for the "scanned" route).
#
# Both pipelines/pdf.py (scanned PDFs) and pipelines/image.py (raw images)
# need the identical layout -> OCR -> table -> element-merge sequence per
# rendered page; it lives here rather than being duplicated in each pipeline
# module.
# ---------------------------------------------------------------------------

_LABEL_TO_ELEMENT_TYPE: dict[str, str] = {
    "title": "heading",
    "section-header": "heading",
    "section_header": "heading",
    "text": "text",
    "paragraph": "paragraph",
    "list-item": "list_item",
    "list_item": "list_item",
    "table": "table",
    "picture": "image",
    "figure": "image",
    "formula": "formula",
    "checkbox-selected": "checkbox",
    "checkbox-unselected": "checkbox",
    "caption": "text",
    "footnote": "text",
    "page-header": "other",
    "page-footer": "other",
}


def _center_in(inner: BBox, outer: BBox) -> bool:
    cx = (inner.x0 + inner.x1) / 2
    cy = (inner.y0 + inner.y1) / 2
    return outer.x0 <= cx <= outer.x1 and outer.y0 <= cy <= outer.y1


# Fraction of the *shorter* of two tokens' heights their y-ranges must
# overlap to count as the same printed line. Words on one line share a
# baseline and so overlap almost completely; the next line down overlaps
# by roughly zero. 0.5 sits in the middle of that gap and is not a tuned
# value -- measured over the 023 corpus, every threshold in 0.3-0.7 gives
# the identical result on all 49 documents.
LINE_BAND_Y_OVERLAP_MIN = 0.5

# How far apart two orphan line bands may sit and still be one recovered
# block, as a multiple of the taller band's height. 1.5 is ordinary
# paragraph leading with room to spare; it separates a dropped column from
# a dropped footer rather than tuning any measured number.
ORPHAN_LINE_GAP_RATIO = 1.5


def _tokens_in_reading_order(tokens: list[OCRToken]) -> list[OCRToken]:
    """Order OCR tokens the way the page reads: line by line, left to right.

    Sorting on the raw `(y0, x0)` tuple looks equivalent and is not. It is
    correct only when a backend emits one token per printed line, which is
    what EasyOCR does -- with a single token per line the sort cannot
    reorder anything, so the defect was structurally invisible for as long
    as EasyOCR was the only recognizer.

    A word-level backend (Tesseract's TSV output) breaks it. Words sharing
    a baseline differ in `y0` by a few pixels -- cap height, ascenders,
    punctuation -- so a lexicographic `y0` sort interleaves them by glyph
    height rather than by position: measured on `ord_policy_en`,
    "INTERNAL EXPENDITURE POLICY" assembled as "POLICY INTERNAL
    EXPENDITURE" (POLICY's y0 was 138 against 139 for the other two), and
    "Section 1. Scope" as "Section Scope 1.".

    The cost was not cosmetic. Experiment 023 measured Tesseract's
    full-pipeline exact recall over the 49-PDF corpus at 0.2222 before this
    change and 0.9311 after. That end-to-end delta is NOT attributable to
    this function alone: `to_tesseract_langs`' `eng`-last ordering landed in
    the same change, and the two were never measured apart end to end. What
    is attributable here is the mechanism above -- a word-level backend's
    lines were being emitted scrambled.

    Tokens are grouped into line bands by mutual vertical overlap
    (single-linkage, same construction as `_cluster_by_row_band` uses for
    table rows), bands are ordered by their top edge, and tokens run left
    to right inside a band.

    What this guarantees, precisely: tokens that share a printed line come
    out left to right, and lines come out top to bottom.

    What it does NOT guarantee is that a one-token-per-line backend is
    unaffected. An earlier version of this docstring claimed that, and it
    is false. Two lines whose y-ranges overlap by at least
    LINE_BAND_Y_OVERLAP_MIN of the shorter height merge into a single band
    and are then ordered by x0 rather than by y0 -- so a backend emitting
    one token per line can still be reordered wherever its lines overlap
    vertically (tight leading, superscripts, a tall glyph reaching into the
    line above). Measured on EasyOCR, which does emit one token per line:
    corpus exact recall moved 0.6380 -> 0.6570, reproduced in two
    independent runs. The direction happened to be favourable; the point is
    that the output changed at all.
    """
    if not tokens:
        return []
    bands: list[dict] = []
    for token in sorted(tokens, key=lambda t: (t.bbox.y0, t.bbox.x0)):
        box = token.bbox
        for band in bands:
            overlap = min(band["y1"], box.y1) - max(band["y0"], box.y0)
            shorter = min(band["y1"] - band["y0"], box.y1 - box.y0)
            if overlap > 0 and shorter > 0 and overlap >= LINE_BAND_Y_OVERLAP_MIN * shorter:
                band["tokens"].append(token)
                band["y0"] = min(band["y0"], box.y0)
                band["y1"] = max(band["y1"], box.y1)
                break
        else:
            bands.append({"y0": box.y0, "y1": box.y1, "tokens": [token]})
    ordered: list[OCRToken] = []
    for band in sorted(bands, key=lambda b: b["y0"]):
        ordered.extend(sorted(band["tokens"], key=lambda t: t.bbox.x0))
    return ordered


# --- orphan OCR evidence recovery -------------------------------------------
#
# `_gather_region_text` keeps only the tokens whose centre falls inside a
# detected layout region. Tokens no region claims are not mis-ordered and not
# mis-assigned -- they are dropped, and nothing downstream ever sees them.
#
# Measured over the 49-PDF corpus (experiments/024_ocr_fidelity_recovery):
# 1000 of 5845 recognised tokens, 17.1%, are orphaned this way. On
# `cmb_scan_multicol_en` the orphans are the page's entire second column,
# 15 of 34 tokens, including a `must_contain` string the recogniser had read
# correctly. On `long_policy_vi_60p` -- a document that scores a perfect
# recall -- 894 tokens are discarded. Sparse ground truth makes only a small
# part of that visible as recall; all of it is real extracted text.
#
# What the same measurement says about *which* orphans to recover: of those
# 1000 tokens, 0 are single characters, 0 are pure punctuation, 4 have
# confidence below 0.5, and 12 (1.2%) fall inside a detected table. They are
# overwhelmingly ordinary body words. So this does not filter on confidence
# or token shape -- there is no measured basis for a threshold, and inventing
# one would discard real text to guard against noise this corpus does not
# contain. The only content guard is that a recovered block must carry at
# least one alphanumeric character, which costs nothing and excludes runs of
# rule/border glyphs.
#
# Tokens inside a detected table are deliberately NOT recovered here. Table
# ownership has its own tiered rules and its own guarantees
# (experiments/017_table_cell_geometry), and text that belongs to a table
# belongs in its cells, not in a sibling text element. Leaving them alone
# also makes duplication impossible by construction: a recovered token is by
# definition claimed by no region and inside no table, so it cannot also have
# reached a region's text or a cell's text.
#
# Recovered blocks carry real geometry, so `compute_reading_order` places
# them by position like any other element rather than at the end of the page.


def _orphan_tokens(
    regions: list[Region], ocr_result: OCRResult, tables: list
) -> list[OCRToken]:
    """OCR tokens claimed by no layout region and inside no detected table.

    Cell boxes are excluded as well as each table's outer box, because
    `Table.bbox` is optional: a table that carries cells but no outer bbox
    would otherwise leave its cells' own tokens looking unclaimed, and
    `_fill_table_cell_text` will have put them in cells regardless. Checking
    both is what makes "recovered tokens cannot also be cell text" true by
    construction rather than by assumption.
    """
    boxes = [t.bbox for t in tables if getattr(t, "bbox", None) is not None]
    boxes += [c.bbox for t in tables for c in (getattr(t, "cells", None) or [])
              if getattr(c, "bbox", None) is not None]
    return [
        t for t in ocr_result.tokens
        if not any(_center_in(t.bbox, r.bbox) for r in regions)
        and not any(_center_in(t.bbox, b) for b in boxes)
    ]


def _cluster_orphans(tokens: list[OCRToken]) -> list[list[OCRToken]]:
    """Group orphan tokens into contiguous blocks, one per run of lines.

    Tokens are first banded into printed lines by the same mutual-vertical-
    overlap rule `_tokens_in_reading_order` uses, then adjacent bands are
    joined into a block while they are vertically close (within
    `ORPHAN_LINE_GAP_RATIO` of the taller band's height) and horizontally
    overlapping. That keeps a dropped column together as one element instead
    of scattering it into one element per line, without merging a header and
    a footer that merely share a page.
    """
    if not tokens:
        return []
    bands: list[dict] = []
    for token in sorted(tokens, key=lambda t: (t.bbox.y0, t.bbox.x0)):
        box = token.bbox
        for band in bands:
            overlap = min(band["y1"], box.y1) - max(band["y0"], box.y0)
            shorter = min(band["y1"] - band["y0"], box.y1 - box.y0)
            if overlap > 0 and shorter > 0 and overlap >= LINE_BAND_Y_OVERLAP_MIN * shorter:
                band["tokens"].append(token)
                band["y0"], band["y1"] = min(band["y0"], box.y0), max(band["y1"], box.y1)
                band["x0"], band["x1"] = min(band["x0"], box.x0), max(band["x1"], box.x1)
                break
        else:
            bands.append({"y0": box.y0, "y1": box.y1, "x0": box.x0, "x1": box.x1,
                          "tokens": [token]})

    bands.sort(key=lambda b: (b["y0"], b["x0"]))
    blocks: list[list[dict]] = []
    for band in bands:
        if blocks:
            prev = blocks[-1][-1]
            gap = band["y0"] - prev["y1"]
            tall = max(prev["y1"] - prev["y0"], band["y1"] - band["y0"], 1.0)
            overlaps_x = min(prev["x1"], band["x1"]) > max(prev["x0"], band["x0"])
            if overlaps_x and gap <= ORPHAN_LINE_GAP_RATIO * tall:
                blocks[-1].append(band)
                continue
        blocks.append([band])

    return [[t for band in block for t in _tokens_in_reading_order(band["tokens"])]
            for block in blocks]


def _gather_region_text(region: Region, ocr_result: OCRResult) -> str | None:
    if not ocr_result.tokens:
        return None
    contained = [t for t in ocr_result.tokens if _center_in(t.bbox, region.bbox)]
    if not contained:
        return None
    text = " ".join(t.text for t in _tokens_in_reading_order(contained) if t.text).strip()
    return text or None


# --- table cell/text assignment fallback tiers ------------------------------
#
# Diagnosed on the real corpus (experiments/017_table_cell_geometry): center
# containment alone silently drops an entire row's text when Table
# Transformer's own row detector under-counts rows -- measured directly on
# `ord_invoice_png_vi`, 3 rows detected where 4 exist, with the missing
# row's own OCR tokens ('Dịch vụ đặt lắp', 'Gói', '1', '3.500.000') sitting
# just below the last detected row's bottom edge, still inside the table's
# own outer bbox. This is a structure-detection undercount, not a
# coordinate-space bug: `docling_page_size()` matched the render size 1:1
# for this document, so no rescale was even in play.
#
# The two fallback tiers below exist for that gap and for ordinary
# rounding noise; both stay inside the table's own outer bbox and both
# require positive alignment evidence, per the same ownership discipline
# `pymupdf_table_backend`'s run-splitting fix already established: a
# fallback that grabs "whichever cell is closest" would let a stamp or an
# adjacent row's text jump into a cell it does not belong to, which is
# exactly the failure class this project has already paid to fix once.

# tier 2: how far a token's center may fall outside a cell's own edge and
# still count as "that cell, plus rounding noise" -- NOT a fraction of
# cell/token area. An area-overlap-ratio threshold >= 0.5 was tried first
# and proven unreachable by construction: if a token's center lies outside
# a cell on some axis, simple interval algebra caps that axis's overlap
# fraction strictly below 0.5 (the excess past the boundary is, by
# definition of "center outside", at least as large as what remains
# inside), so an area-ratio gate can never recover a single case center
# containment already missed. A small absolute pixel margin around the
# cell is the correct tool for "rounding noise", not a ratio.
CELL_ROUNDING_MARGIN_PX = 3.0
ROW_BAND_Y_OVERLAP_MIN = 0.3  # tier 3: tokens cluster into one missing row if their y-ranges overlap this much
COLUMN_ALIGN_MIN = 0.3  # tier 3: token must overlap a column's x-range by this fraction of its own width
MIN_CORROBORATING_COLUMNS = 2  # tier 3: never synthesize a row from a single stray token


def _expanded(bbox: BBox, margin: float) -> BBox:
    return BBox(x0=bbox.x0 - margin, y0=bbox.y0 - margin, x1=bbox.x1 + margin, y1=bbox.y1 + margin)


def _y_overlap_fraction(a: BBox, b: BBox) -> float:
    inter = max(0.0, min(a.y1, b.y1) - max(a.y0, b.y0))
    shorter = min(max(1e-6, a.y1 - a.y0), max(1e-6, b.y1 - b.y0))
    return inter / shorter


def _column_bands(table: "Table") -> dict[int, tuple[float, float]]:
    """Each existing column's x-range, taken as the union of its own cells'
    bboxes -- the anchor grid a synthesized row is placed against. A table
    whose cells carry no geometry yields nothing to anchor to."""
    bands: dict[int, tuple[float, float]] = {}
    for cell in table.cells:
        if cell.bbox is None:
            continue
        lo, hi = bands.get(cell.col, (cell.bbox.x0, cell.bbox.x1))
        bands[cell.col] = (min(lo, cell.bbox.x0), max(hi, cell.bbox.x1))
    return bands


def _best_matching_column(token_bbox: BBox, column_bands: dict[int, tuple[float, float]]) -> int | None:
    """The column whose x-range the token overlaps most, as a fraction of
    the token's own width -- None if it does not meaningfully align with
    any of this table's own detected columns (e.g. it is stamp/overlay
    text that merely happens to sit inside the table's outer bbox)."""
    best_col, best_frac = None, 0.0
    width = max(1e-6, token_bbox.x1 - token_bbox.x0)
    for col, (lo, hi) in column_bands.items():
        overlap = max(0.0, min(token_bbox.x1, hi) - max(token_bbox.x0, lo))
        frac = overlap / width
        if frac > best_frac:
            best_col, best_frac = col, frac
    return best_col if best_frac >= COLUMN_ALIGN_MIN else None


def _cluster_by_row_band(tokens: list[OCRToken]) -> list[list[OCRToken]]:
    """Group orphaned tokens into row-bands by mutual vertical overlap
    (single-linkage): tokens whose y-ranges substantially overlap belong to
    the same physical row Table Transformer failed to detect. Grouping is
    by pairwise overlap, not by emission order, so it does not depend on
    the OCR backend's own token ordering."""
    remaining = list(tokens)
    clusters: list[list[OCRToken]] = []
    while remaining:
        cluster = [remaining.pop(0)]
        changed = True
        while changed:
            changed = False
            still = []
            for t in remaining:
                if any(_y_overlap_fraction(t.bbox, m.bbox) >= ROW_BAND_Y_OVERLAP_MIN for m in cluster):
                    cluster.append(t)
                    changed = True
                else:
                    still.append(t)
            remaining = still
        clusters.append(cluster)
    return clusters


def _renumber_rows_by_position(table: "Table") -> None:
    """Reassign every cell's `row` so row indices read top-to-bottom by
    actual y-position, after tier 3 may have inserted a synthesized row
    above, below, or between the rows Table Transformer itself detected.
    Table Transformer's own rows are already y-sorted among themselves (see
    `table_backend.py`), so this only has to interleave the new ones
    correctly, not re-sort from scratch."""
    by_row: dict[int, list[Cell]] = {}
    for cell in table.cells:
        by_row.setdefault(cell.row, []).append(cell)
    bands = []
    for row, cells in by_row.items():
        ys = [c.bbox.y0 for c in cells if c.bbox is not None]
        bands.append((min(ys) if ys else 0.0, row, cells))
    bands.sort(key=lambda b: b[0])
    for new_row, (_, _old_row, cells) in enumerate(bands):
        for c in cells:
            c.row = new_row
    table.n_rows = len(bands)


def _fill_table_cell_text(table_result: "TableResult", ocr_result: OCRResult) -> None:
    """Table Transformer produces grid geometry only (no text). Fill each
    cell's text from whichever OCR tokens land there, in three tiers:

    1. Center containment (unchanged from the original rule) -- cheap and
       correct for the overwhelming majority of cells.
    2. Overlap-ratio near-miss against an already-detected cell, for a
       token whose *center* crossed a cell edge by a rounding-sized margin
       but whose bbox is still mostly inside exactly one cell.
    3. Missing-row synthesis, only when at least `MIN_CORROBORATING_COLUMNS`
       orphaned tokens land in *different* existing columns at the same
       y-band -- see the module-level comment above for why this needs
       corroboration rather than acting on one token.

    Every tier stays inside the table's own outer bbox; nothing here ever
    considers a token that starts outside it, however close."""
    if not ocr_result.tokens:
        return
    for table in table_result.tables:
        claimed_ids: set[int] = set()

        for cell in table.cells:
            if cell.bbox is None:
                continue
            contained = [t for t in ocr_result.tokens if _center_in(t.bbox, cell.bbox)]
            if not contained:
                continue
            claimed_ids.update(id(t) for t in contained)
            cell.text = " ".join(
                t.text for t in _tokens_in_reading_order(contained) if t.text
            ).strip()

        if table.bbox is None:
            continue

        orphans = [
            t for t in ocr_result.tokens
            if id(t) not in claimed_ids and _center_in(t.bbox, table.bbox)
        ]
        if not orphans:
            continue

        still_orphaned: list[OCRToken] = []
        for t in orphans:
            # Candidates within rounding margin, not just the nearest one --
            # a token sitting on a shared edge (within margin of BOTH
            # neighboring cells) must find NEITHER: ambiguous ownership is
            # not resolved by iteration order, only a token unambiguously
            # within margin of exactly one cell is safe to assign.
            qualifying = [
                cell for cell in table.cells
                if cell.bbox is not None and _center_in(t.bbox, _expanded(cell.bbox, CELL_ROUNDING_MARGIN_PX))
            ]
            if len(qualifying) == 1:
                best_cell = qualifying[0]
                best_cell.text = f"{best_cell.text} {t.text}".strip() if best_cell.text else t.text
                best_cell.confidence = min(best_cell.confidence or 1.0, 0.7)
            else:
                still_orphaned.append(t)

        if not still_orphaned:
            continue

        column_bands = _column_bands(table)
        if not column_bands:
            continue

        next_row = max((c.row for c in table.cells), default=-1) + 1
        n_synthesized_rows = 0
        for cluster in _cluster_by_row_band(still_orphaned):
            by_col: dict[int, list[OCRToken]] = {}
            for t in cluster:
                col = _best_matching_column(t.bbox, column_bands)
                if col is not None:
                    by_col.setdefault(col, []).append(t)
            if len(by_col) < MIN_CORROBORATING_COLUMNS:
                continue
            y0 = min(t.bbox.y0 for t in cluster)
            y1 = max(t.bbox.y1 for t in cluster)
            for col, col_tokens in by_col.items():
                col_tokens.sort(key=lambda t: t.bbox.x0)
                lo, hi = column_bands[col]
                table.cells.append(Cell(
                    row=next_row, col=col,
                    bbox=BBox(x0=lo, y0=y0, x1=hi, y1=y1),
                    text=" ".join(t.text for t in col_tokens if t.text).strip(),
                    is_header=False, confidence=0.5,
                ))
            next_row += 1
            n_synthesized_rows += 1

        if n_synthesized_rows:
            _renumber_rows_by_position(table)
            table_result.warnings.append(
                f"table {table.id}: synthesized {n_synthesized_rows} row(s) Table Transformer's structure "
                f"model did not detect, from corroborating OCR evidence across >= {MIN_CORROBORATING_COLUMNS} columns"
            )
            # Feed the existing Table.confidence / verify_document() /
            # from_table_confidence() convention (see verification.py) --
            # a row whose existence itself was inferred rather than
            # detected is a genuinely different trust level than one Table
            # Transformer found directly, and this is the already-existing
            # channel that distinction is meant to travel through, not a
            # new gate. Tier 2 (rounding-margin recovery of an
            # already-detected cell) does not downgrade table trust -- it
            # is a tolerance correction on structure that was found, not
            # an inference that structure exists at all.
            table.confidence = 0.5


def merge_regions_into_page(
    page_index: int,
    width: float,
    height: float,
    dpi: int | None,
    layout_result: LayoutResult,
    ocr_result: OCRResult,
    table_result: "TableResult | None",
    rendered_image_path: Path | None,
) -> "Page":
    """Combine one page's layout regions + OCR tokens + detected tables into
    a canonical Page. Region text is assembled from whichever OCR tokens
    fall inside the region's bbox (center-point containment — a simple,
    deliberately inspectable rule); table regions are matched to detected
    Table objects by bbox IoU."""
    tables = list(table_result.tables) if table_result else []
    elements: list[Element] = []

    for i, region in enumerate(layout_result.regions):
        etype = ElementType(_LABEL_TO_ELEMENT_TYPE.get(region.label.lower(), "other"))
        element_id = f"p{page_index}-e{i}"

        if etype == ElementType.TABLE and tables:
            best_table = max(
                tables, key=lambda t: (t.bbox.iou(region.bbox) if t.bbox else 0.0)
            )
            matched = (
                best_table.id
                if best_table.bbox is not None and best_table.bbox.iou(region.bbox) > 0.1
                else None
            )
            elements.append(
                Element(
                    id=element_id,
                    type=etype,
                    bbox=region.bbox,
                    page_number=page_index + 1,
                    confidence=region.confidence,
                    source_backend=layout_result.backend,
                    table_id=matched,
                    order_index=i,
                )
            )
            continue

        text = _gather_region_text(region, ocr_result)
        elements.append(
            Element(
                id=element_id,
                type=etype,
                text=text,
                bbox=region.bbox,
                page_number=page_index + 1,
                confidence=region.confidence,
                source_backend=layout_result.backend,
                order_index=i,
            )
        )

    # Recover OCR evidence no region and no table claimed. Appended to
    # `elements` after the detected ones so existing element ids and
    # order_index values are untouched; `compute_reading_order` (stage H)
    # then places them geometrically, which is where this page's canonical
    # ordering actually lives.
    orphans = _orphan_tokens(layout_result.regions, ocr_result, tables)
    recovered_tokens = 0
    for j, block in enumerate(_cluster_orphans(orphans)):
        text = " ".join(t.text for t in block if t.text).strip()
        if not any(ch.isalnum() for ch in text):
            continue
        confidences = [t.confidence for t in block if t.confidence is not None]
        elements.append(
            Element(
                id=f"p{page_index}-r{j}",
                type=ElementType.TEXT,
                text=text,
                bbox=BBox(
                    x0=min(t.bbox.x0 for t in block), y0=min(t.bbox.y0 for t in block),
                    x1=max(t.bbox.x1 for t in block), y1=max(t.bbox.y1 for t in block),
                ),
                page_number=page_index + 1,
                # The recogniser's own confidence for this text, not a layout
                # detector's -- there was no detection to take one from.
                confidence=(sum(confidences) / len(confidences)) if confidences else None,
                source_backend=ocr_result.backend,
                order_index=len(elements),
                extra={"recovered": "orphan_ocr_tokens", "token_count": len(block)},
            )
        )
        recovered_tokens += len(block)

    notes = list(table_result.warnings) if table_result else []
    if orphans:
        notes.append(
            f"orphan OCR recovery: {recovered_tokens} of {len(orphans)} unclaimed "
            f"token(s) recovered into text elements"
        )

    return Page(
        index=page_index,
        width=width,
        height=height,
        dpi=dpi,
        coordinate_unit="px",
        elements=elements,
        tables=tables,
        rendered_image_path=str(rendered_image_path) if rendered_image_path else None,
        # `parse_digital_pdf` already extends its own notes with
        # `table_result.warnings` (pipelines/pdf.py); the scanned/image
        # route funnels through this one shared function, so the same
        # propagation belongs here rather than duplicated in both
        # `parse_scanned_pdf` and `parse_image`. Without it,
        # `verify_document()`'s own comment ("Table.confidence already
        # reached page.notes via the table backend's own warning") was
        # false for every table on this route -- a pre-existing gap this
        # milestone's own new warning (missing-row synthesis) would
        # otherwise have fallen into silently.
        notes=notes,
    )


def run_scanned_page_pipeline(
    image_path: Path,
    page_index: int,
    dpi: int,
    layout_backend: LayoutBackend,
    ocr_backend: OCRBackend,
    table_backend: TableBackend,
    output_dir: Path,
    logger: "StageLogger | None" = None,
) -> "Page":
    """Steps E-H for one already-rendered page: layout -> OCR -> table ->
    merge into a canonical Page. Raises BackendUnavailableError (uncaught)
    if the configured layout/OCR backend isn't installed; the table backend
    is optional (skipped, with a warning, if unavailable)."""
    # Imported lazily to avoid a hard import-time dependency of pipelines.base
    # on the stages package (stages already imports pipelines.base for the
    # Protocol types, so a module-level import here would be circular).
    from PIL import Image

    from doc_extraction.stages import layout as layout_stage
    from doc_extraction.stages import ocr as ocr_stage
    from doc_extraction.stages import table as table_stage

    with Image.open(image_path) as im:
        width_px, height_px = im.size

    page_input = PageInput(
        page_index=page_index, width=width_px, height=height_px, image_path=image_path, dpi=dpi
    )

    layout_result = layout_stage.run_layout(page_input, layout_backend, output_dir / "layout", logger)
    ocr_result = ocr_stage.run_ocr(page_input, ocr_backend, output_dir / "ocr", logger)

    table_result: TableResult | None = None
    if table_backend.is_available():
        table_regions = [r for r in layout_result.regions if r.label.lower() == "table"]
        table_result = table_stage.run_table(
            page_input, table_regions, table_backend, output_dir / "tables", logger
        )
        _fill_table_cell_text(table_result, ocr_result)
    elif logger is not None:
        logger.log_event(
            stage="table",
            backend=table_backend.name,
            status="failure",
            warnings=[f"table backend '{table_backend.name}' unavailable — tables on this page are unstructured"],
            page=page_index,
            error="backend not installed",
        )

    return merge_regions_into_page(
        page_index, width_px, height_px, dpi, layout_result, ocr_result, table_result, image_path
    )
