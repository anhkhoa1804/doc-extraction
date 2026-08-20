from __future__ import annotations

from doc_extraction.ingest.classifier import detect


def test_detects_pdf_by_magic_bytes(sample_files):
    pdfs = [p for p in sample_files if p.suffix.lower() == ".pdf"]
    assert pdfs, "expected at least one sample PDF"
    for path in pdfs:
        info = detect(path)
        assert info.detected_kind == "pdf"
        assert info.confidence == 1.0


def test_detects_docx_by_zip_marker(sample_files):
    docs = [p for p in sample_files if p.suffix.lower() == ".docx"]
    assert docs, "expected at least one sample DOCX"
    for path in docs:
        info = detect(path)
        assert info.detected_kind == "docx"


def test_detects_xlsx_by_zip_marker(sample_files):
    sheets = [p for p in sample_files if p.suffix.lower() == ".xlsx"]
    assert sheets, "expected at least one sample XLSX"
    for path in sheets:
        info = detect(path)
        assert info.detected_kind == "xlsx"


def test_unknown_extension_falls_back_gracefully(tmp_path):
    bogus = tmp_path / "mystery.bin"
    bogus.write_bytes(b"\x00\x01\x02\x03not a real format")
    info = detect(bogus)
    assert info.detected_kind == "unknown"
    assert info.confidence == 0.0
    assert info.notes
