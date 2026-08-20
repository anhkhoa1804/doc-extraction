# Observations — 003 Backend disagreement

`FROGSLEAP_Impact_Module_TriAn_B2B_Sample.pdf` (5 pages), baseline vs
Docling, CPU, 2026-08-20.

## Document-level

| | baseline | docling |
|---|---|---|
| Pages | 5 | 5 |
| Elements | 75 | 39 |
| Tables | **3** | **3** |
| Table cells | 85 | 80 |
| Text characters | 3809 | 3859 |
| Runtime | **0.6 s** | **36.3 s** |

## Per-page disagreement

| Page | elements L/R | tables L/R | text sim. | bbox match | order corr. |
|---|---|---|---|---|---|
| 1 | 30 / 18 | 0 / 0 | 0.465 | 0.833 | 0.871 |
| 2 | 14 / 7 | 1 / 1 | 0.274 | 0.429 | 1.000 |
| 3 | 10 / 5 | 1 / 1 | 0.362 | 0.800 | **0.400** |
| 4 | 5 / 3 | 1 / 1 | **0.976** | 1.000 | 1.000 |
| 5 | 16 / 6 | 0 / 0 | 0.531 | 0.333 | — |

## What the numbers say

**Table detection agrees exactly** — 3 vs 3, `table_count_delta = 0` on
every page, and cell counts within 6%. Two independent implementations, one
reading vector ruling lines and one running a neural table model on pixels,
landing on the same answer is meaningful evidence the tables are really
there. It says nothing about whether the *contents* are right.

**Segmentation granularity differs about 2×** (75 vs 39 elements) on every
page. The baseline splits PyMuPDF text blocks; Docling merges into larger
semantic regions. Neither is "wrong" — but it means element counts are not
comparable across backends without normalization, which is worth remembering
before anyone builds a metric on top of them.

**Text similarity is low (mean 0.52) while text length is nearly identical**
(3809 vs 3859 chars, 1.3% apart). Per the interpretation documented in
`evaluation/disagreement.py`, similar length with low similarity points at
ordering/segmentation differences rather than a missed-content or encoding
problem. Page 4 — the simplest page, 5 elements — scores 0.976, consistent
with that reading.

**Page 3 is the one to look at**: reading-order correlation **0.400** with a
high bbox match rate (0.800). Both systems found the same regions and
ordered them differently. That is a genuine reading-order dispute, which is
exactly what this tooling exists to surface. Not yet adjudicated by hand.

**Page 5** has the worst region agreement (bbox match 0.333) and too few
matched regions for a rank correlation. Also unadjudicated.

## Cost

The baseline is ~60× faster on this document (0.6 s vs 36.3 s) while
agreeing on table structure. For born-digital input the expensive path buys
different segmentation, not obviously better structure.

## What this does not show

* **n = 1 document, 5 pages.** These are anecdotes with numbers attached.
* No ground truth was consulted. Every "disagreement" above could be the
  baseline being wrong, Docling being wrong, or both.
* The two systems were not given identical work: Docling ran its full
  layout+OCR pipeline, the baseline used the native text layer. The runtime
  comparison is therefore about *routes*, not about implementation quality.

## Follow-up

Adjudicate page 3 by hand against the rendered page, and decide whether the
reading-order disagreement is the baseline's row-band heuristic failing or
Docling's ordering failing. That single page is the cheapest available
entry point into the reading-order research question.
