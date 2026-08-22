# Baseline vs. improved — local subset comparison

Same dataset, subset, seed, backend, and match method for both runs — only
the pipeline code and OCR-language config differ. See
`experiments/005_omnidocbench/observations.md` for the full evidence trail
behind each change.

| | Baseline | Improved |
|---|---|---|
| Dataset | `.external/OmniDocBench-data` (full 1651-page OmniDocBench, downloaded locally — see README "Dataset") | same |
| Subset | 20 pages, seed=0, deterministic (`select_subset`) | same 20 pages, same seed |
| Backend | `baseline` | same |
| `doc_extraction` config | `configs/cpu.yaml` (`ocr_languages: [en, vi]`) | `configs/omnidocbench.yaml` (`ocr_languages: [en, ch_sim]`) |
| Pipeline code | pre-fix (commit before this session's changes) | table-cell-text fix applied (`docling_backend.py`) |
| Match method | `quick_match` | same |
| CDM | not run (no Linux toolchain) | same |

**SUBSET: 20 pages, deterministic selection (seed=0), full 1651-page dataset
was obtained and validated locally but not run in full — see "Kaggle
readiness" in the final report.**

## Metrics

Lower is better for every `Edit_dist` row; higher is better for `TEDS` rows.
All numbers read directly from `results/local_{baseline,improved}/metrics.json`
— nothing recomputed or rounded beyond display precision.

| Metric | Baseline | Improved | Delta |
| --- | ---: | ---: | ---: |
| text_block Edit_dist (ALL_page_avg) | 0.7191 | 0.6332 | **-0.0859** |
| text_block Edit_dist (edit_sample_avg) | 0.6496 | 0.4602 | **-0.1894** |
| text_block Edit_dist (edit_whole) | 0.5353 | 0.5638 | +0.0285 |
| table TEDS.all | 0.2458 | 0.2584 | +0.0126 |
| table TEDS_structure_only.all | 0.3617 | 0.3631 | +0.0014 |
| table Edit_dist (ALL_page_avg) | 0.7446 | 0.7438 | -0.0008 |
| reading_order Edit_dist (ALL_page_avg) | 0.6072 | 0.5301 | **-0.0771** |
| display_formula Edit_dist (ALL_page_avg) | 1.0000 | 0.9959 | -0.0041 |
| Overall | not computed (needs CDM) | not computed (needs CDM) | — |
| sec/page (mean) | 51.63 | 51.08 | -0.55 (noise; device unchanged) |

**Read honestly, not cherry-picked:**

- **text_block and reading_order improved clearly and consistently** across
  their `ALL_page_avg` and `edit_sample_avg` variants (both, independently,
  the "typical page" measures). `edit_whole` — one edit distance over all
  20 pages' text concatenated together — got very slightly *worse*
  (+0.0285); one outlier page can move that single number more than it
  moves an average of 20 independent per-page scores. Not hidden here.
- **The reading_order gain was not directly targeted by either change** —
  it's the predicted second-order effect from Experiment 1
  (`observations.md`): previously-blank table cells are markdown blocks
  too, and comparing "all blank" against real ground-truth reading order
  was itself a source of edit-distance penalty independent of block
  ordering.
- **table TEDS moved only slightly** (+0.0126), well short of the
  dramatic single-page evidence (0→42/42 cells on one table; see
  Experiment 1). Only **5 of the 20 subset pages contain a table at all**,
  so this metric is an average over 5 samples, not 20 — noisy by
  construction. Inspecting those 5 directly: the fix filled real text into
  tables on 2 of them (including the 42/42 case), left one nearly
  unchanged, and one page's table stayed **fully empty even after the
  fix**. That last case is real and explained, not swept aside: the fix
  surfaces Docling's *own* already-computed per-cell text — on pages where
  Docling's own conversion also fails to populate that table (a separate,
  unaddressed limitation), there is nothing for this fix to surface. TEDS
  is also structure-sensitive: `TEDS_structure_only.all` barely moved
  (+0.0014), meaning `TableTransformerBackend`'s row/column grid detection
  — a different model, untouched by this fix — remains a real, separate
  ceiling on this metric regardless of cell text.

