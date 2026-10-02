from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import pytest
from PIL import Image

from doc_extraction.backends.paddleocr_vl_backend import (
    E2EInvalidModelOutput,
    PaddleOCRVLBackend,
    validate_worker_response,
)
from doc_extraction.cli import _collect_page_warnings, process_file
from doc_extraction.config import PipelineConfig
from doc_extraction.schemas.document import Document, RunMetadata, RunStatus
from doc_extraction.schemas.element import BBox, Element, ElementType
from doc_extraction.schemas.page import Page
from doc_extraction.schemas.table import Cell, Table
from doc_extraction.utils.hashing import sha256_file
from tests.backend_conformance import (
    assert_document_conforms,
    assert_failed_document_rejected,
)
from tests.fixtures import make_pdf_with_table


def _metadata(status: RunStatus = RunStatus.SUCCESS) -> RunMetadata:
    return RunMetadata(
        input_filename="fixture.pdf",
        input_path="fixture.pdf",
        file_hash_sha256="a" * 64,
        file_type="pdf",
        route="digital_pdf",
        pipeline="baseline",
        backend="classic",
        timestamp=datetime(2026, 1, 1, tzinfo=timezone.utc).isoformat(),
        status=status,
        warnings=["fixture warning"] if status is RunStatus.SUCCESS_WITH_WARNINGS else [],
        errors=[],
    )


def _valid_physical_document() -> Document:
    table = Table(
        id="p0-t0",
        n_rows=2,
        n_cols=2,
        source_backend="fixture",
        cells=[
            Cell(row=0, col=0, row_span=2, text="merged", bbox=None),
            Cell(row=0, col=1, text="known", bbox=BBox(x0=2, y0=0, x1=4, y1=1)),
            Cell(row=1, col=1, text="", bbox=None),
        ],
    )
    page = Page(
        index=0,
        width=10,
        height=20,
        coordinate_unit="pt",
        elements=[
            Element(id="p0-e0", type=ElementType.TABLE, source_backend="fixture", table_id=table.id),
            Element(id="p0-e1", type=ElementType.TEXT, source_backend="fixture", text=None, bbox=None),
        ],
        tables=[table],
        reading_order=["p0-e0", "p0-e1"],
    )
    return Document(
        schema_version="1.4.0",
        document_id="fixture",
        metadata=_metadata(RunStatus.SUCCESS_WITH_WARNINGS),
        pages=[page],
    )


class _FakePaddleResult:
    def __init__(self, result: dict) -> None:
        self.json = {"res": result}


def test_shared_conformance_accepts_physical_structure_nulls_spans_and_diagnostics() -> None:
    document = _valid_physical_document()
    assert_document_conforms(document)


def test_shared_conformance_rejects_mutated_duplicate_id_geometry_order_and_table_link() -> None:
    mutations = []

    duplicate = _valid_physical_document()
    duplicate.pages[0].elements[1].id = duplicate.pages[0].elements[0].id
    mutations.append(duplicate)

    invalid_geometry = _valid_physical_document()
    invalid_geometry.pages[0].elements[1].bbox = BBox(x0=0, y0=0, x1=1, y1=1)
    invalid_geometry.pages[0].elements[1].bbox.x0 = float("nan")
    mutations.append(invalid_geometry)

    incomplete_order = _valid_physical_document()
    incomplete_order.pages[0].reading_order = ["p0-e0"]
    mutations.append(incomplete_order)

    invalid_table_reference = _valid_physical_document()
    invalid_table_reference.pages[0].elements[0].table_id = "missing"
    mutations.append(invalid_table_reference)

    invalid_span = _valid_physical_document()
    invalid_span.pages[0].tables[0].cells[0].row_span = 3
    mutations.append(invalid_span)

    for document in mutations:
        with pytest.raises((AssertionError, ValueError)):
            assert_document_conforms(document)


def test_failed_extraction_payload_cannot_pass_conformance() -> None:
    payload = _metadata(RunStatus.FAILED).model_dump(mode="python")
    assert_failed_document_rejected({
        "schema_version": "1.4.0",
        "document_id": "failed",
        "metadata": payload,
        "pages": [],
    })


