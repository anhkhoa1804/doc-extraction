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
