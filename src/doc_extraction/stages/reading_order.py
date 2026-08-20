"""Stage H (part 1) — reading order.

**This is a geometric baseline, not production-grade semantic reading
order.** It exists so that (a) every route produces *some* deterministic
ordering, and (b) we have an independent ordering to diff against whatever a
backend like Docling produces — reading-order failure is one of this
project's named research interests (docs/research-roadmap.md), and you
cannot study disagreement if the only ordering available comes from the
system under study.

Algorithm (`ORDER_STRATEGY = "column-aware-xy-band"`)
----------------------------------------------------
1. **Column detection.** Project element boxes onto the x axis and look for
   a vertical gutter: an x interval that no element crosses, wide enough
   (`min_gutter_ratio` of page width) and with content on both sides. Split
   recursively, up to `max_columns`.
2. **Row banding within a column.** Sort top-to-bottom, then group
   consecutive elements into bands while they vertically overlap the band's
   running y-range (or start within `y_tolerance` of it).
3. **Left-to-right within a band**, then bands top-to-bottom, then columns
   left-to-right.

Full-width elements (spanning a detected gutter — page headers, footers,
wide tables) are kept in document flow at their vertical position rather
than being forced into one column.

Determinism
-----------
Every comparison falls back to the element's original index, so elements
with identical geometry keep a stable, input-order-defined relationship.
The output is a pure function of the input list.

Known limitations (measured, not hypothetical)
----------------------------------------------
* Gutter detection needs a genuinely empty vertical band. Columns separated
  only by alignment (no gap crossing the full page height) are not split.
* Ordering is geometric only: it has no notion of continuation, so a
  sentence broken across a column boundary is ordered by position, not
  meaning. On the sample corpus this produces visible artifacts such as
  ``Độc lập do Hạnh phúc Tự`` where ``Tự do`` is split across a layout
  boundary — see experiments/004_reading_order/.
* Elements without a bbox cannot be placed geometrically; they are appended
  in their original relative order.
"""
from __future__ import annotations

from doc_extraction.schemas.element import BBox, Element

ORDER_STRATEGY = "column-aware-xy-band"

# An x-gap must be at least this fraction of the page width to count as a
# column gutter. Deliberately generous: splitting a single-column page into
# fake columns is a worse failure than missing a narrow gutter.
DEFAULT_MIN_GUTTER_RATIO = 0.06
DEFAULT_MAX_COLUMNS = 3

# An element at least this fraction of the page width is treated as
# full-width (header, footer, wide table) and excluded from gutter search.
_FULL_WIDTH_RATIO = 0.8

# (original_index, element_id, bbox)
_Item = tuple[int, str, BBox]


def _find_gutter(items: list[_Item], page_width: float, min_gutter_ratio: float) -> float | None:
    """Return the x coordinate of the widest qualifying vertical gutter, or
    None if the items form a single column.

    Full-width elements (page headers, footers, wide tables) are excluded
    from the *search*: a single header spanning the page would otherwise
    bridge the gutter in the x projection and hide a real two-column layout.
    They are still placed correctly afterwards, by `_order_recursive`.
    """
    if len(items) < 2 or page_width <= 0:
        return None

    candidates = [i for i in items if i[2].width < page_width * _FULL_WIDTH_RATIO]
    if len(candidates) < 2:
        return None

    intervals = sorted((item[2].x0, item[2].x1) for item in candidates)
    best_gap = 0.0
    best_x: float | None = None
    reach = intervals[0][1]
    for x0, x1 in intervals[1:]:
        gap = x0 - reach
        if gap > best_gap:
            best_gap = gap
            best_x = reach + gap / 2
        reach = max(reach, x1)

    if best_x is None or best_gap < page_width * min_gutter_ratio:
        return None

    left = sum(1 for item in candidates if item[2].x1 <= best_x)
    right = sum(1 for item in candidates if item[2].x0 >= best_x)
    if left == 0 or right == 0:
        return None
    return best_x


def _band_sort(items: list[_Item], y_tolerance: float) -> list[_Item]:
    """Group into row bands top-to-bottom, sort each band left-to-right."""
    ordered = sorted(items, key=lambda item: (item[2].y0, item[2].x0, item[0]))

    bands: list[list[_Item]] = []
    for item in ordered:
        bbox = item[2]
        if bands:
            band = bands[-1]
            band_y0 = min(b[2].y0 for b in band)
            band_y1 = max(b[2].y1 for b in band)
            overlaps = bbox.y0 < band_y1 and bbox.y1 > band_y0
            starts_close = abs(bbox.y0 - band_y0) <= y_tolerance
            if overlaps or starts_close:
                band.append(item)
                continue
        bands.append([item])

    result: list[_Item] = []
    for band in bands:
        band.sort(key=lambda item: (item[2].x0, item[2].y0, item[0]))
        result.extend(band)
    return result


def _order_recursive(
    items: list[_Item],
    page_width: float,
    y_tolerance: float,
    min_gutter_ratio: float,
    depth: int,
    max_columns: int,
) -> list[_Item]:
    if depth <= 0 or len(items) < 2:
        return _band_sort(items, y_tolerance)

    gutter_x = _find_gutter(items, page_width, min_gutter_ratio)
    if gutter_x is None:
        return _band_sort(items, y_tolerance)

    left = [i for i in items if i[2].x1 <= gutter_x]
    right = [i for i in items if i[2].x0 >= gutter_x]
    spanning = [i for i in items if i[2].x0 < gutter_x < i[2].x1]

    ordered_columns = (
        _order_recursive(left, page_width, y_tolerance, min_gutter_ratio, depth - 1, max_columns)
        + _order_recursive(right, page_width, y_tolerance, min_gutter_ratio, depth - 1, max_columns)
    )

    if not spanning:
        return ordered_columns

    # Full-width elements stay in document flow: emit each one once every
    # column element above it has been emitted.
    result: list[_Item] = []
    remaining = list(ordered_columns)
    for span_item in _band_sort(spanning, y_tolerance):
        span_top = span_item[2].y0
        above = [i for i in remaining if i[2].y1 <= span_top]
        for item in above:
            remaining.remove(item)
        result.extend(above)
        result.append(span_item)
    result.extend(remaining)
    return result


def compute_reading_order(
    elements: list[Element],
    y_tolerance: float = 4.0,
    page_width: float | None = None,
    min_gutter_ratio: float = DEFAULT_MIN_GUTTER_RATIO,
    max_columns: int = DEFAULT_MAX_COLUMNS,
) -> list[str]:
    """Deterministic geometric reading order over `elements`.

    Returns `Element.id`s. Elements without a bbox are appended at the end in
    their original relative order — they cannot be placed geometrically, and
    silently dropping them would lose content.
    """
    items: list[_Item] = [
        (i, e.id, e.bbox) for i, e in enumerate(elements) if e.bbox is not None
    ]
    no_bbox_ids = [e.id for e in elements if e.bbox is None]

    if not items:
        return no_bbox_ids

    if page_width is None:
        page_width = max(item[2].x1 for item in items)

    max_depth = max(0, max_columns - 1)
    ordered = _order_recursive(items, page_width, y_tolerance, min_gutter_ratio, max_depth, max_columns)
    return [item[1] for item in ordered] + no_bbox_ids
