# 024 — OCR fidelity / acquisition recovery

## Baseline

`git rev-parse HEAD` at the start of this milestone: `bdbe5c99ef2cbcb28396746e02c1f69370caaeb0`.
`pytest -q`: 329 passed, 10 skipped, 0 failed
(interpreter `~/.venvs/doc-extraction-gpu312/bin/python`, Python 3.12.14).
Contract: `experiments/023_evidence_centric/NEXT_MILESTONE_PROPOSAL.md`,
sha256 `72f226639ea6b657a393a2cf5b9ce4673a4ed9038b8a0f25674f88356c102845`.
Baseline artifact: `experiments/023_evidence_centric/ab_visual.json`,
sha256 `e64abaed29fedf69327a775debe9d10772a2ad687a3874d55a85f88f7a2267e9`,
committed at `24229f5`.

Frozen and unmodified throughout: failure corpus (7 documents), control
(42 documents), primary metric (mean exact recall on the failure corpus),
acceptance (failure ≥ 0.75, control ≥ 0.9807, invocations ≤ 1.10/document),
rejection (failure < 0.68, or control < 0.9757).

Measured baseline, reproduced from the frozen artifact before any work:
**failure corpus 0.6038, control 0.9857.**

GPU: not used. Every measurement in this milestone is CPU-only. The L4 was
occupied throughout by an unrelated training job and was never signalled.

## The question

> Can OCR-side intervention recover the residual failures without
> sacrificing the strong Tesseract quality/cost advantage?

## What the residual actually is

Thirteen strings are missing across the seven failure-corpus documents under
the frozen baseline. Line 1 classified every one of them by aligning it
against the recogniser's own output and against the assembled document:

| mechanism | definition | n |
|---|---|---|
| acquisition | never read: char recall in raw tokens < 0.90 | 8 |
| fidelity | read at ≥ 0.90 and preserved into the document, still not exact | 4 |
| assembly | read correctly, lost after OCR | 1 |

The four fidelity failures are each **a single glyph**:

| document | expected | Tesseract read | mechanism |
|---|---|---|---|
| `cmb_scan_stamp_table_vi` | `MQ/2026E Số:` | `MQ/2026E_ Số:` | stray `_` (form rule) |
| `cmb_scan_tiny_vi` | `Phạm vi áp dụng` | `Phạm vì áp dụng` | spurious diacritic |
| `cmb_tiny_table_en` | `Product A-100` | `Product A100` | dropped hyphen |
| `cmb_stamp_table_vi` | `Số lượng / Thành tiền` | `bố lượng\|/ Thành tiền` | `Số`→`bố`, stray `\|` |

**No evaluation artifacts were found, in either direction.** `_norm` already
NFC-normalises and collapses whitespace runs (experiment 016), so the class
it was built for is already neutralised: zero strings fail on whitespace,
case or normalisation alone. Every missing string was also checked against
its own document's text layer — all are genuinely present. One candidate
artifact was investigated and disproved: `hc_merged_en`'s `Qty / Amount`
does appear literally in the document, and Tesseract reads it. Nothing here
licenses widening the scorer, and the scorer was not touched.

## Experimental matrix

Every intervention isolated; the composite run only after individual effects
were known. Failure/control are mean exact recall on the frozen split.

| # | intervention | failure | control | Δ control | invocations/doc | decision |
|---|---|---|---|---|---|---|
| — | baseline (frozen) | 0.6038 | 0.9857 | — | 1.000 | — |
| L2a | gap-aware token join | 0.6335* | 0.9721* | −0.0136 | 1.000 | **REJECT** |
| L2b | punctuation-aware join | 0.4592* | 0.6799* | −0.3058 | 1.000 | **REJECT** |
| L2c | gap + punctuation join | 0.4592* | 0.6697* | −0.3160 | 1.000 | **REJECT** |
| L3a | whole page @ 400 DPI | — | — | — | 1.000 | **REJECT** |
| L3b | whole page @ 600 DPI | — | — | — | 1.000 | **REJECT** |
| L3c | whole page @ 600 DPI, psm 6 | — | — | — | 1.000 | **REJECT** |
| L4 | `--psm 1` (auto + OSD), raw screen | 0.7287† | 0.9778† | 0.0000 | 1.000 | screen only |
| L4 | `--psm 1`, **full pipeline** | **0.6038** | **0.9857** | 0.0000 | 1.000 | **REJECT** |
| L5 | recover orphaned tokens | 0.6514 | 0.9857 | 0.0000 | 1.000 | **PROMOTE** |
| L7a | re-OCR all columns, empty-cell trigger | 0.6854 | 0.9857 | 0.0000 | 3.4490 | **REJECT** (cost) |
| L7b | re-OCR first column, confidence trigger | 0.6854 | 0.9857 | 0.0000 | **1.0612** | **PROMOTE** |
| **C** | **L5 + L7b composite** | **0.7330** | **0.9857** | **0.0000** | **1.0612** | **PROMOTE (partial)** |

