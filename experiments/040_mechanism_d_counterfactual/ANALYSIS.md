# Experiment 040 — forensic development counterfactual analysis

This is a development-only paired intervention over the frozen 039 population.
It is not a production change and it does not evaluate the held-out partition.
The compact per-unit evidence is in [`results.json`](results.json), the D2
case index is in [`D2_TREATMENT_CASES.json`](D2_TREATMENT_CASES.json), and raw
telemetry/model evidence is retained below `results/full/raw/` on the VM.

## Executive conclusion

Explicit TableTransformer treatment of the exact frozen baseline region crop
produced a valid, correctly owned recovery for only **4/28 unique development
D2 region units (14.3%; Wilson 95% interval 5.7%–31.5%)**. The recoveries were
limited to wrong-role/partial-ownership cases and occurred in four source
groups, while all three shared-region units and all 15 table-object-present-
but-misattached units failed through contamination, irrelevance, or invalid
structure. The broad non-table-role intervention is falsified by **342/766
material control false positives (44.6%)**, plus 8 contaminations, 2
serialization-damage cases, and 20 unsupported-small-crop operational failures.
`document_index` remains a promising pre-treatment correlate—15 D2 units,
2 recoveries, and no sampled controls—but the frozen controls contain no
same-role `document_index` regions, so its false-positive rate is not
identified. The evidence supports a narrow, mechanism-specific research
hypothesis; it does not support a universal selector, a production rule, or
held-out evaluation.

## Verified facts

- Code commit for the full treatment run: `8dc3dc6d7e47b5a68d58addb8dfa0309a0623e82`.
- Frozen baseline checkpoint: `cdb8fd80f5c2d9dc1711b50828ec9301c5bb1adf`.
- Frozen population hash: `e6ee85b2aec4c85a00006bbee5e23a07cd0ac9f40c3487bba21e24677136f109`.
- The population contained 28 unique development D2 region units and 766 deterministic development non-table controls. It covered 11 D2 source groups, 16 control source groups, and 6 categories.
- All 794 population identities were accounted for. 774 records completed the crop intervention; 20 control records stopped before specialist invocation because their exact crops were smaller than the backend minimum. This is 20/794 (2.52%) overall and 20/766 (2.61%) of controls, below the preregistered 10% unexplained-failure stop condition. All 20 had the same `unsupported_geometry` condition.
- Invocation modes were `LABELLED_CROP=774`, `PAGE_WIDE=0`, and `NOT_INVOKED=20`. No treatment output was written into the 039 baseline tree.
- The 039 adequacy gate remains unchanged and formally passed before this experiment: 34/152 development D2 rows, 11 source groups, 5 raw labels, 6 categories, and a largest-group contribution of 10/34.
- `heldout_accessed = false`.

## D2 taxonomy and treatment outcomes

Assignments below are descriptive candidates inherited from the frozen 039
forensic taxonomy; they are not causal proof.

| Frozen primary candidate | Units | Valid recovery | Treatment outcomes | Interpretation of this intervention |
| --- | ---: | ---: | --- | --- |
| table object present but not correctly attached | 15 | 0/15 | 14 cross-table contamination, 1 structure-invalid | Explicit crop treatment usually produced a second object overlapping the existing production table; it did not repair ownership. |
| partial non-table ownership | 7 | 1/7 | 1 valid recovery, 3 structure-invalid, 3 GT-irrelevant/nonrecovery | Some small or partial non-table regions are recoverable, but the result is heterogeneous. |
| wrong-role ownership | 3 | 3/3 | 3 valid recoveries | This is the strongest narrow treatment signal, but it contains only three units. |
| cross-table contamination/shared region | 3 | 0/3 | 2 cross-table contamination, 1 GT-irrelevant/nonrecovery | Shared/oversized ownership is not repaired by simply adding a crop candidate. |

The 28 treatment units were deduplicated by region identity, not GT row. There
were 25 units linked to one GT table, 2 linked to two tables, and 1 linked to
five tables. The three multi-GT/shared units had zero valid recoveries. The
four valid recoveries were `d2-2819-6`, `d2-4195-1`, `d2-453-2`, and
`d2-474-2`; each had one linked GT table, unique ownership, no material
production-table conflict, no serialization damage, and GT IoU above 0.3.

Layered D2 results were:

- detector evidence: 12/28;
- structurally valid forced table: 24/28;
- unique intended owner: 8/28;
- material production-table conflict: 16/28;
- cross-table contamination: 16/28;
- valid recovery: 4/28.

This separation matters: detector output and structural output were much more
common than safe ownership, and safe ownership was more common than valid GT
recovery.

## D2 versus controls and confounding

### Raw-role comparison

The treatment outcomes by raw role were:

