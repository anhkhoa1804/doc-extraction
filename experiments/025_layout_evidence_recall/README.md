# 025 — Layout Evidence Recall

**Status: COMPLETE. Hypothesis REJECTED. No production code modified.**

Baseline: `0355e79`, branch `fix/table-text-ownership`, cohort SCAN-49 of
`experiments/024_ocr_fidelity_recovery/scan_cohort_manifest.json`
(49 documents / 112 pages, all 51 files sha256-verified before every run).
CPU only; the GPU was idle at 0 MiB throughout and was never used.

## The question

> How much useful evidence is lost because layout analysis fails to create
> regions that cover the OCR evidence that already exists?

## The answer

Measurably little, and almost none of it matters. **Region Coverage Recall is
0.8874** — 5,258 of 5,925 recognised tokens are claimed by a detected region.
Of the 667 that are not:

| orphan class | tokens | share |
| --- | ---: | ---: |
| header_band | 448 | 67.5% |
| footer_band | 128 | 19.3% |
| interior_gap | 53 | 8.0% |
| lateral_band (missing second column) | 28 | 4.2% |
| edge_adjacent / outside_corner / table_adjacent | 7 | 1.1% |

**576 of 664 orphans (86.75%) are running page furniture.** The 664 orphan
tokens contain only **128 distinct strings**; the most frequent are `ty` ×66,
`tnhh` ×64, `minh` ×64, `quang` ×64, `trang` ×64 — one company name in a
running header and one page number in a running footer, repeated across the
60 pages of `long_policy_vi_60p` and the 4 of `hc_crosspage_vi`.

And the documents that actually fail do not fail for this reason. **Seven of
the eight residual-defect documents have coverage recall 1.000 and zero
orphans.**

The hypothesis the milestone was built on — that missing region coverage is
the dominant residual bottleneck — is **rejected by its own instrumentation**.

## What the intervention proved

`gap_region` synthesizes a layout region for every coherent cluster of orphan
tokens, using production's own `_orphan_tokens` and `_cluster_orphans`. It is
the maximal form of the hypothesis: if upstream coverage repair can change
anything, this changes it.

| | none (control) | gap_region | delta |
| --- | ---: | ---: | ---: |
| region coverage recall | 0.8874 | **0.9993** | +0.1119 |
| orphan tokens | 664 | **1** | −663 |
| regions synthesized | 0 | 140 | +140 |
| tokens claimed by synthesized region | 0 | 663 | +663 |
| tokens recovered by L5 | 663 | **0** | −663 |
| L5 elements | 140 | 0 | −140 |
| mean exact recall | 0.9060 | 0.9060 | **0** |
| mean char recall | 0.9803 | 0.9803 | **0** |
| perfect documents | 35 | 35 | **0** |
| order_ok | 45 | 45 | **0** |
| tables_ok | 46 | 46 | **0** |
| hallucinated / errors | 0 / 0 | 0 / 0 | **0** |

**All 49 documents produce byte-identical text (`text_sha` matches 49/49).**
140 synthesized regions replace exactly 140 L5 elements and 663 tokens move
from "recovered by the fallback" to "claimed by layout", and nothing
downstream can tell the difference.

Verdict: **REJECT**. The intervention does not improve the mechanism; it
relocates the repair. That is the §11 accounting answering its own question —
**L5 already absorbs the entire layout coverage gap**, and there is no
residual value upstream of it to collect.

The control arm reproduces 024's frozen `l5` arm on all 49 `text_sha`, so the
comparison is against measured production behaviour, not a re-derivation.

## What the instrumentation found instead

Three mechanisms the proposal did not anticipate, each measured.

**Class C — overlapping ownership (82 tokens, 3 documents).** 82 tokens fall
inside two regions at once. `_gather_region_text` runs once per region, so
each is emitted into both elements: **82 duplicate emissions, 292 duplicated
characters**. All 82 classify as `nested_in_picture_labelled_block`.

