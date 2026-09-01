# Observations — 008

## 1. Always-visual is not the safe choice — it is the worst one

The intuition that a heavier path is a safer path is wrong here, and by a
wide margin.

| Strategy | Mean recall | Worst case | Total failures | Hallucinations | Runtime |
|---|---|---|---|---|---|
| native | 88% | 0% | 1 | **1** | **0.5 s** |
| **adaptive** | **95%** | **67%** | **0** | **0** | 37.5 s |
| visual | 66% | 0% | 1 | 0 | 194.3 s |

Always-visual scores **22 points below always-native** while costing roughly
390× more. On documents whose text layer is intact, rendering to pixels and
recognizing them back is a lossy round-trip of information the pipeline
already had exactly.

The losses are concrete and production-relevant. On `clean_vi` — a perfectly
clean born-digital Vietnamese page — the visual route lost `Độc lập`. On
`watermark` it lost `Vốn điều lệ`; on `stamp_over_text`, `Mã số doanh nghiệp`.
These are precisely the fields an enterprise extraction system exists to
recover.

## 2. Native's weakness is not low recall — it is *confident* failure

Native reaches 88% mean, only 7 points behind adaptive. Read alone that looks
like a reasonable production default at 74× the speed.

It is not, and the corpus shows why in one row: on `broken_cmap_vi`, native
scores 0% **and trips the hallucination check**, emitting `ЅoҖѸ Йoa` as though
it were text. Nothing downstream can tell that apart from a successful
extraction.

This is the whole argument for the quality gate stated as a measurement:
the risk is not that the cheap path is a bit worse, it is that the cheap path
fails *invisibly*. Mean recall alone would have hidden it; `must_not_contain`
is what exposed it.

## 3. Adaptive's cost is almost entirely spent where it is needed

The number that matters most:

```
36.5 s of 36.9 s  (99%)  spent on ONE document of fourteen
```

Thirteen documents took ~0.4 s in total on the native path. One — the corrupt
CMap — consumed everything else, and that expenditure moved it from 0% (plus a
hallucination) to 100%.

That is the "spend compute only where difficulty requires it" thesis measured
rather than asserted. Adaptive is not a compromise between the two extremes;
it is better than both, and its cost profile is a spike rather than a tax.

## 4. A coordinate-space bug was hiding two total failures

The visual route originally scored **0% on all three table cases**
(`tiny_cells_table`, `merged_cells`, `stamp_over_table`). Root cause, found by
following that pattern:

Docling rasterizes internally at its own resolution — **150 DPI**, giving a
1239.6 × 1754.0 page for A4 — *regardless of the resolution of the image it is
handed*. Its coordinates are in that space. `_bbox_from_docling` used them
directly as if they were the caller's 200 DPI pixels, and flipped y using the
*caller's* page height against *docling's* origin.

Every bbox the component path produced was therefore wrong in both scale
(1.333×) and offset. Measured on one page:

| | before | after | expected from source |
|---|---|---|---|
| docling table region | (112,782)-(1074,1109) | **(149,262)-(1432,699)** | 264–697 px |
| table_transformer | (158,265)-(1239,691) | unchanged | 264–697 px |
| cells filled from OCR | **0/50** | **50/50** | — |

**Why it stayed hidden.** `_gather_region_text` compares docling tokens
against docling regions. Both were wrong *identically*, so containment still
worked and text still landed in regions. The error only became observable when
docling geometry met a second backend's — `_fill_table_cell_text` matching
tokens against Table Transformer cells — where it silently matched nothing.

A second, independent defect compounded it: `recognize()` skipped table items
entirely, commented "table text is handled by the table stage". That is untrue
for the configured pipeline, whose table stage is Table Transformer —
geometry only, cell text filled *from OCR tokens*. Each component assumed the
other recovered table text and neither did.

Effect of fixing both: visual mean recall **59% → 66%**, total failures
**3 → 1**, tail (p10) **0% → 33%**. Native and adaptive are unchanged, which
is the control: the fix touches only the path it should.

## 5. What the fix did *not* solve

`stamp_over_table` remains 0% on the visual route. That is correct and
expected: an opaque seal genuinely covers the pixels, so no amount of
coordinate arithmetic recovers what is not visible. Native reads it from the
text layer at 67%.

This is the clearest case in the corpus for **fusion** rather than selection:
native has the occluded text and loses the table grid to the stamp; visual has
the grid and loses the covered text. Neither alone is sufficient and the
information needed is present across the two.

## 6. A negative result: the DPI hypothesis was not the binding constraint

E11 measured that 4pt text at the shipped 200 DPI renders to ~11 px, below the
recognition floor, and that a targeted high-DPI crop is 8.2× cheaper than
globally raising DPI. Those geometric facts stand.

But the recovery experiment built on them (`research/experiments/recovery_hidpi.py`)
returned **0% recall in all three arms**, including full-page 600 DPI. Raising
resolution changed nothing because the text was never being read at any
resolution — the coordinate/adapter defects above were the binding constraint,
not pixel density.

Recorded deliberately: the experiment was well-motivated, the prediction was
reasonable, and it was wrong. Chasing the anomaly ("why did 600 DPI produce
only 19 characters?") is what found the real bug. The DPI question remains
open and should be re-run now that the path underneath it works.

## 7. Implication for the production architecture

The evidence supports the adaptive/quality-gate architecture the repository
already has, and argues against two tempting simplifications:

* Do **not** default to the visual path for safety. It is slower *and* worse.
* Do **not** default to native for speed. Its failure mode is silent.

The gate is what makes the combination work, and its value is concentrated in
a small fraction of documents — which is also the argument for spending a VLM
or other expensive specialist only at that same point in the ladder, rather
than on every page.
