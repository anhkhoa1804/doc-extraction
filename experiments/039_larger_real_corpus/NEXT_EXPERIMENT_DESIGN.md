# Next experiment design — instrumented 039 counterfactual feasibility

**Status:** design only. No treatment, selector tuning, or held-out
evaluation has been run under this design.

## Research question

For naturally occurring 039 development Mechanism-D region units, does an
alternate Table Transformer crop treatment improve table structure and final
IR ownership at an acceptable conflict and control cost? Which observed
pre-treatment signals, if any, identify a treatment-beneficial subtype across
source-document groups?

This is a treatment-value and observability study first. It is not a
production selector evaluation and cannot authorize a production gate change.

## Causal target and estimand

Let `B` be the frozen 039 unchanged-baseline output and `T` be the same-page,
same-region alternate crop treatment defined below. For each eligible
development region unit, define potential outcomes `Y(B)` and `Y(T)` for:

* a valid table structure;
* a unique table owner with no material collision;
* GT-relevant table geometry, used only for scoring; and
* an end-to-end IR evidence improvement without duplicate or damaging output.

The primary estimand is the descriptive average treatment response among the
unique development strict-D2 region units:

```
P(valid_recovery under T | unique development D2 region unit)
```

reported separately from the 039 baseline state. The same estimand is
reported at GT-table level, preserving multiplicity rather than pretending
that multiple GT tables sharing one region are independent. The control
estimand is:

```
P(material false-positive table or ownership conflict under T
  | frozen development non-table control region)
```

These are intervention-response estimates, not causal claims about why the
layout model produced a D2 label. Page-level detector invocation telemetry is
an observational mediator/provenance field, not a selector label.

## Frozen population and split

The population is the already frozen 039 corpus. It must not be reacquired,
resampled, relabelled, or modified.

### Development treatment units

Use every strict-D2 development annotation from the frozen 039 baseline and
deduplicate by `(image_id, region_index)`. This gives:

* 34 strict-D2 GT-table annotation rows;
* 26 source pages; and
* 28 unique non-table region units.

All 28 units are treated or recorded as an explicit operational failure;
none may be dropped because its role, geometry, or predicted response is
 inconvenient. If one region maps to multiple GT tables, each GT table is
scored, but the region-level unit remains one unit.

### Development controls

Use all non-table layout regions on the 47 development non-table control
pages. Forty-six of those pages contain at least one non-table region, giving
766 deterministic control region units. The one development control with no
usable non-table region is retained in the audit ledger but has no crop
treatment. This broad region frame is intentionally more informative than a
single largest-region sample for the current question; its denominator is
fixed before any treatment output is read.

### Held-out reservation

All 16 held-out source-document groups and all 11 held-out strict-D2
annotations remain untouched. They are not used to choose a feature, policy
family, crop rule, owner resolver, threshold, or stopping decision. A later
policy study may use them once, but only after a separate preregistration
freezes the policy and one-shot protocol.

## Inclusion and exclusion

Include every frozen development D2 region and every eligible development
control region described above. Exclude only:

* held-out records;
* `NO_REGION` and `AMBIGUOUS` records from the D2 target arm, because they are
  not strict D2 under the frozen definition;
* table-labelled regions from the alternate non-table treatment arm;
* a control page with no usable non-table region; and
* an invocation that fails for an operational reason, which remains in the
  denominator and is reported as a failure.

No exclusion may be made for inconvenient document category, source group,
raw label, OCR count, geometry, warning, or counterfactual output.

## Instrumentation prerequisite

Additive telemetry must be written to a separate output tree before treatment
execution. The no-treatment pipeline semantics and final IR must remain
unchanged. For every page and candidate region, record:

* route, backend, model IDs, device, and configuration hash;
* raw layout role and deterministic lowercase normalized role;
* layout confidence and source ID, including explicit nulls;
* region bbox, area fraction, aspect ratio, index, page region count;
* OCR child count and child character count under the production center-point
  containment rule;
* table invocation mode: `labelled_crop`, `page_wide_detection`, or
  `not_invoked`;
* supplied crop bbox, page-wide detector boxes and scores when invoked;
* structure boxes, structure validity, and per-stage timing;
* proposed owner, baseline owner candidates, collision decision, and resolver
  reason; and
