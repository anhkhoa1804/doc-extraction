# 026 — Table Cell Ordering

**Status: COMPLETE. Premise FALSIFIED. Decision: HOLD. No production code changed.**

Frozen baseline: `c92eb8b` (025 close), measurements taken against the 025
baseline IR produced at `0355e79` — the frozen SCAN-49 cohort, 49 documents /
112 pages / 94 tables / 1,133 cells, `text_sha`-identical to 024's frozen
`l5` arm on 49/49. Every phase here is offline: no pipeline run, no OCR, no
model, **no GPU** (the L4 was held throughout by an unrelated Research-No.1
workload and was not touched).

## Hypothesis

> **H1.** Table cells should be canonicalized by geometric row/column
> position before serialization. Assigning `row`/`col` from cell bbox
> geometry and emitting cells in that canonical order will raise structural
> integrity from 0.883 toward 1.000 and repair all four `order_ok=False`
> documents, without changing any cell's text.

## Verdict: the premise was wrong, in two separate ways

### 1. 025's "0 cells carry row_index" was a measurement artifact

The schema fields are **`row` and `col`** (`schemas/table.py`).
`row_index`/`col_index` do not exist, so 025's diagnostic — which queried
those names — read `None` on every cell and reported metadata as absent when
it was merely differently named. That statement in the 025 record is wrong
and is corrected here.

### 2. The metadata is already geometrically correct on every table

Re-measured with the real field names, over all 94 tables:

| question | result |
| --- | ---: |
| Q1 — cells **list** in geometric order? | **83 / 94** (11 out of order) |
| Q2 — `row`/`col` **values** geometrically correct? | **94 / 94** |
| degenerate bboxes | 0 |
| cells missing a bbox | 0 |
| spanning cells | 0 |

**H1's intervention is already in production.** There is nothing to
canonicalize: Table Transformer emits correct row/col, and
`_renumber_rows_by_position` (which anchors on `min(y0)`) re-sorts them when
tier-3 synthesis adds rows.

### 3. The brief's preferred anchor is falsified by the corpus

The brief proposed "preferably y-center". Measured over the same 94 tables:

| anchor | tables ordered correctly |
| --- | ---: |
| `min(y0)` — top edge | **94 / 94** |
| y-centre | 93 / 94 |

`hc_tiny_cells_vi` is the counterexample. Its row 2 is **70 px** tall against
~20 px neighbours, so its y-centre (590.0) falls *below* row 3's (581.5) and
a centre-anchored rule inverts them. The top edge orders them correctly.
Production already uses `min(y0)`.

## What is actually wrong, and who can see it

The `cells` **list** is held in Table Transformer's emission order on 11 of
94 tables. That is invisible to every production consumer, because they all
key on `(cell.row, cell.col)`:

* `Table.to_grid()` / `Table.to_markdown()` — `schemas/table.py`
* `evaluation/table_metrics.py` — `{(c.row, c.col): ...}`
* `research/experiments/_table_integrity/probe_*.py`
* `evaluation/metrics.py` — counts only

The **only** consumer that reads the raw list is
`research/production_corpus/run_benchmark.py::document_text`, the benchmark's
own flattening helper. So the defect 025 surfaced as `order_ok` lives in
**evaluation code**, not in the production table IR.

## Phase 3 — offline counterfactual

Intervention: sort each table's `cells` list by `(row, col)`. Nothing else.
Applied offline to the frozen 025 IR and re-scored with the benchmark's own
`score()` and `_norm()`, imported rather than reimplemented.

The control reproduces the 025 baseline exactly — 0.906 / 0.9803 / 35 perfect
/ 45 order_ok — which is what validates the offline harness.

| metric | control | intervention | delta |
| --- | ---: | ---: | ---: |
| tables reordered | 0 | 11 | +11 |
| mean exact recall | 0.9060 | 0.9060 | **0** |
| mean char recall | 0.9803 | 0.9801 | **−0.0002** |
| perfect documents | 35 | 35 | **0** |
| **order_ok** | **45** | **49** | **+4** |
| hallucinated | 0 | 0 | **0** |
| text multiset changed | — | **0 of 49** | — |

All 11 invariants hold on all 49 documents: cell text multiset, cell count,
table count, table bboxes, no cell created or deleted, row/col values, cell
bboxes, page element order, non-table text, declared table shape.

**All four surfaced order failures repaired. None broken.**

### The one metric that moved, and why

`char_recall` uses `difflib.SequenceMatcher` and is therefore **order
sensitive**. Exactly one document moved: `hc_tiny_cells_vi`, 0.8228 → 0.8133,
and within it exactly one string: `'Dịch vụ lắp đặt'`, 0.6000 → 0.5333.

That string was never recognised — OCR read the cell as `'Bren va tap ast'`.
Its char_recall was measuring coincidental in-order character matches spread
across the whole document, and reordering the cells changed which
coincidences difflib could chain. No evidence was lost: the text multiset is
identical, exact recall is unchanged, `order_ok` is unchanged for that
document.

It is nonetheless a **measured regression on a secondary metric**, and the
SHIP gate says "no char recall regression". It is reported, not waived.

## Phase 4 — all 11 tables individually