**Class D — table gating (3 documents).** Docling emits a region of
1039×337 px — the table's geometry, almost exactly — and labels it `picture`.
`pipelines/base.py:747` selects table regions by `label.lower() == "table"`,
so the list is empty and **TableTransformer is never invoked**. `tables_found=0`
follows from the label gate, not from any failure of the table detector.
Docling *also* emits 13–16 `text` regions nested inside it, median 132×28 px —
the table's own cells. The geometry needed to rebuild the table is present in
the detector's output and is discarded by a single label-equality test.

**Class E — cell ordering (11 tables, 11 documents).** Table cells are
serialized in detector emission order, not geometric order. On
`ord_purchase_order_vi` the cell y0 sequence is 536, 536, 536, 536, 580, 580,
580, 580, **491, 491, 491, 491**, 650… — the header row is emitted third.
`row_index` and `col_index` are `None` on **every** cell of every affected
table. All four `order_ok=False` documents attribute here; their page elements
carry monotonic `order_index` `[0, 1, 2]`. **`compute_reading_order` is
exonerated 4 of 4.**

## Evaluation integrity

024 found recall blind to evidence it did not ask for. 025 finds the same
blindness twice more, in the opposite direction and in a third dimension.
`text_recall` and `char_recall` count ground-truth strings **found**, never
output **emitted**, so:

* dropped evidence cannot lower them — 024's finding;
* duplicated evidence cannot lower them — all three stamp documents emit
  26–28 duplicate token emissions at `char_recall` 1.000;
* mis-ordered structure is mostly invisible — **11 of 94 tables emit cells
  out of geometric order and only 4 surface as `order_ok=False`, a benchmark
  detection rate of 0.36.** Seven documents carry scrambled tables that score
  clean.

`evaluation_metrics.json` defines five diagnostic metrics for future layout
work — evidence coverage, orphan rate, overlap rate, evidence duplication,
structural integrity. They are **not** wired into the scorer or any gate.

## L5, restated

**SHIP — CONFIRMED.** Unchanged, unweakened, and this milestone strengthens
the case for it: the `gap_region` arm shows L5 already captures 100% of the
recoverable coverage gap, at zero downstream cost.

What 025 refines is the *interpretation*, not the behaviour:

* **Proven** — L5 restores OCR evidence that would otherwise be discarded.
* **Not proven** — that recovered evidence is body content. On this corpus
  86.75% of it is running headers and footers.

024's `long_policy_vi_60p` result stands as measured — 540 tokens and 2,811
characters were genuinely dropped and are genuinely recovered. Its
*interpretation* needs refinement: those 540 tokens are 420 header + 120
footer tokens, one company name and one page number repeated over 60 pages.
The benchmark was not under-measuring hidden body content there; it was
correctly ignoring repeated page furniture. `recovered token = useful body
content` is not an entailment and 025 measured the gap.

## Failure taxonomy, quantified

Classes kept separate. C, D, E and G are **not** collapsed into "layout failure".

| class | definition | magnitude | documents |
| --- | --- | --- | ---: |
| **A** OCR acquisition | `must_contain` words never recognised at all | 7 strings | 4 |
| **B** orphan evidence | tokens claimed by 0 regions | 664 tokens (11.21%), **576 of them furniture** | 9 |
| **C** overlapping ownership | tokens claimed by ≥2 regions | 82 tokens (1.38%), 82 duplicate emissions, 292 chars | 3 |
| **D** region-label gating | table geometry emitted under label `picture` | 3 tables lost; TableTransformer never invoked | 3 |
| **E** cell ordering | cells serialized in detector emission order | **11 of 94 tables**; 0 cells carry `row_index` | 11 |
| **F** token/text fidelity | recognised, but wrong characters | 28 strings partially recognised | 17 |
| **G** page/region reading order | the page's regions ordered wrongly | **0** | **0** |

Required-string coverage: 189 covered, 28 partially recognised, 7 not
recognised, 2 partially covered.

Class C token distribution: 0 regions 667 · 1 region 5,176 · 2 regions 82 ·
3+ regions 0. All 82 involve a `picture` owner and table-like geometry.

## Next frontier and hypothesis

