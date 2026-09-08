# Proposed evaluation contract — two layers, versioned

**Status: PROPOSED. Nothing here is implemented. The frozen scorer is not modified.**

## The problem this solves

One flattened string, `document_text`, is currently the proxy for at least
five independent properties: whether evidence was extracted, how accurately,
in what order, whether it was duplicated, and whether the table structure
survived. Metrics computed from it therefore interfere with each other. Three
measured consequences:

* **`order_ok` conflates two properties.** 56.1% of all its failures across
  28 replayed arms are table cell emission order, not page reading order. On
  the SCAN-49 family it is 4 of 4 — the metric measured nothing else there.
* **`char_recall` is sequence-sensitive** (difflib in-order matching blocks),
  so any serialization change perturbs it. On `hc_tiny_cells_vi` the same
  reordering moves it **up** 0.0102 in 023's arms and **down** 0.0095 in
  024/025's. Same document, opposite signs, no evidence changed.
* **Structural damage is mostly invisible.** 11 of 94 tables hold cells out
  of geometric order; 4 documents surface. Detection rate 0.36.

## Layer 1 — LEGACY (frozen, never changed)

`run_benchmark.document_text` + `run_ab.score` exactly as they are at
`c92eb8b`. Hashes recorded in `scorer_audit.json`.

Purpose: historical comparability for 023–026. Every number in those
milestones' write-ups is reproducible from it forever. It is not deprecated
and not "wrong to have used"; it is a text-recall instrument that also
happens to be sensitive to serialization, which nobody had measured until now.

## Layer 2 — STRUCTURAL (new, additive)

Never replaces Layer 1. Reported alongside it.

### Representations, replacing one string with four

| name | definition | what it is for |
| --- | --- | --- |
| `document_text_flat` | today's serializer, unchanged | Layer 1 compatibility |
| `table_text` | table cell text serialized in `(row, col)` order | text recall unpolluted by detector emission order |
| `table_structure` | the `(row, col) -> text` mapping itself | structure, compared without any flattening |
| `cell_sequence` | canonical cell order per table | the object `order_ok` should have been reading |

Non-table text is identical in all four; only tables are represented
differently.

### Metrics

| metric | definition | replaces / adds |
| --- | --- | --- |
| `page_order_ok` | required-string positions non-decreasing in **non-table** text | the half of `order_ok` that is genuinely page reading order |
| `table_structural_integrity` | fraction of tables whose stored cell list is in canonical `(row, col)` order | the 11/94 defect, measured directly instead of inferred from 4 documents |
| `cell_grid_accuracy` | `(row, col) -> text` agreement against ground truth where a table has one | structure without approximate string matching |
| `evidence_coverage` | tokens claimed by exactly one region | from 025; serializer-invariant |
| `evidence_duplication` | token emissions minus tokens owned by ≥1 region | from 025; serializer-invariant |

`exact_recall` and `char_recall` stay as they are, in Layer 1, and are
reported as text metrics only — not as structure metrics. `tables_ok` is
already serializer-invariant and needs no change.

## Reporting rule

Future experiments report **both layers**. A conclusion that holds in Layer 1
and not in Layer 2, or vice versa, is a finding to explain rather than a
number to pick between.

## Rebaselining

**Not required, and not recommended.** The replay shows every headline delta
in 023, 024 and 025 is unchanged under the counterfactual: L5's +0.0136 exact
and +2 perfect documents on SCAN-49, its +0.0068 on the adaptive router,
025's all-zero `gap_region` result, and 023's +0.2741 Tesseract-over-EasyOCR
finding all survive intact. Two secondary deltas in one 023 comparison move
(`char_recall` 0.0138 → 0.0136, `order_ok` 1 → 0). Rewriting the historical
record to chase those would cost more than it buys.

What should be added instead is a one-line annotation to 023–026: *"`order_ok`
under the frozen serializer is partly sensitive to table cell emission order;
see 027."*

## Explicitly out of scope

Changing `document_text`, `score`, `char_recall`, `order_ok`, normalization,
or any production code. Layer 2 is new surface, added beside the frozen
instrument, never on top of it.
