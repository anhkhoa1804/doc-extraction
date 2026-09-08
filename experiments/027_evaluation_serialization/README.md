# 027 — Evaluation Serialization Audit

**Status: COMPLETE. Decision: ADOPT (Layer-2 contract). No production code
changed. The frozen scorer was not modified.**

Baseline: `c92eb8bdeba4a7b58579bfdf9a3240ef871d73f3`. Everything here is
offline and CPU-only; the L4 was held throughout by an unrelated
Research-No.1 workload (PID 61016) and was not touched.

## 1. Hypothesis

> Is `run_benchmark.document_text` incorrectly flattening table cells
> according to detector/list order, when the canonical table semantics are
> already represented by `(row, col)`?

**Answer: yes, and it matters more than expected — but only to the evaluation
layer, never to production.**

## 2. Frozen scorer

Read-only, pinned in `scorer_audit.json` with source hashes at `c92eb8b`:

| function | location |
| --- | --- |
| `document_text` | `research/production_corpus/run_benchmark.py:67-80` |
| `_norm` | `research/production_corpus/run_benchmark.py:52-64` |
| `score` | `experiments/023_evidence_centric/run_ab.py:186-205` |
| `char_recall` | `experiments/023_evidence_centric/run_ab.py:167-175` |
| `order_ok` | `experiments/023_evidence_centric/run_ab.py:178-183` |
| `aggregate` | `experiments/023_evidence_centric/run_ab.py:323-337` |

File hashes: `run_benchmark.py` `b69d85dc1a2d3438…`, `run_ab.py`
`26332fe14748b464…`, `schemas/table.py` `663497ebf4226653…`.

Behaviour established by inspection:

* page elements are serialized in `page.elements` list order; `order_index`
  is **not** consulted;
* **all** element text for a page precedes **all** table cell text for that
  page, so a table sitting visually mid-page is serialized last;
* within a table, `tbl.cells` is iterated in **raw list order**;
  `cell.row` and `cell.col` appear nowhere in the function;
* `_norm` is NFC + whitespace collapse + strip, with **no case folding**;
* `exact_recall` is substring `find`; `char_recall` is
  `difflib.SequenceMatcher` matching-block size — **sequence-order
  sensitive**; `order_ok` requires found-string positions to be
  non-decreasing; `tables_ok` is computed by the caller and is
  serializer-invariant.

## 3. Counterfactual

CONTROL = the frozen serializer. COUNTERFACTUAL = identical except table
cells are iterated in `(row, col)` order. The IR is never mutated — both
strings are produced from the same dict, so anything the serializer does not
read is invariant by construction.

The transcription was **verified against the real `run_benchmark.document_text`
on live pydantic objects: 25/25 identical.** All invariants hold on every
document of every arm: same tables, same cell count, same cell text multiset,
same cell identity multiset, same row/col values, same cell bboxes, same page
elements, same non-table text. Evidence coverage, orphan rate, overlap rate
and evidence duplication are token-and-region properties the serializer never
reads, so they are invariant by construction and 025's values stand.

## 4. Historical replay — 37 arms, recomputed from artifacts

Nothing was copied from a previous write-up.

| milestone | arms | `order_ok` control → counterfactual | exact recall | char recall |
| --- | ---: | --- | --- | --- |
| 023 adaptive (6 arms) | 6 | 46 → 46 (no change) | identical | identical |
| 023 visual (6 arms) | 6 | 45→48, 46→48 | **identical** | +0.0002 on 4 arms |
| 023 visual_pre_reading_order_fix (6) | 6 | 42→45, 44→47, 45→48, 46→48 | **identical** | +0.0002 on 4 arms |
| 024 adaptive baseline/l5/l5_audit | 3 | 46 → 46 | identical | identical |
| 024 SCAN-49 baseline/l5/l5_audit | 3 | **45 → 49** | **identical** | −0.0002 |
| 024 IMAGE-2 | 3 | 2 → 2 | identical | identical |
| 024 visual/tesseract | 1 | 46 → 48 | identical | identical |
| 025 coverage / intervention ×2 | 3 | **45 → 49** | **identical** | −0.0002 |

**Exact recall is identical in all 37 arms.** `order_ok` improves in 22 arms
and degrades in none. Full per-arm detail in `historical_replay.json`.

## 5. Per-document changes

74 score changes across 37 arms, touching only **6 distinct documents**:
`ord_invoice_vi`, `ord_purchase_order_vi`, `hc_borderless_en`,
`cmb_borderless_lowcontrast_en`, `cmb_tiny_table_en`, `hc_tiny_cells_vi`.

| kind | count | classification |
| --- | ---: | --- |
| `order_ok` False → True | **60** | **A — genuine correction of benchmark serialization** |
| `order_ok` True → False | **0** | — |
| `char_recall` change | 14 | **C — accidental, sequence-sensitive matching** |
| exact recall change | **0** | — |
| hallucination change | **0** | — |

Text multiset identical in **100%** of changed documents.

**The 14 char changes are all on `hc_tiny_cells_vi`, and their sign is
arbitrary**: 0.9426 → **0.9528** (up 0.0102) in eight 023 arms, 0.8228 →
**0.8133** (down 0.0095) in six 024/025 arms. Same document, same reordering,
opposite directions, no evidence changed. That is the signature of a
sequence-sensitive metric responding to noise — which settles the −0.0002
that 026 flagged and could not fully classify. Its cause: the string
`'Dịch vụ lắp đặt'` was never recognised (OCR read `'Bren va tap ast'`), so
`char_recall` there is chaining coincidental characters across the whole
document, and reordering changes which coincidences difflib can chain.

