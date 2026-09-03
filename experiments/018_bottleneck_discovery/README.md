# 018 — System Bottleneck Discovery: word-order recovery + stamp-table detection boundary

## Current Baseline

`git rev-parse HEAD` at start: `b1d7860`. `pytest -q`: 291 passed, 10
skipped, 1 flaky failure (`test_office_routes_are_deterministic` —
confirmed pre-existing and unrelated: passes reliably in isolation both
before and after this milestone, never touches office-pipeline code this
milestone changed; not chased further, out of scope). GPU preflight
**CLEAR** before every one of the 6 GPU-using commands this milestone
ran, re-checked each time — never assumed from an earlier check.

Fresh 58-document production-corpus run (not reused from prior sessions):
mean recall **0.9491**, 52/58 fully recovered, same 8 failing documents
and same failure-class table as milestone 017 left it — re-measured, not
assumed, exactly as instructed.

## New Failure Ranking

Ranked by frequency × severity × recoverability × compute cost, from
this fresh measurement:

| rank | class | docs | severity | recoverable how | cost |
|---|---|---|---|---|---|
| 1 | word-order scrambling | `hc_scan_vi` (2 instances), `ord_invoice_png_vi` (1, masked by 017's fix already landing) | HIGH (worst single-doc recall in corpus: 0.25) | **deterministic, now validated** (this milestone) | low (CPU, no new model) |
| 2 | stamp-over-table detection | `cmb_scan_stamp_table_vi` | MEDIUM (0.75 recall, table fully unstructured) | **capability boundary demonstrated**, not yet recoverable deterministically at production confidence | none spent (not built) |
| 3 | tiny-text genuine OCR miss | `cmb_scan_tiny_vi` | CRITICAL (0.0 recall) but LOWEST recoverability — both backends genuinely fail, not investigated further this milestone (experiments 014/015 already flagged this needs higher-DPI/resegmentation, untested) | unresolved | high if pursued |
| 4 | borderless table structure | `hc_borderless_en`, `cmb_borderless_lowcontrast_en` | MEDIUM (text 100%, table 0/1) | untested this milestone | unknown |
| 5 | single dropped punctuation glyphs | `hc_scan_en`, `cmb_scan_multicol_en` | LOW (cosmetic, not content loss — experiment 016) | deprioritized, matches 016's own finding | n/a |

**INTERPRETATION**: word-order scrambling ranks #1 not because it's the
most frequent (n=2 documents) but because it's the only class where this
milestone reached a validated, deployable-quality fix at negligible cost
— frequency alone would have put tiny-text or stamp-detection first,
but recoverability and cost break the tie decisively toward the class
that could actually be closed this round.

**LIMITATION**: this ranking is this corpus's own distribution (58
synthetic documents). Frequency counts (n=1-2 per class) are too small
to generalize a population rate from.

## Word Order

