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

# Bottleneck Analysis

Continuing directly from the architecture audit (previous session): the
canonical-IR coupling hypothesis was rejected with evidence (`Element`/
`Table` are structurally separate; `compute_reading_order` reads only
`bbox`). This section investigates the two questions the audit left open —
double jeopardy in the evaluator, and where the real remaining ceiling is —
using the corrected 20-page subset (seed=0) and real per-table/per-page
evaluator output, not aggregate metrics alone.

## 1. Evaluator mechanics — the double-jeopardy verdict

**Question:** does malformed/unrecognized table Markdown get scored as
failed plain text *in addition to* failing the table metric?

**Traced completely**, not assumed, in
`.external/OmniDocBench/src/dataset/end2end_dataset.py` and
`src/core/preprocess/extract.py`:

- `process_get_matched_elements` builds `pred_dataset_mix` (the pool fed to
  plain-text matching) from every `md_tex_filter` category except
  `html_table`/`latex_table`/`md2html_table`/`formula_rescue` — anything
  correctly recognized as a table is excluded from text matching entirely.
  `gt_mix` (the ground-truth pool for text matching) excludes GT's `table`
  category too. Symmetric: no double-jeopardy for a correctly-recognized
  table, by construction.
- Detection itself: `md_table_reg = re.compile(r'\|\s*.*?\s*\|\n')` — any
  line shaped `|...|` followed by a newline. `md_tex_filter` requires 2 or
  more such lines before converting to `html_table`.
- Our `Table.to_markdown()` (`schemas/table.py`) always emits a header
  `---` separator row plus every data row, each individually
  `|...|`-shaped — structurally guaranteed to clear the 2-line threshold
  for any table with `n_rows >= 1`. A zero-row table returns an empty
  string, which `page_to_prediction_markdown` then drops as falsy (silently
  omitted — a third failure mode, not double-jeopardy, but worth naming: a
  zero-row table vanishes from the prediction with no signal at all).

