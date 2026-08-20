# Observations — 004 Reading-order baseline

CPU, 2026-08-20, strategy `column-aware-xy-band`.

## Case 1: phrase-level scrambling on a recovered scan

`FROGSLEAP_BUSINESS LICENSE.pdf` page 1, after the OCR reroute, orders as:

> … CỘNG HÒA XÃ HỘI CHỦ NGHĨA VIỆT NAM **Độc lập do Hạnh phúc Tự** GIẤY
> CHỨNG NHẬN …

The source is the fixed Vietnamese masthead:

> Độc lập **-** Tự do **-** Hạnh phúc

So `Tự do` has been split: `Tự` was emitted at the *end*, after
`Hạnh phúc`. This is a clean, unambiguous ordering failure — no ground-truth
labelling needed, because the phrase is a fixed formula.

**Likely cause**: the masthead is centre-aligned across three
whitespace-separated groups on one visual line. OCR emitted them as separate
regions with slightly different vertical extents; the row-band grouping put
`Tự` into a different band from `do`. This is precisely the limitation
documented in the module docstring — the heuristic has no notion of
continuation, only geometry.

**Not yet verified**: whether the fault is in the band grouping or upstream
in how the OCR backend segmented the line. The rendered page and its bbox
overlays are in the document's `inspection/index.html`; adjudicating that is
the obvious next step and has not been done.

## Case 2: disagreement with Docling's ordering

From 003, on `FROGSLEAP_Impact_Module_TriAn_B2B_Sample.pdf`:

| Page | reading-order correlation | bbox match rate |
|---|---|---|
| 1 | 0.871 | 0.833 |
| 2 | 1.000 | 0.429 |
| 3 | **0.400** | 0.800 |
| 4 | 1.000 | 1.000 |
| 5 | — (too few matches) | 0.333 |

**Page 3 is the interesting one**: 0.800 bbox match rate means both systems
found substantially the same regions, and 0.400 rank correlation means they
ordered those shared regions very differently. That isolates the
disagreement to ordering specifically, not detection — which is exactly what
splitting the metrics was for.

Page 2 shows the inverse pattern (perfect ordering agreement, poor region
agreement), confirming the two metrics really are measuring different things
rather than tracking each other.

## What was fixed during this phase

An earlier revision ordered two-column layouts by naive row bands, which
interleaves columns. Column-gutter detection was added, and a bug was found
by the new tests: a **full-width header or footer bridged the x-projection
and hid the gutter entirely**, silently reverting a two-column page to
interleaved order. Full-width elements are now excluded from the gutter
*search* and re-inserted in document flow afterwards. Covered by
`tests/test_reading_order.py::test_two_column_layout_with_full_width_header_and_footer`.

## Known remaining limitations (documented, not fixed)

* Columns separated only by alignment, with no gap crossing the page
  height, are not split.
* No notion of continuation — case 1 above.
* Elements without a bbox cannot be placed geometrically; they are appended
  at the end rather than dropped.

## What this does not show

n = 2 documents. These are two concrete, reproducible failures, not a
failure *rate*. Nothing here quantifies how often ordering is wrong across
the corpus, because that needs ground-truth ordering labels which do not
exist for this data.
