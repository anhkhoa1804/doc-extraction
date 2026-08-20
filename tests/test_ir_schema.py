"""Canonical IR: serialization, versioning, coordinate semantics, tables."""
from __future__ import annotations

import json
from datetime import datetime, timezone

from doc_extraction.schemas.document import Document, RunMetadata
from doc_extraction.schemas.element import BBox, Element, ElementType
from doc_extraction.schemas.page import Page
from doc_extraction.schemas.table import Cell, Table
from doc_extraction.schemas.version import SCHEMA_VERSION


def _metadata(**overrides) -> RunMetadata:
    defaults = dict(
        input_filename="test.pdf",
        input_path="test.pdf",
        file_hash_sha256="deadbeef",
        file_type="pdf",
        route="digital_pdf",
        pipeline="baseline",
        backend="baseline",
        timestamp=datetime.now(timezone.utc).isoformat(),
    )
    defaults.update(overrides)
    return RunMetadata(**defaults)


def test_document_carries_schema_version():
    document = Document(document_id="d", metadata=_metadata())
    assert document.schema_version == SCHEMA_VERSION
    assert json.loads(document.model_dump_json())["schema_version"] == SCHEMA_VERSION


def test_schema_version_survives_round_trip():
    document = Document(document_id="d", metadata=_metadata())
    restored = Document.model_validate(json.loads(document.model_dump_json()))
    assert restored.schema_version == SCHEMA_VERSION


def test_page_number_may_be_none_and_is_not_defaulted_to_one():
    """Nullable-not-fake: an unknown page number must serialize as null."""
    element = Element(id="e", type=ElementType.TEXT, source_backend="t")
    assert element.page_number is None
    assert json.loads(element.model_dump_json())["page_number"] is None


def test_page_records_coordinate_convention():
    page = Page(index=0, width=595, height=842)
    assert page.coordinate_origin == "top-left"
    assert page.coordinate_unit == "pt"
    assert page.is_rendered_page is True


def test_bbox_invariants_and_geometry():
    box = BBox(x0=10, y0=20, x1=110, y1=70)
    assert box.width == 100
    assert box.height == 50
    assert box.area() == 5000
    assert box.as_tuple() == (10, 20, 110, 70)


def test_bbox_iou_identical_and_disjoint():
    a = BBox(x0=0, y0=0, x1=10, y1=10)
    assert a.iou(a) == 1.0
    assert a.iou(BBox(x0=100, y0=100, x1=110, y1=110)) == 0.0


def test_table_spans_and_grid():
    table = Table(
        id="t",
        page_number=1,
        n_rows=2,
        n_cols=3,
        source_backend="t",
        cells=[
            Cell(row=0, col=0, col_span=3, text="Title", is_header=True),
            Cell(row=1, col=0, text="a"),
            Cell(row=1, col=1, text="b"),
            Cell(row=1, col=2, text="c"),
        ],
    )
    assert table.to_grid() == [["Title", "Title", "Title"], ["a", "b", "c"]]
    assert "| a | b | c |" in table.to_markdown()


def test_table_row_span_fills_grid_downwards():
    table = Table(
        id="t", page_number=1, n_rows=3, n_cols=2, source_backend="t",
        cells=[
            Cell(row=0, col=0, row_span=3, text="tall"),
            Cell(row=0, col=1, text="x"),
            Cell(row=1, col=1, text="y"),
            Cell(row=2, col=1, text="z"),
        ],
    )
    assert [row[0] for row in table.to_grid()] == ["tall", "tall", "tall"]


def test_element_table_link_resolves_through_page():
    table = Table(id="t0", page_number=1, n_rows=1, n_cols=1, source_backend="t",
                  cells=[Cell(row=0, col=0, text="v")])
    element = Element(id="e0", type=ElementType.TABLE, page_number=1, source_backend="t", table_id="t0")
    page = Page(index=0, width=1, height=1, elements=[element], tables=[table])
    linked = page.table_by_id(page.element_by_id("e0").table_id)
    assert linked is not None and linked.cells[0].text == "v"


def test_full_document_round_trips_with_all_features():
    table = Table(id="t0", page_number=1, n_rows=1, n_cols=2, source_backend="b",
                  cells=[Cell(row=0, col=0, text="k", is_header=True), Cell(row=0, col=1, text="v")])
    elements = [
        Element(id="e0", type=ElementType.HEADING, text="Title", page_number=1,
                bbox=BBox(x0=0, y0=0, x1=10, y1=5), source_backend="b", order_index=0, level=1),
        Element(id="e1", type=ElementType.TABLE, page_number=1, source_backend="b",
                table_id="t0", order_index=1),
    ]
    page = Page(index=0, width=595, height=842, elements=elements, tables=[table],
                reading_order=["e0", "e1"], source_route="digital_pdf", source_backend="b",
                notes=["a note"])
    document = Document(document_id="doc", metadata=_metadata(), pages=[page])

    restored = Document.model_validate(json.loads(document.model_dump_json()))
    assert restored.pages[0].reading_order == ["e0", "e1"]
    assert restored.pages[0].notes == ["a note"]
    assert restored.pages[0].tables[0].cells[0].is_header is True
    assert restored.pages[0].source_route == "digital_pdf"

    markdown = restored.to_markdown()
    assert "Title" in markdown
    # Table content must survive into the Markdown export, not just the JSON.
    assert "| k | v |" in markdown


def test_run_metadata_records_routing_evidence():
    metadata = _metadata(
        route_reason="looked fine",
        text_profile={"page_count": 2, "suspicious_page_ratio": 0.0},
    )
    payload = json.loads(metadata.model_dump_json())
    assert payload["route_reason"] == "looked fine"
    assert payload["text_profile"]["page_count"] == 2


def test_element_ids_are_stable_across_serialization():
    element = Element(id="p0-e7", type=ElementType.TEXT, page_number=1, source_backend="b")
    assert Element.model_validate(json.loads(element.model_dump_json())).id == "p0-e7"
