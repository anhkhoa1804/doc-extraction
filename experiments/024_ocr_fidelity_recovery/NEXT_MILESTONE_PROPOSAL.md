# Proposal — 025: Layout evidence recall

**Status: PROPOSED. Not started. No code written, no experiment run.**

024 is frozen at `0355e79`, verdict **CONFIRMED BUT LOW-SENSITIVITY**, L5
**SHIP — CONFIRMED**. This proposal is written from 024's completed
artifacts only. Nothing here has been measured by a new run.

## The question 024 leaves open

L5 recovers OCR tokens that no layout region claims. On SCAN-49 it recovered
663 of 664 orphans (99.85%) across 70 pages and 8 documents, with zero
regressions on every axis. That is a *rescue*. It does not explain why 11.21%
of recognised tokens had no region to belong to in the first place.

> **How much useful evidence is lost because layout analysis fails to create
> the regions that OCR tokens need to belong to?**

L5 makes that loss survivable. It does not make it visible, and it does not
make it stop.

## Why this, and not the alternatives

Taken from `scan_cohort_ab.json` (49 docs / 112 pages, adaptive router, CPU).
Eight documents carry a residual defect under L5. **Seven of the eight have
`char_recall == 1.0`** — every character is acquired and present in the
output. The defect is structural, not recognition.

| residual class | docs | evidence |
|---|---|---|
| reading-order failure | 4 | `order_ok=False`, all `char=1.0`; 3 also `exact=1.0` |
| layout/table region not emitted | 3 | `tables_expected=1, tables_found=0`, all `char=1.0`, all stamp+occlusion |
| OCR acquisition failure | 1 | `hc_rotation_vi`, `char=0.494`, `exact=0.0` |
| region ownership failure | 0 | `orphan_also_claimed=0` across all 112 pages |

**Option C (remaining OCR fidelity) is close to exhausted, and pushing it
harder makes things worse.** `line3_acquisition.json` escalated whole-page
DPI on the five small-text documents: acquisition rate went **0.697 (200 DPI)
→ 0.606 (400) → 0.606 (600) → 0.303 (600, psm 6)**. More pixels lost
evidence. Meanwhile `line7_region_reocr.json` ran 600 DPI psm 6 *per detected
column* and recovered 4 previously-missing strings in `cmb_tiny_table_en` and
`hc_tiny_cells_vi` — the same resolution, the same engine, succeeding only
because it was handed a region-sized crop.

That pair is the core argument of this milestone: **the recognizer is capable;
it fails when it is handed the wrong crop.** The bottleneck is upstream of
recognition, in what the layout stage hands it.

**Option B (table structure/row recall) is real but is a subset of A.** All 3
table failures are `tables_found=0` — the detector emits no table at all under
stamp occlusion, so there are no rows to under-count. Row-level structure
cannot be the bottleneck while region-level existence is failing.

**Option D is not supported.** Ownership was ruled out in 023 and re-confirmed
here (`orphan_also_claimed=0`, 017 closed the assignment gap). Rotation is one
document and line 4 already acts on it.

## The finding that reframes the problem

The obvious hypothesis — "the detector sometimes emits nothing" — is **false**.

From `audit_pages` (112 pages): **zero pages have zero regions.** The detector
always fires, averaging 2.3 regions and 0.84 tables per page. And yet 667 of
5,925 tokens (11.25%) fall outside every region it emits.

So this is not region *existence*. It is **region coverage** — regions exist but
do not span the page's actual text extent. The concentration says where:

- `hc_multicolumn_en` p0 and `cmb_scan_multicol_en` p0: 34 tokens, **2 regions**,
  **15 orphans (44%)**, 97 orphan chars. A two-column page detected as a
  region set that covers one column's worth of extent.
- `hc_tiny_text_vi` / `cmb_scan_tiny_vi` p0: 52 tokens, 2 regions, 17 orphans (33%).
- Orphan rate is **higher on pages that do have a detected table** (11.93%,
  n=92) than on pages without one (8.35%, n=20). Table regions under-cover
  their own content.

2,805 orphan characters over the cohort — carried by L5 today, invisible to the
scorer, and produced by a detector that believes it succeeded.

