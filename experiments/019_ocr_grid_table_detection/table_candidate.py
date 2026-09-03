#!/usr/bin/env python
"""019 -- OCR-grid table candidate detection, prototype (not production
code). Pure function of a token list + a search bbox; no model, no GPU.

Core idea: cluster tokens into physical rows (y-overlap, same primitive
as order_recovery's line clustering), then cluster the SET of tokens
across those rows into columns by x-overlap (a column is a set of tokens
whose x-ranges repeat across multiple rows -- table columns are stable
left edges, prose is not). Score the resulting grid on measurable,
inspected-not-guessed features.
"""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class Tok:
    text: str
    x0: float
    y0: float
    x1: float
    y1: float


def _y_overlap(a: Tok, b: Tok) -> float:
    inter = max(0.0, min(a.y1, b.y1) - max(a.y0, b.y0))
    shorter = min(max(1e-6, a.y1 - a.y0), max(1e-6, b.y1 - b.y0))
    return inter / shorter


def _x_overlap(a: Tok, b: Tok) -> float:
    inter = max(0.0, min(a.x1, b.x1) - max(a.x0, b.x0))
    shorter = min(max(1e-6, a.x1 - a.x0), max(1e-6, b.x1 - b.x0))
    return inter / shorter


def cluster_rows(tokens: list[Tok], y_overlap_min: float = 0.3) -> list[list[Tok]]:
    remaining = list(tokens)
    rows: list[list[Tok]] = []
    while remaining:
        cluster = [remaining.pop(0)]
        changed = True
        while changed:
            changed = False
            still = []
            for t in remaining:
                if any(_y_overlap(t, m) >= y_overlap_min for m in cluster):
                    cluster.append(t)
                    changed = True
                else:
                    still.append(t)
            remaining = still
        rows.append(cluster)
    rows.sort(key=lambda r: sum(t.y0 for t in r) / len(r))
    for r in rows:
        r.sort(key=lambda t: t.x0)
    return rows


def cluster_columns(rows: list[list[Tok]], x_overlap_min: float = 0.3) -> list[tuple[float, float]]:
    """Column bands: x-ranges that recur across >= 2 different rows.
    Built by clustering EVERY token's x-range (regardless of row) by
    mutual x-overlap, then keeping only clusters whose members come from
    at least 2 distinct rows -- a single wide token spanning most of the
    page (a paragraph, a merged header) forms its own one-row cluster and
    is correctly excluded here, not counted as a "column"."""
    all_tokens = [(ri, t) for ri, row in enumerate(rows) for t in row]
    remaining = list(all_tokens)
    clusters: list[list[tuple[int, Tok]]] = []
    while remaining:
        cluster = [remaining.pop(0)]
        changed = True
        while changed:
            changed = False
            still = []
            for item in remaining:
                if any(_x_overlap(item[1], m[1]) >= x_overlap_min for m in cluster):
                    cluster.append(item)
                    changed = True
                else:
                    still.append(item)
            remaining = still
        clusters.append(cluster)

    bands = []
    for cluster in clusters:
        distinct_rows = {ri for ri, _ in cluster}
        if len(distinct_rows) < 2:
            continue
        x0 = min(t.x0 for _, t in cluster)
        x1 = max(t.x1 for _, t in cluster)
        bands.append((x0, x1))
    bands.sort()
    return bands


@dataclass
class TableCandidate:
    bbox: tuple[float, float, float, float] | None
    n_rows: int
    n_cols: int
    row_regularity: float   # 1.0 = perfectly uniform row heights
    coverage: float         # fraction of row x col grid positions populated
    score: float
    row_bands: list[list[Tok]] = field(default_factory=list)
    col_bands: list[tuple[float, float]] = field(default_factory=list)


def _row_height_regularity(rows: list[list[Tok]]) -> float:
    if len(rows) < 2:
        return 0.0
    heights = [max(t.y1 for t in r) - min(t.y0 for t in r) for r in rows]
    mean = sum(heights) / len(heights)
    if mean <= 0:
        return 0.0
    var = sum((h - mean) ** 2 for h in heights) / len(heights)
    std = var ** 0.5
    return max(0.0, 1.0 - std / mean)


def _coverage(rows: list[list[Tok]], col_bands: list[tuple[float, float]]) -> float:
    if not rows or not col_bands:
        return 0.0
    populated = 0
    for row in rows:
        for (cx0, cx1) in col_bands:
            if any(_x_overlap(t, Tok("", cx0, row[0].y0, cx1, row[0].y1)) > 0 for t in row):
                populated += 1
    return populated / (len(rows) * len(col_bands))


def detect_table_candidate(
    tokens: list[Tok],
    search_bbox: tuple[float, float, float, float] | None = None,
    min_rows: int = 3,
    min_cols: int = 2,
) -> TableCandidate:
    """Pure geometric table-candidate detector. Returns the best candidate
    found (score may be low -- caller decides the acceptance threshold).
    `search_bbox`, if given, restricts consideration to tokens whose
    center falls inside it (e.g. a layout region already flagged
    `picture`, or Table Transformer's own low-confidence candidate box)."""
    if search_bbox is not None:
        sx0, sy0, sx1, sy1 = search_bbox
        tokens = [t for t in tokens
                  if sx0 <= (t.x0 + t.x1) / 2 <= sx1 and sy0 <= (t.y0 + t.y1) / 2 <= sy1]

    rows = cluster_rows(tokens)
    col_bands = cluster_columns(rows)

    if len(rows) < min_rows or len(col_bands) < min_cols:
        return TableCandidate(bbox=None, n_rows=len(rows), n_cols=len(col_bands),
                               row_regularity=0.0, coverage=0.0, score=0.0,
                               row_bands=rows, col_bands=col_bands)

    regularity = _row_height_regularity(rows)
    coverage = _coverage(rows, col_bands)
    # Score: requires BOTH structural repetition (>=3 rows, >=2 columns
    # that recur) AND regularity/coverage -- a single strong signal alone
    # (e.g. many rows of unrelated paragraph text with coincidentally
    # overlapping left margins) should not score highly on its own.
    score = min(1.0, (len(rows) - 1) / 4) * min(1.0, len(col_bands) / 3) * regularity * max(coverage, 0.3)

    all_x = [t.x0 for row in rows for t in row] + [t.x1 for row in rows for t in row]
    all_y = [t.y0 for row in rows for t in row] + [t.y1 for row in rows for t in row]
    bbox = (min(all_x), min(all_y), max(all_x), max(all_y)) if all_x else None

    return TableCandidate(bbox=bbox, n_rows=len(rows), n_cols=len(col_bands),
                           row_regularity=round(regularity, 4), coverage=round(coverage, 4),
                           score=round(score, 4), row_bands=rows, col_bands=col_bands)
