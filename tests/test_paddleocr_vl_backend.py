import json
from pathlib import Path

import pytest

from doc_extraction.backends.paddleocr_vl_backend import (
    PaddleOCRVLBackend,
    page_from_paddle_result,
    validate_worker_page,
    validate_worker_response,
)
from doc_extraction.cli import _write_backend_phase_timings
from doc_extraction.schemas.element import ElementType


class FakeResult:
    def __init__(self, res: dict) -> None:
        self.json = {"res": res}


def test_paddle_result_maps_regions_order_geometry_and_formula() -> None:
    page = page_from_paddle_result(
        FakeResult(
            {
                "width": 1000,
                "height": 1400,
                "parsing_res_list": [
                    {
                        "block_id": 3,
                        "block_label": "paragraph_title",
                        "block_content": "Chapter",
                        "block_bbox": [10, 20, 200, 60],
                        "block_order": 1,
                    },
                    {
                        "block_id": 4,
                        "block_label": "display_formula",
                        "block_content": "x^2 + y^2",
                        "block_bbox": [20, 80, 300, 140],
                        "block_order": 2,
                    },
                ],
            }
        )
    )

    assert page.width == 1000
    assert page.height == 1400
    assert [element.type for element in page.elements] == [ElementType.HEADING, ElementType.FORMULA]
    assert page.elements[0].bbox is not None
    assert page.elements[0].bbox.as_tuple() == (10.0, 20.0, 200.0, 60.0)
    assert page.elements[1].confidence is None
    assert page.reading_order == ["p0-e0", "p0-e1"]
    assert page.elements[1].extra["model_block_label"] == "display_formula"


def test_phase_timing_is_explicitly_scoped_to_adapter_work() -> None:
    phases: dict[str, float] = {}
    page = page_from_paddle_result(
        FakeResult(
            {
                "width": 100,
                "height": 200,
                "parsing_res_list": [
                    {"block_label": "table", "block_content": "<table><tr><td>x</td></tr></table>"}
                ],
            }
        ),
        phases,
    )

    assert len(page.tables) == 1
    assert phases.keys() == {
        "result_json_decode_seconds",
        "table_parsing_seconds",
        "canonical_mapping_inclusive_seconds",
    }
    assert all(value >= 0 for value in phases.values())


def test_backend_timing_diagnostic_is_written_outside_canonical_document(tmp_path: Path) -> None:
    class Backend:
        def __init__(self) -> None:
            self.last_phase_timings = {"pipeline_predict_seconds": 12.5}

    _write_backend_phase_timings(tmp_path, Backend(), "success")

    diagnostic = json.loads(
        (tmp_path / "diagnostics" / "backend_phase_timings.json").read_text(encoding="utf-8")
    )
    assert diagnostic == {
        "status": "success",
        "backend": "Backend",
        "phases": {"pipeline_predict_seconds": 12.5},
    }


def test_paddle_table_html_maps_cells_and_spans_without_fake_cell_geometry() -> None:
    page = page_from_paddle_result(
        FakeResult(
            {
                "width": 400,
                "height": 600,
                "parsing_res_list": [
                    {
                        "block_label": "table",
                        "block_content": (
                            "<table><tr><th rowspan='2'>A</th><th>B</th></tr>"
                            "<tr><td colspan='2'>C&amp;D</td></tr></table>"
                        ),
                        "block_bbox": [1, 2, 300, 500],
                        "block_order": 1,
                    }
                ],
            }
        )
    )

    assert len(page.tables) == 1
    assert page.elements[0].type == ElementType.TABLE
    assert page.elements[0].table_id == page.tables[0].id
    assert (page.tables[0].n_rows, page.tables[0].n_cols) == (2, 3)
    assert [(cell.row, cell.col, cell.row_span, cell.col_span, cell.text) for cell in page.tables[0].cells] == [
        (0, 0, 2, 1, "A"),
        (0, 1, 1, 1, "B"),
        (1, 1, 1, 2, "C&D"),
    ]
    assert all(cell.bbox is None and cell.confidence is None for cell in page.tables[0].cells)


