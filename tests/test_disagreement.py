from __future__ import annotations

from doc_extraction.evaluation.disagreement import compare_pages, page_text
from doc_extraction.schemas.element import Element, ElementType
from doc_extraction.schemas.page import Page


def _page(text: str, element_id: str) -> Page:
    return Page(
        index=0,
        width=100,
        height=100,
        elements=[Element(id=element_id, type=ElementType.TEXT, text=text, source_backend="test")],
        reading_order=[element_id],
    )


def test_disagreement_does_not_infer_text_order_from_element_storage() -> None:
    left = _page("same storage order", "left")
    right = _page("same storage order", "right")
    left.reading_order = []
    right.reading_order = []

    assert page_text(left) is None
    assert page_text(right) is None
    assert compare_pages(left, right)["text_similarity"] is None


def test_disagreement_uses_explicit_reading_order_when_available() -> None:
    left = _page("ordered text", "left")
    right = _page("ordered text", "right")

    assert page_text(left) == "ordered text"
    assert compare_pages(left, right)["text_similarity"] == 1.0
