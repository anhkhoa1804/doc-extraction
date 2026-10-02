"""Reusable test-only assertions for canonical output from any backend.

These checks cover structural/physical honesty, not extraction accuracy or
completeness against a source image.
"""

from __future__ import annotations

import json
import math

from pydantic import ValidationError

from doc_extraction.schemas.document import Document


def assert_document_conforms(document: Document) -> None:
    """Revalidate and assert canonical physical invariants shared by backends."""
    # Revalidation matters because Pydantic assignment validation is not
    # enabled: callers/tests can mutate an otherwise valid model after parse.
    validated = Document.model_validate(document.model_dump(mode="python"))
    assert validated == document
    assert validated.schema_version == "1.4.0"

    all_element_ids: set[str] = set()
    all_table_ids: set[str] = set()
    for page_index, page in enumerate(validated.pages):
        assert page.index == page_index
        assert math.isfinite(page.width) and page.width >= 0
        assert math.isfinite(page.height) and page.height >= 0
        assert page.coordinate_origin == "top-left"
        assert page.coordinate_unit in {"pt", "px", "emu"}

        ordered = page.elements_in_reading_order(require_complete=True)
        assert len(ordered) == len(page.elements)
        assert len({element.id for element in ordered}) == len(ordered)

        tables_by_id = {table.id: table for table in page.tables}
        table_owners: dict[str, int] = {table_id: 0 for table_id in tables_by_id}
        for element in page.elements:
            assert element.id not in all_element_ids, f"duplicate document element ID: {element.id}"
            all_element_ids.add(element.id)
            if element.bbox is not None:
                assert all(math.isfinite(value) for value in element.bbox.as_tuple())
                assert element.bbox.x0 <= element.bbox.x1
                assert element.bbox.y0 <= element.bbox.y1
            if element.type.value == "table":
                assert element.table_id in tables_by_id
                table_owners[element.table_id] += 1
            elif element.table_id is not None:
                raise AssertionError(f"non-table element {element.id} references a table")

        for table in page.tables:
            assert table.id not in all_table_ids, f"duplicate document table ID: {table.id}"
            all_table_ids.add(table.id)
            assert table_owners[table.id] == 1, f"table {table.id} must have exactly one owning element"
            occupied: set[tuple[int, int]] = set()
            for cell in table.cells:
                assert cell.row >= 0 and cell.col >= 0
                assert cell.row_span >= 1 and cell.col_span >= 1
                assert cell.row + cell.row_span <= table.n_rows
                assert cell.col + cell.col_span <= table.n_cols
                if cell.bbox is not None:
                    assert all(math.isfinite(value) for value in cell.bbox.as_tuple())
                slots = {
                    (row, col)
                    for row in range(cell.row, cell.row + cell.row_span)
                    for col in range(cell.col, cell.col + cell.col_span)
                }
                assert not occupied.intersection(slots), f"overlapping cells in table {table.id}"
                occupied.update(slots)

    # JSON round-trip is the physical/null/warning preservation check. It
    # does not equate runtime-varying metadata across separate runs.
    encoded = validated.model_dump_json()
    restored = Document.model_validate_json(encoded)
    assert restored == validated
    payload = json.loads(encoded)
    assert payload["metadata"]["warnings"] == validated.metadata.warnings
    assert payload["metadata"]["errors"] == validated.metadata.errors


def assert_failed_document_rejected(payload: dict[str, object]) -> None:
    """A failure payload must not validate as a published canonical Document."""
    try:
        Document.model_validate(payload)
    except ValidationError:
        return
    raise AssertionError("failed extraction was accepted as a canonical Document")
