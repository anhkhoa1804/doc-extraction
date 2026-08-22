# Observations — 005 OmniDocBench, local full-dataset iteration

Run 2026-08-22, CPU-only (`configs/cpu.yaml` baseline device), full
1651-page OmniDocBench dataset obtained locally (see README "Dataset"),
`doc_extraction` 0.1.0 / docling 2.120.3 / easyocr 1.7.2 / torch 2.8.0+cpu.

Continues on from the 18-page demo-set baseline already committed under
`results/baseline/` (device=cpu, run 2026-08-20) — that run's own per-language
attribute breakdown was the first hint investigated here.

## Experiment 1 — table cells are 100% empty in every `baseline`-pipeline prediction

**Hypothesis.** The demo baseline's `table.TEDS.all = 0.1526` against
`table.TEDS_structure_only.all = 0.6095` (see `results/baseline/report.md`)
is a large, suspicious gap: structure detection is reasonable, full TEDS
(which also scores cell text) collapses. That gap shape is a known signature
of "structure right, content wrong/missing" rather than "detector missed the
table."

**Evidence.** Grepped every table in every existing prediction file under
`results/baseline/predictions/` and `results/docling/predictions/`
(2026-08-20 demo-set run, predates this session's changes):

- `baseline` backend: **every single table cell in every prediction is
  blank** (`|  |  |  |  |`), with no exceptions.
- `docling` backend (Docling's own whole-document conversion, a completely
  separate code path): tables **do** have real (if imperfect) cell text —
  e.g. `| PAHs compounds | % Recovery 4 RSD | ... |`.

This rules out "no available model can populate table cells" — Docling's own
pipeline demonstrably can. The bug is specific to how the `baseline`
pipeline's two independent table-related components (`TableTransformerBackend`
+ `_fill_table_cell_text`) are wired together.

**Root cause, traced with a real page**
(`eastmoney_..._pdf_0.jpg`, from the OmniDocBench demo set):

1. `TableTransformerBackend._recognize_structure` (`src/doc_extraction/backends/table_backend.py`)
   builds every `Cell` with `text=""` — Table Transformer detects row/column
   geometry only, by design; it never reads text. This is documented in the
   module's own docstring ("Cell text is filled in by the caller").
2. The intended caller-side fill, `_fill_table_cell_text` in
   `src/doc_extraction/pipelines/base.py`, matches OCR tokens to each cell's
   bbox by center-point containment — but `DoclingBackend.recognize()`
   explicitly **excluded** table-labeled items from its token list:
   `if label == "table": continue  # table text is handled by the table
   stage, not OCR tokens`. That comment was aspirational, not true: the
   table stage (step 1) never had text to hand out. Confirmed directly:
   `docling.recognize(page_input)` on this page returned 11 tokens, **zero**
   of which overlap either of the page's two table regions.
3. Cropping just the table region and re-running OCR on it in isolation
   (with and without a 2x upscale) also found **zero** tokens — ruling out
   "coarse block granularity" and "low resolution" as the cause for this
   specific gap; the text genuinely wasn't being read there at all under the
   configured OCR languages (see Experiment 2 — the table is ~95% Chinese
   text, and `configs/cpu.yaml` has no Chinese OCR model loaded).
4. Docling's own `docling_doc.iterate_items()` table item, from the exact
   same conversion, already carries **real per-cell bboxes and text**
   (`item.data.table_cells[i].{bbox,text}` — TableFormer + Docling's
   internal OCR) — the same data `_convert_docling_table()` already uses
   for the separate `backend=docling` whole-document path. It was being
   computed and then discarded by the `continue` in step 2.

**Change.** `DoclingBackend.recognize()` (`src/doc_extraction/backends/docling_backend.py`):
instead of skipping table items outright, emit one `OCRToken` per non-empty
Docling table cell, at that cell's own tight bbox — not the whole table's
bbox. This is the fix task-recommended direction 2 ("table assembly") names
exactly: the loss was in cell-assignment/text-association, not in either
model. No new model call, no fine-tuning — this only stops discarding data
Docling already computed. `TableTransformerBackend` and
`_fill_table_cell_text` are both unmodified; the existing center-point
matching now has real per-cell tokens to match against instead of nothing.

**Evidence after (single-page, pre-benchmark check).** Same page, same
Table Transformer-detected grid:

| | Table 1 (2x9 grid) | Table 2 (6x7 grid) |
|---|---:|---:|
| Cells filled, before | 0 / 18 | 0 / 42 |
| Cells filled, after | 11 / 18 | **42 / 42** |