| Raw role | D2 units / valid recoveries | D2 outcome summary | Controls | Control outcomes |
| --- | ---: | --- | ---: | --- |
| `document_index` | 15 / 2 | 12 contamination, 1 invalid | 0 | no same-role control exposure |
| `code` | 4 / 1 | 3 contamination, 1 recovery | 3 | 3 false positives |
| `list_item` | 2 / 1 | 1 recovery, 1 nonrecovery | 28 | 9 false positives |
| `picture` | 2 / 0 | 1 contamination, 1 nonrecovery | 57 | 49 false positives |
| `text` | 5 / 0 | 3 invalid, 2 nonrecovery | 497 | 225 false positives, 7 contaminations, 2 damage, 20 operational failures |

The controls also contained `caption` (17/27 false positives), `formula`
(5/20), `section_header` (34/133 plus 1 contamination), and `footnote`
(0/1). The absence of `document_index` controls is a design limitation, not
evidence of zero production false positives for that role.

### Pre-treatment geometry and OCR descriptions

These are descriptive distributions, not a fitted selector or causal model.

| Feature | D2 median (range) | Control median (range) |
| --- | ---: | ---: |
| region area fraction | 0.2728 (0.0005–0.6796) | 0.0058 (0.0001–0.8361) |
| width fraction | 0.5893 (0.0481–0.9278) | 0.2315 (0.0088–0.9999) |
| height fraction | 0.3780 (0.0104–0.8523) | 0.0231 (0.0072–0.8365) |
| aspect ratio | 1.9512 (0.4674–39.2525) | 5.0106 (0.2462–51.3725) |
| OCR child count | 0 (0–92) | 1 (0–38) |
| page region count | 4 (1–100) | 20 (2–52) |

Geometry has broad overlap and is confounded by the construction of D2 and
control populations. The frozen area comparator (`area >= 0.4`) selected 7 D2
units and 3 controls, recovered 0/7 D2 units, and produced 3/3 control false
positives. OCR sparsity is not safe by itself: the zero-OCR bucket contained
2/14 D2 recoveries but also 22/42 control false positives.

### Categories and source groups

Valid recoveries occurred in 2/6 financial-report D2 units, 1/5 government-
tender units, 1/6 manual units, and 0 units in laws/regulations, patents, or
scientific articles. They came from four source groups: the ACN financial
report, OTC_STKAF financial report, Bavaria tender, and Perl manual groups.
This is descriptive cross-group support for a narrow effect, not evidence of
unseen-document generalization. The dominant failures were also distributed
across groups, especially the large shared/table-object cases in the arXiv,
EU tender, FAA, and Perl groups.

## Pre-treatment selectability

The selector indicators were frozen before treatment output was read.

| Frozen policy/comparator | Selected D2 | Selected controls | Valid recovery | Control harm |
| --- | ---: | ---: | ---: | ---: |
| abstain all | 0 | 0 | 0/0 | 0/0 |
| role-only `document_index` | 15 | 0 | 2/15 (13.3%) | 0/0 observed; same-role FP unidentified |
| `document_index` + zero OCR | 14 | 0 | 2/14 (14.3%) | 0/0 observed; same-role FP unidentified |
| broad observed non-table roles | 28 | 585 | 4/28 (14.3%) | 315/585 harmful/conflict (53.8%) |
| area fraction >= 0.4 comparator | 7 | 3 | 0/7 | 3/3 harmful controls |

`document_index` is therefore an associated pre-treatment correlate, not a
validated selector. Its apparent purity is structurally untested because the
control population has no same-role examples. The broad role union directly
repeats the false-generalization problem this study was designed to expose.

## False-positive and end-to-end risk

Across all 766 controls, treatment yielded 394/766 no effect, 342/766
material false positives, 8/766 cross-table contaminations, 2/766
duplication/serialization-damage cases, and 20/766 operational failures.
The material false-positive rate was 342/766 (44.65%); the harmful/conflict
rate including contamination, damage, and operational failure was 372/766
(48.56%). A detector firing was not counted as a false positive by itself;
these classifications required a structurally valid unsupported table or a
harmful ownership/serialization outcome.

The paired IR checks found no changed or missing pre-existing element and no
reading-order change in the 28 D2 units. Two controls changed an existing
element and were classified as `DUPLICATION_DAMAGE`. Thus a table-level
recovery can be structurally plausible while still failing the end-to-end
ownership or evidence-integrity requirement.

## Falsification results

