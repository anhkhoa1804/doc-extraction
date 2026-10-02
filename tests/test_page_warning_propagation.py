from doc_extraction.cli import _collect_page_warnings
from doc_extraction.schemas.page import Page


def test_page_warnings_survive_run_boundary_without_legacy_text_heuristics() -> None:
    page = Page(
        index=0,
        width=0,
        height=0,
        is_rendered_page=False,
        notes=[
            "E2E_UNSUPPORTED: malformed table retained as text",
            "DOCX pagination is a renderer property and is not available",
            "XLSX worksheet 1: 'Overview'",
            "new backend diagnostic unknown to older code",
        ],
    )

    assert _collect_page_warnings([page]) == [
        "page 1: E2E_UNSUPPORTED: malformed table retained as text",
        "page 1: new backend diagnostic unknown to older code",
    ]