| document | cells | rows×cols | row/col correct | order_ok ctl→itv | char ctl→itv |
| --- | ---: | ---: | :---: | :---: | --- |
| cmb_borderless_lowcontrast_en | 16 | 4×4 | ✅ | **False→True** | 1.0→1.0 |
| hc_borderless_en | 16 | 4×4 | ✅ | **False→True** | 1.0→1.0 |
| ord_invoice_vi | 16 | 4×4 | ✅ | **False→True** | 1.0→1.0 |
| ord_purchase_order_vi | 16 | 4×4 | ✅ | **False→True** | 1.0→1.0 |
| cmb_stamp_boundary_vi | 8 | 4×2 | ✅ | True→True | 1.0→1.0 |
| cmb_tiny_table_en | 16 | 4×4 | ✅ | True→True | 0.9665→0.9665 |
| hc_encoding_vi | 10 | 5×2 | ✅ | True→True | 1.0→1.0 |
| hc_scan_vi | 4 | 2×2 | ✅ | True→True | 1.0→1.0 |
| hc_tiny_cells_vi | 16 | 4×4 | ✅ | True→True | 0.8228→**0.8133** |
| ord_financial_report_vi | 16 | 4×4 | ✅ | True→True | 0.957→0.957 |
| ord_form_en | 8 | 4×2 | ✅ | True→True | 1.0→1.0 |

4 surfaced through `order_ok`; **7 were benchmark-invisible**, confirming
025's 0.36 detection-rate finding. Every one of the 11 already carries
correct `row`/`col`.

## Phase 5 — adversarial controls

Two separable rules were tested. **RULE-B** (sort the list by existing
row/col) preserved the text multiset and was deterministic in **12/12**
cases. **RULE-A** (recover row/col from geometry alone — group by mutual
vertical overlap ≥ 0.5 of the shorter cell height, order bands by `min(y0)`,
cells by `x0`) passed **11 of 12**.

| case | RULE-A |
| --- | :---: |
| two rows, slightly different heights | ✅ |
| uneven vertical offsets in one row | ✅ |
| different row heights | ✅ |
| borderless | ✅ |
| tiny cells | ✅ |
| **tall row beside short rows** (real `hc_tiny_cells_vi` geometry) | ⚠️ **LIMITATION** |
| touching edges | ✅ |
| slight row overlap | ✅ |
| empty cells | ✅ |
| one column | ✅ |
| multi-column 4×4 | ✅ |
| irregular widths | ✅ |

**The limitation is the important result.** On the real `hc_tiny_cells_vi`
geometry, rows 1 (551.5–571.6), 2 (555.0–625.0) and 3 (571.8–591.1) overlap
so heavily that mutual-overlap clustering recovers **3 rows where the IR
declares 4**. Geometry alone is *strictly worse* than the row/col Table
Transformer already provides, because the structure model sees the image and
a bbox clusterer sees only boxes. Documented as a limitation rather than
patched with further heuristics.

**So RULE-A must not be implemented.** Implementing H1 as specified would
replace correct detector metadata with a worse geometric guess.

## Production decision: HOLD

Not SHIP, for two independent reasons:

1. **The premise is falsified.** There is no production defect. The IR
   carries correct `row`/`col` on 94/94 tables and no production consumer
   reads list order. The observable defect is in
   `run_benchmark.document_text`, which is evaluation code.
2. **The stated SHIP gate is not met.** char recall regresses by 0.0002
   corpus-wide (0.0095 on one document). Explicable, but real and measured.

Changing production `base.py` to sort the cells list would be **modifying the
system under test so the measuring instrument reads correctly** — the wrong
direction of fix. The defensible target is `document_text`, which should
serialize by `(row, col)`; but that is scorer code, frozen by standing
constraint since 024, and changing it retroactively alters every historical
score in the 023–025 record. That is a deliberate, separately-scoped decision,
not a side effect of this milestone.

Not REJECT: RULE-B demonstrably works (+4 `order_ok`, all invariants hold)
and remains available if the scorer question is ever opened.

## Limitations

* Row recovery from geometry alone fails on heavily overlapping rows; the
  detector's own row assignment is better and should be trusted.
* `char_recall` is order-sensitive by construction (difflib), so *any*
  serialization change perturbs it slightly on documents whose strings were
  not recognised. This is a property of the metric, not of the extraction.
* 79 of 94 tables have vertically overlapping row bands, mostly empty-text
  tables on `long_policy_vi_60p` and `ord_technical_report_*`. Those tables
  are probably spurious detections; that question belongs to table detection,
  which this milestone was forbidden to touch.

## Reproducibility

| artifact | produces |
| --- | --- |
| `table_ir_diagnostic.py` → `table_ir_diagnostic.json` | Q1/Q2 per table, anchor comparison |
| `counterfactual.py` → `counterfactual.json` | control vs intervention, 11 invariants |
| `adversarial.py` → `adversarial.json` | 12 synthetic cases, RULE-A and RULE-B |

Input: `experiments/025_layout_evidence_recall/_runs/coverage/` (gitignored,
regenerable via 025's `coverage_instrument.py`). Scorer and normalizer are
imported from `experiments/023_evidence_centric/run_ab.py` and
`research/production_corpus/run_benchmark.py`, never reimplemented — an
earlier reimplementation of `_norm` silently lowercased and drove control
recall to 0.0136, which is why the control is checked against the frozen 025
baseline before any comparison is believed.

**NO PRODUCTION CODE WAS CHANGED.** `src/`, `configs/` and `tests/` are
untouched; the full suite remains at 341 passed, 10 skipped.
