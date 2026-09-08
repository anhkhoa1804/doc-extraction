"""028 Layer-2 view 4 -- `table_structural_integrity`.

Whether a table's cell structure is internally COHERENT. Deliberately not a
sortedness test: a table whose cells happen to be stored in a tidy order can
still declare 4 rows and populate 3, or place two cells at the same
coordinate. 026 called list order "structural integrity" and that conflated
storage order with structure; this separates them.

Checks, each independently reported:

  coords_in_declared_range    every row in [0, n_rows), every col in [0, n_cols)
  no_duplicate_coordinates    (row, col) is unique -- it IS the cell's identity
  rows_contiguous             occupied rows are 0..k with no gap
  cols_contiguous             occupied cols are 0..k with no gap
  row_order_matches_geometry   rows ordered by min(y0) equal rows ordered by index
  col_order_matches_geometry   cols ordered by min(x0) equal cols ordered by index
  rows_vertically_coherent     cells sharing a row occupy a common y band
  cols_horizontally_coherent   cells sharing a col occupy a common x band
  all_cell_bboxes_valid        x0<=x1 and y0<=y1
  cells_within_table_bbox      every cell box inside the table box (1px tolerance)

`list_order_canonical` is reported SEPARATELY and is explicitly not part of
the integrity verdict.
"""
from __future__ import annotations

from table_text import cells_in
from table_structure import _bbox_ok, _inside


def _coherent(cells, coord_key, lo_key, hi_key):
    """Do cells sharing a coordinate actually occupy a common band?

    A row's cells share a baseline, so their y-ranges overlap. Relabelling
    cells to fake a canonical storage order breaks this immediately -- the
    `renumbering row/col` attack in `anti_gaming.py` put a y=10-90 cell and a
    y=110-190 cell in the same row and the earlier min(y0) group test tied
    and passed it. Overlap is checked pairwise against the group's
    intersection, which is order-free and needs no tolerance constant.
    """
    groups = {}
    for c in cells:
        b = c.get("bbox")
        if not _bbox_ok(b):
            continue
        groups.setdefault(c.get(coord_key), []).append(b)
    for boxes in groups.values():
        if len(boxes) < 2:
            continue
        lo = max(b[lo_key] for b in boxes)
        hi = min(b[hi_key] for b in boxes)
        if hi <= lo:            # no band common to every cell of this group
            return False
    return True


def _order_matches(cells, axis_key, coord_key):
    groups = {}
    for c in cells:
        b = c.get("bbox")
        if not _bbox_ok(b):
            continue
        groups.setdefault(c.get(coord_key), []).append(b[axis_key])
    if len(groups) < 2:
        return True, len(groups)
    by_geom = [k for k, _ in sorted(groups.items(), key=lambda kv: min(kv[1]))]
    return by_geom == sorted(groups), len(groups)


def structural_integrity(doc: dict) -> list[dict]:
    out = []
    for pg in doc.get("pages") or []:
        for tbl in pg.get("tables") or []:
            cells = cells_in(tbl, True)
            raw = cells_in(tbl, False)
            nr, nc = tbl.get("n_rows") or 0, tbl.get("n_cols") or 0
            coords = [(c.get("row"), c.get("col")) for c in cells]
            rows = sorted({r for r, _ in coords})
            cols = sorted({c for _, c in coords})
            tb = tbl.get("bbox")

            row_geom_ok, n_rowgroups = _order_matches(cells, "y0", "row")
            col_geom_ok, n_colgroups = _order_matches(cells, "x0", "col")

            checks = {
                "coords_in_declared_range": all(
                    isinstance(r, int) and isinstance(c, int)
                    and 0 <= r < nr and 0 <= c < nc for r, c in coords) if cells else True,
                "no_duplicate_coordinates": len(set(coords)) == len(coords),
                "rows_contiguous": rows == list(range(len(rows))) if rows else True,
                "cols_contiguous": cols == list(range(len(cols))) if cols else True,
                "row_order_matches_geometry": row_geom_ok,
                "col_order_matches_geometry": col_geom_ok,
                "rows_vertically_coherent": _coherent(cells, "row", "y0", "y1"),
                "cols_horizontally_coherent": _coherent(cells, "col", "x0", "x1"),
                "all_cell_bboxes_valid": all(_bbox_ok(c.get("bbox")) for c in cells) if cells else True,
                # Only cells whose OWN bbox is valid are containment-tested.
                # Without this guard an invalid cell box fails both checks and one
                # defect is reported as two -- caught by control 07_invalid_bbox.
                "cells_within_table_bbox": (
                    all(_inside(c.get("bbox"), tb) for c in cells if _bbox_ok(c.get("bbox")))
                    if _bbox_ok(tb) and cells else True),
            }
            out.append({
                "table_id": tbl.get("id"),
                "page_index": pg.get("index"),
                "n_cells": len(cells),
                "declared_shape": [nr, nc],
                "observed_shape": [len(rows), len(cols)],
                "checks": checks,
                "structurally_valid": all(checks.values()),
                "failed_checks": [k for k, v in checks.items() if not v],
                # storage order, reported but NOT part of the verdict
                "list_order_canonical": [(c.get("row"), c.get("col")) for c in raw] == coords,
            })
    return out