`*` line 2 is a raw-token proxy, so its baseline is 0.6514/0.9857 rather than
the pipeline's 0.6038/0.9857; the comparison within that row block is
internally consistent and every rule loses.
`†` raw-recogniser acquisition, not recall; baseline at psm 3 is 0.6335/0.9778.

### Line 4 is the milestone's methodological lesson

The screen said `--psm 1` acquired two more strings on `hc_rotation_vi` and
changed nothing on the other 48 documents: a clean, free win. End to end it
changed **nothing at all** -- 0 of 49 documents moved, failure corpus
0.6038 -> 0.6038, corpus-wide recall identical at 0.9311 (char recall did
rise, 0.9715 -> 0.9740).

The screen was wrong because it scored a *flat concatenation* of every token
on the page, while the pipeline builds text per detected region. Traced on
`hc_rotation_vi` under psm 1: `'Chứng nhận rằng hệ thống quản lý'` does land
inside a region, and `'phù hợp với các yêu cầu của tiêu'` is neither claimed
nor among the orphans -- the tokens actually read
`'phù hợp với các yêu cầu 9001:2015'`, so `của tiêu` was never recognised
contiguously at all. A flat concatenation finds the words in order across
the page and calls that acquisition; the document never contains the string.

Two consequences, both recorded rather than smoothed over. Raw-concatenation
screens over-predict end-to-end recall and must not be used to promote
anything. And the claim made mid-milestone that line 4 and lines 5/7 act on
disjoint documents and therefore add exactly is **false**: line 4's apparent
gain sits on `hc_rotation_vi`, a document with a 28.9% orphan rate, so what
psm 1 acquires the region filter would discard anyway. The interventions
interact, and only the end-to-end measurement settles it.

Line 3's whole-page rescaling is reported as raw acquisition rather than
recall because it never reached a promotion candidate:

| config | strings acquired (5 small-text docs) | OCR seconds |
|---|---|---|
| 200 DPI, psm 3 (shipped) | **23/33** | 3.6 |
| 400 DPI, psm 3 | 20/33 | 8.9 |
| 600 DPI, psm 3 | 20/33 | 18.4 |
| 600 DPI, psm 6 | 10/33 | 11.3 |

**Raising DPI does not merely fail to help; it actively harms.**
`hc_tiny_cells_vi` falls 4/7 → 2/7 → 1/7 as DPI rises. The inherited prior
that DPI escalation is not the answer is confirmed, and strengthened.

## The mechanism that explains the milestone

Line 3's crop probe is the decisive measurement. The same pixels, three
crops, one document (`hc_tiny_cells_vi`, 4.2 pt type):

| crop | width | result |
|---|---|---|
| full detected table | 241 pt | **empty output** |
| description column only | 37 pt | **4/4 strings acquired**, one call |
| column + adjacent numeric columns | 177 pt | 1–2/4, diacritics lost |

The 4.2 pt text **is** readable by Tesseract. What defeats it is a single
"line" spanning several columns of very small type — a segmentation failure
at recognition time, not a capability limit and not a scale problem.

Line 5 found the same shape one level up. On `cmb_scan_multicol_en`, Docling
emits **2 layout regions**; of 34 OCR tokens, **19 are claimed and 15 are
orphaned**, and the orphans are the entire second column, including the
string the A/B scored missing. `_gather_region_text` keeps only tokens whose
centre falls inside a detected region, so unclaimed tokens are discarded
silently.

