# 039 corpus protocol

## Selected source

039 uses the official DocLayNet 1.0.0 validation source.  DocLayNet is a
human-annotated real-document layout corpus with six document categories:
financial reports, scientific articles, patents, government tenders, laws and
regulations, and manuals.  Its COCO annotations contain page-level bounding
boxes, including the `Table` class, and its image records provide
`collection`, `doc_name`, and `page_no` provenance.

The acquisition uses the official core archive URL and bounded HTTP Range
requests.  The large archive is not retained.  The annotation member and each
selected page image are hash-checked and recorded in the frozen manifest.

## Population and identity

The source-document key is `(collection, doc_name)`.  Only precedence-zero
DocLayNet annotation rows are eligible.  Candidate groups must have at least
three table-bearing validation pages.  Every 038 source-document group and
every 038 image identity is excluded before the 039 split is assigned.  Exact
source/page/image identity comparisons against 035, 036, 037, and 038 are
recorded by the pre-baseline audit.

For each remaining eligible group, up to six table-bearing pages are selected
by a stable hash of the DocLayNet image ID.  Up to three table-free pages from
the same source document are selected independently as controls.  Pages are
never cropped before the unchanged production baseline.

## Split

Groups are split, not pages.  Within each document category, groups are sorted
by:

```
SHA256("039-group-v1:" + doc_category + "::" + collection + "::" + doc_name)
```

The first `ceil(n/2)` groups in each category are development and the rest are
held-out test.  This preserves category representation where the remaining
population permits it and is deterministic before baseline extraction.

## Ground truth and coordinate space

The independent table ground truth is the DocLayNet COCO `Table` annotation,
using `[x, y, width, height]` in the supplied 1025 x 1025 PNG coordinate
space.  The baseline consumes the full PNG page.  GT geometry is used only for
post-baseline matching and outcome scoring, never for extraction decisions or
selector features.

## D2 definition

039 uses the frozen 035-compatible strict D2 definition: an independent GT
table has a relevant production layout-region match, the matched raw region
label is not `table`, and no production table object owns the match.  Matching
thresholds and the `MULTIPLE_MATCH` contributor rule are imported from the
035 `matching_lib.py` implementation.  D2 is evidence of region/crop gating
or ownership loss; it is not proof that Table Transformer was absent from the
whole page.

## Activation adequacy gate

Before baseline extraction, the minimum development activation criterion is
frozen as the conjunction of all conditions below:

1. at least 12 strict-D2 GT-table cases;
2. at least 6 distinct source-document groups containing a strict-D2 case;
3. at least 3 distinct raw region labels among those cases;
4. at least 4 DocLayNet document categories represented among those groups;
5. no single source-document group contributes more than half of development
   strict-D2 cases.

This is an operational diversity gate, not a statistical significance or
power claim.  The minimums require enough cases to compare simple policy arms
without repeating 038's six-case, two-group, one-label concentration.  If
any condition fails, 039 stops with `039_BLOCKED_NO_DEVELOPMENT_ACTIVATION`
when the count is zero or `039_BLOCKED_INSUFFICIENT_DIVERSITY` otherwise.

No relabelling, GT-driven selection, synthetic page, forced crop, or
held-out-to-development transfer can repair a failed gate.
