# 045 — acquisition-time observation capture results

## Decision

`OBSERVABILITY ONLY; ACQUISITION-TIME QUALITY BENEFIT UNPROVEN`

This is a direct current-pipeline acquisition experiment. It does not use
persisted layout/OCR/table artifacts as B observations. It does not establish
that Docling's private internal object graph is captured; the capture boundary
is the earliest common public component-result boundary.

## Boundary and conditions

In `src/doc_extraction/pipelines/base.py`, B captures returned
`LayoutResult`, `OCRResult`, and raw `TableResult` immediately after backend
invocation and before `_fill_table_cell_text` or `merge_regions_into_page`.
The latter is the first canonical page projection. Thus B retains raw OCR
text-region observations, raw layout roles/geometry, and table candidates
before the pipeline mutates cell text from OCR evidence. The post-merge
ledger is a separate reconciliation view.

A ran the uninstrumented current scanned-page pipeline. B ran the identical
pipeline with the opt-in ledger. All ten B raw conversions were executed
directly from frozen image inputs on CPU. No recovery condition C ran.

## Population and truth

The frozen ten-case 044-v2 development population was reused unchanged:
`d2-00` … `d2-07`, `ctl-00`, `ctl-01`; population SHA-256 is
`9323fc61c75dfa211c0c818d2747b226ef12a3a2cdc3098a50c54be1c87b5c25`.
OmniDocBench HTML cells plus GT table rectangles remain the independent truth
source, under 044's normalized-exact rule. No held-out input was read.

## Per-case accounting

`baseline` is locator-scoped duplicate baseline evidence. `lost` is an
acquisition token absent from canonical baseline text at that locator.

| case | acquisition obs | baseline | truth-correct | lost | duplicate | conflicts | provenance | loss boundary | novel-correct |
|---|---:|---:|---:|---:|---:|---:|---|---|---:|
| d2-00 | 11 | 1 | 0 | 0 | 1 | 1 | complete | none | 0 |
| d2-01 | 34 | 14 | 6 | 0 | 14 | 14 | complete | none | 0 |
| d2-02 | 123 | 2 | 0 | 0 | 2 | 2 | complete | none | 0 |
| d2-03 | 123 | 2 | 0 | 0 | 2 | 2 | complete | none | 0 |
| d2-04 | 75 | 1 | 0 | 0 | 1 | 1 | complete | none | 0 |
| d2-05 | 300 | 49 | 16 | 0 | 49 | 48 | complete | none | 0 |
| d2-06 | 96 | 1 | 0 | 0 | 1 | 0 | complete | none | 0 |
| d2-07 | 120 | 0 | 0 | 0 | 0 | 0 | complete | none | 0 |
| ctl-00 | 55 | 5 | 1 | 1 | 5 | 5 | complete | canonical projection | 0 |
| ctl-01 | 55 | 6 | 1 | 0 | 6 | 6 | complete | none | 0 |

The sole baseline-missing token (`ctl-00`, `ps>5oookPa qsik = 100`) is not
cell-exact truth, so it is not positive evidence and does not produce a
control false positive.

## Aggregate results

- Acquisition observations: 992
- Candidate OCR observations inside GT table locators: 82
- Truth-correct: 24
- Baseline-missing: 1
- Novel-correct textual evidence: **0**
- Duplicate baseline evidence: 81
- Ownership conflicts / unresolved: 79 / 79
- Provenance-complete cases: 10 / 10
- Loss taxonomy: acquisition 0; normalization 0; ownership 0;
  reconciliation 0; canonical projection 1; serialization 0; unknown 0.

The lower candidate count than frozen 044 is an outcome of directly rerunning
the current CPU stack, not a redefinition or alteration of 044's frozen
result. Per-case counts for `d2-02`/`d2-03` intentionally reuse one source
page for separate GT table locators and are not independent-source estimates.

## Canonical equivalence and controls

Canonical A and B pages were exactly equal for **10 / 10** cases. The two
controls produced zero novel-correct evidence (0 / 2 false-positive cases).

## Negative finding

Acquisition-time capture works and preserves a pre-projection view, including
raw table candidates before OCR cell filling. However, among truth-supported
OCR evidence, every usable item was already represented by canonical A under
the frozen locator-aware rule. The one canonical-projection loss was
truth-incorrect. Therefore there is no correctly owned, provenance-complete,
baseline-missing textual observation to justify bounded recovery C.

Machine-readable artifact:
`runs/2026-10-01_protocol-v1_acquisition_capture-v2.json`, generated at
implementation commit `09638adf62122fcf9d85fc0c710800f33c22be83`.
