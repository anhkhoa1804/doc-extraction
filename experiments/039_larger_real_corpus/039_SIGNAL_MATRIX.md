# Experiment 039 signal matrix

This is a post-baseline descriptive matrix, not a frozen selector and not a
policy evaluation. The row-level comparison unit is a GT table annotation;
the control exposure counts use unique non-table layout regions on the 95
frozen non-table control pages. The matched region in a D2/non-D2 row is
selected retrospectively with GT geometry for audit, so it cannot be passed
directly to a selector.

The independent raw recomputation found 45 strict-D2 annotations out of 269:
34/152 in development and 11/117 in held-out data. There are 39 unique
layout regions behind the 45 annotations. The numeric bins below are
post-hoc descriptive summaries, not proposed thresholds.

| Candidate signal | Pre-treatment? | D2 enrichment | Cross-group stability | False-positive risk / control exposure | Mechanistic plausibility | Research value |
| --- | --- | --- | --- | --- | --- | --- |
| Raw role `document_index` | Yes, emitted by layout before treatment | 24/24 matched-role D2 annotations; 21/21 unique such regions were D2-associated | 17 development cases in 7 groups and all 6 categories; 7 descriptive held-out cases in 4 groups | 0/1,444 control non-table regions, 0 control pages; this is zero observed exposure, not a validated zero FP rate | High for an index/contents-like structured block being assigned a non-table role; it does not prove a causal role-normalization defect | Strongest candidate for a mechanism-specific study; insufficient for a universal policy |
| Raw role `code` | Yes | 4/4 matched-role D2 annotations; 4 unique D2-associated regions | 4 cases in 1 development group and 1 category (`manuals`); none held out | 3/1,444 control regions on 2 pages | Plausible for code-like structured text, but the observed signal is one-document-specific | Use as a stratified subtype, not a general rule |
| Raw role `picture` | Yes | 6/6 matched-role D2 annotations; 2 unique D2-associated regions | 6 cases in 2 development groups and 2 categories; none held out | 102/1,444 control regions on 38 pages | Plausible for tables embedded in figures or oversized figure regions | High-risk negative/control arm; do not promote |
| Raw role `list_item` | Yes | 3/3 matched-role D2 annotations; 3 unique D2-associated regions | 2 development cases in 2 groups; 1 held-out case in 1 group | 117/1,444 control regions on 21 pages | Plausible for list-shaped tables, but list morphology is common in normal prose | Low-purity subtype; requires explicit abstention/ownership study |
| Raw role `text` | Yes | 8/8 matched-role D2 annotations; 9 unique D2-associated regions when the held-out multi-match contributors are counted | 5 development cases in 4 groups/3 categories; 3 held-out cases in 2 groups | 927/1,444 control regions on 90 pages | Possible layout fragmentation, but ordinary prose dominates the same role | Broad `text` routing is scientifically rejected by the control exposure |
| `ocr_child_count == 0` | Yes, derived from baseline OCR and region center containment | 22/22 selected matched rows were D2; captures 22/44 single-region D2 rows (50.0%) | Not a role-independent signal; zero-token behavior is concentrated in large/index-like regions | 71/1,444 control regions on 29 pages | Consistent with a missing/fragmented OCR ownership path, but also with image/index pages | Worth measuring as a covariate, not using alone |
| `ocr_child_count <= 1` | Yes | 38/41 selected matched rows were D2 (92.7%); captures 38/44 single-region D2 rows (86.4%) | Cross-group stability is not enough to separate the label/family confound | 1,405/1,444 control regions on 93 pages (97.3%) | Weak as a policy signal because it is nearly ubiquitous on controls under the current OCR grouping | Strong evidence that this attractive retrospective association is unsafe |
| Region area fraction `>= 0.4` | Yes | 14/53 selected matched rows were D2; 39 were non-D2 | Not stable enough; overlaps heavily with large table regions | 4/1,444 control regions on 4 pages | Large regions can reflect merged ownership, but geometry alone is non-specific | Descriptive covariate only |
| Aspect ratio `>= 5` | Yes | 10/53 selected matched rows were D2; 43 were non-D2 | No clear cross-group separation | 803/1,444 control regions on 91 pages | Compatible with prose lines and wide tables alike | Reject as a standalone selector |
| Page region count `>= 20` | Yes | 13/31 selected matched rows were D2; 18 were non-D2 | Mostly reflects page-family complexity; FAA contributes a high-complexity cluster | 707/1,444 control regions on 24 pages | May indicate crowded ownership competition, but is not specific | Measure as interaction term only |
| Document category | Available from frozen provenance, not emitted by current production IR | Development rates range from 3/26 patents (11.5%) to 6/6 manuals (100.0%) and 10/14 laws (71.4%) | Strong category/family variation; held-out D2 occurs only in financial, government, and patents | Not a universal runtime feature unless external provenance is guaranteed | Category is a plausible proxy for document family/publisher/layout style | Stratify and report; do not treat as causal |
| Route | Yes | No contrast: all 269 records used the `image` route | No route variation in 039 | Not estimable | Route-specific effects cannot be assessed here | Instrument in future corpora |
| Layout confidence | Nominally yes, but unavailable | 0/3,210 layout regions have non-null confidence | Not estimable | Not estimable | No evidence because the field is absent | Add provenance before considering it |
| Page-level Table Transformer evidence | Potentially yes if measured before treatment | Not recorded in 039; current D2 does not distinguish page-wide detector invocation from ownership loss | Not estimable | Not estimable | This is the key unresolved production-semantics question | Mandatory instrumentation in the next study |
| Existing final ownership/table object | No; post-treatment/ownership output | D2 is defined partly by its absence or failure to own the matched region | Not valid for selector training | Not a selector input | Directly describes the defect, not a cause available before treatment | Outcome and resolver input only |

