"""End-to-end pipeline behaviour, CPU-only.

Uses synthetic fixtures for shapes the real corpus lacks (PPTX, images,
per-page fallback) and the real corpus where it covers the case.
"""
from __future__ import annotations

import pytest

from doc_extraction.config import PipelineConfig
from doc_extraction.pipelines import office, pdf
from doc_extraction.pipelines.base import BackendUnavailableError, PageInput
from doc_extraction.schemas.element import ElementType
from tests.fixtures import (
    CLEAN_ENGLISH_TEXT,
    make_docx,
    make_pdf_with_broken_cmap,
    make_pdf_with_table,
    make_pdf_with_text,
    make_pptx,
    make_xlsx,
)


# --------------------------------------------------------------------------
# Digital PDF: native text + native tables
# --------------------------------------------------------------------------


def test_digital_pdf_extracts_text_elements(tmp_path):
    path = make_pdf_with_text(tmp_path / "doc.pdf", [CLEAN_ENGLISH_TEXT, "Second page text here."])
    pages = pdf.parse_digital_pdf(path, PipelineConfig(), tmp_path / "out")
    assert len(pages) == 2
    assert any(e.text for e in pages[0].elements)
    assert pages[0].source_route == "digital_pdf"
    assert pages[0].coordinate_unit == "pt"
    assert pages[0].coordinate_origin == "top-left"


def test_digital_pdf_extracts_native_table_structure(tmp_path):
    """Regression: digital PDFs used to flatten tables into paragraph text."""
    path = make_pdf_with_table(tmp_path / "table.pdf")
    pages = pdf.parse_digital_pdf(path, PipelineConfig(), tmp_path / "out")

    assert len(pages[0].tables) == 1
    table = pages[0].tables[0]
    assert table.n_rows == 3
    assert table.n_cols == 3
    assert table.source_backend == "pymupdf_tables"

    grid = table.to_grid()
    flat = [cell for row in grid for cell in row]
    assert "Widget" in flat
    assert "25.50" in flat

    table_elements = [e for e in pages[0].elements if e.type == ElementType.TABLE]
    assert len(table_elements) == 1
    assert table_elements[0].table_id == table.id


def test_digital_pdf_table_cells_carry_bboxes(tmp_path):
    path = make_pdf_with_table(tmp_path / "table.pdf")
    pages = pdf.parse_digital_pdf(path, PipelineConfig(), tmp_path / "out")
    cells = pages[0].tables[0].cells
    assert cells
    assert all(c.bbox is not None for c in cells)
    assert all(c.bbox.x0 <= c.bbox.x1 and c.bbox.y0 <= c.bbox.y1 for c in cells)


def test_table_extraction_can_be_disabled(tmp_path):
    path = make_pdf_with_table(tmp_path / "table.pdf")
    config = PipelineConfig(digital_pdf_tables=False)
    pages = pdf.parse_digital_pdf(path, config, tmp_path / "out")
    assert pages[0].tables == []


def test_table_text_is_not_duplicated_as_loose_paragraphs(tmp_path):
    """Content inside a detected table must not also appear as free text."""
    path = make_pdf_with_table(tmp_path / "table.pdf")
    pages = pdf.parse_digital_pdf(path, PipelineConfig(), tmp_path / "out")
    loose_text = " ".join(e.text or "" for e in pages[0].elements if e.type != ElementType.TABLE)
    assert "Widget" not in loose_text


# --------------------------------------------------------------------------
# Per-page fallback
# --------------------------------------------------------------------------


def test_suspicious_page_is_flagged_when_no_ocr_backend_is_available(tmp_path):
    """With no visual backend, a bad page must be kept *and marked*, never
    silently presented as trustworthy."""
    path = make_pdf_with_broken_cmap(tmp_path / "bad.pdf", n_pages=1)
    pages = pdf.parse_digital_pdf(
        path, PipelineConfig(), tmp_path / "out", layout_backend=None, ocr_backend=None
    )
    notes = " ".join(pages[0].notes)
    assert "SUSPECT" in notes
    assert "mixed_script" in notes


