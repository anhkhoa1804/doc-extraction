# 046 — independent corpus challenge protocol v2

## Version note

Protocol v1's runner compared raw acquisition text to normalized baseline text
when assigning only the `canonical_exact_present` loss-taxonomy input. This
misclassified raw-case/whitespace-preserving duplicates as normalization loss.
It did not change the normalized duplicate or primary novelty predicates, but
the entire unchanged population is rerun under v2. V1 is retained as an
immutable invalid-for-boundary-reporting artifact; v2 is the sole primary run.

## Question

On source-document-disjoint OmniDocBench records, does acquisition-time
observation capture expose truth-correct textual evidence absent from the
current canonical output?

## Population and independence

`build_manifest.py` selects 24 records without reading extraction results:
three predeclared controls and three text-annotated cases for each of seven
document-source types. Every case is a distinct filename-derived document
group. UUID-only `page-...` images are excluded because this snapshot does not
provide enough information to establish their document group. All groups that
contain a table page in the historical 035 population are excluded, as are any
exact image hashes or benchmark records in 044/045 (which descend from 035).

The corpus is an independent source-document partition within the checked-in
OmniDocBench snapshot, not a claim of an independent benchmark release.

## Conditions

`A` is the uninstrumented current scanned-page pipeline. `B` is the identical
pipeline with opt-in `ObservationLedger` capture immediately after
`LayoutResult`, `OCRResult`, and `TableResult` return, and before cell fill,
region merge, canonical Page/Document projection, and Markdown serialization.
No recovery/treatment condition is permitted.

Canonical page JSON must be equal after deterministic model serialization. A
mismatch is an instrumentation defect and invalidates the run.

## Truth and matching

Each case has one OmniDocBench non-table `text_block` or `title` annotation
with its annotated text and polygon-derived rectangle. Candidate observations
are acquisition-stage OCR tokens whose geometry centre lies in that rectangle.
Truth correctness is `normalize_text(candidate) == normalize_text(truth)`.
This is deliberately strict: partial phrase overlap and visual plausibility do
not establish correctness.

Baseline presence uses the frozen 044/045 normalized exact phrase rule at the
same truth locator: an observation is duplicate if its normalized text occurs
as a phrase in a baseline canonical element/cell whose centre is in the truth
rectangle. Its text is baseline-missing otherwise.

## Endpoint and ownership

`novel_correct_acquisition_evidence` requires all of: acquisition capture,
text, strict truth correctness, accepted/unique ownership in the reconciled
ledger view, baseline absence at the truth locator, and a reconciled record
with an acquisition derivation. Ambiguous ownership, missing provenance,
unverified text, duplicate baseline text, and empty structure do not count.

## Loss taxonomy

The frozen `classify_loss_boundary` taxonomy is used: `normalization` for raw
phrase absent but normalized canonical phrase present; `ownership` for no
canonical phrase with competing claims; `canonical_projection` for no
canonical phrase without competing claims; `serialization` for canonical
phrase present but Markdown absent. `acquisition`, `reconciliation`, and
`unknown` are assigned only with direct evidence; absence is never invented.

## Decision

With exact A/B equivalence and zero control novelty: zero primary endpoint is
the preregistered strong null, **OBSERVABILITY SUPPORTED; ACQUISITION-TIME
QUALITY THESIS NOT SUPPORTED**. One case is a weak signal only. Multiple valid
cases across source groups are required for next-stage mechanistic support.
