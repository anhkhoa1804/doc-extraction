# Experiment 039 forensic analysis

## Executive conclusion

039 clears the frozen activation gate and establishes that natural strict-D2
activation is not a 038-style zero or one-family artifact: 34/152 development
GT-table annotations are strict D2, spanning 11 source-document groups, five
raw labels, and all six represented DocLayNet categories. The result still
does not justify a universal selector or a transfer of the 036 50% recovery
rate. The raw cases split into high-overlap wrong-role ownership, shared or
fragmented region ownership, and weak partial matches; 23/45 D2 rows overlap
some production table object and 11/45 reuse one region for multiple GT
tables. The strongest next step is an instrumented, development-only
per-region counterfactual that measures treatment value and ownership risk,
with `document_index` as a mechanism-specific candidate and the other roles
as explicit negative/control arms. No selector should be tuned and no
held-out policy evaluation should begin until that design is frozen and
page-level specialist invocation is observable.

## Verified facts

### Population and raw integrity

The frozen 039 population remains unchanged:

| Quantity | Verified value |
| --- | ---: |
| Manifest records | 269 |
| Local PNGs | 269 |
| Source-document groups | 33 |
| Development / held-out groups | 17 / 16 |
| Table pages / non-table controls | 174 / 95 |
| Development / held-out pages | 136 / 133 |
| Manifest SHA-256 | `55fe36b5f39e1e87437f81ed2cc2d120e5c7d747b1f3109318b06d530b50f8e5` |
| Annotation-member SHA-256 | `eacd2ba2a32e6c2ebe2dc5ea1545f405d8461c46bba53e0c35d9c54fba0bcef6` |
| Population audit | `population_audited`, zero integrity errors |

The unchanged CPU baseline completed all 269 records with zero baseline
failures. All records used the `image` route, Docling layout/OCR, and the
Table Transformer table backend. The raw metadata reports CPU execution and
`torch 2.14.0+cpu`; the 039 run index and every required per-record artifact
are present. The baseline produced 3,210 layout regions and 241 production
table objects. These counts are descriptive outputs, not table recall scores.

The independent forensic pass recomputed matching directly from the raw
layout and final JSON using the frozen 035 [`matching_lib.py`](../035_mechanism_d_gating/matching_lib.py).
It did not import the existing `baseline_analysis.json` to make the verdict.
The strict-D2 identity set agrees with the existing analyzer exactly: 45
cases, with 34 development and 11 held-out descriptive cases.

### Frozen matching results

| 035-compatible verdict | GT-table annotations |
| --- | ---: |
| `EXACT_MATCH` | 204 |
| `GOOD_MATCH` | 9 |
| `PARTIAL_MATCH` | 45 |
| `MULTIPLE_MATCH` | 2 |
| `NO_REGION` | 9 |
| `AMBIGUOUS` | 0 |
| Total | 269 |

Strict D2 is 45/269 (16.73%) overall, 34/152 (22.37%) in development, and
11/117 (9.40%) in held-out data. The D2 definition remains the frozen
region/ownership definition: a relevant GT table matches a non-`table` raw
region and the matched region has no production table owner, with the frozen
035 contributor rule for `MULTIPLE_MATCH`. This is evidence of region/crop
gating or ownership loss. It is not proof that page-level Table Transformer
detection was absent.

## D2 taxonomy

The per-case assignment is a forensic classification of observed structure,
not a causal label. Full case-level geometry, ownership, OCR, warnings,
provenance, and assignment caveats are in
[`039_D2_FORENSIC_CASES.json`](039_D2_FORENSIC_CASES.json); the compact
classification is in [`039_D2_TAXONOMY.json`](039_D2_TAXONOMY.json).

