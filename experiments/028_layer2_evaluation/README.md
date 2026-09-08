# 028 — Layer-2 Evaluation Instrument

**Status: COMPLETE. Decision: ADOPT (as the standard research evaluation
contract, alongside Layer 1). No production code changed. The frozen scorer
was executed unchanged.**

Baseline `271abf22b7bf1df326eeddea2f63e6d333881366`; IR measured is 025's
frozen SCAN-49 run at `0355e79`. Offline, CPU-only; the L4 was held
throughout by an unrelated Research-No.1 workload and was not touched.

## 1. Motivation

027 established that one flattened string was acting as a proxy for five
independent properties, and that 56.1% of Layer 1's `order_ok` failures were
table cell emission order rather than reading order. 028 turns the adopted
contract into a working instrument and asks one question:

> Does Layer 2 measure dimensions Layer 1 demonstrably cannot distinguish?

**Yes — and in both directions.** It finds defects Layer 1 is blind to, and
it clears documents Layer 1 wrongly flags.

## 2. The actual IR contract

Introspected from the live pydantic models, not from any prior report
(`ir_schema_inventory.json`, schema version **1.2.0**).

| model | required fields | identity |
| --- | --- | --- |
| `Document` | `document_id`, `metadata` | `document_id` |
| `Page` | `index`, `width`, `height` | `index` (0-based, ≠ page number) |
| `Element` | `id`, `type`, `source_backend` | `id` |
| `Table` | `id`, `n_rows`, `n_cols`, `source_backend` | `id` |
| `Cell` | `row`, `col` | **`(row, col)` — there is no cell id** |
| `BBox` | `x0,y0,x1,y1` | top-left origin, +y down |

The decisive discovery: **`Page.reading_order: list[Element.id]` exists in
production** and `Document.to_markdown` already consumes it. Layer 2's page
ordering therefore uses production semantics rather than an invented proxy.
`Cell` carries `row_span`/`col_span`, so spanning is read rather than assumed.

## 3. Metric definitions

Four views — `table_text`, `table_structure`, `page_order_ok`,
`table_structural_integrity` — specified in `evaluation_contract.md`. Two
design rules govern them:

* **`list_order_canonical` is reported separately and is not part of the
  structural verdict.** 026 treated storage order as structural integrity;
  a tidily-stored table can still be incoherent.
* **`UNMEASURABLE` is a first-class value.** TEXT has no per-cell ground
  truth in this corpus, so no proxy was manufactured for it.

## 4. SCAN-49 results

Layer 1, executed unchanged on the real objects, reproduces its own history
exactly — which is what licenses the comparison:

| Layer 1 (frozen) | value |
| --- | ---: |
| mean exact recall | 0.9060 |
| mean char recall | 0.9803 |
| perfect documents | 35 |
| `order_ok` | **45 / 49** |
| hallucinated | 0 |
| same serializer, canonical cells | `order_ok` **49 / 49** |

| Layer 2 | value |
| --- | ---: |
| documents / tables / cells | 49 / **94** / **1,133** |
| structurally **valid** tables | **90 / 94** (0.9574) |
| structurally **invalid** tables | **4** |
| failed checks | `cells_within_table_bbox`: 4 |
| duplicate-coordinate tables | 0 |
| spanning-cell tables | 0 |
| list order canonical | **83 / 94** (11 non-canonical) |
| `page_order_ok` documents | **48 / 49** |
| unmeasurable strings | **63 across 22 documents** |
| pages with `reading_order` covering every element | **112 / 112** |
| evidence coverage / orphan / overlap | 0.8736 / 0.1126 / 0.0138 |

**Everything 025/026/027 claimed is reproduced from the IR, not copied:**
94 tables, 1,133 cells, 94/94 correct `row`/`col`, 11 raw list-order
anomalies, `order_ok` 45 → 49 under canonical serialization, 667 tokens in
zero regions, 82 multiply-owned, evidence coverage 0.8736.

One reconciliation worth stating: 025's orphan rate uses `n_owners == 0`
(667 tokens); the `claim == "orphan"` subset L5 actually recovers is 664. The
3-token difference is tokens inside a detected table or cell but inside no
region. Both are now recorded, so the two milestones' numbers agree exactly
instead of differing for an unexplained reason.

### Per-table status vectors

| STRUCTURE | ORDER | OWNERSHIP | TEXT | tables |
| --- | --- | --- | --- | ---: |
| VALID | CANONICAL | CLEAN | UNMEASURABLE | **83** |
| VALID | NON_CANONICAL | CLEAN | UNMEASURABLE | **7** |
| INVALID | NON_CANONICAL | CLEAN | UNMEASURABLE | **4** |

## 5. What Layer 1 could not see

**Two new findings, neither previously measured.**

**(a) Four structurally invalid tables.** Cells fall outside their own
table's bbox — `cmb_stamp_boundary_vi` 6/8 inside, `hc_encoding_vi` 8/10,
`hc_tiny_cells_vi` 12/16, `ord_financial_report_vi` 12/16, all from
`table_transformer`. Layer 1 cannot express this defect at all; 025 and 026
never looked for it. All four are also non-canonical in storage order, so the
invalid set is a strict subset of the 11 — the two defects co-occur but are
not the same defect.