def test_classic_production_api_output_passes_shared_conformance(tmp_path: Path) -> None:
    source = make_pdf_with_table(tmp_path / "classic-table.pdf")
    document = process_file(source, PipelineConfig(device="cpu"), output_root=tmp_path / "classic-output")
    assert document.metadata.backend == "baseline"
    assert_document_conforms(document)


def test_e2e_fake_worker_page_passes_same_shared_conformance(tmp_path: Path) -> None:
    source = tmp_path / "page.png"
    source.write_bytes(b"fake image bytes; injected pipeline does not decode")

    class FakePipeline:
        def predict(self, path: str) -> list[_FakePaddleResult]:
            assert path == str(source)
            return [
                _FakePaddleResult(
                    {
                        "width": 100,
                        "height": 150,
                        "parsing_res_list": [
                            {
                                "block_label": "paragraph",
                                "block_content": "recognized text",
                                "block_bbox": [2, 3, 80, 20],
                                "block_order": 1,
                            },
                            {
                                "block_label": "display_formula",
                                "block_content": None,
                                "block_bbox": [5, 30, 60, 50],
                                "block_order": 2,
                            },
                        ],
                    }
                )
            ]

    backend = PaddleOCRVLBackend(device="cpu", pipeline=FakePipeline())

    class Config:
        device = "cpu"

        @staticmethod
        def to_snapshot() -> dict:
            return {"device": "cpu"}

    document = backend.convert(source, Config())
    assert document.pages[0].elements[1].text is None
    assert document.pages[0].elements[1].bbox is not None
    assert document.pages[0].elements[1].confidence is None
    assert document.metadata.file_hash_sha256 == sha256_file(source)
    assert_document_conforms(document)

    response = {
        "state": "completed",
        "input_sha256": document.metadata.file_hash_sha256,
        "page": document.pages[0].model_dump(mode="json"),
        "model_versions": {"model": "fixture@revision"},
        "phase_timings": {"pipeline_predict_seconds": 0.1},
    }
    response["page"]["reading_order"] = ["wrong-element"]
    with pytest.raises(E2EInvalidModelOutput, match="reading_order"):
        validate_worker_response(response, document.metadata.file_hash_sha256)


def test_known_empty_ocr_shape_is_warned_and_null_content_is_not_fabricated(tmp_path: Path) -> None:
    """Classic's formula-only/empty-OCR shape remains honest but not silent."""
    from doc_extraction.pipelines.base import (
        LayoutResult,
        OCRResult,
        Region,
        run_scanned_page_pipeline,
    )

    image_path = tmp_path / "visible-content.png"
    Image.new("RGB", (50, 70), "white").save(image_path)

    class FormulaLayout:
        name = "fixture-layout"

        def is_available(self) -> bool:
            return True

        def analyze(self, page):
            return LayoutResult(
                regions=[Region(BBox(x0=1, y0=1, x1=40, y1=30), "formula")],
                backend=self.name,
                warnings=["layout fixture diagnostic"],
            )

    class EmptyOCR:
        name = "fixture-ocr"

        def is_available(self) -> bool:
            return True

        def recognize(self, page):
            return OCRResult(tokens=[], backend=self.name, warnings=["OCR fixture diagnostic"])

    class NoTables:
        name = "fixture-tables"

        def is_available(self) -> bool:
            return False

        def extract(self, page, regions):
            raise AssertionError("unavailable table backend must not be invoked")

    page = run_scanned_page_pipeline(
        image_path,
        0,
        200,
        FormulaLayout(),
        EmptyOCR(),
        NoTables(),
        tmp_path / "stages",
    )
    assert page.elements[0].type is ElementType.FORMULA
    assert page.elements[0].text is None
    assert page.notes == [
        "layout (fixture-layout): layout fixture diagnostic",
        "OCR (fixture-ocr): OCR fixture diagnostic",
        "OCR returned no text tokens for 1 detected text/formula region(s); page extraction may be incomplete"
    ]
    run_warnings = _collect_page_warnings([page])
    assert len(run_warnings) == 3
    assert "OCR returned no text tokens" in run_warnings[-1]

    metadata = _metadata(RunStatus.SUCCESS_WITH_WARNINGS)
    metadata.warnings = run_warnings
    document = Document(
        document_id="empty-ocr",
        metadata=metadata,
        pages=[page.model_copy(update={"reading_order": [element.id for element in page.elements]})],
    )
    assert_document_conforms(document)