## Per-improvement evidence

### 1. Table cell text association (`docling_backend.py`)

**Hypothesis.** `table.TEDS.all` (0.2458) sits far below
`table.TEDS_structure_only.all` (0.3617) — a smaller gap than the demo
baseline's (0.1526 vs 0.6095) but the same shape: structure is detected
better than content is scored. Root-caused with real single-page evidence
(not assumed) in `observations.md` Experiment 1: `TableTransformerBackend`
never had text to give its cells, and `DoclingBackend.recognize()` was
discarding Docling's own already-computed per-cell text for table-labeled
items, with a stale comment claiming another stage handled it.

**Change.** `DoclingBackend.recognize()` now emits Docling's own per-cell
table text as fine-grained OCR tokens (one per cell, at that cell's own
bbox) instead of discarding them. No new model, no fine-tuning.

**Evidence before.** Every table cell in every `results/baseline/predictions/*.md`
(demo set, 2026-08-20) and every table cell in `results/local_baseline/predictions/*.md`
(this session) is blank.

**Evidence after.** Single-page (isolated, before the language fix below):
0/18 → 11/18 and 0/42 → 42/42 cells filled on the two tables of the
eastmoney page (Experiment 1 in `observations.md`). Benchmark-level: the
Metrics table above reflects this fix **and** the language fix below
applied together (one combined `local_improved` run, not three separate
ablation runs — a time tradeoff, documented rather than hidden); table
TEDS.all +0.0126, reading_order Edit_dist -0.0771 (see the "read honestly"
notes above for why the table gain is small and page-dependent).

**Regression?** `pytest -q` — 6 new tests in `tests/test_table_cell_text.py`
(confirmed to fail against the pre-fix code), full suite unaffected.

### 2. OmniDocBench-specific OCR language profile (`configs/omnidocbench.yaml`)

**Hypothesis.** `text_block` Edit_dist by `text_language` in the demo
baseline: English 0.3893 vs. simplified Chinese 0.9601, on a corpus that is
63% Chinese by line count in that same subset. `configs/cpu.yaml`'s
`ocr_languages: [en, vi]` has no Chinese model loaded.

**Change.** New `configs/omnidocbench.yaml`: identical to `cpu.yaml` except
`ocr_languages: [en, ch_sim]`. Not merged into `cpu.yaml` — EasyOCR hard-
rejects combining `ch_sim` with `vi` (`ValueError: Chinese is only
compatible with English`), so the private corpus's Vietnamese profile and
OmniDocBench's Chinese one cannot be the same list.

**Evidence before.** Same eastmoney demo page: 11 OCR tokens found under
`en`+`vi`, zero of them Chinese, zero overlapping either table.

**Evidence after (single-page, isolated).** 31 tokens under `en`+`ch_sim`
(up from 11), including correctly-read Chinese text. Benchmark-level: run
together with the table fix (see above) — `text_block Edit_dist
edit_sample_avg` -0.1894, `ALL_page_avg` -0.0859. The two changes also
compose directly, not just add: Experiment 1's table-cell text is
Docling's *own* OCR output, so a table's Chinese cell content is only
recoverable once this language fix lets Docling read it correctly in the
first place — table text on Chinese pages needed both fixes together.

**Regression?** `pytest -q` — new test asserts the profile never requests
`vi` (would crash `easyocr.Reader.__init__`); full suite unaffected.

## A third, necessary fix this comparison depends on

Not a pipeline improvement — a correctness fix to the *evaluation
methodology* itself, without which neither run above would be valid.
`prepare.py --subset N` against the full dataset produced predictions for
only N pages, but `evaluate.py` was scoring them against the **full**
1651-record ground truth — the official evaluator treats every ground-truth
page with no matching prediction file as an empty (i.e. failing)
prediction, so ~1631 automatic failures were being added to whatever the
20 real pages scored, collapsing every metric toward 1.0 (or 0 for TEDS)
regardless of actual pipeline quality. First local baseline attempt
(discarded): `text_block Edit_dist 0.9966`, `table TEDS.all 0.0026` — not
real pipeline numbers, an artifact of this bug. Fixed by
`omnidocbench.write_subset_ground_truth`, wired through `prepare.py` (writes
`<output>/subset_ground_truth.json` whenever `--subset` selects fewer than
all records) and `run.py`/`evaluate.py` (`--ground-truth` override, applied
automatically when that file exists). See `observations.md` for the full
trace and `tests/test_omnidocbench.py` for the regression tests.