**(b) A Layer-1 false negative.** `cmb_stamp_boundary_vi` fails
`page_order_ok` (positions `[0, 56, 179, 163, …]` — an inversion) while Layer
1 reports `order_ok=True` under **both** the frozen and the canonical
serializer. 027 found Layer 1's false *positives*; this is the opposite
error, and only a table-free ordering view exposes it.

**(c) A third of the required strings are unorderable.** 63 of the corpus's
`must_contain` strings live inside table cells. Layer 1 assigned every one of
them a position in a flattened string and used it to judge reading order.
Layer 2 marks them UNMEASURABLE.

## 6. Counterfactual (Phase 4)

Same cells, same identities, same text, same `row`/`col`, same bboxes — only
sequence differs. Verified per document. `order_ok` **45 → 49**, reproducing
027's SCAN-49 result (4 → 0 failures) independently from the IR.

## 7. Negative controls — validating the evaluator

**12 / 12 pass** (`evaluator_controls.json`): correct table, shuffled list
with correct row/col, duplicate `(row,col)`, missing cell, invalid row,
invalid col, invalid bbox, cell outside table bbox, duplicate text in
distinct cells, empty cell, multi-row, multi-column.

The suite earned its place twice by failing first:

* `07_invalid_bbox` initially failed because an invalid cell box **cascaded**
  into `cells_within_table_bbox`, reporting one defect as two. Containment is
  now tested only on cells whose own bbox is valid.
* After Phase 7 added band coherence, controls 03 and 08 failed because their
  mutations genuinely violate coherence too. The **expectations** were
  tightened, not the evaluator loosened — a duplicate cell placed 200px away
  really is incoherent.

## 8. Anti-gaming (Phase 7)

Seven transformations that could improve a naive metric without improving
extraction. **None was rewarded** (`anti_gaming.json`).

This phase also found a real weakness. `row_order_matches_geometry`, which
compares row groups by `min(y0)`, **failed to catch** relabelling `row`/`col`
to match storage order: the shuffle put a low-y cell in both rows, the minima
tied, and the check passed. Adding **row/col band coherence** — cells sharing
a coordinate must occupy a common band — catches it. Validated against all 94
real tables with **zero false positives**, which matters because 025 and 026
established that real tables genuinely do have overlapping row *bands*; the
new check tests common intersection per group, not separation between groups.

## 9. Relationship with Layer 1

Layer 2 **supplements** Layer 1 and rewrites nothing. Layer 1 was executed
unchanged and reproduced its historical SCAN-49 numbers exactly. No score in
023–027 is altered, and no rebaseline is proposed.

## 10. Limitations

* **TEXT is UNMEASURABLE.** The corpus has document-level `must_contain`
  only, so per-cell text accuracy cannot be scored. `cell_grid_accuracy` from
  the 027 proposal is deliberately **not implemented**.
* **OWNERSHIP is borrowed**, from 025's token dataset; it exists only for
  SCAN-49 and is not a native Layer-2 computation.
* `page_order_ok` scores only strings outside tables — 63 of the corpus's
  required strings are therefore invisible to it. That is honest scope, not
  coverage.
* Only SCAN-49 was evaluated. The other cohorts have frozen IR and could be
  run, but were out of this milestone's scope.
* Structural validity is *coherence*, not correctness against a truth grid.
  A table can be perfectly coherent and still describe the wrong page region.

## 11. No production change

**NO PRODUCTION CODE WAS CHANGED.** `src/`, `configs/`, `tests/`,
`run_benchmark.py` and `run_ab.py` are byte-identical to `271abf2`; the full
suite remains 341 passed, 10 skipped. Layer 2 lives entirely in this
directory and is wired into no scorer, gate, or pipeline. The only
production-related outcome is the intended one: **the Layer-2 evaluator is
ready to inform future production experiments.**

## 12. Decision

**ADOPT.** Layer 2 measures four dimensions Layer 1 provably cannot
distinguish, it found two real defects Layer 1 is blind to, its evaluator
passes 12/12 controls, it resists 7/7 gaming attacks, and it leaves the
historical record untouched. It becomes the standard research evaluation
contract **alongside** the frozen Layer 1, never in place of it.

## Reproducibility

| script | artifact |
| --- | --- |
| `ir_schema_inventory.py` | `ir_schema_inventory.json` |
| `table_text.py`, `table_structure.py`, `page_order.py`, `structural_integrity.py` | views (imported) |
| `layer2_evaluator.py` | `layer2_scan49.json` |
| `evaluator_controls.py` | `evaluator_controls.json` |
| `anti_gaming.py` | `anti_gaming.json` |
| `evaluation_contract.md` | the implemented contract |

Input: 025's gitignored `_runs/coverage/` and `coverage_dataset.json`,
regenerable from `coverage_instrument.py`. `_norm`, `score` and
`document_text` are **imported** from the frozen scorer, never reimplemented.