## Control-frame arithmetic

The 95 control pages contain 1,444 non-table regions with usable layout
regions; two controls have no non-table region and therefore contribute no
region to this denominator. A rule that fires on the union of the five raw
roles observed among D2 (`document_index`, `text`, `picture`, `code`, and
`list_item`) would fire on 1,149/1,444 control regions and on 92/95 control
pages. This is an exposure rate, not an observed treatment false-positive
rate, because no 039 treatment was run.

The high-purity-looking `document_index` result is different: no control
contains that role. That makes it the most defensible candidate for a focused
follow-up, but it also means the control set has no negative example with the
same role. It must be tested with an explicit ownership resolver and an
end-to-end output comparison before any policy claim.

## Structural and ownership signals

The D2 cases are not interchangeable. Twenty-three of 45 D2 rows have any
positive geometric overlap with an existing production table object; 20/45
meet a more material overlap screen (table-object IoU at least 0.1 or at
least half of the table object lies within the non-table region). Eleven D2
rows reuse one production region across multiple GT tables. These counts
overlap by design and are diagnostic, not causal labels.

The final IR type for the 45 D2 rows is `other` for 28, `image` for 6,
`list_item` for 3, `text` for 7, and one two-region `MULTIPLE_MATCH` text
case. Twenty-three rows retain non-empty text in the non-table final element;
22 retain none. Thus D2 is certainly an ownership/structural failure under
the frozen definition, but it is not evidence that all semantic text was
lost downstream.

## Interpretation

The matrix supports a mechanism-specific research arm centered on
`document_index`, plus explicit negative arms for `picture`, `text`, and
low-OCR routing. It does not support a universal selector, geometry-only
selection, or automatic treatment of every non-table role. The next design
therefore measures treatment value and ownership risk first, with page-level
detector instrumentation included to distinguish gating from whole-page
detector absence.

Source artifacts: [`039_MATCHED_COMPARISONS.json`](039_MATCHED_COMPARISONS.json),
[`039_D2_FORENSIC_CASES.json`](039_D2_FORENSIC_CASES.json),
[`population_manifest.json`](population_manifest.json),
[`population_audit.json`](population_audit.json), and the frozen 035 matcher
[`matching_lib.py`](../035_mechanism_d_gating/matching_lib.py).
