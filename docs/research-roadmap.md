# Research roadmap

These are **hypotheses**, not findings. Where a hypothesis now has *some*
evidence from this repo's own corpus, that evidence is cited and its limits
are stated — n=1 on a 12-file corpus is a starting point, not a result.

The infrastructure exists to test these. Nothing below has been validated at
a scale that would justify a claim.

## 1. Hard-case-aware parsing

**Hypothesis**: average-case extraction on clean, single-column, born-digital
documents is close to saturated across current open-source SOTA. The gap that
matters is concentrated in recognizable hard-case categories.

**Evidence so far (weak, and only for one category)**: on this corpus,
9 of 10 unique PDFs extract cleanly by the cheapest possible path. The one
that does not fails *completely* — its text layer decodes to systematic
garbage — rather than degrading gracefully. See
[experiments/001_pdf_text_quality](../experiments/001_pdf_text_quality/).
This is consistent with the hypothesis but nowhere near sufficient to
support it: one corrupt document is an anecdote.

**What the infra provides**: every stage's raw output is preserved, so a
hard case can be attributed to a specific stage rather than "the output looks
wrong". `scripts/build_failure_report.py` surfaces candidates automatically.

**Next step**: assemble a deliberately hard set (rotated scans, borderless
tables, handwriting, stamps) and measure per-category failure rates.

## 2. Adaptive / region-level routing

**Hypothesis**: running every page through the same fixed backend chain is
wasteful and sometimes harmful. Compute should follow difficulty.

**Evidence so far (a working existence proof, not a validation)**: the
digital-PDF route now assesses text quality per page and renders + OCRs only
the pages that fail. On the 40-page company profile, 2 of 40 pages took the
expensive path and 38 took the near-free one. That demonstrates the
mechanism works and that page-level difficulty really does vary *within* one
document. It does not show the routing decision is *correct* — only that it
is cheap and that it fires selectively.

**What the infra provides**: `LayoutBackend`/`OCRBackend`/`TableBackend` are
Protocols, so a future router could dispatch different *regions* of one page
to different backends, not just different pages.

**Next step**: extend from page-level to region-level, and measure whether
the rerouted output is actually better — currently we assume it is because
OCR reads glyphs rather than a broken mapping, which is sound reasoning but
unmeasured.

## 3. Unseen-layout generalization

**Hypothesis**: layout and reading-order models trained largely on
Western-document datasets degrade on the layouts this corpus actually
contains — bilingual Vietnamese/English headers, stamped licence pages,
dense price lists exported to PDF.

**Evidence so far**: reading-order defects are visible in recovered text —
`Độc lập do Hạnh phúc Tự` where `Tự do` has been split across a layout
boundary. See
[experiments/004_reading_order](../experiments/004_reading_order/). Whether
this is *worse* than on Western layouts is untested; we have no comparison
population.

**What the infra provides**: `stages/reading_order.py` is deliberately our
own geometric baseline, independent of any backend's ordering, and
`evaluation/disagreement.py` computes rank correlation between the two. You
cannot study reading-order disagreement if the only ordering available comes
from the system under study.

## 4. Data-centric document parsing

**Hypothesis**: for this document population, a small well-chosen calibration
set of hard cases will move quality more than a bigger general model.

**Evidence so far**: none. This is currently unverified and largely
unverifiable here — there is no ground truth and no calibration set. The
12 root files are what happens to be available, not a designed sample. (Two
pairs are byte-identical duplicates, so it is really 10 documents.)

**What the infra provides**: comparison output is structured JSON, so a
scored benchmark can be layered on later without changing how backends run.

**Next step**: hand-label ground truth for a handful of pages — enough to
measure, not enough to train on.

## 5. Efficiency / compute allocation

**Hypothesis**: most pages need far less compute than a full
render → OCR → layout → table chain.

**Evidence so far (reasonably direct)**: measured on this corpus, the native
digital-PDF path costs ~0.1–1 s per document including table structure,
versus ~35 s per page for the render+OCR path — roughly two orders of
magnitude. Routing correctly is therefore worth far more than optimizing
either path. The 38-of-40-pages result above is the same point at page
granularity.

**What the infra provides**: routing thresholds are config, not constants,
and every route decision is logged with its evidence, so the cost/benefit of
a threshold change is measurable rather than argued.

**Next step**: skip OCR *within* a page — a digital page containing one small
scanned figure currently either trusts its text layer entirely or re-does the
whole page.

## Explicitly out of scope

No model training or fine-tuning, no knowledge graph, no ontology, no RAG, no
business or workflow reasoning. If a hypothesis above starts to imply one of
these, that is a signal it has drifted outside this project's scope — not a
reason to build it.
