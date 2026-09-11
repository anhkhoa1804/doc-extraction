"""Regression tests for additive table-specialist telemetry.

These tests deliberately mock model inference.  They verify the production
decision boundary, output equivalence, and mode semantics without downloading
or executing model weights.
"""
from __future__ import annotations

import json
from pathlib import Path

from doc_extraction.backends.table_backend import (
    TableTransformerBackend,
    _DetectedTableBox,
)
from doc_extraction.pipelines.base import (
    LayoutResult,
    OCRResult,
    OCRToken,
    PageInput,
    Region,
    run_scanned_page_pipeline,
)
from doc_extraction.schemas.element import BBox
from doc_extraction.schemas.table import Cell, Table
from doc_extraction.utils.table_telemetry import TableTelemetryRecorder


def _table(bbox: BBox, table_id: str = "p0-t0") -> Table:
    return Table(
        id=table_id,
        bbox=bbox,
        page_number=1,
        n_rows=1,
        n_cols=1,
        cells=[Cell(row=0, col=0, bbox=bbox, text="value")],
        source_backend="table_transformer",
    )


def _backend(monkeypatch, *, detected_bbox: BBox | None = None) -> TableTransformerBackend:
    backend = TableTransformerBackend(device="cpu")
    monkeypatch.setattr(backend, "is_available", lambda: True)
    monkeypatch.setattr(backend, "_lazy_load", lambda: None)
    monkeypatch.setattr(
        backend,
        "_detect_tables_with_scores",
        lambda image: []
        if detected_bbox is None
        else [_DetectedTableBox(bbox=detected_bbox, score=0.91)],
    )
    monkeypatch.setattr(
        backend,
        "_recognize_structure",
        lambda crop, bbox, page_index, table_id: _table(bbox, table_id),
    )
    return backend


def _recorder() -> TableTelemetryRecorder:
    return TableTelemetryRecorder(experiment_id="039-instrumentation", run_id="test-run")


def test_table_invocation_modes_are_distinct(tmp_path, monkeypatch):
    from PIL import Image

    image_path = tmp_path / "page.png"
    Image.new("RGB", (100, 100), "white").save(image_path)
    detected_bbox = BBox(x0=10, y0=10, x1=90, y1=90)

    page = PageInput(
        page_index=0,
        width=100,
        height=100,
        image_path=image_path,
        telemetry_page_regions=[Region(bbox=detected_bbox, label="picture")],
        telemetry_page_region_count=1,
    )
    page.telemetry = _recorder()
    backend = _backend(monkeypatch, detected_bbox=detected_bbox)
    backend.extract(page, [])
    page_wide_record = page.telemetry.records[0]
    assert page_wide_record["invocation_mode"] == "PAGE_WIDE"
    assert [call["mode"] for call in page_wide_record["specialist_calls"]] == ["PAGE_WIDE", "PAGE_WIDE"]

    labelled_page = PageInput(
        page_index=0,
        width=100,
        height=100,
        image_path=image_path,
        telemetry_page_regions=[Region(bbox=detected_bbox, label="table")],
        telemetry_page_region_count=1,
    )
    labelled_page.telemetry = _recorder()
    backend.extract(labelled_page, [Region(bbox=detected_bbox, label="table")])
    labelled_record = labelled_page.telemetry.records[0]
    assert labelled_record["invocation_mode"] == "LABELLED_CROP"
    assert all(call["mode"] == "LABELLED_CROP" for call in labelled_record["specialist_calls"])
    assert not any(call["stage"] == "detector" for call in labelled_record["specialist_calls"])

    no_image_page = PageInput(page_index=0, width=100, height=100, telemetry=_recorder())
    backend.extract(no_image_page, [])
    assert no_image_page.telemetry.records[0]["invocation_mode"] == "NOT_INVOKED"


def test_instrumented_and_uninstrumented_page_outputs_are_equivalent(tmp_path, monkeypatch):
    from PIL import Image

    image_path = tmp_path / "page.png"
    Image.new("RGB", (100, 100), "white").save(image_path)
    detected_bbox = BBox(x0=10, y0=10, x1=90, y1=90)

    class FakeLayout:
        name = "fake-layout"

        def is_available(self):
            return True

        def analyze(self, page):
            return LayoutResult(
                regions=[Region(bbox=detected_bbox, label="picture", confidence=0.8)],
                backend=self.name,
            )

    class FakeOCR:
        name = "fake-ocr"

        def is_available(self):
            return True

        def recognize(self, page):
            return OCRResult(
                tokens=[OCRToken(text="value", bbox=BBox(x0=20, y0=20, x1=30, y1=30), confidence=0.9)],
                backend=self.name,
            )

    def run(output_dir: Path, telemetry=None):
        backend = _backend(monkeypatch, detected_bbox=detected_bbox)
        page = run_scanned_page_pipeline(
            image_path=image_path,
            page_index=0,
            dpi=72,
            layout_backend=FakeLayout(),
            ocr_backend=FakeOCR(),
            table_backend=backend,
            output_dir=output_dir,
            telemetry=telemetry,
        )
        return page.model_dump(mode="json")

    baseline = run(tmp_path / "baseline")
    recorder = _recorder()
    instrumented = run(tmp_path / "instrumented", recorder)
    assert instrumented == baseline
    assert [record["record_kind"] for record in recorder.records] == [
        "specialist_invocation",
        "page_assembly",
    ]
    assert recorder.records[0]["invocation_mode"] == "PAGE_WIDE"
    assert recorder.records[1]["output"]["table_count"] == 1


def test_telemetry_writes_complete_payload_atomically(tmp_path):
    recorder = _recorder()
    page = PageInput(page_index=0, width=10, height=10)
    recorder.record_not_invoked(page=page, backend_name="table_transformer", reason="test")
    output = tmp_path / "telemetry.json"
    recorder.write_atomic(output, status="complete")
    payload = json.loads(output.read_text())
    assert payload["status"] == "complete"
    assert payload["record_count"] == 1
    assert payload["records"][0]["invocation_mode"] == "NOT_INVOKED"
