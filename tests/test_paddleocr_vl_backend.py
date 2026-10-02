from pathlib import Path

import pytest

from doc_extraction.backends.paddleocr_vl_backend import (
    PaddleOCRVLBackend,
    page_from_paddle_result,
)
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