Corpus-wide, **1000 of 5845 recognised tokens (17.1%) are orphaned this
way** — including 894 tokens in `long_policy_vi_60p`, a document that scores
1.000. That is the honest calibration: the mechanism is large in volume and
small in measured recall, because `must_contain` supervision covers 226
strings and cannot see most of what is dropped. Only **1 required string**
is recoverable from orphans.

So the milestone's unifying finding is that the residual is gated by
**detection recall upstream of OCR text handling** — layout regions that are
never emitted, and table rows that are under-counted — rather than by
recognition capability, by token ownership, or by the scorer.

This is **not** a reversal of experiment 023's finding. 023 ruled out
token-to-cell *ownership* (0 of 18 table-document failures were assignment
errors) and that stands: line 7 confirmed the detected column geometry is
correct, while the detected **row extent** is truncated, which is what caps
recovery at 2/4 instead of the 4/4 an oracle crop achieves. Assignment
chooses correctly among the cells it is given; the cells it is given are
incomplete. Different mechanism, different fix.

## Failure-mechanism accounting

Re-classified after each intervention, per the rule that a score movement
unaccompanied by a mechanism movement is suspect:

| mechanism | before | after L5 + L7b |
|---|---|---|
| acquisition | 8 | 5 |
| fidelity | 4 | 3 |
| assembly | 1 | **0** |
| total missing | 13 | **8** |

The distribution moves where the mechanisms predict: line 5 targets assembly
and zeroes it; line 7b targets acquisition and removes three of eight;
fidelity moves by one, incidentally, because nothing here was aimed at it.

The `after +L4` column an earlier draft of this table carried has been
removed: line 4 changed no document end to end, so it removes no failure
from any bucket.

## Cost

| | value |
|---|---|
| extra OCR invocations, whole corpus | **+3** |
| invocations per document | **1.0612** (cap 1.10) |
| documents triggering a second pass | 3 of 49 |
| re-OCR wall time | ~3 s total |
| GPU | not used |

The trigger is Tesseract's own mean token confidence inside a detected
table, below 0.70, ignoring detected tables that contain no tokens at all
(those are spurious detections, and including them fires on 36 of 49
documents and costs 3.45 invocations/document — that is L7a, rejected on
cost alone despite an identical quality gain).

Re-OCRing only the **first** column costs 3 calls and recovers exactly what
re-OCRing every column recovers at 8 calls. First-column-only is not a
compromise; it is strictly better here.

## Outcome against the frozen contract

| criterion | threshold | measured | verdict |
|---|---|---|---|
| failure-corpus exact recall | ≥ 0.75 accept / < 0.68 reject | **0.7330** | between |
| control exact recall | ≥ 0.9807 accept / < 0.9757 reject | **0.9857** | pass |
| OCR invocations per document | ≤ 1.10 | **1.0612** | pass |

**OUTCOME B — PARTIAL.** The composite clears the rejection floor by 0.053
and falls short of acceptance by 0.017, with the control untouched and the
cost budget respected. Per the contract, the individually non-regressive
interventions are promoted and the remaining boundary is recorded.

Because the rejection threshold was **not** reached, the line-8 VLM gate
does **not** open. That is a result, not an omission: deterministic
OCR-side recovery removed 5 of 13 residual failures, including the entire
assembly class, without a single control regression.

## Capability boundary

Eight strings remain: 5 acquisition, 3 fidelity, 0 assembly.

**Three fidelity failures** — a stray `_`, a stray `|` with `Số`→`bố`, and
`vi`→`vì` — are single wrong or spurious glyphs on 4.2–9 pt type. Nothing
tried here touches them. They are reachable only by better recognition of
very small glyphs, or by relaxing exact match, which the contract forbids
and which would be dishonest since the extraction is genuinely wrong.

**Two acquisition failures in `hc_tiny_cells_vi`** are capped by table
**row** under-detection: an oracle crop of the description column reads 4/4,
the crop production can actually compute from detected geometry reads 2/4.
That is the Table Transformer structure-recall gap experiment 017
identified. It is a detector problem, not an OCR-side one.