## 6. `order_ok` audit

`order_ok` is documented as detecting a "reading-order defect". It does not
only do that. Under the counterfactual, any surviving flag is genuinely
page-level; any flag that disappears was table serialization.

Over the 28 arms with n ≥ 10:

| | value |
| --- | ---: |
| `order_ok=False` under control | **107** |
| `order_ok=False` under counterfactual | **47** |
| flags caused by table cell serialization | **60** |
| **share of all flags that were serialization** | **56.1%** |

On the SCAN-49 family it is total: **4 → 0**. Every order failure 024 and 025
ever reported on that cohort was table cell emission order, not reading order.
This independently reproduces 025's claim — 11 broken tables, 4 flagged,
detection rate **0.3636** — from the artifacts rather than from its write-up.

**False negatives:** 7 of 11 broken tables never surface, because a flag
requires the document's `must_contain` strings to straddle the inversion.
**False positives:** none identifiable — the vanishing flags were true
observations of a real defect, merely mislabelled as reading order.

And it strengthens 025's exoneration of `compute_reading_order`: under
canonical serialization SCAN-49 has **zero** order failures of any kind.

## 7. Historical comparability

| comparison | metric | control Δ | counterfactual Δ | preserved |
| --- | --- | ---: | ---: | :---: |
| 024 L5 on the shipped router | exact / char / perfect | +0.0068 / +0.0056 / +1 | same | ✅ |
| 024 L5 on SCAN-49 | exact / char / perfect | +0.0136 / +0.0115 / +2 | same | ✅ |
| 025 `gap_region` vs control | all | 0 | 0 | ✅ |
| 023 reading-order fix | all | +0.7089 exact, +39 perfect | same | ✅ |
| 023 Tesseract vs EasyOCR | exact / perfect | +0.2741 / +26 | same | ✅ |
| 023 Tesseract vs EasyOCR | char / order_ok | +0.0138 / +1 | +0.0136 / 0 | ❌ |

Answering §6 directly:

1. **Is the current scorer semantically wrong?** Partly. As a text-recall
   instrument it is sound. As the basis of `order_ok` it is measuring
   something other than what its docstring claims, 56% of the time.
2. **Is the counterfactual more faithful to IR semantics?** Yes. `(row, col)`
   is the canonical table representation — every production consumer uses it
   (026), and the serializer is the sole exception.
3. **Does changing it invalidate historical comparisons?** No. Every headline
   delta survives. Two secondary deltas in one 023 comparison move.
4. **Can the frozen scorer be preserved and a second metric added?** Yes —
   that is the proposal in `evaluation_contract.md`.
5. **Should future experiments report both?** Yes.
6. **Should history be rebaselined?** No. An annotation is enough.

## 8. Proposed contract

See `evaluation_contract.md`: **Layer 1 LEGACY** (frozen forever, unchanged)
and **Layer 2 STRUCTURAL** (additive) — replacing one flattened string with
`document_text_flat`, `table_text`, `table_structure`, `cell_sequence`, and
adding `page_order_ok`, `table_structural_integrity`, `cell_grid_accuracy`
beside the existing evidence metrics. Proposed only; nothing implemented.

## 9. Limitations

* The 023 `visual_pre_reading_order_fix` arms predate a production fix, so
  their absolute scores are historical curiosities; they are included because
  they exercise the serializer, not because their scores mean anything today.
* `cell_grid_accuracy` needs per-table ground truth the corpus does not yet
  carry; it is proposed, not costed.
* Only the SCAN-49 and production-corpus cohorts have frozen IR. The
  OmniDocBench real-scan probe has no `must_contain` and is out of scope.
* This audit cannot say whether a document's *page* reading order is right —
  only that 47 flags survive canonicalization and are therefore page-level.

## 10. Decision

**ADOPT** — the Layer-2 contract, not a scorer edit. The counterfactual is
demonstrably more faithful to IR semantics, its historical impact is fully
quantified across 37 arms with every headline finding preserved, a safe
versioned dual-metric strategy is defined, and 026 already removed all
ambiguity about production behaviour: the production IR is correct and needs
no change. Adopting costs nothing historically and stops a conflated metric
from being read as a reading-order result again.

## Reproducibility

| script | artifact |
| --- | --- |
| `scorer_audit.py` | `scorer_audit.json` — frozen scorer, hashes, line numbers |
| `counterfactual_serializer.py` | the two serializers + invariants (imported, no artifact) |
| `historical_replay.py` | `historical_replay.json` — 37 arms, per-document changes |
| `order_metric_audit.py` | `order_metric_audit.json` — `order_ok` conflation analysis |
| `evaluation_contract.md` | the proposed two-layer contract |

Inputs are the gitignored `_runs/` trees of 023, 024 and 025, regenerable
from those milestones' own scripts. `_norm` and `score` are **imported** from
the frozen scorer, never reimplemented — 026 recorded what happens otherwise.

**NO PRODUCTION CODE CHANGED. THE FROZEN SCORER WAS NOT MODIFIED.**
`src/`, `configs/`, `tests/`, `run_benchmark.py` and `run_ab.py` are all
byte-identical to `c92eb8b`.