Table 1's shortfall is a genuine grid-size mismatch between the two
independent models (Table Transformer detected a slightly different row
count than Docling's own TableFormer on that specific table) — not a
regression, and not something this fix claims to solve; it is the ceiling of
"two independently-detected structures, geometrically reconciled."

**Tests.** `tests/test_table_cell_text.py` (6 cases, all confirmed to fail
against the pre-fix code before the fix was applied): per-cell token
emission, tight-bbox-not-whole-table-bbox (the actual bug), non-table tokens
unaffected, `BOTTOMLEFT`-origin conversion, end-to-end fill through the
unmodified `_fill_table_cell_text`, and a defensive empty-`table_cells` case.

**Benchmark-level before/after:** see `results/comparison.md`.

## Experiment 2 — OCR has no Chinese language model loaded

**Hypothesis.** The same demo baseline's `text_block` attribute breakdown
(`results/baseline/report.md`) shows `Edit_dist` by `text_language`:
**English 0.3893** vs **Chinese (simplified) 0.9601** — near-total failure
on Chinese, on a benchmark whose demo subset is 149/238 (63%) Chinese text
lines by this same breakdown.

**Evidence.** `configs/cpu.yaml` sets `ocr_languages: ["en", "vi"]` — tuned
for this repo's own private corpus (Vietnamese/English; see
`data/README.md`), which has no relation to OmniDocBench's language mix.
Visually confirmed on the same `eastmoney_...pdf_0` table crop (rendered at
2x): the table is ~95% Chinese characters (行业, 银行, 公司网址, 总股本...)
with one English URL. Under `en`+`vi`, Docling's page-level OCR pass found
zero tokens overlapping either table on that page (Experiment 1, step 3).

**Change.** New `configs/omnidocbench.yaml`, identical to `configs/cpu.yaml`
except `ocr_languages: ["en", "ch_sim"]`. Not applied to `configs/cpu.yaml`
itself: `easyocr.Reader.setModelLanguage` hard-rejects combining `ch_sim`
with anything but `en` (`ValueError: Chinese is only compatible with
English`) — `ch_sim` and `vi` cannot coexist in one EasyOCR config, so the
private corpus's language profile and OmniDocBench's are genuinely
different deployments, not a single list that should grow. This is a
general "use the right OCR language profile for the corpus" choice (the
same reasoning `configs/cpu.yaml` already documents for choosing `vi`), not
an OmniDocBench-specific hack.

**Evidence after (single-page check).** Same page, `en`+`ch_sim` (ch_sim
EasyOCR model prefetched via `docling.cli.tools models download easyocr
--easyocr-lang en --easyocr-lang ch_sim`):

- OCR tokens found on the page: 11 → 31, now including correctly-read
  Chinese text (`常熟银行(601128.SH)`, `强烈推荐(维持)`, analyst names, etc.)
- Table region tokens specifically: still 0 under `en`+`ch_sim` alone —
  this is Experiment 1's bug, a *different* cause (table items are excluded
  from OCR tokens regardless of language). The two fixes are independent
  and compose: language fix recovers non-table Chinese text; the
  cell-association fix (Experiment 1) recovers table text, and needed the
  language fix first for Docling's *own* table-cell OCR to read Chinese
  correctly in the first place.

**Tests.** `tests/test_config_and_backends.py::test_omnidocbench_config_uses_chinese_compatible_ocr_languages`
asserts the profile only ever requests a subset of `{en, ch_sim}` and never
`vi` — a regression guard against silently merging this back toward
`cpu.yaml`'s language list, which would crash `easyocr.Reader.__init__`.

**Benchmark-level before/after:** see `results/comparison.md`.

## Experiment 3 — `--subset` against the full dataset was silently scoring ~1600 phantom failures

Not a pipeline finding — a bug in this repo's own benchmark tooling,
discovered while trying to produce a *valid* local baseline for Experiments
1-2, and one that had to be fixed before either of those experiments' numbers
could mean anything.

**What happened.** First `local_baseline` attempt: `--dataset
.external/OmniDocBench-data --subset 20 --seed 0`. Every metric came back
near-total-failure — `text_block Edit_dist.ALL_page_avg 0.9966`, `table
TEDS.all 0.0026`, `reading_order Edit_dist.ALL_page_avg 0.9952` — a much
larger collapse than the demo baseline's known-working numbers, despite
spot-checking the actual generated predictions and finding real, correct
extracted text (e.g. `"Rensselaer Polytechnic Institute"` from an academic
slide).

