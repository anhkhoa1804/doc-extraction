"""028 Layer-2 view 1 -- `table_text`.

Table text, represented independently of the document-level flattened string.
Consumes only fields the IR actually has (see `ir_schema_inventory.json`):
`Table.id`, `Cell.row`, `Cell.col`, `Cell.text`.

Two orderings are produced from the SAME cells so the 027 counterfactual is
reproducible here without mutating anything:

  legacy    raw `Table.cells` list order -- what Layer 1's serializer reads
  canonical `(row, col)` order          -- the IR's own semantics

No OCR, no re-recognition, and no normalization beyond `_norm`, which is
imported from the frozen benchmark so Layer 2 and Layer 1 agree on what a
string *is* even where they disagree on what order strings come in.
"""
from __future__ import annotations

import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "src"))
sys.path.insert(0, str(REPO / "research/production_corpus"))

from run_benchmark import _norm  # noqa: E402  -- frozen normalizer, imported


def _flat(tbl: dict) -> list[dict]:
    out = []
    for row in tbl.get("cells") or []:
        out.extend(row if isinstance(row, list) else [row])
    return out


def cells_in(tbl: dict, canonical: bool) -> list[dict]:
    flat = _flat(tbl)
    if canonical:
        flat = sorted(flat, key=lambda c: (c.get("row", 0), c.get("col", 0)))
    return flat


def table_text(doc: dict) -> list[dict]:
    """Per-table text views. `text` joins non-empty cells with a newline, the
    same join Layer 1 uses, so the only difference between the two strings is
    sequence."""
    out = []
    for pg in doc.get("pages") or []:
        for tbl in pg.get("tables") or []:
            leg = [c.get("text", "") for c in cells_in(tbl, False)]
            can = [c.get("text", "") for c in cells_in(tbl, True)]
            out.append({
                "table_id": tbl.get("id"),
                "page_index": pg.get("index"),
                "n_cells": len(leg),
                "legacy_sequence": leg,
                "canonical_sequence": can,
                "legacy_text": _norm("\n".join(t for t in leg if t)),
                "canonical_text": _norm("\n".join(t for t in can if t)),
                "sequence_differs": leg != can,
                "text_multiset_identical": sorted(leg) == sorted(can),
                "non_empty_cells": sum(1 for t in can if t),
                "empty_cells": sum(1 for t in can if not t),
            })
    return out


def non_table_text(doc: dict) -> str:
    """Document text with every table excluded. This is the half of the
    document whose ordering is genuinely a page-reading-order question, and
    it is what `page_order` scores against."""
    parts = []
    for pg in doc.get("pages") or []:
        for el in pg.get("elements") or []:
            if el.get("type") == "table":
                continue
            if el.get("text"):
                parts.append(el["text"])
    return _norm("\n".join(parts))