def test_suspicious_page_uses_fallback_when_backend_is_available(tmp_path):
    """The whole point of the cheap-signal design: only the bad page is
    rendered and re-extracted."""

    class FakeLayout:
        name = "fake-layout"

        def is_available(self):
            return True

        def analyze(self, page: PageInput):
            from doc_extraction.pipelines.base import LayoutResult, Region
            from doc_extraction.schemas.element import BBox

            return LayoutResult(
                regions=[Region(bbox=BBox(x0=0, y0=0, x1=100, y1=50), label="text")],
                backend=self.name,
            )

    class FakeOCR:
        name = "fake-ocr"

        def is_available(self):
            return True

        def recognize(self, page: PageInput):
            from doc_extraction.pipelines.base import OCRResult, OCRToken
            from doc_extraction.schemas.element import BBox

            return OCRResult(
                tokens=[OCRToken(text="RECOVERED", bbox=BBox(x0=10, y0=10, x1=40, y1=30))],
                backend=self.name,
            )

    class UnavailableTables:
        name = "fake-tables"

        def is_available(self):
            return False

        def extract(self, page, regions):
            raise AssertionError("must not be called when unavailable")

    path = make_pdf_with_broken_cmap(tmp_path / "bad.pdf", n_pages=1)
    pages = pdf.parse_digital_pdf(
        path,
        PipelineConfig(),
        tmp_path / "out",
        layout_backend=FakeLayout(),
        ocr_backend=FakeOCR(),
        image_table_backend=UnavailableTables(),
    )

    assert pages[0].source_route == "digital_pdf+page_fallback"
    assert any("fallback" in n for n in pages[0].notes)
    assert any((e.text or "") == "RECOVERED" for e in pages[0].elements)


def test_fallback_can_be_disabled(tmp_path):
    path = make_pdf_with_broken_cmap(tmp_path / "bad.pdf", n_pages=1)
    config = PipelineConfig(digital_pdf_page_fallback=False)
    pages = pdf.parse_digital_pdf(path, config, tmp_path / "out")
    assert pages[0].source_route == "digital_pdf"
    assert not any("fallback" in n for n in pages[0].notes)


# --------------------------------------------------------------------------
# Native office
# --------------------------------------------------------------------------


def test_docx_has_no_fabricated_pagination(tmp_path):
    """DOCX pagination is undefined without rendering; page_number must be
    None rather than a fabricated 1."""
    path = make_docx(tmp_path / "doc.docx")
    pages = office.parse_docx(path)
    assert len(pages) == 1
    assert pages[0].is_rendered_page is False
    assert all(e.page_number is None for e in pages[0].elements)
    assert all(t.page_number is None for t in pages[0].tables)
    assert pages[0].notes


def test_docx_extracts_headings_lists_and_tables(tmp_path):
    path = make_docx(tmp_path / "doc.docx")
    page = office.parse_docx(path)[0]
    types = {e.type for e in page.elements}
    assert ElementType.HEADING in types
    assert ElementType.PARAGRAPH in types
    assert ElementType.TABLE in types
    assert page.tables[0].n_rows == 2 and page.tables[0].n_cols == 2


def test_xlsx_yields_one_page_per_sheet(tmp_path):
    path = make_xlsx(tmp_path / "book.xlsx", n_sheets=3)
    pages = office.parse_xlsx(path)
    assert len(pages) == 3
    assert [p.index for p in pages] == [0, 1, 2]
    assert pages[0].is_rendered_page is False
    assert pages[0].tables[0].page_number == 1


def test_pptx_yields_one_page_per_slide(tmp_path):
    path = make_pptx(tmp_path / "deck.pptx", n_slides=2)
    pages = office.parse_pptx(path)
    assert len(pages) == 2
    assert pages[0].is_rendered_page is True
    assert pages[0].coordinate_unit == "emu"
    assert any(e.type == ElementType.HEADING for e in pages[0].elements)


# --------------------------------------------------------------------------
# Failure handling
# --------------------------------------------------------------------------


def test_corrupt_pdf_raises_rather_than_returning_empty(tmp_path):
    """A parser failure must be loud. Silently returning zero pages would
    look identical to a genuinely empty document."""
    from tests.fixtures import make_corrupt_pdf

    path = make_corrupt_pdf(tmp_path / "broken.pdf")
    with pytest.raises(Exception):
        pdf.parse_digital_pdf(path, PipelineConfig(), tmp_path / "out")


def test_native_table_backend_without_source_pdf_warns(tmp_path):
    from doc_extraction.backends.pymupdf_table_backend import PyMuPDFTableBackend

    result = PyMuPDFTableBackend().extract(
        PageInput(page_index=0, width=100, height=100), regions=[]
    )
    assert result.tables == []
    assert result.warnings


def test_native_table_backend_out_of_range_page(tmp_path):
    from doc_extraction.backends.pymupdf_table_backend import PyMuPDFTableBackend

    path = make_pdf_with_text(tmp_path / "one.pdf", ["only page"])
    result = PyMuPDFTableBackend().extract(
        PageInput(page_index=99, width=100, height=100, source_pdf_path=path), regions=[]
    )
    assert result.tables == []
    assert any("out of range" in w for w in result.warnings)


def test_backend_unavailable_error_is_raised_not_swallowed():
    from doc_extraction.backends.mineru_backend import MinerUBackend

    with pytest.raises(BackendUnavailableError):
        MinerUBackend().convert(__import__("pathlib").Path("x.pdf"), config=None)