* output hashes and serialized IR counts.

The instrumented no-treatment run must be compared with the frozen baseline
on all 039 development pages before treatment. Any semantic IR difference,
population mismatch, model mismatch, or unexplained detector-path change
stops the study and is recorded as an engineering incident. The frozen
baseline is never overwritten.

This instrumentation is required because D2 does not prove that page-wide
Table Transformer detection was absent. It must distinguish “not invoked,”
“invoked but no detection,” “detection found but ownership lost,” and
“ownership collision.”

## Selector feature contract

The counterfactual feasibility arm does not fit or tune a selector. The
following contract is frozen for any later development-only selector stage:

### Permitted pre-treatment fields

* raw layout role and deterministic lowercase normalized role;
* layout confidence/provenance when non-null;
* region area fraction, width/height fractions, aspect ratio, region index,
  and page region count;
* OCR child count and character count from baseline OCR;
* route, backend/model identity, and externally guaranteed document category;
* independently measured page-level detector evidence collected before the
  selector acts; and
* deterministic combinations of the fields above.

The retrospectively GT-matched region is an audit anchor, not a runtime
feature. A real selector must score candidate regions independently.

### Forbidden fields

GT bbox or table identity, strict-D2 status, forced-crop detector/structure
outcome, post-treatment ownership/conflict, final treated IR, held-out
outcome, and any feature generated after the alternate treatment are
forbidden.

### Policy families to compare later, without tuning here

1. no-treatment baseline;
2. exact `document_index` role arm;
3. one-arm-per-role diagnostic arms for `code`, `picture`, `list_item`, and
   `text`;
4. a role-plus-low-OCR arm with its threshold frozen before outcome review;
5. a separately preregistered page-detector-evidence arm; and
6. “any non-table role” as an explicit unsafe negative-control policy, not a
   deployment candidate.

No threshold or policy family may be selected from held-out outcomes. If a
later study needs a different family, it requires a new preregistration.

## Treatment definition

For each target or control region, run the existing Table Transformer
counterfactual on the exact baseline region bbox, using the frozen CPU model
and configuration. The treatment consists of:

1. structure recognition on the supplied region crop;
2. independent page/crop detector evidence recorded as observation;
3. construction of an alternate table object in a separate result tree; and
4. deterministic ownership resolution below.

The treatment must not read GT, route from D2, use a forced-crop outcome to
choose another crop, mutate the frozen baseline, or alter unrelated page
elements. The page-wide detector result must not be silently interpreted as
proof of whole-page absence or presence in the baseline.

## Pre-registered outcome thresholds

The following definitions are fixed before treatment:

* structure-valid means a non-empty positive row/column grid, using the
  existing 036 structural-validity definition;
* GT relevance is alternate-table IoU `>= 0.3` with the independent GT table,
  used only after treatment for scoring;
* material production-table conflict is IoU `> 0.1` with an existing baseline
  table object, using the existing 036 boundary;
* an owner is valid only when the alternate object has a unique deterministic
  owner with owner IoU `> 0.1`;
* valid recovery requires structure validity, a unique owner, GT IoU `>= 0.3`,
  and no material conflict;
* a control false positive is a material table object or table-owned IR
  element produced from a frozen control region whose page has no GT table;
* a duplicate is any alternate object that creates two owners for one region,
  one owner for incompatible overlapping regions, or a second owner for an
  existing baseline table; and
* a structural damage event is a changed unrelated element, changed reading
  order outside the treated owner, duplicate serialized evidence, invalid
  cell geometry, or a new unowned table object.

No threshold may be tuned after seeing a target or control output. These are
study definitions, not a production false-positive budget.

## Ownership resolver

The resolver is frozen before treatment and is conservative by construction:

1. Preserve the baseline document and all baseline table objects unchanged.
2. Treat the supplied region as a candidate owner only; do not infer an owner
   from GT or from the label “table.”
3. If the alternate table materially overlaps any existing baseline table, or
   if two alternate candidates materially overlap, mark `CONFLICT` and abstain
   from attachment.