**OBSERVED**, traced directly on real pixels (`hc_scan_vi`): Docling's
`recognize()` merges the salutation line ("Kính gửi: Phòng Tài chính -
Kế toán") and the body paragraph beneath it into ONE item, whose internal
word order comes out scrambled:

```
docling: 'Kính Phòng Tài chính Kế toán Căn cứ biên bản ... gửi: phải'
```

Docling exposes only ITEM-level bbox+text — no per-word geometry exists
to re-sort. EasyOCR's raw tokens covering the identical region, in
contrast, are 6 well-formed, individually-correct per-line detections
(it did not merge across physical lines). Clustering those tokens by
mutual y-overlap into lines, sorting each line left-to-right, and sorting
lines top-to-bottom reconstructs:

```
reconstruction: 'Kính gửi: Phòng Tài chính Kế toán Căn cứ biên bản ...'
```

**Exact order-recovery test performed** (not assumed): a plain `(y0, x0)`
tuple sort was checked against this same data and found wrong — three
same-line tokens have y0 values 449.0/450.9/452.0 (a few px apart, same
physical line), and a naive sort would place them by that y0 noise
instead of by x, producing "thu tại... phải công nợ" instead of "công nợ
phải thu tại...". Line-clustering (group by y-*overlap*, not y0 value)
is necessary, not optional — recorded as the reason this module clusters
rather than tuple-sorts.

**Signal, deliberately not word-Jaccard**: `order_consistency()`, a
Longest-Increasing-Subsequence-based measure (see
`src/doc_extraction/ingest/order_recovery.py`) — maps each word of one
reading to its first-unused position in the other, scores what fraction
of that index sequence is already increasing. 1.0 = same order; a single
displaced word among ~9 scores 0.929–0.939 (measured, not assumed); a
fully reversed sequence scores near 0. Word-Jaccard is 1.000 on both real
scrambled items (same words present, by construction of the defect) —
directly confirming this needed a genuinely different signal, not a
retuned threshold on the existing one (explicit instruction: do not
change agreement casually — a separate module was built instead).

**Order recovery, measured**: applying the reconstruction to `hc_scan_vi`
does **not** move the manifest's exact-substring recall (0.25→0.25) or
its word-recall (0.938→0.938, already saturated) — both numbers are
blind to this fix for reasons unrelated to whether it worked. Verified
directly: the ground-truth phrases require literal hyphens
("Độc lập **-** Tự do **-** Hạnh phúc") that neither OCR backend ever
recognizes (a separate, already known character-level gap — same class
as experiment 016's "Ký hiệu" whitespace-artifact finding). Stripping
punctuation from both sides for a fair, order-focused comparison:

| | before | after |
|---|---|---|
| punctuation-insensitive exact match | 0/2 | **2/2** |

**INTERPRETATION**: the fix is real and complete on this document; the
benchmark metric is doubly blind to it (an unrelated punctuation gap,
and a word-level metric that was never sensitive to order in the first
place — the same property that let this defect go undetected by
`assess_ocr_agreement` for two milestones). This is the second time in
two milestones (after 017's `ord_invoice_png_vi`) that document-level
recall has been shown not to reflect a real, verified improvement —
worth treating as a standing property of this metric, not a one-off.

**LIMITATION**: verified on n=2 real scrambled items (1 document). The
mechanism is designed to generalize (any Docling item vs. any EasyOCR
line-cluster) but was directly measured on one.

## Stamp/Table Detection

**OBSERVED**, traced directly (not assumed): `cmb_scan_stamp_table_vi`'s
Docling layout labels the entire table area `picture` (matching
experiment 011's already-fixed text-recovery mechanism — the loose text
IS present, confirmed present in the final IR). Because no region is
labeled `table`, `run_scanned_page_pipeline` calls Table Transformer's
own *standalone* whole-page detector. Probed directly at threshold 0.01
(bypassing the configured 0.7 cutoff to see what exists): the detector's
own best candidate for this table scores **0.267–0.272** — genuinely low
confidence, not zero, and not absent — multiple overlapping boxes
roughly cover the real table area, all well under threshold.

**INTERPRETATION**: this separates cleanly into the two cases the
instructions asked to distinguish. **Not** "table detected, text
assignment fails" (milestone 017's class — there is no detected table
object here for that fix to act on). **Is** "table never detected" — a
genuine confidence collapse in Table Transformer's own visual model when
a stamp occludes enough of the table's ruling/grid pattern, quantified
here rather than left as a 0/1 count.

**Cheap-evidence probe** (per instructions, before considering a new
model): the OCR text elements *do* show a clear repeated row/column
pattern independent of Table Transformer entirely — 4 rows at
y≈552/606/658/715, and consistent column x-bands at ≈170-190 (row
number), ≈240-470 (description), ≈948-1096 (price), each appearing in
every row. This is exactly the kind of structural signal (repeated x
positions, row clustering) the instructions named as worth testing
before adding a model — **and it is present here**, evidenced directly,
not assumed.

**Deliberately not built this milestone**: a deterministic table-
candidate detector from this signal was not implemented. Doing it with
the same regression rigor as milestone 017 (a synthetic matrix, real-
corpus validation, negative controls against ordinary tables/stamps) is
itself a full milestone's worth of work, and this one's evidence budget
was spent validating the word-order fix to completion instead of
splitting across two half-validated ones — directly following "do not
continue adding heuristics blindly."

## New Hard Cases

Forms/checkboxes/key-value/charts (instructions §10) were **not**
probed this milestone. Given the size of the word-order + stamp-
detection investigation already completed and the explicit instruction
to avoid "benchmark inflation," this was judged lower priority than
finishing the two investigations already in flight to a decisive
conclusion, rather than starting a third at survey depth only. Recorded
here as **not done**, not silently skipped.

## Verification

Reviewed against the instructions' target shape
(`status + failure_type + affected_region + recommended_action`).
Current state: `assess_ocr_agreement` returns `status` + a raw score
only; `order_recovery`'s own `OrderRecoveryRecord` now separately
carries `jaccard` + `order_consistency` + `decision` + `reasons`, which
covers `failure_type` (kept_old reasons name the specific rejection:
"content disagreement, not order" / "already order-consistent") and
`affected_region` (`element_id`) informally, per-call, not yet through
the shared `Verification` type both this module and `scan_recovery`
independently reimplement pieces of. **Not implemented this milestone**:
unifying these into one shared diagnostic type — the instructions
explicitly ask to review, not build, this layer yet ("do not implement
the whole recovery policy yet"). The concrete, evidence-backed case for
doing so next: two independent recovery modules
(`scan_recovery.RecoveryRecord`, `order_recovery.OrderRecoveryRecord`)
now carry near-identical shapes by convergent design, which is itself
the signal that a shared type is due.

## Recovery Policy

Prototyped as a decision table, not implemented as a dispatcher (per
instructions — only build actions the measured failures justify):

| diagnosis | evidence this milestone | action | status |
|---|---|---|---|
| same words, different order (`order_consistency` low, `jaccard` high) | `hc_scan_vi`, `cmb_scan_stamp_table_vi` (real, measured) | REORDER (line-cluster + spatial sort) | **built**, `order_recovery.py` |
| same words, different order, but reconstruction source itself incomplete | `cmb_scan_multicol_en` (real, measured — reconstruction would have made a correct reading worse) | NO_ACTION (guarded by `RECON_JACCARD_MIN`) | **built as a safety gate**, not a separate action |
| table region present but low-confidence structure | `cmb_scan_stamp_table_vi`'s table, quantified 0.267 vs 0.7 threshold | TABLE_RECOVERY (accept a lower-confidence candidate given corroborating OCR-grid evidence) | **not built** — evidence exists, mechanism does not yet |
| tiny text, correlated backend failure | `cmb_scan_tiny_vi` | RERENDER_HIGH_DPI / VLM_REGION | **not investigated this milestone** |
| single dropped punctuation | `hc_scan_en`, `cmb_scan_multicol_en` | NO_ACTION (cosmetic, per experiment 016) | **deliberately not built** |

## GPU/VLM

`nvidia-smi` checked CLEAR before all 6 GPU-using commands this
milestone; never LIMITED or PROTECTED; nothing else on the box was
touched. **No VLM benchmark was run**, per instructions — the VLM
decision test (instructions §15) was applied to the strongest unresolved
case (`cmb_scan_stamp_table_vi`'s table detection): existing evidence
(the OCR-token row/column pattern found above) **can** in principle
recover it deterministically — the mechanism to act on that evidence
simply was not built this round. Per the stated rule
("if yes: NO VLM"), **no VLM experiment was justified or run**.

## Real Data Gap

Not pursued this milestone (instructions §16 names it as a task, not a
requirement for every session). Flagged, not investigated: the specific
gap this milestone's own findings point to is **real scanned Vietnamese
official-letter/invoice documents with genuine multi-line letterhead or
salutation blocks** — the exact geometry `order_recovery` targets. The
synthetic corpus has exactly one document (`hc_scan_vi`) exhibiting this,
which is enough to validate the mechanism works but not enough to
estimate how often it would fire on a real production stream. This is
the most concrete, smallest real-data ask this milestone's evidence
supports — not a general "we need more data" statement.

## Production Impact

58-document corpus, before/after `order_recovery`, GPU CLEAR both runs:

| | before | after |
|---|---|---|
| mean text recall | 0.9491 | **0.9513** |
| documents with recall improved | — | **1/58** (`cmb_scan_stamp_table_vi`, 0.750→0.875) |
| documents with element text changed (recall or not) | — | **2/58** (above, plus `hc_scan_vi`, recall unchanged for the reason traced above) |
| documents regressed | — | **0/58** |
| total elements replaced across the corpus | — | 3 |
| total elements checked-and-kept (negative controls that ran and correctly declined) | — | 27 |

14-document hardcase corpus: **0/14** changed, **0/14** regressed — a
clean negative control (this corpus has almost no real scan-order-
scrambling geometry to exercise the mechanism against, so a null result
here is expected, not informative on its own).

**Quality caveat, measured not assumed**: the one recall-improving case
(`cmb_scan_stamp_table_vi`) also introduces EasyOCR-specific character
noise absent from Docling's original reading (`"Mô_tả"`, `"Số
IượngThành tiển"`, `"Bộ loc khí"` — a stray underscore, a missing space
plus a misread character, and a missing diacritic, respectively). Net
effect on the measured metric is positive (+0.125 recall on this
document, driven by "Dịch vụ lắp đặt" now landing in the correct order),
but the swap is not unambiguously an improvement in every dimension —
recorded honestly rather than presented as a clean win.

## Research Direction

Re-ranked, per instructions, against production impact / research value
/ evidence strength / implementation cost:

| direction | production impact | evidence strength this session | cost | verdict |
|---|---|---|---|---|
| **order recovery** (this milestone) | measured: +0.0022 corpus mean, +0.125 on the one real case it fires on | strong (2 real cases, 2 full corpora, 0 regressions) | low (shipped) | **the dominant direction — done, not hypothetical** |
| table intelligence (structure detection under occlusion) | one document, but that document's table is now the corpus's most severe remaining table failure | strong diagnosis (0.267 vs 0.7, quantified), zero recovery evidence | medium (a real detector-fallback build) | next in line, not started |
| scan recovery v1 (agreement-trigger) | REJECTED (015) | — | — | closed |
| table cell geometry (017) | PROMOTED, shipped | — | — | closed |
| VLM specialist | no case in this corpus demonstrated a genuine capability gap this session | none produced | high | not justified yet |
| forms/charts/checkboxes | unmeasured | none (deliberately not surveyed this round) | unknown | open, next discovery pass |

## What We Should NOT Build

* A generic recovery-policy dispatcher wiring every row of the table
  above — only REORDER has evidence sufficient to justify existing as
  code; the rest are named, not implemented.
* A unified `Verification` type merging `scan_recovery` and
  `order_recovery`'s near-identical record shapes — the convergence is
  now visible (two independent modules landed on similar fields), which
  is the signal that doing this is due, not evidence that doing it *now*
  is the highest-value next step.
* A table-candidate detector from the OCR-grid signal found above —
  real, evidenced, and specifically NOT built this round; the next
  milestone's job, with its own regression matrix, not a rushed add-on
  here.
* Any VLM work — no case in this session's evidence required visual
  semantic reasoning beyond what the existing OCR backends already
  extracted.

## Next 3 Actions

1. **Build the OCR-grid table-candidate detector** for the
   stamp-occlusion case — the evidence (repeated row/column x-bands,
   Table Transformer's own sub-threshold candidates) is already gathered
   above; this is now a scoped, evidence-backed build, not exploratory
   research.
2. **Unify `scan_recovery` and `order_recovery`'s record types** into
   the shared diagnostic shape (`status`/`failure_type`/
   `affected_region`/`recommended_action`) the instructions named — now
   justified by two independent, convergent implementations rather than
   designed speculatively.
3. **Investigate `cmb_scan_tiny_vi`** (the corpus's one 0.0-recall
   document, and the last major failure class with zero recovery
   progress across three consecutive milestones) — experiments 014/015
   already named padding-proportional resegmentation and higher-DPI
   re-render as untested candidates; this is the next real gap after
   order recovery and table detection.

## Promotion Decision

No hedging, per instructions:

| | decision |
|---|---|
| **ORDER RECOVERY v1** (`order_consistency` trigger → line-cluster reconstruction) | **EXPERIMENTAL** |

Sound design, zero regressions across 58 + 14 real documents, one clean
win and one mixed-but-net-positive win on real data — but the total real
positive-case count is **2 documents**, the same evidence class
(`targeted_recovery`, experiment 014, n=2) this project has already
established as EXPERIMENTAL rather than PROMOTE. Not wired into
production `cli.py`/`configs/*.yaml`; remains a validated research
module, same status and same reasoning as its sibling modules.

## Reproduce

```bash
pytest tests/test_order_recovery.py -v
python experiments/018_bottleneck_discovery/word_order_recovery.py --device cuda
python experiments/018_bottleneck_discovery/run_order_recovery.py --device cuda --scope six
python experiments/018_bottleneck_discovery/run_order_recovery.py --device cuda --scope corpus
python experiments/018_bottleneck_discovery/run_order_recovery_hardcases.py --device cuda
```
