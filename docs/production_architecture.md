# Target production architecture

A **target**, not a specification to implement blindly. Several components
below have not yet earned their compute cost, and this document says which
ones and what measurement would settle it. The ordering principle
throughout: *measure before routing.*

Compute target: A30-class internal GPU host. The development laptop is the
control plane for code and tests only.

---

## 1. Where the current system already is

More of this architecture exists than a fresh reader would expect:

| Capability | Status |
|---|---|
| Canonical IR (`Document → Page → Element/Table → Cell`) | **Built**, stable across every backend |
| Backend protocols (`LayoutBackend`, `OCRBackend`, `TableBackend`, `WholeDocumentBackend`) | **Built** |
| Model-agnostic N-way candidate composition | **Built** (`select_best_table_candidate`) |
| Device plumbing (`device: cuda` reaching every stage) | **Built**, wired, **never measured on GPU** |
| Models loaded once per process | **Built** (`_COMPONENT_BACKEND_CACHE`) |
| Deterministic subsets + evaluator hygiene | **Built**, hardened |
| Environment diagnostics | **Built** (`cli env`) |
| Tier routing (cheap → expensive) | **Not built — deliberately** |
| GPU-served VLM tier | **Not built** |

The gap to production is therefore **not** an IR or protocol redesign. It
is: (a) a strong parser tier, (b) a routing signal good enough to justify
spending it selectively, and (c) measurements from a real GPU.

---

## 2. Target shape

```
                      INPUT DOCUMENT
                            │
                     ingestion / route
                    (digital vs scanned)
                            │
            ┌───────────────┴───────────────┐
            ▼                               ▼
      native path                      visual path
   (PyMuPDF text+tables)                    │
      quality-gated                         │
            │                    ┌──────────┴──────────┐
            │                    ▼                     ▼
            │              TIER 1 (cheap)        TIER 2 (strong)
            │           Docling layout+OCR      document VLM, GPU
            │           Table Transformer       PaddleOCR-VL / dots.ocr
            │                    │                     │
            │                    └──────────┬──────────┘
            │                               │
            │                        TIER 3 (specialist)
            │                     formula / hard region only
            │                               │
            └───────────────┬───────────────┘
                            ▼
                  candidate composition
              (model-agnostic, already built)
                            ▼
                      canonical IR
                            ▼
              validation / diagnostics / audit
                            ▼
                        output
```

The routing decision (which pages reach Tier 2) is the **open systems
question**, addressed in §4 — not something to hardcode now.

---

## 3. Tiers

### Tier 1 — cheap baseline (exists)

Native PDF extraction with a text-quality gate; Docling layout + OCR;
Table Transformer + Docling TableFormer with N-way composition; geometric
reading order. ~70 s/page CPU measured; GPU unmeasured.

**Keep it.** It is not a placeholder for a VLM — it is the path most pages
should take, and every measured table-composition gain lives here.

### Tier 2 — strong document parser (to add, GPU)

A document VLM producing layout + text + tables + reading order + formula
in one pass. Candidates, licence-ordered (`docs/model_licenses.md`):

1. **PaddleOCR-VL** (Apache-2.0, 0.9B) — *gate: verify Vietnamese*
2. **dots.ocr** (MIT, 3B) — permissive fallback
3. **MinerU2.5** (AGPL-3.0 weights) — measured working here, adapter
   exists, but needs legal review before production

**Integration rule already measured:** feed a document VLM **whole pages**,
never pre-cropped regions. On `page-28657a85` a tight ground-truth crop
made MinerU2.5 emit no table at all, while the full page produced the exact
1×3 table. These models do coarse-to-fine internally; pre-cropping removes
context they depend on — the **opposite** of Table Transformer, which needs
a crop. A composed pipeline must therefore feed its candidate sources
*differently*, and the composition layer must not assume a shared input
form.

### Tier 3 — specialists (mostly absent)

Formula recognition is **not active in the baseline at all** — the largest
untouched capability gap in the current system (`display_formula` edit
distance ≈ 0.995, i.e. near-total failure). Whether Tier 2 subsumes this
or a specialist is still needed is an open measurement.

---

## 4. The hardness-signal problem (the real open question)

