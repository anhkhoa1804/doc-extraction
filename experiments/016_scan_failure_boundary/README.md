# 016 — Scan Failure Boundary: what's actually wrong when two OCR backends agree on the wrong answer

## Question

Experiment 015 established that `scan_recovery`'s only trigger
(cross-backend agreement) never fires on 5 of the 6 real `scan_quality`
documents, because Docling and EasyOCR fail *the same way*. That is a
diagnosis of the trigger's blind spot, not of the underlying failures. This
experiment traces all 9 missing `must_contain` phrases across those 5
documents through every real pipeline stage — render, layout (`analyze`),
OCR (`recognize`), region/table-cell assignment, final assembly — using
the actual production route, to answer: **what is actually wrong, per
case, and what is the cheapest causal fix?**

No code changes. No new model. This is measurement only, per the
instructions this milestone was scoped under.

## Method

`forensics.py` runs each of the 5 documents through `process_file`
(strategy `adaptive`, default config), then, against the exact same
rendered image the production run used, separately calls
`DoclingBackend.analyze()` (raw layout regions, independent of OCR) and
`DoclingBackend.recognize()` (raw OCR tokens, independent of region
assignment) plus a direct `EasyOCRBackend.recognize()` pass. For every
`must_contain` phrase it computes exact-substring and word-level recall
against final IR text, raw Docling OCR text, and raw EasyOCR text, and
classifies each miss by comparing those three:

* `present` — found in final text (sanity check, should never appear for
  a listed miss)
* `ocr_missing` — words absent from **both** backends' raw output even at
  the word level (word-recall < 0.8 in the best backend) — Class B, OCR
  never saw it
* `assignment` — words recognized by a backend (word-recall ≥ 0.8 in raw
  OCR) but absent from the final assembled text (word-recall < 0.8 there)
  — lost strictly between OCR and IR assembly
* `ocr_scrambled` / `assembly` — words present in both raw OCR and final
  text, but never as the exact contiguous phrase at either stage — Class A,
  something reordered or split it (further broken down manually below,
  because this bucket turned out to hide three unrelated mechanisms — see
  Six Scan Cases)

It also directly *tests*, rather than infers, one structural hypothesis:
for every miss, it locates the enclosing layout region, crops the
rendered page to it, and runs the already-built
`targeted_recovery.segment_lines()` projection-profile line detector on
the crop — computed for `present` phrases too, as a control group. And it
computes deterministic image-quality signals (Laplacian-variance
sharpness, contrast, Gaussian-residual noise, Otsu ink coverage,
connected-component count) and runs the existing
`text_quality.assess_text` plausibility check on each document's final
text — no training, just correlation-checking.

Device: `cuda`, GPU preflight **CLEAR** before every run (re-checked
before each of the 4 script invocations this milestone made).

## Baseline

Recall values reproduced from experiment 015 (unchanged, no code touched):
`hc_scan_vi` 0.250, `hc_scan_en` 0.667, `cmb_scan_multicol_en` 0.667,
`cmb_scan_stamp_table_vi` 0.750, `ord_invoice_png_vi` 0.714 — 22
`must_contain` phrases total, 13 present, **9 missing**.

## Six Scan Cases (all 9 misses, traced to source text)

Reading the actual raw OCR strings (not just recall flags) revealed the
initial mechanical classification above was too coarse — several misses
that scored identically (`ocr_scrambled`, word-recall 1.0 at every stage)
turned out to be three unrelated defects. Corrected breakdown, all 9:

| document | phrase | true cause | evidence |
|---|---|---|---|
| `hc_scan_vi` | `Độc lập - Tự do - Hạnh phúc` | **genuine word-order scrambling** | raw Docling: `"...Độc lập do Hạnh phúc Tự"` — word "Tự" displaced from position 3 to the end, within one OCR token |
| `hc_scan_vi` | `Kính gửi: Phòng Tài chính - Kế` | **genuine word-order scrambling, severe** | raw Docling: `"Kính Phòng Tài chính Kế toán Căn cứ biên bản... gửi: phải"` — the salutation line's own words are split apart and reattached to the *end* of an unrelated body paragraph, in one OCR token |
| `hc_scan_vi` | `CÔNG VĂN V/V XÁC NHẬN CÔNG NỢ` | **character misrecognition** | raw Docling: `"...VIV..."` — the slash in the abbreviation `V/V` misread as the letter `I` |
| `hc_scan_en` | `OFFICIAL LETTER — CONFIRMATION OF OUTSTANDING BALANCE` | **single dropped punctuation glyph** | raw Docling: `"OFFICIAL LETTER CONFIRMATION OF..."` — every word correct and in order; only the em-dash is missing |
| `cmb_scan_multicol_en` | `Section 2. Approval authority` | **single dropped punctuation glyph** | raw Docling: `"...Section 2 Approval authority..."` — only the period after "2" is missing |
| `cmb_scan_stamp_table_vi` | `Ký hiệu: MQ/2026E    Số: 0004417` | **ground-truth metric artifact** | raw Docling: `"Ký hiệu: MQ/2026E Số: 0004417..."` — correct content and order; the manifest's `must_contain` string bakes in 4 literal spaces from the source layout that no text extractor reproduces |
| `ord_invoice_png_vi` | `Ký hiệu: MQ/2026E    Số: 0004417` | **ground-truth metric artifact** | identical mechanism to the row above |
| `cmb_scan_stamp_table_vi` | `Dịch vụ lắp đặt` | **occlusion-driven fragmentation** | raw Docling table-row tokens: `'Dịch vụ'`, `'đặt'`, `'lắp'` — three disjoint detections, interleaved with `'ĐÃ DUYỆT'` (the stamp text) — the `stamp`/`occlusion`-labeled document's own approval stamp physically interrupts this row |
| `ord_invoice_png_vi` | `Dịch vụ lắp đặt` | **table-cell bbox mismatch** | raw Docling token `'Dịch vụ đặt lắp'` (words present, minor 2-word swap) has word-recall 1.0 in raw OCR **and 0.0 in final text** — the text exists but never reaches any `Table.cell` or `Element.text`; Table Transformer's independently-detected cell geometry does not contain Docling's own OCR-token bbox for this row |

**OBSERVED**: 9 misses decompose into 2 genuine word-order defects (1
document), 2 single-glyph OCR misses, 2 ground-truth formatting
artifacts, 1 occlusion-fragmentation case, and 1 table-cell geometry-
mismatch case that loses content completely.

**INTERPRETATION**: "two backends fail together" is not one failure mode —
it is at least five. A single aggregate "scan_quality" label, and a single
aggregate recall number, hides this. Any fix aimed at "scan_quality" in
the abstract will underperform a fix aimed at one of these five specific
mechanisms.

**LIMITATION**: n=9 misses across n=5 documents from one synthetic corpus.
Every count above is small; several categories are n=1. This is a map of
*this sample's* failure boundary, not a population estimate.

## Earliest Failure Stage

| mechanism | earliest stage | evidence |
|---|---|---|
| word-order scrambling | **OCR (recognize)** | already scrambled in the raw `OCRResult.tokens` text, before any region/table matching runs |
| character misrecognition | **OCR (recognize)** | glyph substituted/dropped at the character level, inside Docling's own recognition |
| ground-truth artifact | **not a pipeline stage** | the pipeline's output is correct; the benchmark string is unrealistic |
| occlusion fragmentation | **render → OCR boundary** | the physical pixels are already interrupted by stamp ink before any software stage runs; OCR faithfully reports disjoint fragments |
| table-cell bbox mismatch | **table-cell assignment** (`_fill_table_cell_text`) | raw OCR token correct; loss occurs strictly at the geometric match between Docling's own OCR-token bbox and Table Transformer's independently-computed cell bbox |

**OBSERVED**: only one of five mechanisms (table-cell bbox mismatch) fails
strictly at an orchestration/assignment stage; the rest fail at or before
OCR recognition, or aren't a pipeline defect at all.

**INTERPRETATION**: this corpus's dominant loss point is *inside* OCR
recognition (scrambling, character misses), not in the region-assignment
code experiment 015 already showed is not where cross-backend agreement
would help either. The one true assignment-stage bug (table cells) is
also the one case a structural/geometric fix (not a smarter OCR call)
would directly address.

## OCR vs Layout Failure

