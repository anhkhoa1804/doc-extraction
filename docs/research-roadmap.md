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

---

# Phased roadmap (A30-class compute target)

Added when the compute target moved off the development laptop. The
hypotheses above predate the OmniDocBench work; **this section supersedes
them wherever the two disagree**, because it is backed by measurement.

Full reasoning: `docs/final_research_gap.md`. Commands: `docs/gpu_host.md`.

## NOW — laptop only (no GPU required)

| Item | Status |
|---|---|
| `pytest -q` green | **done** — 209 tests |
| Environment diagnostics (`cli env`) | **done** this phase |
| Licence audit for every candidate | **done** — `docs/model_licenses.md` |
| Production candidate matrix | **done** — `docs/sota_comparison.md` |
| A30 runbook | **done** — `docs/gpu_host.md` |
| Target architecture + tiering | **done** — `docs/production_architecture.md` |
| Research-gap classification | **done** — `docs/final_research_gap.md` |

Deliberately **not** done on the laptop, and not to be attempted here:
GPU throughput, VLM feasibility, production latency, VRAM figures.

## NEXT — first hours on the A30

1. `pytest -q`; `cli env --require-gpu`.
2. **Time the existing pipeline under `configs/gpu.yaml`** — wired for CUDA
   since before this phase, never measured on a GPU. This is the missing
   baseline everything else is compared against.
3. Bring up **PaddleOCR-VL** (Apache-2.0, 0.9B). **Gate: verify Vietnamese
   directly** — the card claims 109 languages without naming it, and this
   project's real corpus is Vietnamese/English.
4. If Vietnamese fails → **dots.ocr** (MIT, 3B).
5. Only if a permissive model is materially worse → MinerU2.5 (AGPL-3.0
   weights; adapter already exists), and start the legal review then, not
   before.

## AFTER A30 VALIDATION

6. Quality A/B on deterministic 20- then 100-page subsets: current vs
   Tier 2 alone vs composed. Same evaluator, same normalisation,
   TEDS-timeout hygiene on. Never compare across subset sizes.
7. **Measure formula.** `display_formula` edit distance ≈ 0.995 — near-total
   failure, no formula model active at all. Largest single quality gap.
8. Compare reading order head-to-head against a SOTA parser.
9. Fix the two known pipeline defects with the measurements that gate them:
   the `label == "table"` filter (needs a false-positive study) and orphan
   tables (needs a duplication check).
10. Full 1651-page run only after 100 is clean.

## RESEARCH — gated, not scheduled

Only after step 6 produces Tier-1-vs-Tier-2 labelled data:

- **Hardness signal** (`production_architecture.md` §4): which cheap signals
  predict Tier-1 failure? Note fill-rate was measured and **rejected** — do
  not rebuild it.
- **Multi-model evidence fusion**: composing *partial* candidates rather
  than selecting whole ones. The most research-shaped direction available,
  but gated on observing distributed partial correctness — and there is
  reason to doubt it, since MinerU2.5 scored a *perfect* structure on all
  five hard cases, leaving nothing for fusion to add.

**Closed by evidence — do not reopen:** novel small-table detection
(coarse-to-fine is published SOTA), "both structure models fail together"
(refuted twice — a timeout artifact, then solved by a third model),
confidence-aware candidate ranking (measured and rejected), cross-region
reasoning (zero cases in the corpus need it).

## PRODUCTION

- Tier routing, once a hardness signal is validated — **not before**.
- vLLM serving for the Tier-2 model; batch at page level; one worker per
  GPU until utilisation says otherwise.
- Resolve the AGPL items (`pymupdf` **core**; MinerU2.5 weights if adopted).
- Keep: local-only inference, no SaaS, pinned evaluator, deterministic
  seeds, per-run environment capture.
