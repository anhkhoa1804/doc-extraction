"""Ablations must isolate their variable and verify retained predictions."""
import pytest

from benchmarks.scripts.classic_completion_ablation import (
    formula_configs,
    verified_replacement,
)
from doc_extraction.schemas.element import Element, ElementType
from doc_extraction.schemas.page import Page
from doc_extraction.schemas.table import Cell, Table


def test_formula_arms_differ_only_in_enrichment():
    base = {"device": "cuda", "ocr_languages": ["en", "vi"], "limits": {"max_runtime_seconds": 300}}
    off, on = formula_configs(base, ".cache/docling")
    assert off | {"docling_formula_enrichment": True} == on
    assert base == {"device": "cuda", "ocr_languages": ["en", "vi"], "limits": {"max_runtime_seconds": 300}}


def test_replay_requires_exact_baseline_content():
    table = Table(id="t", n_rows=1, n_cols=1, source_backend="test", cells=[Cell(row=0, col=0, text="a|b")])
    page = Page(index=0, width=10, height=10, tables=[table], reading_order=["e"],
                elements=[Element(id="e", type=ElementType.TABLE, table_id="t", source_backend="test")])
    result = verified_replacement(page, "| a|b |\n| --- |\n")
    assert "<td>a|b</td>" in result
    with pytest.raises(ValueError, match="does not reproduce"):
        verified_replacement(page, "| different |\n| --- |\n")
