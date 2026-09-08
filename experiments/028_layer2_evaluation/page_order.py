"""028 Layer-2 view 3 -- `page_order_ok`.

Page-level ordering, measured WITHOUT any table text. Layer 1's `order_ok`
reads a string in which every page's table cells are appended, in detector
emission order, after every element on that page; 027 measured that 56.1% of
its failures across 28 arms were that appending, not reading order. This view
removes the confound by construction: it scores only non-table element text.

It uses production's own ordering semantics -- `Page.reading_order`, a list
of `Element.id` that `Document.to_markdown` already consumes -- rather than
an ordering invented here.

Honest scope. A `must_contain` string that lives inside a table cannot be
placed by a metric that excludes tables. Such strings are reported
UNMEASURABLE rather than assigned a position, because guessing one is how
`order_ok` came to mean two things at once.
"""
from __future__ import annotations

import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "src"))
sys.path.insert(0, str(REPO / "research/production_corpus"))

from run_benchmark import _norm  # noqa: E402


def ordered_elements(pg: dict) -> list[dict]:
    """Elements in production's reading order.

    `Page.reading_order` is authoritative when populated; the documented
    fallback (`Document.to_markdown`) is list order, and that fallback is
    reproduced rather than replaced.
    """
    els = pg.get("elements") or []
    ro = pg.get("reading_order") or []
    if not ro:
        return els
    by_id = {e.get("id"): e for e in els}
    out = [by_id[i] for i in ro if i in by_id]
    out += [e for e in els if e.get("id") not in set(ro)]
    return out


def page_order(doc: dict, must_contain: list[str]) -> dict:
    """Score required-string ordering over non-table text only."""
    parts, provenance = [], []
    for pg in doc.get("pages") or []:
        for el in ordered_elements(pg):
            if el.get("type") == "table":
                continue
            t = el.get("text")
            if t:
                parts.append(t)
                provenance.append({"page": pg.get("index"), "element_id": el.get("id"),
                                   "type": el.get("type")})
    text = _norm("\n".join(parts))

    table_texts = [c.get("text", "") for pg in (doc.get("pages") or [])
                   for tb in (pg.get("tables") or []) for c in (tb.get("cells") or [])]
    table_blob = _norm("\n".join(t for t in table_texts if t))

    positions, measurable, unmeasurable = [], [], []
    for s in must_contain:
        n = _norm(s)
        i = text.find(n)
        if i >= 0:
            positions.append(i)
            measurable.append(s)
        elif n and n in table_blob:
            unmeasurable.append({"string": s, "reason": "lives in a table cell"})
        else:
            unmeasurable.append({"string": s, "reason": "not found in non-table text"})

    # reading_order health, independent of any ground truth
    ro_declared = ro_covering = pages = 0
    for pg in doc.get("pages") or []:
        pages += 1
        ro = pg.get("reading_order") or []
        ids = {e.get("id") for e in (pg.get("elements") or [])}
        if ro:
            ro_declared += 1
            if set(ro) == ids:
                ro_covering += 1

    return {
        "page_order_ok": positions == sorted(positions),
        "strings_measurable": len(measurable),
        "strings_unmeasurable": len(unmeasurable),
        "unmeasurable_detail": unmeasurable,
        "positions": positions,
        "non_table_chars": len(text),
        "reading_order": {
            "pages": pages,
            "pages_with_reading_order": ro_declared,
            "pages_where_it_covers_every_element": ro_covering,
        },
        "status": ("MEASURABLE" if measurable else "UNMEASURABLE"),
    }
