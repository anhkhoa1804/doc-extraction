# 017 — Table Cell/Text Geometry: hardening `_fill_table_cell_text`

## Baseline

`git rev-parse HEAD` at the start of this milestone: `f41cceb4c4a7e6c08c7e47d878be8a4ef66924e1`.
`pytest -q`: 275 passed, 10 skipped, 0 failed. GPU preflight **CLEAR** (0
MiB used, 0% util, no other processes) before every GPU-using command in
this milestone, re-checked immediately before each one.

Production corpus (58 docs), strategy `adaptive`, device `cuda`, before any
change: mean recall **0.9491**, 52/58 fully recovered, 1 critical failure
class (`scan_quality`, `tiny_text` case). Hardcase corpus (14 docs): mean
recall **98%**, worst case 67% (`merged_cells`), 13/14 tables OK, 0 errors.
Both numbers reproduced independently before touching any code — not
assumed from prior sessions, per instructions.

## Root Cause

**OBSERVED**: `ord_invoice_png_vi`'s product table, traced end to end
(`analyze()` for layout, `recognize()` for raw OCR tokens, direct
`TableTransformerBackend.extract()` call, all against the exact rendered
image the real pipeline used): Table Transformer's structure model
detected **3 rows** where the table visibly has **4**. The 4th row's own
OCR tokens (`'Dịch vụ đặt lắp'`, `'Gói'`, `'1'`, `'3.500.000'`) sit at
y≈705–749px, cleanly below the last detected row's bottom edge (y=686.53)
but still inside the table's own outer bbox (from Docling's independent
layout detection, y1=750.31) — with no cell geometry anywhere to claim
them. `_center_in` correctly reported "no cell contains this token"
because, geometrically, that was true: no cell existed there.

**Coordinate-space check, done before any fix (per instructions)**:
`docling_page_size()` for this document returned `(1653.0, 2339.0)` —
identical to the actual rendered image size. `_bbox_from_docling`'s scale
factor (`page_height / src_h`) is therefore exactly `1.0` for this
document; the pre-existing scale-correction code (already in the
codebase, from an earlier fix, see docstring in `docling_backend.py`)
was not even active here. This document's coordinate spaces already
agree.

