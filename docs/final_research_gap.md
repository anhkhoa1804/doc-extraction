# Final research-gap assessment

Answers, from the accumulated evidence: **after fixing our own pipeline and
adding a real SOTA comparator, what remains unsolved, and is there a
scientifically defensible research contribution there?**

**Headline: no research gap is currently established in table extraction.**
Every residual table failure this project could reproduce is accounted for
as a pipeline defect or a missing SOTA integration. The candidate
directions that remain are **systems** questions, and the one genuine
untested capability gap is **formula**, not tables.

Status: this is an honest negative result on the table question, which the
brief explicitly permits.

---

## 1. Classification of every residual failure

The population is the 5 tables still scoring 0.0 TEDS on the 100-page
subset after the candidate-recovery fix, each individually traced.

| # | Case | Mechanism (measured) | Classification |
|---|---|---|---|
| 1 | `jiaocaineedrop_46` | Layout localized the region (IoU 0.753, 98.3% GT coverage) but labelled it `picture`; our `label == "table"` filter discarded it. TT-on-crop: 0.9434, exact 2×7. | **pipeline bug** |
| 2 | `page-d29fe4d2` | TT detects at **0.9991 on the unmodified full page**; lost because no `table`-labelled layout region exists to attach it to. | **pipeline bug** |
| 3 | `page-28657a85` | 1× crop → wrong `1×2`; 2× crop → exact `1×3`. Recoverable with an existing model. | **implementation gap** (no crop-refine stage) |
| 4 | `..._en_2901` [0] | TT structure `None` at 1×/2×/3×; TableFormer nothing. **MinerU2.5: structure-only TEDS 1.0000.** | **SOTA integration gap** |
| 5 | `..._en_2901` [1] | TT `2×1` at all scales; TableFormer nothing. **MinerU2.5: structure-only TEDS 1.0000.** | **SOTA integration gap** |

```
pipeline bug ............... 2 / 5
implementation gap ......... 1 / 5
SOTA integration gap ....... 2 / 5
known model limitation ..... 0 / 5   (of the field; TT/TableFormer individually, yes)
open research problem ...... 0 / 5
```

**Zero cases qualify as a research gap**, against the six-part bar in the
brief. Criterion 1 alone ("multiple strong systems fail") is not met: a
third model family solves every case where the incumbents fail.

---

## 2. Why the earlier candidate directions do not qualify

Each was investigated and closed by evidence, not by preference:

| Candidate direction | Why it is not a research gap |
|---|---|
| Small/borderless table detection | Coarse-to-fine crop-refine is **published SOTA** (MinerU2.5 Stage I/II; PaddleOCR-VL native-res encoder). Reinventing it is not novel. |
| "Both structure models fail together" | **Refuted twice.** First the 47% both-fail statistic proved to be a TEDS-timeout artifact (real rate 27%); then MinerU2.5 solved all 5 remaining cases. |
| Confidence-aware candidate ranking | Measured and rejected. Fill-rate matched a GT oracle on 5/7; no cheap signal separated the misses; neither model's fill-rate predicted when to invoke the other. |
| Selective escalation on candidate quality | Same measurement — the available signals do not support a trigger. |
| Cross-region / document-level reasoning | **Zero cases in the corpus demonstrate a need for it.** Building it would address a phenomenon we have not observed. |

A pattern worth naming: **three of this project's four "promising research
directions" dissolved into measurement artifacts or already-published
techniques once examined properly.** That is the process working.

---

## 3. What is genuinely untested — and where a gap could still exist

The table question is closed. These are not:

### 3a. Formula — the largest untouched capability gap

`display_formula` edit distance is **≈ 0.995** on the 100-page subset:
near-total failure. No formula model is active in the baseline at all. This
is not a research gap — it is an **unfilled integration slot**, and every
Tier-2 candidate claims formula capability. But it is by far the biggest
single quality gap remaining, and it has never been measured with a
competent model in place.

### 3b. Reading order under mixed content

Currently a deterministic geometric heuristic with known, documented
limitations (no continuation semantics). SOTA parsers predict reading order
directly and report strong numbers. **Never compared head-to-head on our
subset.**