| Primary mechanism candidate | D2 rows | What is directly observed | Confidence boundary |
| --- | ---: | --- | --- |
| Table object present but not correctly attached | 16 | A material-overlap table object exists near a relevant non-table region, but that region's final IR element has no table owner | Ownership interpretation is strong; whether the overlap is the intended table object is not always proven |
| Cross-table contamination / shared region | 11 | One layout region is matched to multiple GT tables on the same page | Directly supports shared ownership risk; does not prove the upstream cause |
| Partial non-table ownership | 10 | The best non-table region covers only part of the GT table under the frozen geometry | Direct geometry; “partial ownership” is a mechanism candidate, not a causal explanation |
| Wrong-role ownership | 7 | High-overlap non-table region has a raw role such as `document_index` or `code` and no material nearby table object | Strong role mismatch observation; role-normalization causality remains unproven |
| Multi-region ownership fragmentation | 1 | A held-out GT table satisfies the frozen `MULTIPLE_MATCH` contributor rule with two non-table text regions | Directly supports fragmentation; treatment value is unknown |

These primary labels are intentionally not mutually causal. A case can be a
wrong-role case and also have a nearby table object, or be a shared-region
case with an oversized geometry. For example:

* Image `717` / GT table `9249` is an `EXACT_MATCH` to a
  `document_index` region (IoU 0.9749), with zero OCR child tokens and two
  nearby table objects. The raw page visibly resembles a contents/index page
  with dotted leaders. The table-like structure was assigned to `other`, not
  a table owner.
* Image `3381` contains five D2 GT tables. All five are matched to the same
  oversized `picture` region, with 92 OCR child tokens and no production table
  object. This is a direct shared-region/figure-boundary risk, not five
  independent examples.
* Image `3741` contains four D2 GT tables assigned through two
  `document_index` regions. Nearby table objects overlap those regions
  materially, so the page demonstrates both role mismatch and ownership
  ambiguity.
* Held-out image `1082` is the one strict-D2 `MULTIPLE_MATCH` case: two
  non-table `text` contributors cover the GT table under the frozen union
  rule. It has no production table object.

### No-region and warning cases

The nine `NO_REGION` annotations are near-D2 evidence but are not strict D2:
eight are in development and one is held out. They indicate an upstream
layout matching miss, not a table-gate case. They should not be fed into a
selector as positive D2 labels.

Ten of the 45 D2 rows carry a warning: five synthesized table rows, two
“structure recognition found no row/column grid” warnings, one two-row
synthesis warning, and one suspicious verification warning. Thirty-five D2
rows have no warning. No D2 row has a fallback or ownership warning. Warning
co-occurrence is therefore a useful telemetry field but does not explain the
D2 outcome.

## D2 vs non-D2

### Role and category distributions

The raw D2-role counts are:

| Raw label | All D2 | Development | Held-out descriptive |
| --- | ---: | ---: | ---: |
| `document_index` | 24 | 17 | 7 |
| `text` | 8 | 5 | 3 |
| `picture` | 6 | 6 | 0 |
| `code` | 4 | 4 | 0 |
| `list_item` | 3 | 2 | 1 |

The D2 role is not a generic “non-table” label effect. The role distribution
is highly heterogeneous. `document_index` spans 11 groups and all six
categories across the full D2 set, but `code` is four cases from one manuals
document, `picture` is six cases from two groups, and `list_item` is three
cases from three groups. `text` is common in normal pages and cannot be
treated as a safe trigger.

All non-table roles that are selected as the GT-matched region are D2 under
the strict definition in this corpus. That 100% conditional result is not a
deployable precision estimate: the region was selected retrospectively using
GT geometry. The proper control-frame exposure is below.

Development D2 by category is:

| Category | Development D2 / annotations | Held-out D2 / annotations |
| --- | ---: | ---: |
| Financial reports | 6/71 (8.5%) | 3/54 (5.6%) |
| Government tenders | 5/24 (20.8%) | 7/18 (38.9%) |
| Laws and regulations | 10/14 (71.4%) | 0/6 (0.0%) |
| Manuals | 6/6 (100.0%) | no held-out group |
| Patents | 3/26 (11.5%) | 1/29 (3.4%) |
| Scientific articles | 4/11 (36.4%) | 0/10 (0.0%) |

The category differences are large and the small manuals denominator is
especially unstable. Category is a provenance feature in the frozen manifest,
but it is not emitted by current production metadata; using it operationally
would require an external metadata contract and would risk becoming a
publisher/family proxy.

### Geometry, OCR, and page complexity

The comparison below uses one retrospectively matched region per annotation
where available (44 D2 and 214 non-D2 rows). It is descriptive, not selector
validation.

