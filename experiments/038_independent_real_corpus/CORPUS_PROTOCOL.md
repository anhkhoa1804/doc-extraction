# 038 corpus protocol

## Source and license

038 uses the validation split of DocLayNet, an independently human-annotated
real-document layout corpus.  The frozen source is the official
`ds4sd/DocLayNet` 1.0.0 core archive (CDLA-Permissive-1.0), whose validation
COCO member contains 6,489 full-page PNG records and table boxes.  The archive
is 28 GiB; acquisition downloads only the validation annotation member and
selected PNG members using HTTP Range requests.  The acquisition URL, member
hashes, and code are recorded by `acquire_doclaynet.py`.

## Unit and identity

The source-document unit is `(collection, doc_name)`.  `doc_name` and
`page_no` are supplied by DocLayNet, not inferred from image filenames.
Repeated annotation records are restricted to `precedence == 0`; redundant
precedence records are not mixed into the population.  Each selected page
retains its COCO image ID, source document group, page number, source PNG hash,
and all independent table annotations.

## Inclusion and exclusions

Candidate groups have at least three table-bearing validation pages, are not
represented in 035/036 identity manifests, and have no duplicate image ID.
For every selected group, up to five table-bearing pages and up to three
non-table pages are selected by a deterministic page-number rule.  Non-table
pages are controls only; a table-bearing page may also provide non-table
layout-region controls after baseline matching.  No table-only crops are used
as the headline corpus.

## Split and freeze

Groups are ranked by `SHA256("038-split-v1:" + collection + "::" + doc_name)`.
The first 10 groups are development and the next 10 are held-out test.  No
group can occur in both.  The exact page and table identity list is frozen in
`population_manifest.json` before any policy outcome or counterfactual call.

## Coordinate contract

DocLayNet COCO boxes are `[x,y,width,height]` in the 1025x1025 PNG coordinate
space.  The production baseline consumes those exact PNGs without resizing by
this experiment.  All GT comparisons use half-open geometric rectangles in
that same space; conversion to the repository `BBox` is explicit and recorded.

## Activation gate

After the unchanged production baseline, compute total documents/pages/tables,
development and held-out table counts, and naturally occurring D2-like cases:
a GT table with a relevant production layout region whose raw label is not
`table`.  If development D2-like cases are zero, status is
`038_BLOCKED_NO_DEVELOPMENT_ACTIVATION`; no selector or counterfactual is run.
If positive but too small for defensible development policy selection, status
is `038_BLOCKED_INADEQUATE_DEVELOPMENT`.  A positive count alone is not a
license to tune on held-out pages.
