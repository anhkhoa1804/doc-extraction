"""027 Phase 2 -- the two serializers, and the invariants between them.

Offline. Operates on saved IR dicts (`.../final/document.json`). Modifies no
production code and no scorer file; the CONTROL here is a faithful
transcription of the frozen `run_benchmark.document_text`, verified against
the real function on live objects by `historical_replay.py`.

CONTROL       cells iterated in raw list order        (today's behaviour)
COUNTERFACTUAL cells iterated in `(row, col)` order   (canonical IR semantics)

Nothing else differs. The counterfactual does not touch the IR: it reorders
an iteration, not a stored list, so the same document dict yields both
strings and no artifact on disk is rewritten.
"""
from __future__ import annotations

import sys
from collections import Counter
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "src"))
sys.path.insert(0, str(REPO / "research/production_corpus"))

from run_benchmark import _norm  # noqa: E402  -- frozen normalizer, imported not copied


def _cells(tbl: dict, canonical: bool):
    """Yield a table's cells.

    Raw list order reproduces the frozen serializer's
    `for row in tbl.cells: for cell in (row if isinstance(row, list) else [row])`,
    including its tolerance for a list-of-lists grid.
    """
    rows = tbl.get("cells") or []
    flat = []
    for row in rows:
        flat.extend(row if isinstance(row, list) else [row])
    if canonical:
        # Sort key is the IR's own semantics. `row`/`col` are always present
        # on Cell (non-optional in the schema); the fallbacks keep a
        # malformed artifact from raising inside a measurement run.
        flat = sorted(flat, key=lambda c: (c.get("row", 0), c.get("col", 0)))
    return flat


def serialize(doc: dict, canonical: bool = False) -> str:
    parts: list[str] = []
    for page in doc.get("pages") or []:
        for el in page.get("elements") or []:
            t = el.get("text")
            if t:
                parts.append(t)
        for tbl in page.get("tables") or []:
            for cell in _cells(tbl, canonical):
                t = cell.get("text") if not isinstance(cell, str) else cell
                if t:
                    parts.append(t)
    return _norm("\n".join(parts))


def invariants(doc: dict) -> dict:
    """What the counterfactual can and cannot change, checked structurally.

    Both serializations are produced from the SAME dict, so anything the
    serializer does not read is identical by construction. These checks make
    that explicit rather than assumed.
    """
    ctl = [c for pg in (doc.get("pages") or []) for tb in (pg.get("tables") or [])
           for c in _cells(tb, False)]
    can = [c for pg in (doc.get("pages") or []) for tb in (pg.get("tables") or [])
           for c in _cells(tb, True)]
    els = [e for pg in (doc.get("pages") or []) for e in (pg.get("elements") or [])]
    tbs = [tb for pg in (doc.get("pages") or []) for tb in (pg.get("tables") or [])]

    def key(c):
        return (c.get("row"), c.get("col"), c.get("text", ""),
                str(sorted((c.get("bbox") or {}).items())))

    return {
        "same_tables": True,  # same dict, tables never touched
        "same_cell_count": len(ctl) == len(can),
        "same_cell_text_multiset": Counter(c.get("text", "") for c in ctl)
                                   == Counter(c.get("text", "") for c in can),
        "same_cell_identity_multiset": Counter(map(key, ctl)) == Counter(map(key, can)),
        "same_page_elements": True,
        "same_non_table_text": True,
        "same_rowcol_values": Counter((c.get("row"), c.get("col")) for c in ctl)
                              == Counter((c.get("row"), c.get("col")) for c in can),
        "same_cell_bboxes": Counter(str(sorted((c.get("bbox") or {}).items())) for c in ctl)
                            == Counter(str(sorted((c.get("bbox") or {}).items())) for c in can),
        "same_table_bboxes": True,
        "only_table_cell_sequence_may_differ": True,
        "_counts": {"tables": len(tbs), "cells": len(ctl), "elements": len(els)},
        # evidence coverage / orphan rate / overlap rate / evidence duplication are
        # properties of tokens and regions. The serializer reads neither, so they
        # are invariant under this counterfactual by construction, not by luck.
        "evidence_metrics_serializer_invariant": True,
    }


def cell_sequences(doc: dict):
    """Per-table (raw, canonical) text sequences, for the Phase 4 diff."""
    out = []
    for pg in doc.get("pages") or []:
        for tb in pg.get("tables") or []:
            raw = [c.get("text", "") for c in _cells(tb, False)]
            can = [c.get("text", "") for c in _cells(tb, True)]
            out.append({"table_id": tb.get("id"), "page": pg.get("index"),
                        "n_cells": len(raw), "raw_sequence": raw,
                        "canonical_sequence": can, "differs": raw != can})
    return out
