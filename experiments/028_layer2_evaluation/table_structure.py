"""028 Layer-2 view 2 -- `table_structure`.

Structure as data, not as a flattened string: the `(row, col)` grid, its
declared shape, cell and table geometry, and spanning information. Every
field read here exists in the production IR; nothing is inferred.

`row_span`/`col_span` ARE present on `Cell` (defaults 1), so spanning is
reported. Whether any backend in this repo ever sets them above 1 is an
observation this view makes, not an assumption it starts from.
"""
from __future__ import annotations

from collections import Counter

from table_text import cells_in


def _bbox_ok(b) -> bool:
    return (isinstance(b, dict) and b.get("x1", 0) >= b.get("x0", 0)
            and b.get("y1", 0) >= b.get("y0", 0))


def _inside(inner, outer, tol=1.0) -> bool:
    if not (_bbox_ok(inner) and _bbox_ok(outer)):
        return False
    return (inner["x0"] >= outer["x0"] - tol and inner["y0"] >= outer["y0"] - tol
            and inner["x1"] <= outer["x1"] + tol and inner["y1"] <= outer["y1"] + tol)


def table_structure(doc: dict) -> list[dict]:
    out = []
    for pg in doc.get("pages") or []:
        for tbl in pg.get("tables") or []:
            cells = cells_in(tbl, True)
            coords = [(c.get("row"), c.get("col")) for c in cells]
            rows = sorted({r for r, _ in coords})
            cols = sorted({c for _, c in coords})
            boxes = [c.get("bbox") for c in cells]
            tb = tbl.get("bbox")
            out.append({
                "table_id": tbl.get("id"),
                "page_index": pg.get("index"),
                "source_backend": tbl.get("source_backend"),
                "confidence": tbl.get("confidence"),
                "declared_n_rows": tbl.get("n_rows"),
                "declared_n_cols": tbl.get("n_cols"),
                "observed_n_rows": len(rows),
                "observed_n_cols": len(cols),
                "n_cells": len(cells),
                "expected_cells_if_dense": (tbl.get("n_rows") or 0) * (tbl.get("n_cols") or 0),
                "row_values": rows,
                "col_values": cols,
                "coordinates": [list(c) for c in coords],
                "duplicate_coordinates": [list(k) for k, v in Counter(coords).items() if v > 1],
                "empty_cells": sum(1 for c in cells if not c.get("text")),
                "header_cells": sum(1 for c in cells if c.get("is_header")),
                "spanning_cells": sum(1 for c in cells
                                      if (c.get("row_span", 1) or 1) > 1
                                      or (c.get("col_span", 1) or 1) > 1),
                "table_bbox": tb,
                "table_bbox_valid": _bbox_ok(tb),
                "cells_with_bbox": sum(1 for b in boxes if isinstance(b, dict)),
                "cells_with_valid_bbox": sum(1 for b in boxes if _bbox_ok(b)),
                "cells_inside_table_bbox": (sum(1 for b in boxes if _inside(b, tb))
                                            if _bbox_ok(tb) else None),
            })
    return out