4. If the alternate object has no unique positive owner association, mark
   `AMBIGUOUS_OWNER` and abstain.
5. Attach an alternate table only when one deterministic candidate owner
   remains, preserving baseline and alternate provenance side by side.
6. Never replace an existing owner automatically and never allow one alternate
   object to silently count as independent recovery for multiple GT tables.
7. Record every rejection, collision, owner ID, bbox, and resolver reason.

## Cost metric

Record specialist invocations, detector and structure calls, CPU wall time,
per-stage time, peak process RSS when available, output bytes, and incremental
storage. Compare treatment cost with the frozen baseline per page and per
region. Cost is reported by subtype and source group; no GPU inference claim
is made from this CPU study.

## Negative controls and falsification tests

### Negative controls

* all 766 development control regions from 46 usable control pages;
* role-specific control strata for every observed D2 raw role;
* table-labelled regions passed through a no-op branch to verify the existing
  path is not changed; and
* pages with no production table object versus pages with one or more objects,
  reported without using that post-treatment result as a selector feature.

### Falsification tests

* Run the same deterministic crop request twice in fresh processes and require
  identical structural/ownership JSON apart from timestamps.
* Run a fixed, preregistered crop displacement placebo on a small control
  subset. A high rate of equally valid output from displaced crops indicates
  generic crop susceptibility rather than table-specific evidence.
* Compare page-wide detector evidence with supplied-crop structure evidence;
  do not collapse them into one detection outcome.
* Permute role labels within source-document groups for a descriptive placebo
  policy analysis. A role rule whose apparent value survives arbitrary role
  permutation is not credible.
* Require that the instrumented no-treatment output matches the frozen
  baseline, including table ownership and reading order, before any treated
  result is interpreted.

## Stop conditions

Stop before scientific interpretation if any of the following occurs:

* frozen manifest, image hash, source group, or split mismatch;
* any held-out outcome is read by the treatment or policy code;
* the frozen baseline is overwritten or used as the alternate output target;
* model ID, device, configuration, or coordinate space changes unexpectedly;
* a duplicate output identity or non-atomic result is detected;
* instrumentation changes no-treatment semantic IR;
* more than 10% of planned invocations fail for an unexplained engineering
  reason; or
* an ownership resolver cannot produce an auditable decision for a result.

A high control false-positive or conflict result is not deleted or hidden; it
is a scientific negative result and closes the corresponding policy arm. The
10% figure is an operational completeness stop, not a claim that a 10% harm
rate is acceptable in production.

## Decision rules after completion

Report region-level recovery, GT-table-level recovery, control false-positive,
conflict, structural damage, and cost with exact denominators and group-level
breakdowns. Do not pool repeated GT tables without a multiplicity note.

Proceed to a separate selector preregistration only if at least one
mechanism-specific arm shows treatment value with an auditable resolver and
control/conflict behavior that the research owner explicitly accepts. The
result is not a deployment authorization. If `document_index` is favorable but
other roles are not, continue only with a mechanism-specific arm. If all arms
are unsafe or non-beneficial, preserve the negative result and choose
instrumentation or stratified corpus expansion rather than weakening the gate.

The held-out split is then evaluated once, with selector, threshold, cost,
resolver, and one-shot protocol frozen in a separate document. No development
result may be used to retune the held-out run.

## Reproducibility plan

* Keep the 039 manifest, annotation hash, image hashes, and baseline index
  immutable.
* Use the exact production model IDs, CPU configuration, and recorded library
  versions; run offline where practical.
* Store alternate results beside, never over, the baseline results.
* Write per-region records atomically and retain interrupted attempts.
* Record source image, baseline output, alternate output, telemetry, resolver
  decision, and code/config hashes for every invocation.
* Run the pure analysis and resolver regression tests before and after the
  study, then run the full suite when practical.
* Commit only protocol, compact audits, reports, tests, and research code;
  keep large raw alternate outputs ignored.

## Rationale

This design addresses the two uncertainties that 039 leaves most important:
whether alternate treatment helps the new corpus's unusually large
`document_index` subtype, and whether the apparent signal survives conflicts
and normal-control exposure. It keeps the 039 formal READY status intact while
preventing that status from being misread as evidence for a universal policy.