### 3c. Multilingual verification — Vietnamese

This project's actual target corpus is Vietnamese/English. PaddleOCR-VL
claims 109 languages but **does not name Vietnamese** in its card or
abstract, and no primary-source list was located. If the strongest
permissively-licensed parser does not handle Vietnamese well, that is a
real, practical, and possibly under-served capability — worth measuring
before assuming.

### 3d. Adaptive compute allocation (systems, not model, research)

The honest framing of "don't run the VLM on every page". The measurement
plan is in `docs/production_architecture.md` §4. Note the naive version of
this was already tried and failed — so the contribution, if any, is finding
a signal that *does* work, which requires the Tier-1-vs-Tier-2 labelled
data that does not exist yet.

---

## 4. Direction scoring

Scored 1–5. "Compute" = feasibility on a single A30 (5 = easily).

| Direction | Novelty | Impact | Production | Data avail. | Compute | Difficulty | Benchmarkable | Risk |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| **A. Integrate a Tier-2 parser + measure** | 1 | **5** | **5** | 5 | 4 | 2 | **5** | **1** |
| **B. Formula capability (3a)** | 1 | **5** | 4 | 5 | 4 | 2 | **5** | **1** |
| C. Adaptive compute allocation (3d) | 3 | 4 | **5** | 2 → after A | 4 | 4 | 4 | 3 |
| D. Multi-model evidence fusion (partial-candidate merge, not selection) | **4** | 3 | 3 | 2 → after A | 4 | 4 | 3 | 4 |
| E. Vietnamese/multilingual gap (3c) | 2 | 4 | **5** | 3 | 4 | 2 | 3 | 3 |
| F. Reading order vs SOTA (3b) | 2 | 3 | 3 | 5 | 4 | 2 | **5** | 2 |
| G. Novel small-table detection | 1 | 2 | 2 | 5 | 4 | 4 | 4 | **5** |

**Ranking: A → B → E → C/F → D. G is closed.**

A and B score low on novelty *and that is the correct answer* — the
evidence says the highest-value work right now is integration and
measurement, not research. D is the most research-shaped direction, but it
is explicitly gated: it needs the Tier-1-vs-Tier-2 disagreement data that
only A produces.

---

## 5. The one direction that could become genuine research

**D — multi-model evidence fusion**, and only under a specific condition:

> If, after adding a Tier-2 parser, there exist pages where **each system
> produces partially-correct output and no single system is best**, then
> composing *partial* evidence (rather than selecting a whole candidate)
> could produce something no individual system achieves.

This project has already built candidate *selection* and measured its
ceiling (oracle headroom +0.115 TEDS at n=7, with the misses explained).
Fusion is the strictly harder problem selection cannot reach.

**The evidence needed to justify it does not exist yet**, and there is a
concrete reason to doubt it: MinerU2.5 scored `structure_only = 1.0000` on
all five hard cases — perfect, not partial. Fusion has nothing to add where
one system is already exactly right. Pursue only if the A30 comparison
actually shows distributed partial correctness.

---

## 6. Answer to the brief's final question

> *Given an A30 host tomorrow, what should we run?*

1. `pytest -q`, then `python -m doc_extraction.cli env --require-gpu`.
2. Time the **existing** pipeline under `configs/gpu.yaml` — wired for CUDA
   since before this phase, never once measured on a GPU.
3. Bring up **PaddleOCR-VL** (Apache-2.0) — **verify Vietnamese first**;
   fall back to **dots.ocr** (MIT). Defer MinerU2.5 until a permissive
   model proves insufficient, so the AGPL review may never be needed.
4. A/B on the deterministic 20- then 100-page subsets: current vs Tier 2
   alone vs composed. Same evaluator, same normalisation, TEDS-timeout
   hygiene on.
5. **Measure formula** — the ≈0.995 edit distance is the largest single
   quality gap and has never been attempted with a real model.
6. Collect the Tier-1-vs-Tier-2 labels needed for the hardness-signal
   study, and only then consider routing or fusion.

**Do not** build a novel table method, a cross-region reasoning
architecture, or another confidence selector. The first is published SOTA,
the second addresses a phenomenon absent from our corpus, and the third was
measured and rejected.