**INTERPRETATION**: this is a **structure-detection recall gap**
(Table Transformer's row detector under-counting), not a coordinate-
space bug. Renamed in this document's own history from "geometry
mismatch" (experiment 016's working hypothesis) to what the evidence
actually shows once traced to the pixel level.

**LIMITATION**: n=1 real case traced to this level of detail. The fix
below is designed to generalize (any missing-row/column pattern with
corroborating evidence), and is validated against 16 synthetic
geometries plus two full corpora showing zero side effects — but the
*causal mechanism* (row-detector undercount specifically) is confirmed
on one document, not surveyed across many.

## Coordinate Systems

Recorded once, explicitly, per instructions, rather than assumed:

| | space | origin | notes |
|---|---|---|---|
| rendered page image | px @ `config.render_dpi` (200) | top-left | ground truth pixel grid |
| Docling OCR tokens (`recognize()`) | px, rescaled to page via `_bbox_from_docling` | top-left (after BOTTOMLEFT→TOPLEFT flip using Docling's own page height) | scale = `page_height / docling_internal_height`; measured 1.0 for this document (Docling's internal raster happened to match 200 DPI here), 1.333 in the general case Docling's own docstring documents (150 DPI internal vs 200 DPI render) |
| Docling layout regions (`analyze()`) | same as OCR tokens | same | same conversion function, same call site pattern |
| Table Transformer table bbox | page px (from the layout region handed in) | top-left | no crop, no rescale — `regions` already page-space |
| Table Transformer cell bboxes | page px | top-left | computed as `table_bbox.x0 + local_x`; local coordinates come from `post_process_object_detection(target_sizes=crop_image.size)`, i.e. rescaled back to the crop's own actual pixel size before translation — verified arithmetically sound, not the defect |

All four therefore land in the **same space** (page pixels, top-left
origin, at `config.render_dpi`) once each backend's own conversion runs.
The defect is not a disagreement between these spaces; it's a hole in
one of them (Table Transformer's cell grid not covering the full table
bbox).

## Fallback Design

Three tiers in `_fill_table_cell_text` (`pipelines/base.py`), in order:

1. **Center containment** (unchanged from before this milestone) — cheap,
   correct for the overwhelming majority of cells. No regression risk:
   every already-working case takes the identical code path.
2. **Rounding-margin recovery**: a token whose center falls within
   `CELL_ROUNDING_MARGIN_PX` (3px) of exactly one cell's edge is
   recovered into that cell. Rejected if margin-expanded ranges of more
   than one cell would qualify (ambiguous boundary/gap cases are left
   unassigned, not guessed).

   An earlier design used an area-overlap-ratio threshold (≥0.5) instead
   of a pixel margin. That version was **proven mathematically dead
   code** before being tested: simple interval algebra shows that if a
   token's center lies outside a cell along some axis, that axis's
   overlap fraction is *always* strictly below 0.5 — meaning tier 1
   (center containment) and the ratio-based tier 2 could never disagree,
   so tier 2 could never fire on anything tier 1 had already missed. Kept
   here as the record of a real dead end, not silently dropped.
3. **Missing-row/column synthesis**: for tokens still unassigned, cluster
   by mutual y-overlap into row-bands (Table Transformer's own missing-
   row pattern), match each token in a cluster against the table's
   existing column x-ranges, and synthesize a new row **only if at least
   `MIN_CORROBORATING_COLUMNS` (2) tokens in the same band align with
   different existing columns**. Rows can be inserted anywhere (above,
   below, or between existing rows); `_renumber_rows_by_position`
   re-sorts every row (old and new) by y-position afterward so reading
   order is never broken by an insertion in the middle.

Every tier stays strictly inside the table's own outer bbox; nothing
considers a token that starts outside it.

## Ownership Safety

The corroboration requirement (≥2 columns) in tier 3 is the direct
defense against the exact failure class `pymupdf_table_backend`'s
earlier ownership fix (`dff7d02`) already paid to fix once: a single
stray mark (a stamp fragment, an unrelated annotation) sitting inside a
table's bbox must never become table content just because it is
spatially close. A lone token, however well aligned with one column,
stays unassigned — see `test_single_stray_token_does_not_synthesize_a_row`.

**Documented, not hidden, residual gap**: the corroboration check is
purely geometric. If an overlay drops fragments into two *different*
columns at the same y-band — not observed in this corpus, not
structurally impossible — this fallback cannot distinguish that from a
genuine missing row, because it reasons about geometry only, never text
content or style. `test_two_stamp_fragments_coincidentally_aligned_can_still_synthesize_a_row`
locks in current (imperfect) behavior explicitly rather than leaving the
gap implicit. Closing it would need a content/style signal — the same
kind `table_quality.assess_table` already uses for the PyMuPDF path —
which this milestone deliberately did not add to the Table Transformer
path (out of scope: "do not add a new model", and this isn't one, but
it is more machinery than the evidence here justifies).

## Regression Matrix

16 synthetic tests in `tests/test_table_cell_geometry.py`, all pure
geometry (no image, no model, no GPU):

| test | covers |
|---|---|
| `test_token_fully_inside_cell_unchanged` | tier 1 unchanged |
| `test_ordinary_full_table_is_completely_unchanged` | negative control: fallback never fires when unneeded |
| `test_multi_token_cell_joins_in_reading_order` | reading order within a cell |
| `test_token_slightly_outside_due_to_rounding_is_recovered` | tier 2 positive |
| `test_token_beyond_rounding_margin_is_not_recovered` | tier 2 negative (too far) |
| `test_token_in_gap_between_cells_ambiguously_is_not_assigned` | tier 2 negative (ambiguous) |
| `test_token_far_outside_any_cell_or_table_is_never_assigned` | outer-bbox boundary |
| `test_missing_row_below_last_detected_row_is_synthesized` | tier 3, the real diagnosed case |
| `test_single_stray_token_does_not_synthesize_a_row` | ownership safety |
| `test_stray_token_not_aligned_to_any_column_is_never_assigned` | column-alignment requirement |
| `test_missing_row_inserted_between_existing_rows_renumbers_correctly` | reading order after mid-insertion |
| `test_missing_row_before_first_row_renumbers_correctly` | reading order, edge case |
| `test_scale_invariance_2x` | relative-geometry robustness at a different DPI-equivalent scale |
| `test_vietnamese_diacritics_preserved_through_tier1_and_tier2` | no text mangling |
| `test_vietnamese_diacritics_preserved_through_tier3_synthesis` | no text mangling, single-column non-synthesis edge case |
| `test_synthesized_row_downgrades_table_confidence_but_tier2_does_not` | verification-chain integration |
| `test_two_stamp_fragments_coincidentally_aligned_can_still_synthesize_a_row` | documented limitation, not hidden |

Every test **fails against the pre-fix code** (verified directly: 8 of
16 fail when `pipelines/base.py` is reverted, the rest pass trivially
since tier 1 is unchanged) and passes after — a real regression lock,
not a test written to match whatever the code already does.

**LIMITATION**: synthetic geometry only for the matrix; end-to-end
validation against real pixels is the one document below, not a survey.

## Adversarial Tests

`test_scale_invariance_2x` covers the "different DPI" axis (all
coordinates doubled, same relative behavior required). Pixel-perturbation
robustness (±1/2/5px) is covered directly by the margin mechanism itself
— `CELL_ROUNDING_MARGIN_PX = 3.0` — rather than as a separate sweep: the
margin *is* the tolerance being tested, and
`test_token_slightly_outside_due_to_rounding_is_recovered` /
`test_token_beyond_rounding_margin_is_not_recovered` bracket it on both
sides (2px recovered, ~16px not). A dedicated ±1/±2/±5px parametrized
sweep was not built as a separate artifact — the two bracketing tests
already establish the boundary at the one place it's defined (the
constant itself), and multiplying test count without new information
was judged not worth it at this milestone's scope.