Layout (`analyze()`) itself was never the direct cause of a miss in this
sample: every phrase that reached OCR recognition also landed inside some
detected region (the `assignment`-classified case failed at *table-cell*
matching, a different, finer-grained geometry than region-level layout).
The one visible layout failure in this sample is a known, separate issue:
`cmb_scan_stamp_table_vi` found **0/1 expected tables** — Table
Transformer's own table-detection model fails to find a grid under the
stamp, an already-documented gap from experiment 011 ("table structure
still not recovered... out of scope there"), confirmed still present and
unrelated to text recall (the row text still reaches the document via
loose `text` elements once no table geometry exists to claim it).

## Single-Source Quality Signals

`text_quality.assess_text` was run on all 5 documents' final text.
**Result: `suspicious: False`, `reasons: ['ok']` on every single one** —
including `hc_scan_vi`, the worst-recall document (0.25) with the
severest scrambling case. This empirically confirms, on real production
output (not the synthetic example in its own docstring), that
`assess_text`'s character/script-plausibility signals are structurally
blind to every mechanism found here: scrambled-but-valid words, dropped
punctuation, and missing table content all still read as perfectly
plausible Vietnamese/English prose.

**OBSERVED**: 0/5 documents flagged by the one single-source quality
signal already in the codebase, despite 4/5 having real content defects.

**INTERPRETATION**: this is not a wiring gap (experiment 015's own "next
step" suggestion) — it is a genuine capability gap. `assess_text` answers
"is this decodable as real language," not "is this the right words in the
right order," and none of this sample's defects are decoding problems.

**LIMITATION**: n=5. `assess_text` may still catch defects outside this
sample (e.g. genuine CMap corruption, its original design target); this
result only says it does not catch *these* five documents' defects.

## Scan Quality (image-level signals)

| document | sharpness | contrast | noise | ink coverage | conn. components | recall |
|---|---|---|---|---|---|---|
| `hc_scan_vi` | 137 | 20.95 | 2.78 | 0.95% | 251 | 0.250 |
| `hc_scan_en` | 119 | 20.68 | 2.61 | 0.90% | 182 | 0.667 |
| `cmb_scan_multicol_en` | 131 | 19.05 | 2.74 | 0.82% | 211 | 0.667 |
| `cmb_scan_stamp_table_vi` | 200 | 23.52 | 3.39 | 1.59% | 288 | 0.750 |
| `ord_invoice_png_vi` | 613 | 22.70 | 5.72 | 1.11% | 300 | 0.714 |

**OBSERVED**: no monotonic or even directional relationship between any
single image-quality feature and recall. `ord_invoice_png_vi` (highest
sharpness by 3-5x, highest noise) scores mid-pack; `hc_scan_vi` (lowest
recall, worst case) is not a sharpness/contrast/noise outlier at all — it
sits inside the same narrow band as the two 0.667-recall documents.

**INTERPRETATION**: these five deterministic pixel-level features, tested
directly (not assumed), do **not** discriminate failure severity in this
sample. This is a real negative result, not a gap in feature choice
necessarily — it is consistent with this milestone's own causal finding:
the dominant defects (scrambling, punctuation drops, table-cell geometry)
are not explained by *how degraded the scan looks*, they are explained by
*how OCR/layout software structures what it read*. A page can be
reasonably sharp and still have its recognizer scramble word order.

**LIMITATION**: n=5, one corpus, one rendering pipeline (uniform DPI 200
for all five). A genuinely blurrier or lower-resolution real-world scan
might show a real correlation this sample is too narrow to detect. This
result rules out these features as *sufficient* explanations here; it does
not rule them out as *ever* useful.

## Title/Header Loss — the structural hypothesis, tested and revised

The framing hypothesis going in was "titles/headers are disproportionately
lost, likely because layout merges multi-line headers into one
over-broad region that OCR then reads out of order." 7 of 9 misses are
indeed header/title/metadata-line content (vs. 2 table-row misses) — that
part holds. But the causal mechanism does not, once tested directly:

`segment_lines()` (the existing projection-profile line detector from
experiment 014) was run against the actual enclosing region for every
missing AND every present phrase, as a control:

| phrase | outcome | region label | line-bands detected |
|---|---|---|---|
| `Kính gửi: Phòng Tài chính - Kế` | scrambled | `text` | 6 |
| `Căn cứ biên bản đối chiếu ngày 28` | **present**, same region | `text` | 6 |
| `Section 2. Approval authority` | scrambled | `text` | 3 |
| `Section 1. Scope` | **present**, same region | `text` | 3 |
| `OFFICIAL LETTER — CONFIRMATION...` | scrambled | `section_header` | **1** |

**OBSERVED**: line-band count does not separate scrambled phrases from
present ones — in two cases a scrambled and a correctly-read phrase share
the *identical* region and identical line-band count, and one scrambled
case (the em-dash drop) lives in a region `segment_lines()` reports as a
single line, not multiple.

**INTERPRETATION**: the original hypothesis (multi-line region →
line-reading-order corruption, fixable by pre-OCR resegmentation) does
**not** survive direct testing on this sample. Splitting `hc_scan_vi`'s
`text` region into 6 line-bands and re-OCR'ing each independently
(exactly what `targeted_recovery.recover_region`'s resegment path already
does) might *still* help the severe cross-paragraph case, since it forces
per-line boundaries Docling's own reading order ignored — but that is a
different, weaker claim than "a structural line-count signal identifies
which regions need it," which this test disproves. No such cheap
structural trigger for resegmentation currently exists.

**LIMITATION**: this is the honest failure of a specific hypothesis, not
proof no structural signal exists — only that region height / line-band
count, the simplest candidate, is not it.

## Recovery Candidates

| mechanism | count | cheapest causal action | justification |
|---|---|---|---|
| ground-truth artifact | 2/9 | **fix the benchmark**, not the pipeline | the extracted text is already correct; normalize whitespace in `must_contain` strings or in the recall metric |
| single dropped/misread punctuation glyph | 3/9 | **untested candidate: higher-DPI re-render**, targeted at just the offending token's bbox | plausible (small glyphs are the classic resolution casualty) but not measured this milestone — do not build before testing |
| word-order scrambling | 2/9 (1 document) | **no validated cheap fix yet** — the natural candidate (structural resegmentation trigger) failed direct testing above | needs either a better trigger than line-band count, or more real cases before generalizing |
| occlusion fragmentation | 1/9 | **no cheap deterministic fix identified** — the pixels themselves are interrupted; reordering fragments by y/x position rather than emission order is a plausible next probe, untested | genuinely the closest thing to a capability gap found this milestone, but n=1 |
| table-cell bbox mismatch | 1/9 | **`TABLE_SPECIALIST`-class orchestration fix**: make `_fill_table_cell_text`'s cell-containment check fall back to nearest-cell/IoU matching instead of strict center-in-bbox when Docling's own OCR-token bbox and Table Transformer's cell bbox disagree | concrete, deterministic, reuses code already in the repo, and is consistent with experiment 011's independently-documented "table structure not recovered" gap on the same corpus |

**Do not use the same recovery action for every miss** (explicit
instruction, and now empirically justified): the five mechanisms above
have five different cheapest fixes, one of which (ground-truth) is not a
code fix at all, and two of which (scrambling, occlusion) have no
validated cheap fix yet.

## VLM Necessity

**Not justified.** Every mechanism found either (a) is not a real defect
(ground truth), (b) has an untested but plausible deterministic candidate
fix (high-DPI re-render for glyph drops, cell-matching fallback for the
table case), or (c) has too little evidence (n=1) to justify building
anything, deterministic or not. None of the nine misses required visual
semantic understanding beyond what Docling+EasyOCR already extracted —
in every genuine-content-loss case, the correct words were already inside
some backend's raw OCR output. The gap is in orchestration and glyph-level
recognition, not in "understanding what's in the image."

## Verification Architecture

This milestone's own findings make the case concretely for what
experiment 015's report flagged as an open question: `Verification`
should expose more than a status. A `assess_ocr_agreement` call today
returns TRUSTED/SUSPICIOUS and a score; it cannot distinguish "these two
backends agree because both are right" from "these two backends agree
because both scrambled the same words" (015's finding) or say *which* of
the five mechanisms above is in play. A verification result that carried
`failure_type` (one of: `ocr_missing`, `ocr_scrambled`, `assignment`,
`occlusion`, `ground_truth`/`unclassified`) and `affected_region` would
let a caller route directly to the matching `RecoveryAction` instead of
the current single-action `scan_recovery` orchestration this milestone's
predecessor rejected. This is a design direction, not a proposal to
implement yet — the failure-type taxonomy above was derived by manual
forensic reading (raw-token inspection), not by a signal cheap enough to
run automatically; that gap needs closing first.

## Recommended Recovery Policy

Do not build one universal `recover()`. Per mechanism:

```
ground_truth_artifact   -> fix the benchmark manifest / recall metric
                            (whitespace-normalize must_contain matching)
punctuation/glyph miss  -> UNTESTED candidate: RERENDER_HIGH_DPI on the
                            token's own bbox, only after measuring it
                            actually helps (not yet done)
word_order_scramble     -> NO ACTION YET -- needs a real detector; the
                            obvious one (line-band count) failed testing
occlusion_fragment      -> NO ACTION YET -- reorder-by-position is the
                            next thing to try, not yet measured
table_cell_mismatch     -> RESEGMENT-class fix: robust cell-matching
                            fallback in _fill_table_cell_text (concrete,
                            deterministic, ready to scope as real work)
```

## Final Decision

No hedging, per instructions, choosing from the given menu:

| | decision |
|---|---|
| **NEXT DIRECTION** | **B — implement targeted preprocessing** (table-cell bbox-matching fallback in `_fill_table_cell_text`) |

Not A: diagnosis is not the bottleneck anymore for the one mechanism ready
to act on (table-cell mismatch) — it is fully traced to a specific
function and a specific geometric cause. Not C: the only candidate for
high-DPI (punctuation/glyph drops) is unmeasured and lower-value than the
table fix (3 minor glyphs vs. complete content loss on a table row). Not D:
no case required visual semantics; the correct text was always already in
some backend's raw OCR output. Not E: this milestone did not run out of
diagnostic signal — it ran out of *validated* fixes; gathering more
signals without acting on the one already-proven mechanism would repeat
experiment 015's own lesson (diagnose before building, but also *act* once
a diagnosis is actually solid, rather than diagnosing indefinitely).
Word-order scrambling and occlusion fragmentation are real but stay
**NO ACTION YET** — both are n=1, and the one structural detector tested
for scrambling failed direct verification; building on either now would be
exactly the kind of premature generalization this milestone's own
predecessor was rejected for.

## Production Impact

None yet — this milestone made no code changes (explicit instruction).
The one item above concrete enough to scope as real work (table-cell
matching fallback) has not been measured against the corpus; its
production impact is unknown until implemented and run through the same
6-case + 58-doc harness experiment 015 already built.

## Research Opportunity

The clearest opportunity this milestone surfaces is not a new capability
gap — it's that **roughly a fifth of measured "failures" on this corpus
(2/9 misses, both `Ký hiệu` cases) are not pipeline defects at all**, and
a further third (3/9, the punctuation drops + character misread) are
narrow single-glyph misses, not the broad content-loss the aggregate
"scan_quality, recall 0.25–0.75" numbers suggest. The real, actionable
residual — genuine word-order scrambling and table-cell loss — is smaller
and more specific than the raw recall numbers imply, and concentrated in
exactly the two document types (multi-line Vietnamese official letters;
occluded/stamped tables) the corpus's own hard-case labels already name.

## Next 3 Actions

1. **Fix the `Ký hiệu` ground-truth artifact** in
   `research/production_corpus/corpus/manifest.json` (or normalize
   whitespace in the recall metric used across all `run_*.py` scripts) —
   near-zero cost, removes 2/9 false failures, makes every future recall
   number on this corpus more honest.
2. **Scope and measure the `_fill_table_cell_text` bbox-mismatch fallback**
   (nearest-cell/IoU matching when strict center-containment fails) against
   `ord_invoice_png_vi` specifically, then the 58-doc corpus — the one
   finding this milestone produced that is concrete, deterministic, and
   ready to build without further research.
3. **Before building anything for word-order scrambling or occlusion
   fragmentation, gather more real cases** — both are currently n=1 (one
   severe, one document); the one structural detector tested
   (line-band count) failed, and building a second guess without more
   evidence repeats experiment 015's own mistake at one level up.

## Reproduce

```bash
python experiments/016_scan_failure_boundary/forensics.py --device cuda
```
