# Experiment 038 — final research report

**Status:** `038_BLOCKED_INADEQUATE_DEVELOPMENT`

## Question

Can a selective pre-treatment policy be evaluated on independent real
documents with naturally occurring Mechanism-D table-label activation?

## Frozen population and audit

The corpus is the official DocLayNet 1.0.0 validation source, using the
CDLA-Permissive-1.0 dataset license.  The frozen slice contains 149 selected
records from 20 document groups: 10 development groups and 10 held-out groups.
It contains 91 table-bearing pages with 137 independent table annotations and
58 same-document non-table control pages.  The selected images are complete
page PNGs in the frozen 1025 x 1025 coordinate space and retain source
document/page identity.  The source archive itself was not retained locally;
the annotation member and every selected image have SHA-256 verification.

The population audit found zero missing images, zero image-hash mismatches,
and zero annotation-link mismatches.  The manifest split and hash-ranked group
order reproduced exactly.

## Unchanged production baseline

The baseline ran against the unchanged production pipeline on CPU because the
NVIDIA driver was unavailable.  All 149 records completed, with zero pipeline
errors.  The baseline index records 5,788.990659 seconds of per-run metadata
runtime; one resumed first record has no per-run runtime field in the index.
No forced-crop or policy treatment was invoked.

Pre-treatment matching produced:

| Quantity | Count |
|---|---:|
| table annotations analyzed | 137 |
| exact matches | 118 |
| good matches | 3 |
| partial matches | 6 |
| no-region matches | 10 |
| strict D2 cases, all | 18 |
| strict D2 cases, development | 6 |
| strict D2 cases, held-out (descriptive only) | 12 |

The all-corpus strict-D2 wrong-label counts were `document_index=10`,
`list_item=1`, `text=3`, `picture=3`, and `section_header=1`.  The six
development cases came from only two source-document groups, with the single
raw label `document_index`; five of the six came from one group.

## Decision

Natural development activation exists, so this is not a zero-trigger result.
However, six cases across two source groups and one raw-label category are
insufficient to assess document-group-generalized selectivity or compare the
preregistered policy families defensibly.  The experiment therefore stops at
baseline activation with status `038_BLOCKED_INADEQUATE_DEVELOPMENT`.

No selector was tuned or frozen.  No forced-crop counterfactual was run.  No
held-out policy evaluation, recovery estimate, false-positive estimate, or
production recommendation is claimed.  The 12 held-out D2 cases remain
reserved and untouched.

As in 035/036, a D2 case is evidence of a region/crop gating or ownership
loss.  It is not proof that Table Transformer was absent from the whole page.

## Limitations

This acquisition retains selected full-page contexts and source-document
grouping, not every page of each source document as a locally retained
multi-page corpus.  The archive hash is unavailable because the 28 GiB archive
was intentionally not retained.  These limitations are recorded rather than
silently upgraded into claims of a full-document archive.

## Evidence

- `population_manifest.json` — frozen source/page/table identity list.
- `population_audit.json` — independent manifest/image/annotation audit.
- `baseline_run_index.json` — ignored raw-run index and resume ledger.
- `baseline_analysis.json` — pre-treatment matching and activation analysis.
- `run_baseline.py` — resumable unchanged-baseline runner.
- `analyze_baseline.py` — 035-compatible pre-treatment analyzer.