| Feature | D2 median (range) | Non-D2 median (range) | Interpretation |
| --- | --- | --- | --- |
| Matched-region area / page area | 0.273 (0.0005–0.693) | 0.143 (0.0079–0.701) | D2 is somewhat larger on average but heavily overlaps |
| Aspect ratio | 1.918 (0.467–39.252) | 2.808 (0.854–16.638) | No clean separation; wide prose is common in non-D2 |
| Page region count | 7.5 (1–100) | 9 (1–50) | D2 mean is higher because of complex outliers, not a stable boundary |
| OCR child tokens in matched region | 0.5 (0–92) | 17.5 (1–321) | Low OCR ownership is associated with D2, but is very common on controls |
| OCR child characters | 3.5 (0–1,436) | 197 (3–2,267) | Same caveat; Docling token confidence is null throughout |
| Existing page table objects | 1 (0–2) | 1 (0–5) | D2 is not equivalent to a page with no table object |

The retrospective bins make the conflict clear. `ocr_child_count == 0`
selects 22/44 D2 rows and 0/214 non-D2 matched rows, but it also selects
71/1,444 control regions on 29 pages. `ocr_child_count <= 1` selects 38/44
D2 rows but 1,405/1,444 control regions. Geometry-only bins are weak:
`region_area_fraction >= 0.4` selects 14 D2 and 39 non-D2 rows, while
`page_region_count >= 20` selects 13 D2 and 18 non-D2 rows. These are
post-baseline descriptive bins, not proposed policy thresholds.

### Label confounding and group stability

The apparent `document_index` signal is the most interesting pre-treatment
finding. There are 21 unique non-table `document_index` regions in the 039
baseline, all 21 associated with at least one strict-D2 annotation; they
produce 24 D2 annotation rows because some regions cover more than one GT
table. No one of the 1,444 non-table control regions is labelled
`document_index`. Across development, the role appears in 17 D2 rows from
seven groups and all six categories; held-out descriptive activation adds
seven rows from four groups and two categories.

This is evidence of a potentially useful role-specific signal, not proof that
`document_index` causes D2 or that a document-index rule will remain pure in a
new corpus. There are no same-role negative controls in the frozen controls,
and the role itself may encode a page-family/layout decision. The signal
should therefore be tested as a mechanism-specific arm, not used to justify
all non-table treatment.

The other roles are visibly confounded:

* `code`: 4/4 D2 cases from one manuals source group, with 3 control code
  regions on two pages. A raw-code rule is not cross-document evidence.
* `picture`: 6/6 D2 cases, but only two unique D2 regions and 102 picture
  control regions on 38 pages. The five-table `picture` page is a major
  multiplicity effect.
* `list_item`: 3 D2 cases versus 117 control list-item regions on 21 pages.
* `text`: 8 D2 cases versus 927 control text regions on 90 pages.

The union of all five observed D2 labels would fire on 1,149/1,444 control
non-table regions and 92/95 control pages. This does not measure a treatment
false-positive rate because 039 treatment was not run; it does show that a
universal role union is operationally indefensible.

### Telemetry limitations

All 269 pages used the same `image` route, so route effects are not
estimable. All 3,210 layout-region confidences are null, and all 8,917 OCR
token confidences are null. The current output does not record a normalized
role separate from the raw label; the analysis derives lowercase normalization
only. Region `source_id` is also null in the raw layout artifacts.

Most importantly, the table backend records the number of output tables but
not whether it used a supplied table-labelled crop or page-wide detection,
which detector boxes were produced, or how those boxes were associated with
regions. Because the backend can run page-wide detection when no table crop is
supplied, this missing field prevents the analysis from distinguishing:

1. page-wide Table Transformer detection never finding the table;
2. page-wide detection finding it but the output losing ownership; and
3. a non-table region being supplied/used in a way that prevented expected
   table ownership.

The D2 definition remains valid as an ownership/gating outcome, but causal
interpretation is bounded by this telemetry gap.

## Development adequacy

The frozen criterion is passed exactly:

| Criterion | Required | Observed | Result |
| --- | ---: | ---: | --- |
| Development strict-D2 cases | >=12 | 34 | Pass |
| Development source groups | >=6 | 11 | Pass |
| Development raw labels | >=3 | 5 | Pass |
| Development categories | >=4 | 6 | Pass |
| Largest group fraction | <=50% | 10/34 = 29.4% | Pass |

039 status is therefore **`039_READY_FOR_POLICY_DESIGN`**. This is a formal
activation status, not evidence that a policy is safe or that the cases are
independent identically distributed observations.

The deeper diversity assessment is more qualified. Development has 34 D2
annotation rows, 26 source pages, and 28 unique matched layout regions. Nine
development rows are part of shared-region reuse. One FAA source group
contributes 10/34 rows, although it remains below the frozen 50% rule; five
of those rows come from one `picture` region and four from two `document_index`
regions. The 10 rows are therefore not ten independent mechanism instances.

Held-out D2 is 11 rows from nine pages and six groups. It contains D2 in only
financial reports, government tenders, and patents; laws, scientific articles,
and manuals have no held-out D2 activation, although the held-out population
does contain pages in some of those categories. This makes held-out data
useful descriptive evidence, but not a complete category-balanced test of a
universal policy.

## Pre-treatment selectability

The strongest evidence for pre-treatment selectability is role-based:
`document_index` is emitted before table treatment, appears across seven
development groups and six categories, and has zero observed control exposure.
The second candidate is low OCR child count, but its apparent enrichment
collapses on the 1,444-region control frame. Geometry is weak and overlapping.
Category is potentially useful for stratification but is not a general
runtime feature; route and confidence provide no variation.

The following distinction must remain explicit:

| Field | Status for a future selector |
| --- | --- |
| Raw region role / lowercase normalized role | `PRE_TREATMENT = valid` |
| Region bbox geometry, area fraction, aspect ratio, index | `PRE_TREATMENT = valid` |
| Page region count and OCR child count | `PRE_TREATMENT = valid`, but current grouping is a weak/noisy signal |
| Route, backend/model identity, external category | `PRE_TREATMENT = valid` only where a stable metadata contract exists |
| Independently instrumented page-level detector evidence | `PRE_TREATMENT = valid` if collected before selector treatment and not used to mutate baseline |
| GT bbox/table identity or strict-D2 label | `POST_TREATMENT = forbidden` |
| Forced-crop detector/structure result | `POST_TREATMENT = forbidden` |
| Final ownership, conflict, table-cell structure, held-out outcome | `POST_TREATMENT = forbidden` |

The “matched region” used in this report is a retrospective GT-selected audit
anchor. A future selector must score each candidate region independently from
pre-treatment fields; it cannot assume the GT-matched region is known.

## False-positive risk

The 95 control pages are valuable because their ordinary non-table content
contains many of the labels that appear in D2. Representative raw pages
include a patent prose page with ordinary two-column text and figure captions
(image `6424`) and a Perl manual page whose code-formatting region is ordinary
documentation rather than a table (image `5676`). These controls illustrate
why the labels are not table truth oracles.

The control exposure is:

| Candidate | Control exposure |
| --- | ---: |
| Union of observed D2 labels | 1,149/1,444 regions; 92/95 pages |
| `document_index` | 0/1,444 regions; 0 pages |
| `code` | 3/1,444 regions; 2 pages |
| `list_item` | 117/1,444 regions; 21 pages |
| `picture` | 102/1,444 regions; 38 pages |
| `text` | 927/1,444 regions; 90 pages |
| OCR child count <=1 | 1,405/1,444 regions; 93 pages |
| OCR child count ==0 | 71/1,444 regions; 29 pages |

Two control pages have no non-table layout region, so the region denominator
is 1,444 while the page denominator remains 95. These are trigger-exposure
figures only. No 039 forced treatment was run, so no 039 control false-positive
rate is claimed.

## Treatment value hypothesis

036 measured a 50.0% valid forced-crop recovery rate (17/34) on the historical
035 D2 treatment set, with 8/34 conflicts. Its 145-control arm produced
104/145 structurally valid isolated outputs, a 71.72% false-positive rate in
that preregistered eligible-control-crop frame. Those results establish that
forced treatment can recover some known blocked crops and that structure
success alone is unsafe. They do not transfer a 50% recovery rate to 039.