**Three acquisition failures in `hc_rotation_vi`** survive everything tried.
`--psm 1` genuinely improves the recogniser's output there and still moves
no metric, because one target string is never recognised contiguously and
the rest is discarded by the same region filter line 5 addresses. This
document needs orientation correction *and* region recovery *and* better
small-glyph recognition, and having two of the three is worth nothing.

So the boundary of deterministic OCR-side recovery, measured rather than
asserted, is **detection recall — layout regions and table rows — plus
single-glyph fidelity on very small type**. Neither is an OCR-side problem,
which is why an OCR-side milestone stops here.

## Production implementation of line 5

Line 5 was promoted and implemented in `merge_regions_into_page`
(commit `1ae81e0`). The production run re-measures it on the frozen
contract, through experiment 023's own `run_ab`, with the `tesseract` arm
built exactly as production builds it.

| metric | frozen baseline | proxy | **real production** |
|---|---|---|---|
| failure-corpus exact recall | 0.6038 | 0.6514 | **0.6514** |
| control exact recall | 0.9857 | 0.9857 | **0.9857** |
| failure-corpus char recall | 0.8430 | — | **0.8836** |
| control char recall | 0.9930 | — | **0.9930** |
| corpus-wide exact recall | 0.9311 | — | **0.9380** |
| corpus-wide char recall | 0.9715 | — | **0.9773** |
| documents perfect | 40 | — | **41** |
| `order_ok` | 46 | — | 46 |
| `tables_ok` | 47 | — | 47 |
| errors | 0 | — | 0 |
| OCR invocations/document | 1.000 | 1.000 | **1.000** |

**The production implementation reproduces the proxy exactly** -- same
failure-corpus recall to four decimals, same control, and it additionally
lifts character recall and one more document to perfect, which the
text-level proxy could not show. Exactly one document changed:
`cmb_scan_multicol_en` 0.6667 -> 1.0000. Zero documents regressed.

Mechanism validation, from the production run's own artifacts:

| | value |
|---|---|
| orphan tokens detected | **988** (= the experiment's 1000 minus the 12 inside tables) |
| orphan tokens recovered | **988** (100%) |
| recovered elements | 135 across 7 documents |
| empty recovered elements | 0 |
| recovered tokens also claimed by a region or cell | **0** |

Reading order, on the two documents the contract named:

* `cmb_scan_multicol_en` -- recovered block at x 876-1469 (the right column);
  `reading_order` is `[heading, left column, recovered right column]`.
* `cmb_scan_tiny_vi` -- recovered `'Điều 1. Phạm vì áp dụng'` at y 240-253 is
  ordered *between* the title and the body, not appended. It still does not
  score, because the recogniser read `Phạm vì` for `Phạm vi` -- a line 1
  fidelity failure, untouched by line 5 and correctly so.

## Line 5 under the shipped router

Everything above forces OCR on every page (`--strategy visual`). That is the
right way to see a recogniser-side mechanism and it is not what production
does: the shipped router sends a page to OCR only when its text layer is
absent or fails the quality gate. Line 5 lives inside
`merge_regions_into_page`, so under `--strategy adaptive` it can only act on
the pages the router actually sends there.

`line5_adaptive_ab.py` measures exactly that -- same 49 documents, 112
pages, same scorer, thresholds, router, `tesseract` arm, layout and table
backends. The only difference between the two arms is whether
`_orphan_tokens` returns its orphans or an empty list, which is precisely
pre-`1ae81e0` behaviour: with no orphans the recovery loop appends nothing
and `notes` stays `list(table_result.warnings)`. No production code is
modified. Layout is not shared between arms (that would give arm 2 free work
arm 1 paid for); a per-page region fingerprint is recorded instead and is
identical in both, `5217ebb6876b1536`.

| metric | adaptive baseline | adaptive + L5 | delta |
|---|---:|---:|---:|
| exact recall | 0.9838 | **0.9906** | **+0.0068** |
| char recall | 0.9941 | **0.9997** | **+0.0056** |
| perfect documents | 46 | **47** | **+1** |
| zero-recall documents | 0 | 0 | 0 |
| `order_ok` | 46 | 46 | 0 |
| `tables_ok` | 46 | 46 | 0 |
| hallucinations | 0 | 0 | 0 |
| errors | 0 | 0 | 0 |
| OCR pages | 7 | 7 | 0 |
| OCR invocations/document | 0.1429 | 0.1429 | 0 |
| wall time | 80.3 s | 79.8 s | not quotable |

By language: `en` 0.9833 -> **1.0000** exact and 0.9943 -> **1.0000** char;
`vi` 0.9842 -> 0.9842 exact and 0.9940 -> **0.9995** char.

### The adaptive workload

The router is the dominant term. Of 112 pages, **7 reach OCR (6.25%)**,
across **6 of 49 documents (12.2%)** -- 7 invocations, 0.1429 per document,
1.1667 per OCR'd document. The other 105 pages take the `digital_pdf` route
and never enter `merge_regions_into_page`. On this corpus the
`digital_pdf+page_fallback` route -- the third caller of
`run_scanned_page_pipeline`, and therefore a third route line 5 can reach --
fired on **zero** pages.

`long_policy_vi_60p` is the clearest illustration. Under `visual` it
contributed 894 of the 1000 discarded tokens. Under `adaptive` all 60 of its
pages route native, it is never OCR'd, and it is byte-identical in both arms
(`37a3c21ccf8b0f20`, 15082 chars, recall 1.0). The document that made the
data-loss case is not a document the router lets line 5 touch.

### Mechanism, on the pages the router did send

| | value |
|---|---|
| OCR tokens recognised | 386 |
| tokens claimed by no region | 32 (8.3%) |
| excluded as table/cell tokens | 0 |
| orphan tokens detected | 32 |
| orphan tokens recovered | **32 (100%)** |
| recovered elements | 4, in 4 blocks |
| pages carrying recovered evidence | 2 of 7 OCR'd (2 of 112) |
| documents carrying recovered evidence | 2 of 6 OCR'd (2 of 49) |
| empty recovered elements | 0 |
| recovered text also present in a region or cell | **0** |
| provenance | `source_backend='tesseract'`, `extra.recovered='orphan_ocr_tokens'`, `extra.token_count`, mean token confidence 0.915-0.956 |

Five of the seven OCR'd pages have zero orphans and are byte-identical
between the arms. Two changed:

**`cmb_scan_multicol_en`** -- 0.6667 -> **1.0000** exact, 0.8851 ->
**1.0000** char. Before: heading + left column only. After: one recovered
block at x 876-1469, `'Section 2. Approval authority Expenditure above USD
5,000 requires written approval from the Managing Director.'` -- 15 tokens,
the page's entire second column, carrying the `must_contain` string
`Section 2. Approval authority` that was missing. `reading_order` is
`[heading, left column, recovered right column]`; `order_ok` stays true.

**`cmb_scan_tiny_vi`** -- 0.6667 -> 0.6667 exact, 0.8261 -> **0.9855** char.
Three recovered blocks, 17 tokens: `'Điều 1. Phạm vì áp dụng'` (a section
heading), `'ty và các chỉ nhánh.'` and `'đốc phê duyệt bằng văn bản.'` --
the second and third are the tails of two sentences the region filter had
truncated mid-word (`...thuộc công` + `ty và các chỉ nhánh.`). `reading_order`
places the heading *between* the title and the body:
`[p0-e0, p0-r0, p0-e1, p0-r1, p0-r2]`. It still does not score exact,
because the recogniser read `Phạm vì` for `Phạm vi` -- a line 1 fidelity
failure, untouched by line 5 and correctly so.

### Regression audit

Measured on what the adaptive path actually exercises, not inferred:

* **110 of 112 pages byte-identical** across both arms on route, native
  element count, native element text, table count, cell count, cell text,
  `reading_order` and `notes`.
* **All 105 `digital_pdf` pages unchanged** -- zero differences of any kind.
* **All 5 OCR'd pages with no orphans unchanged.**
* **Tables unchanged**: 0 table/cell-box exclusions fired, table and cell
  text hashes identical everywhere, `tables_ok` 46 in both arms.
* **Reading order unchanged**: `order_ok` 46 in both arms; on the two
  changed pages the existing element ids keep their relative order and the
  recovered blocks are inserted by geometry.
* **No duplication**: recovered text is disjoint from native element text on
  both changed pages, and the native text hash is unchanged there.
* **Office routes**: not exercised -- the frozen contract is 49 PDFs.
  `pipelines/office.py` imports nothing from `pipelines/base.py`, so it has
  no path to line 5, and the suite's 11 office tests pass (341 passed, 10
  skipped, no failures; the known office-route flake did not reproduce).