## Distinguishing the four failure modes

The milestone must keep these separate. Collapsing them into "layout failure"
is what would make the result unusable.

1. **OCR acquisition failure** — the token was never recognised. Measured
   against the recognizer's own output, not the pipeline's.
2. **Layout detection failure** — the region does not exist, or exists with
   insufficient extent. This is the target.
3. **Region ownership failure** — the region and token both exist, correctly,
   and `_center_in` still assigns wrongly. Currently measured at zero; the
   milestone must keep measuring it, not assume it.
4. **Reading-order failure** — regions and ownership are correct and the
   sequence is wrong.

Classes 2 and 4 are *linked but not identical*, and the evidence says so: 023
found all three of its assembly losses were region-ordering under multi-column
scans, and the two 44%-orphan pages here are the same multi-column shape. A
missing second-column region cannot be ordered correctly. **A region-recall fix
may resolve some order failures for free; the milestone must attribute that
rather than claim it.** The 4 order-failing documents here have `char=1.0` and
3 have `exact=1.0`, so they are measurable only through `order_ok`, not recall.

## Proposed investigation order

Adopted as given in §9, with two justified changes.

1. **Measure region recall directly from OCR-token geometry.** Tokens are the
   ground truth the detector never sees: any token outside every region is a
   coverage miss. Yields per-page region recall with no new labels and no new
   corpus.
2. **Quantify orphan concentration by region type.** *Requires instrumentation
   that does not exist* — `audit_pages` records region counts, not types. This
   is a prerequisite, not an analysis of existing data.
3. **Quantify table row/column under-detection** — scoped to the 3
   `tables_found=0` occlusion documents plus the 16 `expected_tables` docs.
4. **Test cheap deterministic geometric recovery** — region extension /
   merging driven by orphan geometry. Must be evaluated against L5, not
   against baseline: the question is whether fixing coverage beats rescuing
   orphans, and whether the two are redundant.
5. **Region-level fallback only where detector confidence is weak.** 024
   proved the cost model: whole-page escalation is harmful and per-region
   escalation is expensive — `line7` spent 120 extra OCR calls (3.449/doc,
   57.4 s) for 4 strings. A confidence gate is mandatory, not optional.
6. **Learned detector/router only if deterministic recovery hits a real
   boundary** — and the boundary must be demonstrated, not asserted.
7. **VLM remains gated** behind proven deterministic failure. Not in scope.

**Change 1:** step 2 is reclassified as instrumentation work, ahead of
analysis. **Change 2:** reading-order attribution is added as a standing
measurement across steps 1–4 rather than deferred, because the multi-column
evidence says the two classes share a cause and the milestone would otherwise
mis-attribute its own wins.

## What this milestone must not do

- Not modify L5, the scorer, the thresholds, the cohort rule, or the
  production router.
- Not replace the pipeline. The architecture stands: native-first → layout →
  Tesseract-first OCR → evidence preservation / L5 → reading-order assembly →
  table / IR construction → verification. **This milestone improves the layout
  layer only.**
- Not add an OCR engine. 022 settled the recognizer question.
- Not treat rasterized born-digital pages as real scans. SCAN-49's own limit
  carries forward.

## Evaluation warning that carries forward

024's central methodological result must govern this milestone's design:
**recovered evidence can be substantial while benchmark recall barely moves.**
`long_policy_vi_60p` recovered 540 tokens and 2,811 characters across all 60
pages and neither exact nor char recall moved by a digit. Benchmark
sensitivity per recovered token collapsed 10× (0.2125 → 0.0205 per thousand)
as scan exposure rose.

**A layout-recall milestone scored only on `must_contain` recall will report
approximately nothing and be wrongly abandoned.** It needs a coverage metric —
tokens claimed, region recall, orphan chars — as a primary outcome, with
recall as a secondary guard against regression. This is the same trap 024
walked into and documented; walking into it twice would be a choice.

Hallucination safety remains **UNDER-MEASURED** (must_not_contain on 1 of 51
documents, 2 strings). Any milestone that *adds* or *extends* regions raises
the hallucination surface, so this gap must be closed before, not after.