**Different OCR granularities** (word/line/span/character): not tested
this milestone. The Table Transformer path only ever receives Docling's
own OCR tokens (`OCRToken`, already line/paragraph-level per
`docling_backend.recognize()`'s own design — see experiment 016's
tracing of the same tokens); character-level or span-level OCR granularity
is not a configuration this path exposes, so there was nothing to test
without inventing a scenario the real pipeline cannot produce.

## Table Metrics

Cell-level scoring (`table_metrics.score_table`, the module built for
exactly this purpose in the earlier ownership-fix milestone) against
`ord_invoice_png_vi`'s product table, ground truth in the *true* word
order (not Docling's scrambled reading — see below):

| | before | after |
|---|---|---|
| **structure** position_recall | 0.75 (3/4 rows) | **1.0** (shape_exact=True) |
| **content** cell_exact_accuracy | 0.75 | **0.9375** (15/16) |
| **content** cell_text_recall | 0.7407 | **1.0** |
| **content** cell_text_f1 | 0.8511 | **1.0** |
| contamination_rate | 0.0 | 0.0 (unchanged — no new contamination) |

The one remaining exact-match miss (`r3c0`, expected `"Dịch vụ lắp đặt"`,
got `"Dịch vụ đặt lắp"`) is **not** this fix's residual — it is Docling's
own OCR misreading the word order inside that single token, an
independent defect experiment 016 already diagnosed and explicitly left
as "no action yet" (n=1, no validated fix). `cell_text_recall`/`f1`
score it as fully correct (token-level, order-insensitive, by
`table_metrics`'s own deliberate design), which is the honest
distinction this module exists to draw: the *right information* is now
in the *right cell*; whether the string inside is byte-exact is a
separate, already-tracked question.

Reproduce: `python experiments/017_table_cell_geometry/score_ord_invoice.py --before <before/document.json> --after <after/document.json>`.

## Production Corpus

58 documents, strategy `adaptive`, device `cuda`, GPU CLEAR before both
the pre-fix and post-fix runs:

| | before | after |
|---|---|---|
| mean text recall | 0.9491 | 0.9491 (unchanged — see Table Metrics above for why) |
| fully recovered | 52/58 | 52/58 |
| documents with any table-cell content change | — | **1/58** (`ord_invoice_png_vi`, exactly the diagnosed case) |
| documents with contamination introduced | — | **0/58** |

Every one of the other 57 documents' table cells (byte-for-byte, every
row/col/text/confidence) is identical before and after — verified by
direct diff of the assembled `document.json` for every document, not
inferred from the summary recall number.

## Hard Cases

14-document `research/hardcases` corpus, same device/strategy:

| | before | after |
|---|---|---|
| mean recall | 98% | 98% (unchanged) |
| worst case | 67% (`merged_cells`) | 67% (unchanged) |
| tables_ok | 13/14 | 13/14 (unchanged) |
| any table-cell content change | — | **0/14** |

`stamp_over_table` was checked specifically (the adversarial case this
milestone's own instructions named): its table is on the **native
digital-PDF path** (`pymupdf-native` / `pymupdf_tables`), an entirely
different backend this milestone's fix never touches. Its cell `r2c1`
does show mixed content (`'ĐÃ THU 5'`) — pre-existing, unchanged by this
milestone, and **already correctly flagged**: `page.notes` carries
`"table quality: p0-t0 SUSPICIOUS [high] — 1 text run(s) cross cell
boundaries; 1 cell(s) contain runs of more than one style"` from the
existing `table_quality.assess_table` gate on that path. Confirmed as a
negative control that this milestone's change did not touch that
mechanism, not a new finding.

## Verification

A real, pre-existing gap was found and closed. `verify_document()`
reads `Table.confidence` via `from_table_confidence()`, with a comment
stating "Table.confidence already reached page.notes via the table
backend's own warning at extraction time" — true for the native
digital-PDF route (`pipelines/pdf.py` line 225 explicitly does
`notes.extend(table_result.warnings)`), **false** for the scanned/image
route this fix operates on (`merge_regions_into_page` built `Page.notes`
as always-empty; neither `parse_scanned_pdf` nor `parse_image` ever
propagated it). Fixed at the one shared call site
(`merge_regions_into_page`) rather than duplicated in both callers.

The new evidence (a synthesized row) now correctly downgrades
`Table.confidence` to 0.5, which `verify_document()` reads as
**SUSPICIOUS** — verified directly on the real document:

```
summary: VerificationSummary(trusted=0, suspicious=1, invalid=0)
table confidence: 0.5
notes: ["table p0-t0: synthesized 1 row(s) Table Transformer's structure
         model did not detect, from corroborating OCR evidence across
         >= 2 columns"]
```

Tier 2 (rounding-margin recovery of an already-detected cell) does
**not** downgrade confidence — it corrects tolerance on structure Table
Transformer already found, a materially smaller claim than inferring a
row exists at all. `TRUSTED → SUSPICIOUS` fires exactly when structure
was inferred rather than detected; nothing in this milestone produces
`INVALID` (no case reached that severity, and inventing one to exercise
the code path would be the "make the gate more aggressive without
evidence" the instructions explicitly warned against).

## Performance

Table geometry assignment stayed CPU-only throughout (Table Transformer
itself already ran on GPU before and after; `_fill_table_cell_text`
never touches a tensor). Isolated microbenchmark (500 iterations, no
GPU, no image I/O — pure function calls):

| scenario | time/call |
|---|---|
| ordinary 120-cell table, no orphans (tiers 2/3 never engage) | 4.93 ms |
| same table with one missing row (tier 3 fires) | 6.13 ms |

**+1.2ms worst-case overhead**, confirming the fallback tiers are cheap
and — per instructions — only pay their cost when there is actually
something to resolve (both tiers exit immediately when `orphans` is
empty). Corpus-level wall-clock timing across the three separate runs
this milestone made showed swings up to +60% on individual documents,
but this was proven **not attributable to the fix**: documents that
never call `_fill_table_cell_text` at all (native digital-PDF route, no
tables) showed the identical swing between runs. The final production
and hardcase runs (after all three code changes were in place) landed
back within the original baseline's timing envelope (p99 15.03s vs
14.75s originally), consistent with ordinary session-level variance, not
a real per-call cost — the microbenchmark above is the number to trust.

## GPU

`nvidia-smi` checked CLEAR (0 MiB, 0% util, no other processes)
immediately before every GPU-using command in this milestone (8 checks
total across the tracing, the two before-runs, and the three after-runs)
— never assumed from an earlier check. No GPU state was ever LIMITED or
PROTECTED during this session; the yield/reduce-load branches of the
GPU-state protocol were not exercised.

## What Improved

* `ord_invoice_png_vi`'s product table: structure position_recall 0.75→1.0,
  cell_text_recall/F1 0.7407/0.8511 → 1.0/1.0, zero new contamination.
* A pre-existing verification-architecture gap (table warnings on the
  scanned/image route never reaching `page.notes` or `Table.confidence`)
  closed for the whole route, not just this fix's own new warning.
* A dead-code design flaw (area-ratio tier 2) was caught and replaced
  *before* being shipped, by testing rather than assuming the design was
  sound — the mathematical proof is recorded in the code comment.

## What Failed

* The document-level `must_contain` recall number for `ord_invoice_png_vi`
  did **not** improve (0.7143 → 0.7143) — masked by the coexisting,
  independent Docling word-order defect on the exact probe phrase
  (experiment 016). Not a failure of this fix; a limitation of a
  document-level metric this milestone's own instructions anticipated
  ("do not let document-level recall hide cell-level corruption").
* Column synthesis (a 5th, undetected "STT" row-number column, observed
  in passing while tracing this same document) was **not** attempted —
  out of scope for this milestone, noted as a related, smaller,
  symmetric gap for a future one.
* No adversarial case in either real corpus exercised the documented
  two-column-stamp-corroboration gap; it remains a synthetic-only test,
  not a corpus-validated one.

## Promotion Decision

No hedging, per instructions:

| | decision |
|---|---|
| **TABLE CELL/TEXT GEOMETRY FALLBACK** | **PROMOTE** |

**PROMOTE**, as the default behavior of `_fill_table_cell_text` on the
Table Transformer path (already the case — this is shipped in
`pipelines/base.py`, not gated behind a flag). Justification against the
four stated criteria:

* **Quality**: the one real diagnosed case improved from a completely
  silent, undetectable content loss (0.75 structure recall, no warning
  anywhere) to full recovery with explicit provenance and a correct
  SUSPICIOUS verification verdict.
* **Robustness**: 16 synthetic tests covering the requested matrix (near-
  miss, ambiguous, out-of-bounds, scale, diacritics, mid-insertion
  reordering) all pass, and a real design flaw was caught by testing
  before shipping.
* **Regression**: zero content changes on 57/58 production documents and
  14/14 hardcase documents — the tightest possible negative-control
  result available from real data.
* **Runtime**: +1.2ms worst case, isolated and measured, not inferred
  from noisy corpus timing.

This does not promote the *specific two-column corroboration threshold*
as tuned-and-final — it is a deliberately conservative, undertuned
constant (matching this project's own stated discipline: "the only
evidence available is synthetic... tuning to one generator's geometry is
how a gate becomes a corpus artifact") — nor does it claim column-level
synthesis, occlusion-aware reordering, or the two-column-stamp gap are
solved; those remain open, honestly scoped items for later work.

## Updated Failure Ranking

Re-derived from this milestone's own final corpus run, not assumed from
before:

```
scan_quality       n=6  crit=1 high=1 med=4   <- unchanged, still #1
borderless_table   n=2  crit=0 high=2 med=0
table_detection    n=2  crit=0 high=2 med=0   <- unchanged (ord_invoice_png_vi
                                                  still classified here, since
                                                  classification keys off
                                                  document recall, which the
                                                  coexisting word-order bug
                                                  still holds below 1.0)
tiny_text          n=1  crit=1 high=0 med=0
table_structure    n=1  crit=0 high=1 med=0
stamp              n=1  crit=0 high=0 med=1
occlusion          n=1  crit=0 high=0 med=1
multi_column       n=1  crit=0 high=0 med=1
reading_order      n=1  crit=0 high=0 med=1
```

**`scan_quality` remains #1, checked rather than assumed.** This
milestone's fix is real (verified at the cell level above) but invisible
to this document-level ranking, because the ranking is driven by
`must_contain` recall and this document's recall is gated by a *second*,
independent defect on the same probe phrase. This is itself informative:
it is a second, corpus-level demonstration of exactly what experiment
016 already found — document-level recall undercounts real quality
improvements when multiple defects compound on the same content. The
dominant remaining problem, by this fresh measurement, is still **scan
quality** (word-order scrambling and outright OCR misses on real scanned
documents), not table structure — table structure's *known* remaining
gap (`cmb_scan_stamp_table_vi`, table detection failing entirely under a
stamp) is a detection problem this milestone's assignment-layer fix
cannot reach by construction (there is no table object to fill cells
into when none was detected).

## Research Opportunity

Cell-level scoring (`table_metrics.score_table`) proved decisive for
seeing this fix's real effect when the document-level number could not
— the same module experiment 010's original milestone built it for. Its
value compounds with this fix: any future table-geometry work now has a
correct baseline harness (16 synthetic geometries + 2 corpora + cell-
level scoring) to measure against, rather than starting from a document-
level recall number that has already been shown to hide exactly this
class of improvement twice now (010's original stamped-cell case, and
this one).

## Next 3 Highest-Value Actions

1. **Column synthesis, symmetric to the row synthesis built here** — the
   same document's "STT" column was independently observed missing from
   Table Transformer's own column detection; the corroboration-based
   ownership discipline built for rows generalizes directly, but this
   milestone did not build it (kept in scope to one diagnosed axis).
2. **Investigate `scan_quality`'s word-order scrambling directly**
   (experiment 016's own "next 3 actions" #3) — this milestone's own
   result (`ord_invoice_png_vi`'s document-level number staying flat
   despite a real cell-level fix) is a second, independent data point
   that this is the higher-value remaining problem, not table structure.
3. **`cmb_scan_stamp_table_vi`'s table-detection failure under a stamp**
   remains open (0/1 tables found, unchanged across every run this
   milestone made) — a detection-stage gap this milestone's assignment-
   stage fix was never positioned to close; the next table-quality
   milestone should target Table Transformer's own detector, not cell
   assignment again.

## Reproduce

```bash
pytest tests/test_table_cell_geometry.py -v
python research/production_corpus/run_benchmark.py --strategy adaptive --device cuda
python research/hardcases/run_benchmark.py --strategy adaptive --device cuda
python experiments/017_table_cell_geometry/score_ord_invoice.py --before <before.json> --after <after.json>
```