039's D2 morphology differs from the 035/036 treatment population. 035/036
were dominated by `picture` (16/34 in the 036 treatment), `text` (10/34),
`document_index` (7/34), and `code` (1/34). 039 has 24 `document_index`, eight
`text`, six `picture`, four `code`, and three `list_item` D2 annotation rows.
039 also exposes explicit shared-region multiplicity and many pages where a
material nearby table object exists. The likely recovery rate and conflict
rate are therefore heterogeneous by subtype and may differ materially from
036.

The current evidence supports the following hypothesis, not a conclusion:

> A subset of high-overlap `document_index` ownership failures may be
> recoverable by an alternate table path, while oversized picture regions,
> ordinary text/list regions, and shared-region cases may have materially
> different benefit/conflict profiles.

This hypothesis must be tested with a frozen counterfactual and ownership
resolver. It must not be converted into a selector by retrospective outcome
prediction.

## End-to-end evidence impact

At the extraction/IR boundary, strict D2 cases have no final table owner for
the relevant matched region. Their final IR row types are `other` (28),
`image` (6), `list_item` (3), `text` (7), and one two-region text
`MULTIPLE_MATCH`. Twenty-three D2 rows retain non-empty region text in the
final element; 22 retain none. This proves a structural ownership failure,
but it does not prove complete semantic evidence loss because the frozen
DocLayNet annotations supply geometry, not canonical table cell text.

A treatment could improve table structure while harming reading order or
ownership. The next experiment must therefore compare, side by side:

* table-object existence and owner mapping;
* cell grid validity, dimensions, and text assignment;
* duplicate or cross-region ownership;
* reading-order placement;
* serialized IR/evidence changes; and
* baseline-preservation invariants outside the treated region.

No current 039 artifact records page-level detector boxes, per-region table
invocation mode, ownership collision decisions, or per-stage timing at the
region level. These are engineering gaps with direct scientific impact.

## Mechanism interpretation

### Supported by 039

* Natural strict-D2 activation is substantial enough to pass the frozen formal
  adequacy gate.
* Non-table ownership failures occur across multiple real-document groups and
  categories, not only the two-group/one-label pattern that blocked 038.
* `document_index` is a promising pre-treatment correlate across groups and
  categories.
* Shared-region and nearby-table-object patterns make ownership resolution a
  first-class problem.
* Broad union-of-label treatment has high control exposure.

### Contradicted or weakened

* The hypothesis that all D2 cases share one raw-label mechanism is weakened
  by the distinct role, geometry, and ownership patterns.
* Geometry-only selection is weakened by strong D2/non-D2 overlap and control
  exposure.
* A universal “treat every non-table region” policy is contradicted by the
  control-frame exposure and by 036's control result.
* D2 as proof of whole-page Table Transformer absence is contradicted by the
  documented page-wide fallback semantics; 039 telemetry cannot resolve which
  path occurred in each case.

### Unresolved

* Whether page-wide detection already found the relevant table in each D2
  page.
* Whether role normalization, layout grouping, OCR grouping, or ownership
  merge logic is the dominant upstream cause for each subtype.
* Which D2 subtypes are counterfactually recoverable and at what conflict
  cost.
* Whether `document_index` remains high-purity on a new corpus containing
  same-role non-table negatives.
* Whether a recovered table improves serialized evidence rather than merely
  adding a duplicate or structurally misleading object.

## Candidate research directions

| Direction | Assessment |
| --- | --- |
| Universal selector | Reject now. The role union exposes 1,149/1,444 control regions; text/picture/list are common normal content, and mechanisms are heterogeneous. |
| Mechanism-specific selector | Promising, centered first on `document_index`; code is too one-document-specific, while picture/text/list require high-risk negative arms. Still not ready for held-out tuning. |
| Role normalization first | Good engineering candidate. It could clarify whether index/code/list labels are stable ontology errors, but it does not estimate alternate-treatment value and must not be conflated with relaxing the table gate. |
| Controlled counterfactual first | Recommended. 039 differs from 036 and has enough development D2 region units to estimate recovery/conflict heterogeneity without using held-out outcomes. |
| Instrumentation first | Mandatory companion to the counterfactual. Without invocation-mode and detector-box telemetry, D2 causal interpretation remains underdetermined. |
| Larger corpus | Conditional fallback. Formal 039 adequacy passes; expand only if the instrumented counterfactual shows insufficient within-subtype controls or unstable group-level behavior. |

