# Layer-2 evaluation contract — as implemented

**Status: IMPLEMENTED as a research instrument. Not wired into any scorer,
gate, or production path. Layer 1 is executed unchanged.**

Supersedes the *proposal* in `experiments/027_evaluation_serialization/evaluation_contract.md`
by making it concrete. Where 027 guessed at a metric, this file records what
was actually built and what it can and cannot measure.

## Layer 1 — LEGACY, frozen

`run_benchmark.document_text` + `run_ab.score`, byte-identical at
`b69d85dc1a2d3438…` / `26332fe14748b464…`. Executed unchanged in
`layer2_evaluator.py` on the real pydantic objects. Never replaced, never
rewritten, never rebaselined.

## Layer 2 — STRUCTURAL, additive

Four views over the real IR (`ir_schema_inventory.json` pins every field
used; nothing is invented).

### `table_text` — text, decoupled from document flattening

Per table: the legacy cell sequence, the canonical `(row, col)` sequence, and
both joined strings. Uses `Table.id`, `Cell.row`, `Cell.col`, `Cell.text`.
Normalization is the frozen `_norm`, imported — Layer 1 and Layer 2 must
agree on what a string *is* even where they disagree on ordering.

Also exposes `non_table_text(doc)`, the half of a document whose ordering is
genuinely a page-reading-order question.

### `table_structure` — structure as data, not as a string

Declared vs observed shape, `(row, col)` assignments, duplicate coordinates,
empty and header cells, spanning cells, table and cell bboxes, and how many
cells fall inside their table's box. `row_span`/`col_span` are read because
the IR has them; whether any backend sets them above 1 is reported as an
observation (on SCAN-49: **0 tables**), not assumed.

### `page_order_ok` — ordering without table text

Scores required-string ordering over **non-table elements only**, walked in
production's own `Page.reading_order` (with `Document.to_markdown`'s
documented fallback to list order reproduced, not replaced).

A `must_contain` string that lives inside a table is reported
**UNMEASURABLE**, with a reason, rather than assigned a position. On SCAN-49
that is **63 strings across 22 documents** — a third of the corpus's required
strings are table content and simply cannot be page-ordered. Layer 1 gave all
63 a position anyway, which is how `order_ok` came to mean two things.

### `table_structural_integrity` — coherence, not sortedness

Eight independent checks: coordinates within declared range, no duplicate
`(row, col)`, contiguous rows, contiguous cols, row order matching geometry,
col order matching geometry, valid cell bboxes, cells inside the table bbox,
plus **row/col band coherence** (cells sharing a coordinate must occupy a
common band).

`list_order_canonical` is reported **separately and is explicitly not part of
the verdict** — a table stored tidily can still be incoherent, and 026's use
of storage order as "structural integrity" conflated the two.

## Per-table status vector (Phase 5)

Four dimensions, never collapsed into one score:

| dimension | source | SCAN-49 |
| --- | --- | --- |
| **TEXT** | per-cell ground truth | **UNMEASURABLE** — the corpus carries document-level `must_contain` only |
| **STRUCTURE** | `table_structural_integrity` | VALID 90 / INVALID 4 |
| **OWNERSHIP** | 025 token data (`n_owners`) | CLEAN 94 |
| **ORDER** | `list_order_canonical` | CANONICAL 83 / NON_CANONICAL 11 |

`UNMEASURABLE` is a first-class value. A proxy was not manufactured for TEXT.

## Anti-gaming invariants (documented, tested)

1. Sorting a cell list changes ORDER only, never TEXT.
2. Duplicating a cell is caught by `no_duplicate_coordinates` — never rewarded.
3. Deleting a hard cell is visible as a cell-count drop — never rewarded.
4. Moving geometry damages STRUCTURE and leaves TEXT untouched.
5. Collapsing a table into one cell is visible as a shape change.
6. Relabelling `row`/`col` to fake canonical storage order is caught by band
   coherence.
7. TEXT is `UNMEASURABLE`, so no transformation can improve a score that does
   not exist.

All seven verified in `anti_gaming.json`; **no attack was rewarded**.

## Reporting rule

Report both layers, always. A conclusion holding in one and not the other is
a finding to explain, not a number to choose between.

## Out of scope

No change to `document_text`, `score`, `char_recall`, `order_ok`,
normalization, the production IR, or any production code. `cell_grid_accuracy`
from the 027 proposal is **not implemented**: it needs per-table ground truth
the corpus does not carry, and inventing one would have violated the contract
this milestone exists to establish.