### Cost

The wall-time delta is **-0.5 s (-0.62%)** and is **not quotable as a
latency figure**: two runs of the *identical* L5 configuration differed by
-1.4 s, so the A/B delta is smaller than the run-to-run spread. Per-document
runtime delta has a median of +1.0 ms against a standard deviation of
49.6 ms. OCR time is unchanged (5.332 s vs 5.323 s) because line 5 adds no
invocation.

What *is* isolatable is the L5 computation itself, timed directly on the
captured adaptive inputs (`_orphan_tokens` + `_cluster_orphans` + the text
join and alnum guard, median of 200 repeats per page):

| | value |
|---|---|
| total over the adaptive workload | **0.543 ms** |
| per OCR'd page | **0.078 ms** (range 0.034-0.125) |
| per document (49) | **0.011 ms** |
| as a share of OCR time (5.32 s) | **0.010%** |

Line 5 is free at the resolution this corpus can measure.

### Verdict

**Outcome A -- a measurable adaptive quality gain.** L5 moves the shipped
metric, not just the forced-OCR one: +0.0068 exact, +0.0056 char, one more
perfect document, with zero regressions and no measurable cost. The gain is
smaller than under `visual` (+0.0069 exact there) only because the router
sends 6.25% of pages to OCR; on the pages it does send, the mechanism
recovers 100% of what it detects.

The corpus does bound the claim. Only 2 of 112 pages carry recovered
evidence, so the +0.0068 rests on a single document's `must_contain` string
and the second document's character recall. The adaptive corpus can prove
line 5 fires correctly, in order, without duplication, and without touching
the 105 pages it should not touch. It cannot size the production win on a
scan-heavy input distribution, because 88% of this corpus is digital.

## Reproducibility

- Interpreter: `~/.venvs/doc-extraction-gpu312/bin/python` (Python 3.12.14)
- Baseline commit: `bdbe5c9`; corpus `research/production_corpus`, 49 PDFs,
  112 pages, 200 DPI, `vie+eng`, manifest carries per-document sha256
- Scripts, each writing machine-readable JSON beside it:
  - `fidelity_analysis.py` → `fidelity_analysis.json` (line 1)
  - `line2_fragmentation.py` → `line2_fragmentation.json` (line 2)
  - `line3_acquisition.py` → `line3_acquisition.json` (line 3)
  - `line4_psm_screen.py` → `line4_psm_screen.json` (line 4 screen)
  - `line4_end_to_end.py` → `ab_visual.json`, renamed here to
    `line4_psm1_ab_visual.json` so it can never be mistaken for 023's frozen
    baseline (line 4, full pipeline, tesseract arm only, psm=1)
  - `line5_orphaned_tokens.py` → `line5_orphaned_tokens.json` (line 5)
  - `line7_region_reocr.py` → `line7_region_reocr.json` (line 7)
  - `composite.py` → `composite.json`; `mechanism_accounting.json`
  - `line5_production_e2e.py` → `line5_production_ab_visual.json`
    (line 5, full pipeline, `--strategy visual`)
  - `line5_adaptive_ab.py` → `line5_adaptive_ab.json` (line 5 under the
    shipped router, `--strategy adaptive`, both arms in one run)
- Evidence read: `experiments/023_evidence_centric/_runs/visual/tesseract/`
  (untracked, 81 MB, regenerable from the tracked scripts and the seeded corpus)
- `_runs/` produced here is excluded by `experiments/**/_runs/`
