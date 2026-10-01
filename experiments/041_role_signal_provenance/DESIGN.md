# Experiment 041 design

## Research question

Is `document_index` a genuine pre-treatment, mechanism-specific correlate of
table ownership loss; did the original 039 production path already invoke
page-wide table detection on D2 pages; and is the upstream failure better
described as role normalization than as table extraction?

These are three separate modules. A detector invocation is not a recovery,
and D2 is ownership/gating evidence rather than proof that no page-wide
specialist ran.

## Frozen provenance

The design was prepared at parent commit
`1b4b43b9366d0f695671cbde28c28ecd8c14b1a6` on branch
`fix/table-text-ownership`, from origin
`git@github.com:anhkhoa1804/doc-extraction.git`.

The 039 population manifest is SHA-256
`55fe36b5f39e1e87437f81ed2cc2d120e5c7d747b1f3109318b06d530b50f8e5`; its
annotation member is
`eacd2ba2a32e6c2ebe2dc5ea1545f405d8461c46bba53e0c35d9c54fba0bcef6`.
The 040 population hash is
`e6ee85b2aec4c85a00006bbee5e23a07cd0ac9f40c3487bba21e24677136f109`.
The frozen 039 baseline index hash used by 040 is
`97e66f2cf68be97e14fc6f53223790f5e9580bb1dc10e32e28e51227aac58372`.

The repository artifacts contain a legacy denominator inconsistency: the
039 manifest has 136 development and 133 held-out records, while some 039/040
prose writes `34/152` for development activation. Experiment 041 does not
rewrite that lineage; it treats the frozen manifest as authoritative for page
counts and does not use the 152 denominator for a new analysis.

## Verified 040 evidence

The committed 040 result artifact was checked before this design:

| quantity | verified value |
| --- | ---: |
| unique D2 units | 28 |
| development controls | 766 |
| evaluable units | 774/794 |
| operational failures | 20/794 |
| valid recoveries | 4/28 |
| `document_index` D2 recoveries | 2/15 |
| `document_index` controls | 0 |
| wrong-role subtype recoveries | 3/3 |
| D2 material conflicts | 16/28 |
| control material false positives | 342/766 |
| control contamination | 8/766 |
| control duplication/damage | 2/766 |
| held-out access | false |

These are prior evidence, not 041 outcomes.

## Module A — same-role controls

### Population and unit

The D2 treatment arm, if the gate can be repaired, is the 15 unique 040
development D2 region units whose frozen raw role is `document_index`. A
shared region remains one unit even when it links to multiple GT annotations.

Controls must be selected from the frozen 039 development baseline layout,
before 041 treatment output exists, have raw role `document_index`, and not be
one of the 28 frozen D2 region identities. Selection is deterministic by
`(image_id, region_index)` after filtering to `split == development`; it does
not use treatment output or a GT-derived positive/negative label. Source-group,
category, page, bbox, OCR, and layout metadata are retained.

The preregistered target is at least 30 naturally occurring controls, with
source-group and category diversity reported. No synthetic controls and no
held-out substitutions are permitted. If fewer than 30 exist, the result is
descriptive and cannot establish low false-positive exposure. If zero exist,
the hard stop prevents treatment.

The audit found 15 candidate regions and excluded all 15 because their frozen
identities are D2 units. Thus the eligible control count is zero.

### Intervention and estimands

For an executable Module A, each D2 target and each same-role control would be
paired with:

* B: the frozen baseline page and region state;
* T: the exact frozen baseline region crop passed through the existing
  `extract_crop_counterfactual` treatment path.

The image, bbox, preprocessing, models, thresholds, OCR, layout, and
ownership semantics remain unchanged. GT is inaccessible to treatment input
and may enter only in post-treatment evaluation of D2 targets. Controls use
material unsupported output, conflict, contamination, and serialization harm
definitions, not detector activation alone.

Primary estimands are `P(valid recovery | D2, document_index)` and
`P(material false positive | development control, document_index)`, with exact
counts, clustering metadata, operational failures, contamination, duplication,
and runtime.

### Hard stop

`same_role_controls == 0` is a protocol-blocking condition. No crop treatment
was run and no result was imputed.

## Module B — baseline invocation provenance

Module B is observational and no-treatment. It would replay a deterministic
development-only stratified sample through the already validated additive
telemetry path, using `configs/cpu.yaml` and the unchanged production call
chain. The sample contract includes known D2 pages, non-D2 table pages,
non-table controls, ambiguous layout pages, and examples expected from the
baseline layout to exercise page-wide and labelled-crop routing. Sample
membership is frozen from development baseline metadata only. Held-out pages
are rejected before processing.

For each page the telemetry must distinguish `PAGE_WIDE`, `LABELLED_CROP`,
both, or neither, with specialist call count, detector boxes/scores, tables,
ownership, and final serialized table state. No invocation mode is inferred
from D2 or final output. Because Module A's no-controls hard stop applies, the
Module B sample was not replayed in this checkpoint; its contract is frozen in
`PAGE_WIDE_PROVENANCE.md` for a future corpus-expansion checkpoint.

## Module C — role-normalization routing counterfactual

Module C is an offline routing-only counterfactual. It does not invoke a
specialist and does not produce recovery output. The current code lowercases
the raw label for telemetry but the production gate consumes
`region.label.lower() == "table"`; there is no independent role-normalization
stage at that boundary.

The sole transparent mapping hypothesis is:

`document_index -> table`

Negative roles `text`, `picture`, `code`, and `list_item` remain unchanged.
The phrase “wrong-role ownership” is not itself an eligible mapping because it
requires post-hoc GT/ownership knowledge. The routing counterfactual would
compare the raw-label gate with a hypothetical gate that consumes the frozen
normalized role, and classify `INVOCATION_CHANGED`,
`INVOCATION_UNCHANGED`, `ROUTE_ERROR`, or `PROTOCOL_ERROR`. It would not claim
that changed routing recovers evidence.

Module C was not executed after the Module A hard stop.

## No leakage and no deployment

No held-out record is admitted by the protocol. No treatment outcome, GT
geometry, specialist output, post-treatment ownership, or conflict may enter
the feature contract. The 040 broad role union is not rerun. No production
rule, selector, or threshold is changed.

## Decision rule

The current decision is `REFINE_EXPERIMENT`: the `document_index` false
positive estimand is unidentifiable in the frozen development corpus. A new
experiment may proceed only after freezing an independent development
population with natural same-role controls, while preserving the original
039 held-out groups for eventual one-shot policy evaluation.