def test_malformed_table_is_retained_as_text_and_disclosed() -> None:
    page = page_from_paddle_result(
        FakeResult(
            {
                "width": 10,
                "height": 20,
                "parsing_res_list": [
                    {"block_label": "table", "block_content": "not a table", "block_order": 1}
                ],
            }
        )
    )
    assert page.elements[0].type == ElementType.PARAGRAPH
    assert page.elements[0].text == "not a table"
    assert page.tables == []
    assert page.notes and "E2E_UNSUPPORTED" in page.notes[0]


def test_table_dimensions_include_rowspan_beyond_final_explicit_row() -> None:
    page = page_from_paddle_result(
        FakeResult(
            {
                "width": 100,
                "height": 100,
                "parsing_res_list": [
                    {
                        "block_label": "table",
                        "block_content": "<table><tr><td rowspan='2'>continued</td></tr></table>",
                    }
                ],
            }
        )
    )

    assert page.tables[0].n_rows == 2
    assert page.tables[0].cells[0].row == 0
    assert page.tables[0].cells[0].row_span == 2
    assert validate_worker_page(page.model_dump(mode="json")) == page


@pytest.mark.parametrize("dimensions", [(0, 4), (4, 0), (float("nan"), 3)])
def test_invalid_model_dimensions_fail_loudly(dimensions: tuple[float, float]) -> None:
    with pytest.raises(ValueError, match="dimensions"):
        page_from_paddle_result(
            FakeResult({"width": dimensions[0], "height": dimensions[1], "parsing_res_list": []})
        )


def test_backend_uses_injected_pipeline_and_returns_canonical_document(tmp_path: Path) -> None:
    source = tmp_path / "page.png"
    source.write_bytes(b"image-fixture")

    class FakePipeline:
        def predict(self, path: str) -> list[FakeResult]:
            assert path == str(source)
            return [FakeResult({"width": 8, "height": 9, "parsing_res_list": []})]

    backend = PaddleOCRVLBackend(pipeline=FakePipeline())

    class Config:
        device = "cuda"

    document = backend.convert(source, Config())
    assert document.metadata.backend == "paddleocr_vl"
    assert document.metadata.device == "cuda"
    assert document.pages[0].width == 8
    assert document.pages[0].elements == []


def test_worker_page_validation_rejects_broken_reading_order_and_table_links() -> None:
    page = page_from_paddle_result(
        FakeResult(
            {
                "width": 100,
                "height": 100,
                "parsing_res_list": [
                    {"block_label": "text", "block_content": "x", "block_bbox": [1, 2, 10, 12]}
                ],
            }
        )
    )
    value = page.model_dump(mode="json")
    value["reading_order"] = []
    with pytest.raises(ValueError, match="reading order"):
        validate_worker_page(value)


def test_worker_response_is_exact_bounded_protocol_and_identity_checked() -> None:
    expected_hash = "a" * 64
    page = page_from_paddle_result(FakeResult({"width": 8, "height": 9, "parsing_res_list": []}))
    response = {
        "state": "completed",
        "input_sha256": expected_hash,
        "page": page.model_dump(mode="json"),
        "model_versions": {"model": "fixture@revision"},
        "phase_timings": {"pipeline_predict_seconds": 0.25},
    }
    validated_page, versions, timings = validate_worker_response(response, expected_hash)
    assert validated_page == page
    assert versions == {"model": "fixture@revision"}
    assert timings == {"pipeline_predict_seconds": 0.25}

    for mutation, message in [
        ({"unexpected": True}, "unexpected"),
        ({"page": None}, "page"),
        ({"input_sha256": "b" * 64}, "identity"),
        ({"phase_timings": {"pipeline_predict_seconds": float("nan")}}, "phase_timings"),
        ({"model_versions": {}}, "model_versions"),
    ]:
        bad = {**response, **mutation}
        with pytest.raises(ValueError, match=message):
            validate_worker_response(bad, expected_hash)


def test_worker_page_rejects_unrecognized_nested_fields() -> None:
    page = page_from_paddle_result(FakeResult({"width": 8, "height": 9, "parsing_res_list": []}))
    payload = page.model_dump(mode="json")
    payload["unrecognized"] = "must not be silently dropped"
    with pytest.raises(ValueError, match="Extra inputs are not permitted"):
        validate_worker_page(payload)
