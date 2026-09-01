from __future__ import annotations

import pytest

from doc_extraction.config import PipelineConfig
from doc_extraction.ingest import dispatcher


def test_docx_routes_to_native_office(sample_files):
    docs = [p for p in sample_files if p.suffix.lower() == ".docx"]
    if not docs:
        pytest.skip("no local sample DOCX under data/ (private corpus, see data/README.md)")
    config = PipelineConfig()
    for path in docs:
        decision = dispatcher.route(path, config)
        assert decision.route == dispatcher.ROUTE_NATIVE_OFFICE


def test_xlsx_routes_to_native_office(sample_files):
    sheets = [p for p in sample_files if p.suffix.lower() == ".xlsx"]
    if not sheets:
        pytest.skip("no local sample XLSX under data/ (private corpus, see data/README.md)")
    config = PipelineConfig()
    for path in sheets:
        decision = dispatcher.route(path, config)
        assert decision.route == dispatcher.ROUTE_NATIVE_OFFICE


def test_pdfs_route_to_a_pdf_route_and_report_text_ratio(sample_files):
    pdfs = [p for p in sample_files if p.suffix.lower() == ".pdf"]
    if not pdfs:
        pytest.skip("no local sample PDF under data/ (private corpus, see data/README.md)")
    config = PipelineConfig()
    for path in pdfs:
        decision = dispatcher.route(path, config)
        assert decision.route in (dispatcher.ROUTE_DIGITAL_PDF, dispatcher.ROUTE_SCANNED_PDF)
        assert decision.pdf_text_ratio is not None
        assert 0.0 <= decision.pdf_text_ratio <= 1.0


def test_unknown_file_routes_to_unknown(tmp_path):
    bogus = tmp_path / "mystery.xyz"
    bogus.write_bytes(b"not a real document")
    decision = dispatcher.route(bogus, PipelineConfig())
    assert decision.route == dispatcher.ROUTE_UNKNOWN
