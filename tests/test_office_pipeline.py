from __future__ import annotations

import pytest

from doc_extraction.pipelines import office


def test_parse_docx_extracts_some_content(sample_files):
    docs = [p for p in sample_files if p.suffix.lower() == ".docx"]
    if not docs:
        pytest.skip("no local sample DOCX under data/ (private corpus, see data/README.md)")
    for path in docs:
        pages = office.parse_docx(path)
        assert len(pages) == 1
        assert len(pages[0].elements) > 0
        assert all(e.source_backend == office.BACKEND_NAME for e in pages[0].elements)


def test_parse_xlsx_extracts_a_table_per_sheet(sample_files):
    sheets = [p for p in sample_files if p.suffix.lower() == ".xlsx"]
    if not sheets:
        pytest.skip("no local sample XLSX under data/ (private corpus, see data/README.md)")
    for path in sheets:
        pages = office.parse_xlsx(path)
        assert len(pages) >= 1
        for page in pages:
            assert len(page.tables) == 1
            assert page.tables[0].n_rows >= 0
            assert page.tables[0].n_cols >= 0
