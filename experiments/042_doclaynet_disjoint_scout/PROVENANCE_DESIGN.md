# 042 baseline specialist-provenance design

Run only after the 042 scout population is acquired and frozen. This is an
unchanged baseline replay, not treatment.

For every selected development page, use the validated additive telemetry and
record separate counts of:

* `PAGE_WIDE`: no table-labelled region supplied; TableTransformer's detector
  runs over the page;
* `LABELLED_CROP`: at least one naturally table-labelled region supplied;
* `NOT_INVOKED`: backend unavailable, no image, or another explicit
  non-invocation reason.

The page-level result reports `PAGE_WIDE`, `LABELLED_CROP`, both, or neither.
It also retains specialist calls, detector boxes/scores, structure results,
ownership events, final table objects, reading order, serialization hash,
warnings, errors, and timing.

The replay includes new `document_index` candidates, non-document-index
regions, table-bearing pages where naturally present, pages without table
objects, and a small deterministic subset of known 039 development D2 pages
where technically justified. No 039 held-out page is accessed.

No mode is inferred from D2 status. Page-wide detection is not correct
ownership and neither is evidence recall.