**Primary next frontier: E — cell ordering.** Chosen on the evidence, not on
sophistication: it affects 11 documents against D's 3, it touches every route
that builds tables rather than only the scanned one, the correction is a
deterministic sort with `_renumber_rows_by_position` already present at
`pipelines/base.py:460`, and — decisively — reordering **creates no new
content**, so it can be validated under the `must_not_contain` supervision
this corpus actually has (1 of 51 documents, 2 strings, still
**UNDER-MEASURED**). D is the immediate successor: higher severity per
document but narrower, and it *creates* table structure, which raises a
hallucination surface the present corpus cannot police. C is subsumed by D —
the overlap is a consequence of the same `picture` mislabel.

> **Hypothesis for the next milestone.** Table cells should be canonicalized
> by geometric row/column position before serialization. Assigning
> `row_index`/`col_index` from cell bbox geometry — row-band clustering on
> y, then ordering by x — and emitting cells in that canonical order will
> raise structural integrity from 0.883 toward 1.000 and repair all four
> `order_ok=False` documents, **without changing any cell's text**.

Falsified if: cell geometry cannot recover row bands on any affected table
(overlapping or degenerate y-bands); or canonicalization changes cell *text*
rather than only sequence; or `order_ok` fails to improve on all four
documents; or any control document regresses on exact recall, char recall,
`tables_ok`, or hallucination. To be measured on the frozen SCAN-49 cohort
with hard cases, control, and ordinary pages reported separately.

**Not implemented here.** 025 proposes it and stops.

## Production-code status

**NO PRODUCTION CODE WAS CHANGED BY THIS MILESTONE.** Nothing under `src/`,
`configs/` or `tests/` was modified — verified by `git status --porcelain`
on those paths being empty at freeze. Every measurement was taken by wrapping
or monkeypatching objects the experiment scripts construct themselves;
`coverage_instrument.py` delegates to the real `merge_regions_into_page`
unchanged, and both it and the A/B control arm reproduce 024's frozen `l5`
arm on 49/49 `text_sha`. The only production feature shipped from this chain
remains L5, whose behaviour is untouched.

Repository state at freeze: HEAD `0355e79`, branch
`fix/table-text-ownership`, 024 proposal
`NEXT_MILESTONE_PROPOSAL.md` sha256 `fc0a493d8ec71e1542b48d088fa12262709b0c5118cb6357090d18b913f531f3`.
No GPU was used; the L4 was held by an unrelated Research-No.1 workload
during part of this milestone and was not touched, paused, or reset.

## Artifacts

| file | what |
| --- | --- |
| `coverage_instrument.py` → `coverage_dataset.json` | per-token/region/table geometry, 112 pages, 5,925 tokens; `text_sha` identical to 024's `l5` arm on 49/49 |
| `coverage_analysis.py` → `coverage_analysis.json` | region coverage recall, required-string coverage |
| `orphan_topology.py` → `orphan_topology.json` | orphan geometric classification, structure vs noise |
| `case_studies.py` → `case_studies.json` | the six §7 documents |
| `failure_taxonomy.py` → `failure_taxonomy.json` | token and document accounting, classes A–G |
| `overlap_diagnostic.py` → `overlap_diagnostic.json` | class C, multiply-owned tokens |
| `stamp_causal_chain.py` → `stamp_causal_chain.json` | class D, five measured links |
| `reading_order_attribution.py` → `reading_order_attribution.json` | class E vs G attribution |
| `evaluation_metrics.py` → `evaluation_metrics.json` | five diagnostic metrics |
| `interventions.py`, `intervention_ab.py` → `intervention_ab.json` | the two-arm A/B |

`_runs/` is excluded by `experiments/**/_runs/`. Every script is offline
except `coverage_instrument.py` and `intervention_ab.py`.

## Not implementable, and why

* **Proposal intervention 3 (table extent recovery)** — presupposes a
  detected table whose extent is short. The three failing documents have no
  detected table at all. There is no extent to extend.
* **Proposal intervention 4 (confidence-aware fallback)** — Docling emits
  `confidence=None` on all 258 regions. There is no signal to gate on.