## Improved vs. table-ensemble — bottleneck-analysis follow-up

Full evidence trail in `observations.md`, "Bottleneck Analysis". Same
20-page subset, seed=0, `configs/omnidocbench.yaml`, same pipeline code as
`local_improved` plus one change: when Table Transformer's structure
disagrees with Docling's own native table extraction for the same region,
keep whichever has more populated cells
(`pipelines/base.select_better_populated_table`).

| Metric | local_improved | local_table_ensemble | Delta |
| --- | ---: | ---: | ---: |
| table TEDS.all | 0.2584 | **0.3311** | **+0.0727** |
| table TEDS_structure_only.all | 0.3631 | **0.3791** | **+0.0160** |
| table Edit_dist (ALL_page_avg) | 0.7438 | 0.7621 | +0.0183 |
| text_block Edit_dist (ALL_page_avg) | 0.6332 | 0.6329 | -0.0003 (noise) |
| reading_order Edit_dist (ALL_page_avg) | 0.5301 | 0.5301 | 0.0000 |
| display_formula Edit_dist (ALL_page_avg) | 0.9959 | 0.9959 | 0.0000 |

**Read honestly:** the table TEDS gain is large (+0.073, ~28% relative)
and driven by two real per-table wins verified against ground truth —
`eastmoney_d2bb183f...` (TEDS 0.083 → 0.829: Docling's own TableFormer
found the exact correct 4x2 structure where Table Transformer detected
roughly 1x3) and `yanbaor2_ey-global-fintech...` (0.490 → 0.716). The
`table Edit_dist` regression (+0.018) traces to one specific table
(`jiaocaineedrop_..._en_1898`, TEDS 0.65 → 0.022) where the *pre-fallback*
score was itself a metric artifact — an all-empty prediction accidentally
matching a naturally sparse (checkbox-matrix) ground truth. Replacing empty
cells with a real-but-wrong attempt removed that lucky match; this is the
named, watched-for risk from the hypothesis in `observations.md`, not a
new problem discovered after the fact. text_block, reading_order, and
display_formula are unchanged to the fourth decimal place — confirming the
change is table-local, as designed.

For each improvement, per the required format:

```
Hypothesis: Table Transformer and Docling's own TableFormer structure
  models fail on different tables; a per-table fill-rate comparison
  recovers whichever did better without needing to predict in advance
  which one will win.
Change: pipelines/base.py — select_better_populated_table() +
  _apply_native_table_fallback(), wired into run_scanned_page_pipeline
  right after existing cell-text association. DoclingBackend.native_tables()
  exposes Docling's own table extraction from the SAME cached conversion
  recognize() already triggers — zero extra model inference.
Evidence before: 3 real per-table counterfactuals (oracle-region ablation,
  cross-model structure comparison) — see observations.md sections 3 and 7.
Evidence after: table TEDS.all +0.0727, TEDS_structure_only.all +0.0160,
  zero movement in text_block/reading_order/display_formula.
Regression?: table Edit_dist +0.0183, traced to one specific table and a
  pre-existing scoring artifact, not a new extraction failure. Tests:
  tests/test_table_cell_text.py (4 new cases covering fill-rate
  comparison, geometric matching, and graceful no-op for backends without
  native_tables).
```

## Larger-subset validation (100 pages)

Same experiment, same seed, `--subset 100` instead of 20 — see
`observations.md` "Larger-subset validation" for why (n=7 tables in the
20-page run is a small sample) and the full result. Summary:

- `results/local_table_ensemble_100/`: 100/100 pages succeeded, 0 failed,
  6956.8s total (~69.6s/page — matches the 20-page run's per-page cost).
- No separate 100-page pre-ensemble baseline was run (a second ~2-hour
  `prepare` pass, judged not worth the compute given what a real,
  unplanned check already provides — see below). Full aggregate numbers
  for this run are in `local_table_ensemble_100/report.md`; not repeated
  here since there is no paired "before" at this scale to diff them against.
- **Real reproducibility check found instead:** `select_subset(seed=0)`'s
  sampling is nested — the 100-page subset contains 6 of the 20-page
  subset's 7 real GT tables as the exact same source files. Each of those
  6 scores **identically** (to 3 decimals) in the 100-page ensemble run as
  in the 20-page one, and matches the 20-page `local_improved`→
  `local_table_ensemble` before/after pairs already reported above
  (`eastmoney_d2bb183f` 0.083→0.829, `yanbaor2_ey-global-fintech`
  0.490→0.716, `jiaocaineedrop_1898` 0.65→0.022, `jiaocaineedrop_46` and
  `page-28657a85` both 0.0→0.0, `book_zh_DLT10902008` 0.232→0.246). That is
  a genuine before/after pairing at 2x subset size, at zero extra compute
  cost, and it confirms the fix's per-table effect is deterministic and
  page-local rather than a 20-page-sample artifact.
- Of the 24 additional real GT tables only present at n=100: 14/30 tables
  in the full 100-page set (47%) score exactly 0.0 TEDS — both structure
  models fail together, the same failure mode as 2 of the original 7
  tables (29%), but *more* common in the larger sample, not less. Read
  honestly: this does not undercut the ensemble result (the 6 reproduced
  tables above still show it works exactly where it's supposed to) but it
  does sharpen the scope claim — composition recovers real gains where the
  two specialists disagree, and disagreement is common, but it does
  nothing for the (larger-than-expected) fraction of tables where both
  specialists fail together.
- **Decision: robust, not a small-subset artifact.**

## Oracle ablation — Opus audit (20-page subset, n=7 real GT tables)

Independent re-verification, full methodology and negative findings in
`observations.md` ("Opus audit and oracle analysis") and
`docs/research_proposal.md`. Candidates generated in one coherent process
(cross-run comparison was tried first and found unreliable — Table
Transformer's structure output is not bit-identical across separate
`prepare.py` invocations on CPU).

| Selector | mean table TEDS | matches oracle |
|---|---:|---:|
| Always Table Transformer | 0.2376 | 0/7 |
| Always Docling | 0.3325 | 5/7 |
| **Fill-rate (production, unchanged)** | **0.3325** | **5/7 (71%)** |
| Oracle (upper bound — picks the GT-better candidate per table; not a production method) | **0.4476** | 7/7 by definition |

Headroom (oracle − fill-rate) = **+0.115 mean TEDS**. Both misses
(`book_zh_DLT10902008`, `jiaocaineedrop_...en_1898`) share one root cause:
TEDS scores an all-empty prediction generously against a naturally-sparse
ground-truth table, and fill-rate cannot tell "correctly recognized
nothing is here" apart from "failed to recognize something that is here."
Checked directly whether a fill-rate threshold closes this without
breaking the currently-correct `docstructbench` decision (same TT-fill=0
signature) — none does. Selective-escalation-to-save-compute was also
tested and rejected on the same data: neither model's own fill-rate
reliably predicts when the other should be invoked (full detail in
`docs/research_proposal.md`, "Selector").

100-page validation of the *both-fail* rate (directly measured, no
reconstruction): 14/30 tables (47%), larger than the 7-table sample's 29%
— narrows, not inflates, the claimed opportunity. The full 100-page
oracle-vs-selector gap was not completed (11 of 29 table pages
independently timeout-flagged by the evaluator itself for TEDS matching;
stopped after the first untested page ran past 850 CPU-seconds — see
`observations.md` section 17 for the full accounting).

**Decision: composition is a validated, bounded engineering improvement,
not (yet) a generalizable confidence-aware-ranking research result.** See
`docs/research_proposal.md` for the full writeup and rationale.