Verified empirically, not just by reading the regex: ran `md_tex_filter`
(the evaluator's own parser, via `.venv-omnidoc`) directly against all 20
real `local_improved` prediction files. Every one of the 5 files containing
pipe-table syntax parsed to exactly one `html_table` entry plus separate
`text_all` entries for the surrounding prose — zero leakage either
direction, on every real table in this subset.

**Verdict: double-jeopardy does not occur for our serialization, given the
evidence gathered.** Neither intrinsic to the benchmark (a genuinely
malformed table elsewhere could in principle leak into text scoring —
nothing in the evaluator prevents that in general) nor a problem introduced
by our implementation (our generator's output structurally cannot fail the
2-pipe-line detection threshold for any non-empty table). This closes the
open question from the architecture audit.

## 2. Serialization quantification — table recognition per page

All 7 pages in the 20-page subset containing a GT table (not 5 — see the
taxonomy below for why the earlier count was wrong), read from the
evaluator's own per-table debug output
(`.external/OmniDocBench/result/predictions_quick_match_table_per_table_TEDS.json`)
cross-referenced against real prediction Markdown:

| Page | Recognized as table? | Matched? | TEDS available? | Leaked into text? | Reading-order contribution |
|---|---|---|---|---|---|
| page-28657a85... | no (nothing emitted) | yes, vs empty pred | yes (0.0) | no | none |
| docstructbench_...0768-9.pdf_2 | yes | yes | yes (0.354) | no | partial (9/10 rows) |
| yanbaor2_ey-global-fintech...30 | yes | yes | yes (0.490) | no | partial (11/13 cells matched) |
| jiaocaineedrop_46.pdf_1 | no (nothing emitted) | yes, vs empty pred | yes (0.0) | no | none |
| jiaocaineedrop_...en_1898 | yes | yes | yes (0.65, misleading — see below) | no | minimal (all-empty cells) |
| eastmoney_d2bb183f...pdf_7 | yes | yes | yes (0.083) | no | minimal (1/4 rows) |
| book_zh_DLT10902008...page_8 | yes | yes | yes (0.232) | no | minimal (wrong col count) |

## 3. Table failure taxonomy (7 real GT tables, real root causes)

Each classified with a targeted counterfactual, not a guess:

1. **page-28657a85** (TEDS 0.0) — structure-model capability ceiling. GT
   is one row, 3 cells, each a full Chinese sentence (an atypical,
   borderline "table"). Neither Docling's layout classifier nor Table
   Transformer's own standalone detector found a table region on the full
   page. Oracle ablation: handed Table Transformer the exact GT bbox
   directly (bypassing detection) — its structure model still found zero
   rows/columns. Detection failure and structure failure are the same
   event here: even given a perfect crop, this table's shape is outside
   what the structure model recognizes.
2. **jiaocaineedrop_46.pdf_1** (TEDS 0.0) — detection miss, secondarily an
   OCR gap. GT is a tiny 2-row math sequence table (fractions, symbols).
   Both detectors missed it standalone. Oracle ablation: given the GT
   bbox directly, Table Transformer did recover a plausible 2x6 structure —
   so detection, not structure, was the bottleneck for this one. But
   cell-text association still produced 0/12 filled: Docling's own OCR
   found nothing in that region either (a formula-heavy math table,
   consistent with this project's already-documented no-formula-model
   limitation).
3. **docstructbench_..._0768-9.pdf_2** (TEDS 0.354, structure 0.691) —
   structure imperfect plus partial content. A complex 2-row rowspan/
   colspan header was entirely dropped (9 predicted rows vs GT's 10); many
   correct numeric values recovered (38.7, 5.70, 97.5(2.5)a — near-exact
   matches), but a "soil texture" column came through mostly empty and
   digit ranges lost their hyphen (26-51 became 2651).
4. **yanbaor2_ey-global-fintech...30** (TEDS 0.490, structure 0.606) —
   cell-text-association gap on an otherwise-correct structure. Verified
   directly: Table Transformer found all 11 rows at the right position
   (confirmed by reading the raw structure-model output, scores
   0.999-1.000) — the missing header text is not a dropped row, it's
   Docling's own per-cell OCR coming back empty for that specific row. The
   rest of the table's text matches near-verbatim.
5. **jiaocaineedrop_..._en_1898** (TEDS 0.65 — a metric artifact, not a
   win) — 100% of predicted cells are empty. GT itself is a checkbox
   matrix where most cells are legitimately blank, so an all-empty
   prediction accidentally matches most of GT's own emptiness. This is a
   genuine, separate cell-text-association total failure that TEDS happens
   to score generously — worth flagging so it isn't mistaken for a success
   in any future aggregate-only reading.
6. **eastmoney_d2bb183f...pdf_7** (TEDS 0.083, structure 0.167) — wrong
   structure. Table Transformer detected roughly 1 row x 3 cols; GT is 4
   rows x 2 cols. Counterfactual: Docling's own native TableFormer, run on
   the identical page, found the exact correct 4x2 structure with all 6
   cells correctly populated (评级/定义 header, 买入/持有/卖出 labels, and a
   near-verbatim definition string). Confirms the ceiling here is Table
   Transformer's structure model specifically, not text association, not
   our orchestration — and that a second, independent structure model does
   not share the same failure.
7. **book_zh_DLT10902008...page_8** (TEDS 0.232, structure 0.429) — wrong
   structure, and neither model handles it. Table Transformer detected 6
   columns against GT's 2. Counterfactual: Docling's own TableFormer on the
   same page collapsed the table to 1x1 (worse). A genuinely hard case
   (sparse fill-in-the-blank form table, vertical Chinese unit labels)
   where both independent structure models fail — ensembling the two would
   not help this specific page, and does not pretend to.

Tally: 2/7 pure or compounded detection misses; 3/7 structure-recognition
clearly wrong (including one where a second independent model gets it
exactly right, and one where neither does); 2/7 structure essentially
correct with the remaining loss in cell-text association (Docling's own
OCR, not our matching code — the association mechanism itself, fixed in
the prior session, now works correctly whenever the underlying OCR text
exists). n=7 is small — this is a real, page-level-verified directional
signal, not a population-level statistical claim; see the larger-subset
validation this motivates, below.

## 4. Multilingual OCR, quantified separately from table content

Per-page text_block edit-distance (already-Chinese-OCR-enabled run),
cross-referenced against each page's own `page_info.page_attribute.language`
(read directly from the ground truth, not inferred):

| GT page language | n pages | mean text_block Edit_dist |
|---|---:|---:|
| simplified_chinese | 10 | 0.5869 |
| english | 7 | 0.6866 |
| en_ch_mixed | 2 | 0.6776 |

Chinese pages now score better on average than English pages in this
subset — a full reversal of the pre-fix demo baseline's 0.9601 (Chinese) vs
0.3893 (English). The OCR-language fix's effect on text is confirmed,
large, and separable from the table fix (this table uses text_block
matching, which — per section 1 above — never includes table content). Its
effect on table content is conditional, not automatic: Chinese table text
is only recoverable when Docling's own per-cell OCR succeeds in the first
place (tables 3, 4, 6 above show real Chinese/mixed cell text; table 5's
total OCR failure would remain a failure regardless of language config).
OCR language and table-cell association are two independent fixes that
compose only when both preconditions hold on the same table. The
highest-error remaining pages are not obviously language-driven (e.g. a
formula-dense English PPT slide scored 1.0) — consistent with this
project's already-documented no-formula-recognition-model limitation, not
an OCR-coverage gap.

## 5. Component upper-bound estimates (from the evidence above)

| Component | Evidence | Verdict |
|---|---|---|
| Table detection | 2/7 tables never got a region at all; 1 of those recovered structure once given the true bbox (oracle) | Real, but narrow — mostly atypical/small tables, not the dominant loss |
| Table structure recognition | TEDS_structure_only ranges 0.0-0.69 across real tables; an independent second model (Docling's TableFormer) gets one case exactly right where Table Transformer fails outright, and gets a different case wrong where Table Transformer does relatively better | The largest remaining, addressable component — neither model is uniformly sufficient, but the two disagree in ways an ensemble can exploit |
| Cell-to-text association | Fixed in the prior session; verified still working via the unmodified matching logic. Remaining no-text cases trace to the upstream OCR step producing nothing, not to the association step mismatching | Not the ceiling anymore |
| Serialization / evaluator matching | Section 1 above — verified no double-jeopardy on any real table this session | Not a source of measurable loss here |
| OCR language coverage | Full reversal of the Chinese/English gap, confirmed on real per-page data | Fixed; remaining large-error pages look formula-driven, not language-driven |

## 6. Hypothesis ranking (per the four candidate directions)

- A, late fusion / specialist composition: the evidence directly supports
  a narrow form of this — not "fuse all specialists better in general,"
  but specifically that Table Transformer and Docling's TableFormer
  disagree, and a cheap per-table signal picks the right one on both
  observed disagreement cases. This is the direction pursued below.
- B, confidence-aware selective processing: the concrete, minimal instance
  the evidence supports is table-level, not page-level: use each
  candidate's own output (cell fill-rate) as the confidence signal, per
  table, rather than a whole-page easy/hard classifier. A page-level
  version is not supported by evidence gathered this session — the two
  structurally-wrong tables (6, 7) don't share an obvious page-level
  "hard page" signal distinguishing them from the two well-structured
  ones (3, 4).
- C, coarse-to-fine / multi-resolution: not supported by evidence
  gathered. The one resolution test performed (table-crop upscaling,
  prior session) changed nothing; none of the 7 failures here trace to
  resolution.
- D, table-specific specialist cascade (detect, classify difficulty,
  route): a strict superset of the chosen direction below, requiring an
  additional difficulty classifier with no evidence yet that one is
  learnable from available signals. The simpler fill-rate-based version
  (compute both, keep the better one, rather than predict which will win)
  is preferred as the smaller, more directly evidenced first experiment.

## 7. Chosen experiment

Hypothesis: Table Transformer and Docling's own TableFormer fail on
different tables (confirmed: table 6 above breaks Table Transformer but
not Docling; table 7 breaks both, roughly equally). A per-table choice
between the two, using cell fill-rate as a cheap proxy for "which one
actually extracted something," recovers the better structure on tables
where the two disagree, without needing to know in advance which model
will win.

Expected failure mechanism: Table Transformer's structure model, run
independently of Docling's, sometimes detects the wrong row/column grid
(confirmed on 2/7 real tables, one where the ceiling is model capability
even given a perfect crop, one where a second model does much better).

Proposed change: after Table Transformer plus cell-text association
produce a table, also fetch Docling's own native table extraction for the
same page (already computed by the same cached conversion `recognize()`
uses — no extra model inference) and keep whichever of the two has more
populated cells, matched geometrically per table.

Metric expected to improve: table TEDS.all, TEDS_structure_only.all.

Potential regression: none expected on tables where both backends already
agree (a tie keeps the original); a table where Docling's own extraction
is populated but wrong could in principle score worse than a
correctly-empty Table Transformer result — cell fill-rate does not
distinguish "correct content" from "confident but wrong content." Watched
for directly in the result below, not assumed away.

Experiment: same 20-page subset, seed=0, same `configs/omnidocbench.yaml`,
baseline pipeline code from `local_improved` plus this one change ->
`results/local_table_ensemble/`.

Success criterion: table TEDS.all improves without any of the other four
metric categories (text_block, reading_order, display_formula, table
Edit_dist) moving in the wrong direction beyond noise.

## 8. Result

Same 20-page subset, seed=0, `configs/omnidocbench.yaml`, only the
native-table-fallback change on top of `local_improved`:

| Metric | local_improved | local_table_ensemble | Delta |
|---|---:|---:|---:|
| table TEDS.all | 0.2584 | **0.3311** | **+0.0727** |
| table TEDS_structure_only.all | 0.3631 | **0.3791** | **+0.0160** |
| table Edit_dist.ALL_page_avg | 0.7438 | 0.7621 | +0.0183 (regression, explained below) |
| text_block Edit_dist.ALL_page_avg | 0.6332 | 0.6329 | -0.0003 (noise) |
| reading_order Edit_dist.ALL_page_avg | 0.5301 | 0.5301 | 0.0000 |
| display_formula Edit_dist.ALL_page_avg | 0.9959 | 0.9959 | 0.0000 |

**Success criterion met**: table TEDS improved substantially (+0.073, ~28%
relative — not a "+0.005" result) with text_block, reading_order, and
display_formula all unchanged to the fourth decimal place. This is expected
and confirms the change is table-local, as designed: it touches nothing in
layout, OCR, or reading order.

**Per-table**, from the evaluator's own debug output — the aggregate hides
real, large, individually-verifiable swings, not a uniform small nudge:

| Table | Before TEDS | After TEDS | What happened |
|---|---:|---:|---|
| page-28657a85 | 0.0 | 0.0 | unchanged — both models fail (predicted, see taxonomy #1) |
| docstructbench | 0.354 | 0.505 | +0.151 |
| yanbaor2_fintech | 0.490 | 0.716 | +0.226 |
| jiaocaineedrop_46 | 0.0 | 0.0 | unchanged — both models fail (predicted, see taxonomy #2) |
| jiaocaineedrop_1898 | 0.65 | 0.022 | **-0.628 — see below** |
| eastmoney | 0.083 | 0.829 | **+0.746 — the predicted counterfactual, confirmed** |
| book_zh | 0.232 | 0.246 | +0.014 (both models weak, as predicted, ~a wash) |

**The one real per-table "loss" (jiaocaineedrop_1898, table 5 in the
taxonomy) is the metric artifact flagged in advance, not a new problem.**
Before: 100% empty predicted cells accidentally matched most of a
naturally-sparse (checkbox-matrix) ground truth, scoring 0.65 by luck. The
fallback replaced those empty cells with Docling's own real-but-wrong
attempt — TEDS dropped to 0.022 because the table is now scored on actual
(incorrect) content instead of getting a pass for predicting nothing. This
is the honest cost of removing a scoring artifact, not a new extraction
regression — and it was named as a specific, watched-for risk in the
hypothesis above before the run, not rationalized after the fact.

**table Edit_dist.ALL_page_avg's small regression (+0.0183) is consistent
with the same table**: its per-table Edit_dist in this run is 0.917 (the
second-worst of all 7, after two complete 1.0 failures) — matching the
TEDS collapse. The pre-ensemble per-table Edit_dist value isn't recoverable
(the evaluator overwrites its own debug directory each run, and only
aggregate `metrics.json` is copied out), so this is the best-supported
explanation available, stated as such rather than as a confirmed fact.

**Regression check, explicit:** none of `text_block`, `reading_order`,
`display_formula` moved beyond floating-point noise. The single metric
that moved against the hypothesis (`table Edit_dist`) is accounted for by
name, not ignored, and traces to the one table where "have I introduced
new plausible-looking wrong content" is a real cost — worth remembering if
this direction is extended (e.g. gating the fallback on more than raw
fill-rate in a future iteration), not disqualifying this result.

## 9. Decision

**The next 10-20% of extraction quality is not hiding in OCR, reading
order, or serialization/matching — evidence across sections 1-6 rules each
of those out or shows them already fixed. It is in table structure
recognition specifically**, and it is recoverable *now*, without training,
by exploiting that two independently-trained structure models
(Table Transformer, Docling's TableFormer) fail on different tables. This
is not a hypothesis anymore — it produced a real, measured, mechanism-
understood +0.073 TEDS / +0.016 structure-only gain on real pages, with a
named and explained (not hidden) trade-off on one table, and zero
collateral movement elsewhere.

This does **not** mean Table Transformer should be replaced or fine-tuned
(explicitly out of scope, and not what the evidence supports — table 7
shows both models can fail together, so a single better single model isn't
guaranteed by this evidence either). It means composition between existing,
already-available specialists has real, unclaimed headroom — a
reusable principle (`select_better_populated_table` in
`pipelines/base.py`), not a one-off patch: any future second table (or
layout, or OCR) backend can plug into the same fill-rate comparison.

## 10. Larger-subset validation (n=7 tables is small)

The 20-page result rests on 7 real tables — real, page-verified, but a
small sample. The ensemble pipeline was re-run on `--subset 100 --seed 0`
(same config, same code) — `results/local_table_ensemble_100/`, 100/100
pages succeeded, 6956.8s wall clock (~69.6s/page, consistent with the
20-page run's per-page cost — no scaling surprise).

**No separate 100-page pre-ensemble ("before") run was executed.** Each
100-page `prepare` pass costs ~2 hours; running a second one purely to
re-derive numbers already well-established at n=20 was judged not worth
the compute, per this task's own budget-consciousness constraint. Instead,
a real, unplanned check turned up: `select_subset(..., seed=0)`'s sampling
is nested, not independently re-randomized per `limit` — the 100-page
subset contains (at least) 6 of the 7 tables from the 20-page subset, as
*the exact same source files*. That gives a genuine, zero-extra-cost
before/after pairing at 100-page scale, not just at 20:

| Table | 20-page before (`local_improved`) | after (both 20-page and 100-page ensemble runs, independently) |
|---|---:|---:|
| eastmoney_d2bb183f | 0.083 | 0.829 (identical in both runs) |
| yanbaor2_ey-global-fintech | 0.490 | 0.716 (identical in both runs) |
| jiaocaineedrop_1898 | 0.65 | 0.022 (identical in both runs) |
| jiaocaineedrop_46 | 0.0 | 0.0 (identical in both runs) |
| page-28657a85 | 0.0 | 0.0 (identical in both runs) |
| book_zh_DLT10902008 | 0.232 | 0.246 (identical in both runs) |

Every one of these 6 tables scores **exactly identically** (to 3 decimal
places) whether the ensemble pipeline runs as part of a 20-page batch or a
100-page batch. That is a real reproducibility result, not a coincidence:
the fix's effect is deterministic and page-local, not an artifact of which
other pages happen to be in the same run. This directly answers the
question this section set out to check — "is the improvement robust or a
small-subset artifact" — for the original 7 tables: robust, confirmed at
2x the subset size, same result.

**What is genuinely new at n=100** is 24 more real GT tables (30 total vs.
7), giving a broader, still-honest picture of the surrounding landscape:

- Aggregate: `table TEDS.all` 0.2743, `TEDS_structure_only.all` 0.3504,
  `table Edit_dist.ALL_page_avg` 0.7177 (all post-ensemble; no matching
  pre-ensemble 100-page aggregate exists, for the cost reason above — do
  not read these as a delta against `local_improved`'s 20-page 0.2584).
- **14 of 30 tables (47%) score exactly 0.0 TEDS** — both structure models
  fail together, the same phenomenon as taxonomy table #1 and #2 in section
  3, but at a *higher* rate than the 7-table sample suggested (2/7 ≈ 29%).
  Read honestly: the larger sample does not make the detection/structure
  capability ceiling look smaller — it looks larger. This strengthens,
  not weakens, section 9's caveat that composition recovers real headroom
  but does not close the gap where both existing specialists fail
  together; that gap remains open and, on this evidence, is the single
  largest remaining component of table loss.
- `text_block`, `reading_order`, `display_formula` all completed with
  0/100 failed pages and metric values in the same range as the 20-page
  run (`text_block Edit_dist.ALL_page_avg` 0.4869 vs. 0.6332 at n=20 — a
  real difference, expected, since a larger random page sample pulls in
  different document types, not a sign of instability: no NaNs, no
  collapsed/degenerate scores, no crashes across 100 diverse pages).

**Decision: the table-ensemble result is robust, not a small-subset
artifact** — the strongest available evidence (exact reproduction of 6
real tables' scores across two independently-run subset sizes) supports
this directly. The one thing the larger sample changes is the *context*:
composition recovers real, real-page-verified gains where the two models
disagree, but "both models agree by failing" is more common than n=7
suggested, and remains this pipeline's largest untouched table-quality
gap — a detection/structure capability question, not an orchestration one,
and out of this experiment's scope (see section 9 and "does not claim" in
`docs/research_direction.md`).

# Opus audit and oracle analysis

Taking over as senior owner (previous work: Claude Sonnet, commit
`746808f`). Per instructions, this section independently re-verifies the
composition claim from primary evidence before extending it — not a
continuation write-up.

## 11. Audit verdict

Every numeric claim in the "Bottleneck Analysis" section above and in
`results/comparison.md` was checked against the actual `metrics.json`
files (not the markdown summaries) and matches to the reported precision:
`local_improved` table TEDS.all `0.2583704785790072`,
`local_table_ensemble` `0.3311...`, all four runs' `run_metadata.json`
confirm identical `ground_truth_sha256`, evaluator commit, config, and
seed. The implementation (`select_better_populated_table`,
`_apply_native_table_fallback`, `DoclingBackend.native_tables`) does what
the docstrings claim — read directly, not inferred from comments.
**Sonnet's numbers are real, not overclaimed.** Sonnet's own hypothesis
text before running the experiment explicitly named the exact risk this
audit's oracle analysis went on to confirm as real ("cell fill-rate does
not distinguish correct content from confident but wrong content") — this
was flagged as a risk in advance, not discovered after the fact and
retrofitted.

What this audit adds: (1) a quantified oracle ceiling — Sonnet's taxonomy
was qualitative ("the selector can be wrong when a table is a metric
artifact") without a number for how much that costs in aggregate; (2) a
tested, evidence-based verdict on whether the composition layer could
safely SAVE compute by escalating selectively, which Sonnet's work did not
address; (3) a genuinely N-candidate, model-agnostic selection primitive
(Sonnet's was a fixed pairwise function); (4) a previously-undocumented
finding that `TableTransformerBackend`'s structure output has real
run-to-run variability on marginal tables (see methodology note below) —
a reproducibility caveat for any future cross-run comparison of TT scores.

## 12. Oracle analysis — methodology

**First attempt (rejected):** reused `local_improved`'s stored predictions
as "Table-Transformer-only" and generated a fresh "Docling-only" set in a
*separate* process. Result was internally inconsistent — on 2 of 7 tables,
the *real* production fill-rate-selector score (from `local_table_ensemble`)
was numerically outside the range `[TT-only, Docling-only]` the cross-run
reconstruction implied, which is impossible for a strict either/or
selector. Root cause: `TableTransformerBackend`'s structure output is not
bit-identical across separate process invocations on CPU (confirmed:
`book_zh_DLT10902008` scored TT-alone TEDS 0.232 in one run and 0.368 in
another, from the same image, same code, same config — plausibly
multi-threaded BLAS/attention nondeterminism in the detection/structure
transformer, not Docling — `native_tables()` reproduced bit-identical
output across repeated calls in isolation, so Docling was ruled out as the
source). **This means any comparison of Table-Transformer scores across
separate `prepare.py` invocations carries real noise** — a limitation not
previously documented, and one that affects interpreting small deltas in
`results/comparison.md`'s cross-run tables at the single-percentage-point
level (the large, headline deltas there — e.g. +0.073 TEDS — are far
larger than this noise and are not in question).

**Fix:** generate Table-Transformer and Docling candidates for each table
in the *same* process, from the *same* cached Docling conversion (layout →
OCR → Docling's own `native_tables()` all share one `_convert_cached` call
per page), so cross-model comparisons are never contaminated by cross-run
model drift. Verified self-consistent: every fill-rate-selected score now
falls exactly on `TT` or `Docling` for every table, as a strict either/or
selector requires.

Script: coherent single-run generation replicating
`run_scanned_page_pipeline`'s table stage exactly (layout → OCR →
`TableTransformerBackend.extract` → `_fill_table_cell_text` →
`DoclingBackend.native_tables`, geometric IoU matching), producing three
full prediction sets (`tt_only`, `docling_only`, `fillrate_local`) scored
by the same official evaluator, same ground truth, same match method as
every other run in this experiment.

## 13. Oracle analysis — 20-page subset (n=7 real GT tables)

| Table | TT | Docling | FillRate (production logic) | Oracle | Selector optimal? |
|---|---:|---:|---:|---:|---|
| book_zh_DLT10902008 | 0.368 | 0.191 | 0.191 | 0.368 | **NO** (short 0.178) |
| docstructbench_...0768-9.pdf_2 | 0.072 | 0.570 | 0.570 | 0.570 | yes |
| eastmoney_d2bb183f...pdf_7 | 0.083 | 0.829 | 0.829 | 0.829 | yes |
| jiaocaineedrop_46.pdf_1 | 0.000 | 0.000 | 0.000 | 0.000 | yes |
| jiaocaineedrop_...en_1898 | 0.650 | 0.022 | 0.022 | 0.650 | **NO** (short 0.628) |
| page-28657a85 | 0.000 | 0.000 | 0.000 | 0.000 | yes |
| yanbaor2_ey-global-fintech...30 | 0.490 | 0.716 | 0.716 | 0.716 | yes |

```
mean TT       = 0.2376
mean Docling  = 0.3325
mean FillRate = 0.3325   (identical to Docling here: Docling wins every
                           disagreement in this specific sample except one)
mean Oracle   = 0.4476
headroom (oracle - fillrate) = 0.1151
selector matches oracle on 5/7 tables (71%)
```

**Both misses share one root cause, not two independent failure modes.**
`book_zh` and `jiaocaineedrop_1898` both have TT producing a 100%-empty
table (fill-rate 0.0) against a naturally sparse ground-truth table, which
OmniDocBench's TEDS scores generously because an empty prediction cannot
contain *wrong* content, only missing content. Docling produces a
confident, populated-but-incorrect table on both, and cell fill-rate
cannot distinguish "correctly recognized there's nothing here" from
"failed to recognize something that is here" — it only measures whether
*something* was written, exactly the "activity vs. quality" gap flagged in
the task brief. This is not fully a genuine extraction-quality gap: a
downstream reader would very plausibly still prefer Docling's honest
attempt over TT's blank table on both pages even though TEDS scores the
blank one higher — part of the oracle headroom is a property of the
benchmark's scoring function on sparse tables, not of the pipeline.

**Checked directly whether any fill-rate threshold or simple rule on the
same feature closes this gap without breaking a currently-correct
decision — none does.** `docstructbench` (a currently-*correct* decision,
+0.498 real gain) also has TT fill-rate exactly 0.0 — identical to both
failure cases. A rule like "keep TT whenever its own fill-rate is 0" would
fix the two artifact losses but destroy the docstructbench win, a clearly
bad trade (one large real gain for two small artifact-driven corrections).
No univariate rule on fill-rate (from either model) separates the 2
failures from the 5 successes on this data — closing this specific gap
would need either genuinely new features (e.g. structural regularity
independent of content) or ground truth, neither available at inference
time.

## 14. Disagreement coverage (20-page subset)

```
N real GT tables            = 7
N both-fail (TEDS 0 either way) = 2   (page-28657a85, jiaocaineedrop_46)
N models agree (no disagreement, tie) = 0
N models disagree, selector correct   = 3   (docstructbench, eastmoney, yanbaor2)
N models disagree, selector wrong     = 2   (book_zh, jiaocaineedrop_1898)
composition opportunity (disagree)    = 5/7 (71%)
unrecoverable by composition (both-fail) = 2/7 (29%)
```

Disagreement is common (5/7) and composition captures most of it (3/5
correctly) — but "both models fail together" is not rare either (2/7),
and is the actual bottleneck component composition cannot touch (see
section 9's "does not claim" and the taxonomy in section 3: this is a
structure/detection capability ceiling, not an orchestration gap).

## 15. Selective-escalation signal analysis (task-required *before*
implementing any compute-saving routing)

Tested directly, using each backend's own quality features
(`compute_table_quality_features`) as the candidate confidence signal,
whether either model's own fill-rate predicts when the other model should
be invoked:

- **Docling's own fill-rate is not usable as a confidence signal**: it is
  exactly `1.0` on every table where Docling detects anything at all (5/7
  tables), and `0.0` only when it detects nothing. It has zero variance
  across the range TEDS 0.022–0.829 — a binary "found something" signal,
  not a graded confidence measure. No threshold on it distinguishes a good
  Docling table from a bad one.
- **Table Transformer's own fill-rate is graded (0.0, 0.333, 0.636, ...)
  but not predictive in the useful direction**: low TT fill-rate appears
  both in cases where escalating to Docling helps a lot (`docstructbench`,
  TT_fill 0.0, real +0.498 gain) and in cases where escalating hurts
  (`jiaocaineedrop_1898`, `book_zh`, TT_fill 0.0 both, escalating loses
  points to the sparse-GT artifact from section 13). The two real,
  legitimate Docling wins (`eastmoney`, `yanbaor2`) have *moderate*, not
  low, TT fill-rate (0.333, 0.636) — a threshold low enough to avoid the
  two artifact losses would also miss triggering escalation on real wins.

**Verdict: neither model's own fill-rate is a reliable trigger for
selective escalation on this evidence.** Per the task's explicit
instruction to measure this before implementing, this direction is not
pursued further — implementing an escalation policy on this data would be
building on a signal proven not to work, not a defensible experiment.

This is compounded by an architectural fact worth naming separately:
**in the current pipeline, Docling's table candidate is already free.**
`layout_backend` and `ocr_backend` both default to Docling, so its own
table conversion (`native_tables()`) reuses the *same cached conversion*
`recognize()`/`analyze()` already produced for OCR/layout — calling it
costs nothing extra. The only genuinely optional, costed model in this
comparison is Table Transformer itself (two additional HF model loads +
forward passes per table region). "Selective escalation to save compute"
would therefore have to mean *skipping Table Transformer* when Docling's
own result looks trustworthy — but section 15 above just showed Docling's
own fill-rate carries no usable confidence signal to gate that skip on.
There is currently no evidence-backed way to reduce specialist invocations
below "always run both" without a real quality cost.

## 16. Architecture change: model-agnostic candidate selection

Independent of the selector-quality question above, the *composition
layer's* implementation was hardcoded to exactly two candidates
(`select_better_populated_table(candidate, alternative)`), not genuinely
N-way — the task specifically asks whether the design conceptually
extends to a third/fourth specialist without rewriting the selector.
Refactored `src/doc_extraction/pipelines/base.py`:

- `TableCandidate` (table + provenance `source` string + a `quality`
  feature dict) — the common interface a selector consumes; nothing reads
  `source` to make a decision.
- `compute_table_quality_features(table)` — fill_rate, n_cells,
  avg_text_len, empty_cell_ratio; explicitly does *not* invent an
  `ocr_confidence` or `cross_model_agreement` signal, because neither is
  actually available: `Cell.confidence` is never populated by either
  backend (checked directly in `schemas/table.py` and both backends'
  code), and Table Transformer receives its table bbox from Docling's own
  layout stage by default — so a TT-vs-Docling bbox IoU check is trivially
  ~1.0 by construction in the current wiring, not an independent
  cross-model agreement signal (confirmed empirically: IoU was 1.0 on
  every one of the 7 real tables tested).
- `select_best_table_candidate(candidates, key="fill_rate")` — takes any
  number of candidates, deterministic tie-break (first-by-input-order
  keeps its current "prefer the already-detected candidate" behavior).
- `select_better_populated_table` and `_apply_native_table_fallback` are
  now thin wrappers over the above (existing behavior, existing tests,
  unchanged — all 10 pre-existing tests in `tests/test_table_cell_text.py`
  pass unmodified against the refactor).
- `_gather_extra_table_candidates` replaces the single `native_tables`
  duck-type check with a list of recognized candidate-source method names,
  so adding a third backend (MinerU, PaddleOCR-VL) that exposes its own
  `*_tables(page)` method is a one-line addition to that list, not a
  change to selection logic.

9 new tests added covering the general primitives directly: quality
features on empty/partial tables, the "no invented confidence signal"
guard, N-way (not just pairwise) selection, deterministic tie-breaking,
empty-candidate-list handling, custom selection keys, multi-source
candidate gathering, and both-fail behavior (primary kept unchanged, not
replaced by an equally-bad copy). `pytest -q`: 178 passed (169 existing +
9 new), 0 regressions.

## 17. 100-page validation of the oracle/disagreement analysis

**What is directly measured at 100-page scale (real production run, no
reconstruction needed):** the actual fill-rate selector's per-table
output, already generated by `local_table_ensemble_100` (100/100 pages
succeeded) and re-extracted from the evaluator's own per-table debug
output:

```
N real GT tables (100-page subset) = 30
N scoring exactly 0.0 TEDS         = 14  (47%)
mean table TEDS (fill-rate, production) = 0.2743
```

This directly answers the most important part of task section 13 at
scale: **the "both models fail together" rate is not smaller at n=30 than
n=7 suggested — it is larger** (47% vs. 29%). This is real, measured,
not reconstructed, and it is the single most decision-relevant number
from the larger sample: composition cannot address a bottleneck that is
already this common, and it looks more like the actual ceiling on this
component than the 20-page sample implied.

**What is not available at 100-page scale: the full oracle-ceiling
breakdown** (per-table Table-Transformer-only vs. Docling-only
counterfactuals, as computed for the 7 tables in section 13). Attempted
via the same coherent single-run methodology, generating fresh candidates
for each of the 100-page subset's real-GT-table pages. Aborted partway
through for a documented, evidence-based reason, not silently: the
official evaluator's own logs
(`experiments/005_omnidocbench/logs/local_table_ensemble_100_evaluate.log`)
show 11 of the subset's 29 table-bearing pages independently flagged as
pathologically slow for TEDS matching alone (`[TEDS-timeout]`, near the
120-second per-page cap — not a symptom of this reconstruction, a
property of those specific tables' size/structure). Excluding those 11
(a cost-based criterion, decided before seeing any result from the
remaining pages — not an outcome-based exclusion) left an 18-page
"tractable" subset. Generating fresh Table Transformer + Docling
candidates for even the *first* page of that reduced list (`eastmoney_...pdf_16`,
not one of the 11 flagged-slow pages) ran past 850 CPU-seconds without
completing — plausibly a large/dense OCR page, consistent with this
subset's pages generally being denser-than-average documents (pages with
a real table skew toward denser document types in this dataset). Given
the marginal value of a full breakdown against the compute cost of
generating it (each such page reruns a full Docling conversion plus Table
Transformer inference from scratch, with no way to reuse the original
100-page run's per-page timings since those didn't preserve intermediate
candidate objects), this was stopped rather than run for an open-ended
amount of wall-clock time — the same budget-consciousness this project's
own prior sessions have applied to Kaggle-scale runs.

**Honest scope of the 100-page validation, stated precisely rather than
rounded up to "confirmed at scale":**

- **Directly confirmed at n=30**: the both-fail rate is real and, if
  anything, worse than the small sample suggested (47% vs. 29%) — this
  narrows rather than inflates the claimed opportunity, which is the
  right direction for a validation to move a possibly-optimistic small-n
  estimate.
- **Reproduced exactly at n=6 tables across two independent runs** (see
  section 10 above, pre-existing from the Sonnet phase and independently
  re-checked here): the fill-rate selector's per-table output is
  deterministic and page-local — running it inside a 20-page batch or
  a 100-page batch gives bit-identical scores for the same underlying
  page.
- **Not extended to a full 100-page oracle-vs-selector gap number.** The
  n=7 oracle-headroom result (+0.115 mean TEDS, 5/7 selector-optimal)
  stands on its own evidence, mechanistically explained (one identified,
  named root cause for both misses, section 13), but should be read as a
  small-sample, page-verified directional result, not re-confirmed at
  n=30 for the specific "how big is the residual gap" question. A future
  session with either more compute budget or a fix for the per-page TEDS-
  matching slowness (worth investigating in its own right — it may point
  to a real serialization issue on large/dense tables, separate from this
  experiment) could complete this.

  **Follow-up: that per-page slowness turned out to matter far more than
  suspected here — see section 18, which shows it was silently
  manufacturing zero scores and contaminating this very section's
  headline number.**

# Hard-table capability analysis

New owner session. Question posed: *why do both table specialists fail on
the same tables, and can a new capability close part of that shared
failure region?* The investigation began by rebuilding the both-fail
corpus from primary evidence — and the first result invalidated the
premise. Artifacts: `hard_tables/both_fail_100.json`,
`hard_tables/failure_taxonomy.json`, `hard_tables/failure_taxonomy.md`.

## 18. The 47% both-fail figure was a measurement artifact

Regenerating the per-table debug output for `local_table_ensemble_100`
required re-running the evaluator over the **byte-identical predictions**.
The re-run disagreed with the stored result: 8 zero-TEDS tables, not 14.

Cause, traced to upstream source: `_evaluate_teds_pair_with_timeout` in
`.external/OmniDocBench/src/metrics/cal_metric.py` returns `0.0, 0.0` when
a single TEDS comparison exceeds a **120-second wall-clock timeout**. The
returned zero is indistinguishable from a genuine extraction failure in
both the per-table output and the aggregate mean. `cal_metric.py` is
unmodified at the pinned commit (`git diff` clean) — upstream behaviour,
not something this project introduced.

The original 100-page evaluation logged **9 `[TEDS-timeout]` events**; a
re-evaluation on an unloaded machine logged **zero**. Same predictions,
same ground truth, same evaluator commit:

| Metric | as reported (sections 10, 17) | correct | delta |
|---|---:|---:|---:|
| `table TEDS.all` | 0.2743 | **0.4080** | **+0.1337** |
| `table TEDS_structure_only.all` | 0.3504 | **0.5084** | **+0.1579** |
| both-fail tables | 14/30 (47%) | **8/30 (27%)** | -6 |
| `text_block`, `reading_order`, `display_formula`, `table Edit_dist` | — | *bit-identical* | 0.0000 |

Every non-TEDS metric is unchanged to four decimals — confirming the
mechanism is precisely the TEDS timeout and nothing else. Two independent
timeout-free runs (default 120s on an idle machine, and
`OMNIDOCBENCH_TEDS_TIMEOUT_SEC=1800`) agree on all 30 tables to 1e-9, so
the corrected values are reproducible, not a second lucky draw.

Six tables previously recorded as "both models failed" in fact score
0.3704-0.9310 — one of them 0.9310 with `TEDS_structure_only = 1.0000`,
i.e. a perfectly recovered structure logged as a total failure.

**Corrections to the prior record, stated plainly:**

- The section 10/17 claim that both-fail is *more* common at scale (47%)
  than the 20-page sample implied (29%) is **withdrawn**. The corrected
  27% is statistically indistinguishable from 2/7. The small sample was
  right, and the "larger sample sharpens the scope claim downward"
  narrative was itself the artifact.
- `local_table_ensemble_100`'s table TEDS is **0.4080**, not 0.2743. The
  stored `results/local_table_ensemble_100/metrics.json` retains the
  contaminated values (it is the untouched record of that run); the
  corrected re-evaluation lives in `results/_hardtable_scan_notimeout/`.
- Operational rule going forward: **any run whose evaluator log contains
  `[TEDS-timeout]` is invalid for table metrics.** Set
  `OMNIDOCBENCH_TEDS_TIMEOUT_SEC` high enough that wall-clock never
  decides a score. The evaluator itself is not modified, and timeout pages
  are not removed from the benchmark.

## 19. The hard-table population is one coherent family

All 30 ground-truth tables in the subset, by ground-truth row count:

| GT rows | n | mean TEDS | scoring exactly 0.0 |
|---|---:|---:|---:|
| **<= 2** | 7 | **0.0000** | **7 / 7 (100%)** |
| > 2 | 23 | 0.5322 | 1 / 23 (4%) |

The separation is essentially perfect. By document source the same family
appears as `exam_paper` **6/6 tables at 0.0**, against at most one zero in
any other source. These are short, wide banner tables at **1.5-5.2% of
page area**: exam answer keys, score boxes, two-cell grammar fill-ins. The
single >2-row member (`page-d29fe4d2`, 4x4, 63% of page) fails by a
different mechanism.

Correlation summary: failure tracks **row count and table area**, not
language (all 30 tables are Chinese or mixed), not cell count, and not
merged-cell complexity — the failing tables are the *structurally
simplest* ones in the subset.

## 20. "Both-fail" decomposes into three mechanisms — half are ours

Each of the 8 classified by replaying the exact production path per page:

| Category | Tables | % | Model capability gap? |
|---|---:|---:|---|
| **Composition-layer loss** | 3 | 37.5% | **No** — a viable candidate existed, and was discarded |
| Shared detection failure | 4 | 50.0% | **Yes** — no source found a region |
| Orphaned table | 1 | 12.5% | **No** — table produced, never referenced |

Against the Case A/B/C framing: **Case A (both detect, both produce
similar wrong structure) is 0 of 8 — not observed at all.** Case B is 3/8,
Case C is 4/8. Wherever both models actually engaged with a table they did
*not* share a blind spot; one of them got it substantially right. The
genuinely shared blind spot is at **detection**, never at structure.

### The composition-layer loss (3 tables), verified per page

| Page | GT | Docling's own candidate | Table Transformer | Emitted |
|---|---|---|---|---|
| `..._en_2540` | 2x13 | **2x12, 18/18 cells filled, bbox within ~2px of GT** | none | **nothing** |
| `..._en_922` | 2x13 | 2x6, 7 filled | none | **nothing** |
| `..._en_1349` | 2x9 | 1x6, 6 filled | none | **nothing** |

On all three, Docling's layout correctly located the region and Docling's
TableFormer produced a real table for it. Table Transformer's structure
model returned no row/column grid for the same crop (a short, very wide
strip), so `extract()` emitted no `Table` at all — and
`_apply_native_table_fallback` iterated over the primary backend's tables
to compare each against alternatives, so **with zero primary tables the
loop body never ran** and the good candidate was dropped. The element got
`table_id=None` and serialized to nothing.

The composition layer could only ever *replace* a table the primary had
found; it could never *add* one the primary had missed. That asymmetry —
not a model capability gap — accounts for 3 of the 8.

## 21. Experiment

```
Hypothesis: A material fraction of the both-fail region is candidates the
  pipeline already produced and then discarded, not capability gaps. Making
  the composition layer able to ADD an unmatched candidate (not only
  replace a matched one) recovers them.
Expected mechanism: TableTransformerBackend returns no Table for short/wide
  crops; Docling's TableFormer handles them; the reconciliation loop never
  executes when the primary list is empty.
Change: pipelines/base.py - _apply_native_table_fallback gains a recovery
  pass appending extra-source candidates that matched no primary table
  (guarded: only candidates with >=1 non-empty cell, plus id-collision
  handling). Separately, merge_regions_into_page now falls back to region
  OCR text when a table-labelled region matches no Table, instead of
  emitting an element with neither table nor text (a second, independent
  content-loss path found in the same trace).
Metric expected to improve: table TEDS.all, TEDS_structure_only.all.
Potential regression: recovered tables are added where previously the
  region's flattened text was emitted, so text_block could move; a
  spurious candidate in a non-table region would add noise.
Success criterion: table TEDS improves on the 100-page subset (which
  contains all 3 recoverable cases) with text_block/reading_order not
  materially worse.
```

Note on subset choice: the **20-page subset contains none of the three
recoverable cases** (its only both-fail tables are `page-28657a85` and
`jiaocaineedrop_46`, both genuine shared detection failures). The 20-page
run is therefore a *regression check*, not a test of the hypothesis; the
100-page subset is the actual experiment. Stated in advance rather than
discovered afterwards.

## 22. Result

100-page run with the fix, `results/local_recovered_100/`, evaluated with
`OMNIDOCBENCH_TEDS_TIMEOUT_SEC=1800`. Baseline for comparison is the
corrected re-evaluation of the same 100 pages,
`results/local_table_ensemble_100_corrected/` (table TEDS.all 0.4080) —
NOT the contaminated stored value in `local_table_ensemble_100/`.

**A second timeout artifact appeared during this run and was caught and
fixed before trusting the numbers** (documented here rather than silently
corrected, per this project's standing rigor practice): the first
evaluation of the fixed predictions logged 12 `[TEDS-timeout]` events even
at the raised 1800s threshold — a different, larger set than the 9 seen at
120s in section 18. Cross-checking confirmed all 12 timeout image IDs
overlapped exactly with 12 of that run's 14 zero-TEDS tables (the other 2
zeros, both `..._en_2901`, are the genuine shared-detection-failure cases
and were not in the timeout list). Re-running the evaluator a second time
on an otherwise-idle machine (0 other Python processes, confirmed) reduced
timeouts to **zero**; per-table TEDS for all 27 unaffected tables matched
the first evaluation to 4 decimal places, and only the timeout-affected
tables changed — consistent with system CPU contention (the same 100-page
`prepare` run had just been resumed from a several-hour OS sleep suspend,
and `--match-workers 4` runs multiple TEDS computations concurrently)
inflating wall-clock time past even a 30-minute cap for large tables under
load, not a change in the tables' actual complexity. **All table numbers
below are from the second, zero-timeout evaluation.**

| Metric | baseline (corrected, no fix) | recovered (with fix) | delta |
|---|---:|---:|---:|
| `table TEDS.all` | 0.4080 | **0.4514** | **+0.0434** |
| `table TEDS_structure_only.all` | 0.5084 | **0.5734** | **+0.0650** |
| `table Edit_dist.ALL_page_avg` | 0.7177 | **0.6792** | **-0.0384** (improvement — lower is better) |
| `text_block Edit_dist.ALL_page_avg` | 0.4869 | 0.4870 | +0.0001 (noise) |
| `reading_order Edit_dist.ALL_page_avg` | 0.4921 | 0.4912 | -0.0008 (noise) |
| `display_formula Edit_dist.ALL_page_avg` | 0.9951 | 0.9951 | 0.0000 |

**Full per-table diff, all 30 tables — the clean result the taxonomy
predicted:**

| Table | before | after | |
|---|---:|---:|---|
| `..._en_2540` | 0.0000 | **0.6429** (structure-only **0.9643**) | recovered — hypothesis target |
| `..._en_922` | 0.0000 | **0.4464** | recovered — hypothesis target |
| `..._en_1349` | 0.0000 | **0.2114** | recovered — hypothesis target |
| all other 27 tables | — | — | **bit-identical, delta 0.0000 on every one** |

Zero-TEDS count: **8/30 (27%) -> 5/30 (17%)**. The remaining 5 are exactly
the 4 shared-detection-failure tables (`jiaocaineedrop_46`, both
`..._en_2901` tables, `page-28657a85`) and the 1 orphaned-table case
(`page-d29fe4d2`) — precisely the tables section 20 predicted this change
would *not* touch, because neither mechanism is what this fix addresses.
No table outside the 3 targeted ones moved by more than floating-point
noise in either direction. This is as close to a fully-predicted,
fully-explained result as this investigation has produced.

**Regression check, explicit:** `text_block`/`reading_order`/
`display_formula` moved by at most 0.0008 — noise, not signal — confirming
the change is exactly as table-local as the two edits in `pipelines/base.py`
were designed to be. `table Edit_dist` improved alongside TEDS rather than
trading off against it (both edit-distance and tree-similarity metrics
agree the recovered tables are genuinely better, not just differently
structured). `pytest -q`: 185 passed (178 + 7 new, 3 of which were
confirmed to fail against the pre-fix code before the fix was applied).

**Runtime note, so it is not misread:** the reported `mean_seconds_per_page`
for this run (338s, vs. ~70s in earlier runs) is **not a real regression** —
`prepare.py`'s per-page timer was running when the host machine was put to
sleep for several hours mid-run; the process resumed cleanly afterward
(confirmed: zero errors, the pause is visible only as a large gap in
prediction-file write timestamps). The two source changes themselves add
no new model inference and no new per-page work beyond a few dict/list
operations.

Success criterion from section 21 (table TEDS improves, other four metric
categories not worse than noise): **met.**

**20-page regression check:** not run separately. The 20-page subset
contains none of the 3 recoverable tables (its both-fail tables are both
genuine shared-detection-failure cases, unaffected by this fix by
construction), so a 20-page run would only serve as a regression check —
and the 100-page run's own non-table metrics (delta <= 0.0008 across all
three) already provide a stronger regression signal, over a larger and
more diverse page sample, than a separate 20-page run would add. Skipped
to avoid a further ~40-60 minutes of compute for evidence this
investigation already has.

## 23. What this says about a third candidate model

**A third table-structure model is not justified by this evidence.** In
every one of the 8 both-fail cases where the region was detected at all, an
existing model already produced a usable structure — adding a third
structure specialist would address 0 of 8. The remaining genuine gap
(4/8) is **detection recall on small, borderless, few-row banner tables**,
shared by both backends. That is a detection problem, not a structure
problem — a materially different conclusion from "both table structure
models fail together", and it points at a different class of solution
(small-region detection, or a document VLM with stronger layout reasoning)
than swapping in another TableFormer-style checkpoint.