Running a GPU VLM on every page is the wrong production design — on CPU
MinerU2.5 cost ~2.6–3× the current pipeline, and on GPU it will still be
the dominant cost. The systems question is:

> **What tells us Tier 1 is likely to fail, cheaply enough to be worth
> asking before spending Tier 2?**

**What is already ruled out by measurement:** cell fill-rate. It matched a
ground-truth oracle on only 5/7 tables, and the two misses shared one
mechanism (an empty prediction scores well against a sparse GT). Neither
model's own fill-rate predicted when the other should be invoked —
Docling's is binary "found something", Table Transformer's is graded but
predictive in the *wrong* direction. **Do not rebuild that selector.**

Untested candidate signals, to evaluate on the A30:

| Signal | Cheap? | Rationale |
|---|---|---|
| **Cross-candidate structural disagreement** (TT vs TableFormer row/col topology) | yes — both already run in Tier 1 | disagreement is where composition already earns gains |
| **Layout label ambiguity** (region scoring high for TABLE *and* PICTURE) | yes | directly implicated in a measured failure (upstream Docling issue #3495); our `label == "table"` filter turns it into total loss |
| Zero-candidate regions (layout says table, no structure produced) | yes | already a known, measured failure class |
| OCR/text-quality scores | yes | `ingest/text_quality.py` exists and is calibrated |
| Region density / tiny-region count | yes | the residual hard family was ≤2-row, 1.5–5.2% page area |
| Model-reported confidence | varies | **not currently populated** — `Cell.confidence` is never set by either backend |

**Method:** run Tier 1 and Tier 2 over the same subset, label each page by
whether Tier 2 materially improved it, then test which cheap signals
predict that label. That is a measurement, not a heuristic — and it is the
honest version of "adaptive compute allocation".

---

## 5. Known pipeline gaps to fix regardless of tiering

Diagnosed, reproduced, and deliberately **not** fixed pending measurement
(`docs/research_gap_analysis.md`, `docs/pipeline_integrity.md`):

1. **`label == "table"` filter** (`pipelines/base.py:559`) discards regions
   the layout model localized correctly but labelled `picture`. Measured:
   IoU 0.753, 98.3% GT coverage, thrown away. Needs a false-positive study
   before fixing.
2. **Orphan tables** — a table detected at 0.9991 confidence on the
   unmodified full page is dropped because no `table`-labelled layout
   region exists to attach it to. Fixing risks duplicating content into
   `text_block`; needs a 100-page check.
3. **Table Transformer nondeterminism** across processes on CPU — affects
   any future cross-run comparison at the sub-0.1 level. Unaddressed
   (no seeding anywhere in the backends).

---

## 6. Enterprise constraints (§19) — how the design satisfies them

| Requirement | How |
|---|---|
| No external document upload | Every candidate runs fully locally; no SaaS in any path |
| No SaaS dependency | Confirmed per-model in `docs/model_licenses.md` |
| Local model inference | HF weights cached on a local/shared volume (`HF_HOME`) |
| Local caches | `cache_dir` config + `HF_HOME`/`TORCH_HOME`; `cli env` warns when unset |
| Internal networking | Nothing in the pipeline egresses at inference time |
| Audit logs | `StageLogger` per stage; `run_metadata.json` records evaluator commit, GT hash, model versions, device, config snapshot |
| Reproducible versions | Pinned evaluator commit, deterministic seeded subsets, recorded model versions |

The one genuine risk to these properties is **licensing, not
architecture** — see `docs/model_licenses.md` for the AGPL items
(`pymupdf` core; MinerU2.5 weights).

---

## 7. What must be measured before building further

In order, on the A30:

1. GPU bring-up + the existing pipeline under `configs/gpu.yaml` (never
   timed on a GPU).
2. Tier 2 candidate feasibility: loads, VRAM, latency, throughput.
3. **Vietnamese verification** for PaddleOCR-VL — blocking for this
   project's actual target corpus.
4. Quality A/B on identical subsets: current vs Tier 2 alone vs composed.
5. Hardness-signal study (§4) — only then implement routing.
6. Formula: does Tier 2 close the near-total gap, or is Tier 3 needed?

Commands for 1, 2, and 4 are in `docs/gpu_host.md`.
