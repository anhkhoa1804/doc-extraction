"""Physical grid/content must survive Markdown's table representation."""
from xml.etree import ElementTree

import pytest

from doc_extraction.schemas.document import Document, RunMetadata
from doc_extraction.schemas.element import Element, ElementType
from doc_extraction.schemas.page import Page
from doc_extraction.schemas.table import Cell, Table


def test_simple_table_keeps_existing_markdown():
    table = Table(id="t", n_rows=1, n_cols=2, source_backend="test",
                  cells=[Cell(row=0, col=0, text="a"), Cell(row=0, col=1, text="b")])
    assert table.to_markdown() == "| a | b |\n| --- | --- |"


@pytest.mark.parametrize("text", ["a | b", "a\nb", "a\rb", "a | <script>&x</script>"])
def test_cell_delimiters_and_markup_do_not_change_table_shape(text):
    table = Table(id="t", n_rows=1, n_cols=1, source_backend="test",
                  cells=[Cell(row=0, col=0, text=text)])
    tree = ElementTree.fromstring(table.to_markdown())
    assert len(tree.findall("tr")) == 1
    assert len(tree.findall(".//td")) == 1
    # XML normalizes CR to LF; content otherwise remains verbatim.
    assert tree.find(".//td").text == text.replace("\r", "\n")
    assert tree.find(".//script") is None


def test_spans_preserve_single_cell_ownership():
    table = Table(id="t", n_rows=2, n_cols=3, source_backend="test", cells=[
        Cell(row=0, col=0, row_span=2, text="vertical"),
        Cell(row=0, col=1, col_span=2, text="heading", is_header=True),
        Cell(row=1, col=1, text="a"), Cell(row=1, col=2, text="b"),
    ])
    html = table.to_markdown()
    tree = ElementTree.fromstring(html)
    assert tree.find(".//td").attrib == {"rowspan": "2"}
    assert tree.find(".//th").attrib == {"colspan": "2"}
    assert html.count("vertical") == html.count("heading") == 1
    assert len(list(tree.iter("td"))) == 3


def test_document_default_markdown_path_preserves_table_spans():
    """The normal Document serializer must use the safe Table serializer."""
    table = Table(
        id="t0",
        n_rows=1,
        n_cols=2,
        source_backend="test",
        cells=[Cell(row=0, col=0, col_span=2, text="merged heading", is_header=True)],
    )
    document = Document(
        document_id="doc0",
        metadata=RunMetadata(
            input_filename="fixture.png",
            input_path="fixture.png",
            file_hash_sha256="0" * 64,
            file_type="image/png",
            route="image",
            pipeline="baseline",
            backend="test",
            timestamp="2026-01-01T00:00:00Z",
        ),
        pages=[
            Page(
                index=0,
                width=100,
                height=80,
                coordinate_unit="px",
                elements=[
                    Element(
                        id="e0",
                        type=ElementType.TABLE,
                        source_backend="test",
                        table_id="t0",
                        order_index=0,
                    )
                ],
                tables=[table],
                reading_order=["e0"],
            )
        ],
    )

    markdown = document.to_markdown()
    table_markup = markdown[markdown.index("<table>"):markdown.index("</table>") + len("</table>")]
    tree = ElementTree.fromstring(table_markup)
    assert tree.find(".//th").attrib == {"colspan": "2"}
    assert tree.find(".//th").text == "merged heading"


def test_ambiguous_spans_fail_closed():
    table = Table(id="t", n_rows=1, n_cols=2, source_backend="test", cells=[
        Cell(row=0, col=0, col_span=2, text="a"), Cell(row=0, col=1, text="b"),
    ])
    with pytest.raises(ValueError, match="overlapping cells"):
        table.to_markdown()