## Recommendation

**Do not build or tune a selector yet. Proceed to an instrumented,
development-only per-region counterfactual feasibility study, with
`document_index` as the primary mechanism-specific arm and all other observed
roles represented as explicit negative/control arms.** First freeze the design
in [`NEXT_EXPERIMENT_DESIGN.md`](NEXT_EXPERIMENT_DESIGN.md), add telemetry that
records page-wide versus labelled-crop specialist invocation and detector
boxes, and verify that the instrumented no-treatment output is semantically
identical to the frozen baseline. Then treat the 28 unique development D2
region units (not 34 inflated annotation rows) and a deterministic broad
control frame from the 47 development control pages. Score alternate outputs
end to end with a predeclared owner resolver and conflict cost.

This choice reduces the two largest uncertainties at once: whether alternate
treatment has value on 039's genuinely different D2 morphology, and whether
the apparent `document_index` signal survives ownership and control scrutiny.
If the counterfactual is favorable for one subtype, write a separate policy
preregistration and reserve the 039 held-out groups for one-shot evaluation.
If it is not, retain the negative result and prioritize role/invocation
instrumentation or a larger stratified corpus. Do not weaken the frozen gate
or convert the formal READY status into a deployment claim.

## What NOT to do

* Do not treat `document_index` as a production rule merely because its
  observed control exposure is zero.
* Do not union all five observed D2 labels into a universal selector.
* Do not use GT geometry, strict-D2 labels, forced-crop outcomes, final
  ownership, conflicts, or held-out outcomes as selector features.
* Do not transfer the 036 `17/34` recovery fraction to 039.
* Do not count repeated GT tables sharing one region as independent treatment
  units.
* Do not relax `region.label.lower() == "table"`, promote the 033 shape rule,
  or auto-promote any forced-crop structure result.
* Do not run held-out policy evaluation before a separate selector,
  cost function, resolver, and one-shot protocol are frozen.

## Evidence sources

* [`population_manifest.json`](population_manifest.json) — frozen 039
  identities, GT boxes, categories, and split.
* [`population_audit.json`](population_audit.json) — image, source-link, hash,
  and cross-experiment integrity audit.
* [`results/baseline_run_index.json`](results/baseline_run_index.json) —
  complete baseline ledger; raw run directories are intentionally ignored.
* [`baseline_analysis.json`](baseline_analysis.json) — existing 035-compatible
  activation summary, independently reproduced here.
* [`039_D2_FORENSIC_CASES.json`](039_D2_FORENSIC_CASES.json) — compact raw
  case-level reconstruction and near-D2 records.
* [`039_D2_TAXONOMY.json`](039_D2_TAXONOMY.json) — descriptive subtype
  assignments with evidence-for/evidence-against fields.
* [`039_MATCHED_COMPARISONS.json`](039_MATCHED_COMPARISONS.json) — feature,
  label, group, category, control-exposure, and telemetry summaries.
* [`../035_mechanism_d_gating/FINAL_RESEARCH_REPORT.md`](../035_mechanism_d_gating/FINAL_RESEARCH_REPORT.md)
  — frozen 035 findings.
* [`../036_mechanism_d_counterfactual/ANALYSIS.md`](../036_mechanism_d_counterfactual/ANALYSIS.md)
  and [`../036_mechanism_d_counterfactual/forensic_audit.json`](../036_mechanism_d_counterfactual/forensic_audit.json)
  — frozen 036 treatment/control evidence.
* [`../037_selective_policy_validation/EXPERIMENT_STATUS.md`](../037_selective_policy_validation/EXPERIMENT_STATUS.md)
  and [`../038_independent_real_corpus/FINAL_RESEARCH_REPORT.md`](../038_independent_real_corpus/FINAL_RESEARCH_REPORT.md)
  — frozen negative/blocked lineage.