**Root cause, traced in the evaluator's own source (not assumed).**
`metrics.json`'s own `match_debug.page_count` read **1651** — the evaluator
had scored against the *entire* dataset's ground truth, not our 20-page
subset. Confirmed in
`.external/OmniDocBench/src/dataset/end2end_dataset.py`:
`End2EndDataset.__init__` loads the full `gt_path` JSON unfiltered
(`filtered_gt_samples = gt_samples` when no attribute `filter` is set) and
`_match_single_page` does `pred_content = read_md_file(pred_path) if
pred_path else ""` — a ground-truth page with no matching prediction file is
scored as an **empty prediction**, not skipped. With 20 real predictions
against 1651 ground-truth pages, ~1631 pages (98.8%) were being scored as
complete failures, swamping whatever the 20 real pages actually achieved.

This had never surfaced before in this project because every prior
evaluator run used the **demo** dataset, whose `OmniDocBench_demo.json`
*is* an 18-record file with exactly 18 matching images — 1:1 correspondence
by construction, so the bug had no unmatched pages to manifest through.
This session is the first time `--subset` was combined with the full
1651-page dataset.

**Fix.** `omnidocbench.write_subset_ground_truth(gt_path, samples,
output_path)`: writes a ground-truth JSON containing only the original
records for the selected subset (looked up by `OmniDocSample.index`, the
record's exact position in the source JSON — not reconstructed from our own
trimmed sample fields, so every original annotation field survives).
`prepare.py` calls it automatically whenever `--subset` selects fewer than
all records, writing `<output>/subset_ground_truth.json`. `evaluate.py`
gained a `--ground-truth` override flag; `run.py` detects the file and
passes it automatically, including under `--skip-prepare` (checked by file
presence, not by `--subset` being set on the current invocation, so
re-evaluating an earlier subset run picks it up too).

**Verification.** Re-evaluated the *same* 20 predictions (no
re-generation) against the corrected subset ground truth:
`text_block Edit_dist.ALL_page_avg` 0.9966 → **0.7191** — in line with the
demo baseline's 0.7448 on a similar (majority-Chinese, mixed document type)
corpus, not a coincidental improvement.

**Tests.** `tests/test_omnidocbench.py`:
`test_write_subset_ground_truth_keeps_only_selected_records`,
`test_write_subset_ground_truth_matches_original_record_exactly`,
`test_run_passes_ground_truth_override_only_when_subset_file_exists`.

## What was NOT changed, and why

- **Reading order** (task direction 1): the demo baseline's
  `reading_order.Edit_dist.ALL_page_avg = 0.6463` is mediocre but not the
  standout outlier the table/language findings are (0.15 TEDS, 0.96 Chinese
  edit-distance) — no page-level reading-order failures were mined this
  session; revisit after re-measuring with both fixes in place, since a
  correctly-populated table changes what "reading order" is scoring in the
  first place (previously-empty cells could not be out of order).
- **Rendering resolution** (task direction 4): tested directly (Experiment 1,
  step 3) as a candidate explanation for the table token-finding failure —
  a 2x upscale of the table crop found the same zero tokens as no upscale.
  Resolution was not the cause here; not pursued further.
- **Adaptive routing** (task direction 3): every OmniDocBench sample is a
  standalone image with no native text layer — the `digital_pdf` vs
  `scanned_pdf`/`image` routing decision this direction targets never
  triggers for this benchmark at all (see `results/*/report.md`, "Routes
  taken: {'image': N}" for every run observed this session). Not applicable
  to this corpus.
- **VLM backends**: explicitly out of scope for this phase per the task.

## Environment note (not a pipeline finding)

`experiments/005_omnidocbench/run.py`, invoked directly on this Windows dev
machine, crashed with `UnicodeEncodeError` from `prepare.py`'s own
`print()`-based progress logging when the full dataset's subset included a
filename containing non-cp1252-encodable characters. Same root cause as the
already-documented "Known Windows issue" for the evaluator subprocess
(`experiments/005_omnidocbench/README.md`), just in the parent process
this time — Windows' default console encoding, not UTF-8. Fixed the same
way the evaluator subprocess already is: `PYTHONUTF8=1` in the environment
before invoking `run.py`. Not a pipeline defect; not changed in source
(the existing fix pattern already documents how to work around it).