- **A — document_index versus geometry: PASS descriptively.** The frozen role-only indicator selected 2 recoveries among 15 D2 units with no sampled control exposure; the geometry comparator selected 0/7 D2 recoveries and caused 3/3 control false positives. This does not identify the document-index false-positive rate.
- **B — crop-specific versus page-wide: INCONCLUSIVE.** Every 040 intervention was explicitly `LABELLED_CROP`; 039 did not preserve sufficient invocation-mode telemetry to prove that page-wide detection was absent in the original baseline. D2 remains ownership/gating evidence, not proof of specialist absence.
- **C — shared-region concentration: PASS against a shared-region-only explanation.** Shared units produced 0/3 recoveries, while 4 recoveries came from non-shared units. This does not make non-shared ownership causal.
- **D — control harm: FAIL.** Harmful/conflict outcomes were 372/766.
- **E — table gain versus serialization damage: FAIL as a clean universal intervention.** Two controls had serialization damage; no D2 recovery had damage.
- **F — source-group concentration: PASS descriptively, limited.** Recoveries occurred in four groups, with no recovered group contributing more than one of the four recovered units. This is not a held-out generalization test.
- **G — OCR sparsity confound: INCONCLUSIVE/concern remains.** Zero OCR enriched the narrow D2 role arm but also had 22/42 control false positives; it is not a sufficient selector feature.
- **H — duplicate evidence: FAIL for universal treatment.** The two damage cases demonstrate that output insertion can alter existing evidence even when the synthetic candidate has a unique local owner.

## Mechanism interpretation

### Supported by the evidence

- An exact baseline-region crop can sometimes recover a real table whose
  baseline region had the wrong role, with 4/28 valid recoveries overall and
  3/3 in the frozen wrong-role subtype.
- Conservative ownership and conflict checks are essential. Structure-valid
  outputs were frequently rejected because they overlapped an existing table.
- Shared oversized regions and table-object-present-but-misattached cases are
  materially different from simple wrong-role cases.
- Broad treatment of observed non-table roles is operationally unsafe on this
  control population.

### Weakened

- A universal selective policy across document families is not supported by
  this intervention.
- Geometry-only or OCR-sparsity-only selection is contradicted by control
  exposure and poor recovery in the frozen comparators.
- `document_index` as a production rule is weakened by the lack of same-role
  controls and by 12/15 contaminated/nonrecovering document-index treatments.

### Rejected for this study

- D2 is not evidence that TableTransformer was absent from the page; page-wide
  invocation remains unresolved.
- Detector success, structure validity, or visual plausibility alone is not a
  valid recovery.
- The 4/28 result cannot be generalized as the 036 17/34 rate.

### Unresolved

- Whether `document_index` identifies a genuine cross-document role-normalization
  problem or merely a page-family proxy.
- The false-positive rate of a role-only `document_index` intervention on
  same-role negative controls.
- Whether an instrumented production run can separate an existing page-wide
  specialist result from crop-specific recovery in the baseline.
- The end-to-end information-retrieval benefit of the four structural
  recoveries after text ownership and serialized evidence are assessed.

## Candidate next directions

1. **Universal selector:** reject. The broad role union produced 315/585
   harmful/conflict outcomes among selected controls, and the geometry
   comparator failed on 3/3 controls.
2. **Mechanism-specific selector:** retain only as a research hypothesis.
   Wrong-role ownership is the only subtype with a clean 3/3 signal, but the
   arm is too small and lacks same-role controls.
3. **Role normalization first:** high research value. Test whether a
   deterministic, pre-treatment role-normalization intervention can reduce
   ownership loss, while measuring table-gate behavior separately. Do not
   conflate role normalization with universal table treatment.
4. **Another crop counterfactual:** lower priority in its current broad form.
   The present experiment already shows that treatment value is heterogeneous
   and that broad control harm is large.
5. **Instrumentation and stratified controls:** highest priority. Add a
   development-only same-role negative-control population, preserve explicit
   `PAGE_WIDE`/`LABELLED_CROP`/`NOT_INVOKED` provenance, and test the narrow
   wrong-role hypothesis without touching held-out data.

## Recommendation

**Do not freeze a policy for held-out evaluation yet. Refine the experiment
around wrong-role ownership and role normalization, but first add same-role
negative controls—especially `document_index` controls—and instrument baseline
page-wide specialist activity.** This is the highest-value uncertainty: the
only promising signal has 2/15 recovery in the document-index arm and an
unidentified false-positive rate, while the broad alternatives are already
falsified by control harm. The next design should freeze the new control
population, feature contract, ownership resolver, and end-to-end metric before
any further treatment. No selector, threshold, production route, or held-out
decision should be changed from this result.

## What not to do

- Do not deploy `if raw_role == document_index`.
- Do not treat all non-table labels as table candidates.
- Do not use GT geometry, treatment output, or forced-crop success to tune a
  selector.
- Do not infer page-level TableTransformer absence from D2.
- Do not count 34 GT rows as 34 independent treatments or transfer 036's
  recovery rate.
- Do not use held-out cases to fill the missing same-role controls.
- Do not rerun with enlarged/moved crops and call it the same counterfactual.
- Do not ignore ownership conflicts, serialization damage, or operational
  failures when reporting recovery.

## Provenance and replay

The full raw result, telemetry, treatment-observed, and failure records are
under `results/full/raw/` on the CPU VM. The full run index, metadata, compact
results, failure taxonomy, population, feature contract, and protocol preserve
the population hash, baseline checkpoint, treatment commit, model IDs, CPU
device, Python/package environment, crop hashes, and exact source bboxes.
