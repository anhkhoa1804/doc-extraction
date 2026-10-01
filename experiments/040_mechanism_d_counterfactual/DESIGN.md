# Experiment 040 — development-only Mechanism-D crop counterfactual

Status: **frozen before treatment**. This experiment is not a production
feature, selector deployment, or held-out evaluation.

## Research question and estimand

Among the 28 unique development strict-D2 region units from 039, can explicit
TableTransformer treatment of the exact frozen baseline region crop yield a
valid, correctly owned table without conflict or damage? The primary
descriptive estimand is:

```text
valid recoveries / 28 unique development D2 region units
```

The control estimand is the proportion of the 766 frozen development
non-table control regions producing material unsupported table evidence,
ownership conflict, duplication, contamination, or an operational failure.
GT-table scoring is secondary and retains linked-table multiplicity.

## Population and boundary

The population is built deterministically from the frozen 039 manifest,
baseline layout/OCR/final artifacts, and the committed 039 forensic D2 cases.
The target arm deduplicates `(image_id, region_index)`; linked GT tables remain
attached to one unit. The control arm includes every positive-area non-table
layout region on the 46 usable development control pages, for 766 units.

Only `split == "development"` is accepted by the runtime guard. Any other
split raises before image crop or specialist invocation. Held-out records are
not in the population manifest and are not read by the treatment runner.

## Arms and treatment

Arm B is the frozen 039 baseline page artifact. Arm T uses the same image and
the exact baseline region bbox. The existing `TableTransformerBackend`
counterfactual helper performs structure recognition on that supplied crop and
records independent detector evidence on the same crop. OCR, layout, routing,
page-wide fallback, and the canonical baseline are unchanged. Treatment
outputs are written only below this experiment's `results/` directory.

The treatment must report `LABELLED_CROP`; `PAGE_WIDE` and `NOT_INVOKED` are
protocol failures for the treatment arm. Detector output is Layer 1 evidence,
structure validity is Layer 2, ownership is Layer 3, and only the final
post-treatment evaluator may assign `VALID_RECOVERY`.

## Frozen evaluation

Structure validity is the 036 rule: at least one positive row and column,
nonempty cells and bbox, and fewer than 20% of cell boxes escaping the table
bbox by more than one pixel. GT IoU `>= 0.3` is computed only after treatment.
Existing baseline-table overlap `> 0.1` is material conflict. Ownership uses
the production merge mechanism with a synthetic table-labelled candidate; a
candidate is accepted only if the intended candidate is the unique owner.

Control outcomes are mutually exclusive in this order: operational failure,
duplication/damage, cross-table contamination, ownership conflict, material
false positive, and no effect. Detector activation without a material table
interpretation is not a control false positive.

The frozen feature contract and policy-family indicators are in
[`feature_manifest.json`](feature_manifest.json). They are computed from
baseline layout/OCR evidence before treatment output is inspected. The
pre-registered families are abstain-all, document-index-only,
document-index-plus-zero-OCR, and the broad observed-role union as an unsafe
negative control. No learned selector or post-hoc threshold is permitted.

## Pilot and full run

The deterministic pilot is four units: one `document_index` D2 unit, one
non-`document_index` D2 unit, and two controls. Pilot output is an engineering
integrity check only and cannot alter the protocol. After pilot integrity
passes, the full run processes all 28 D2 units and 766 controls. Both runners
are resumable and atomically checkpoint per unit.

## Reproducibility

`population_manifest.json`, `feature_manifest.json`, and `protocol.json` are
frozen before treatment. Runtime metadata records the code SHA, population and
protocol hashes, model IDs, config hash, CPU device, Python and package
versions, and environment provenance. Raw per-unit treatment outputs and
telemetry are retained; aggregate results are written only after the selected
phase completes.

The VM's temporary `libGL` workaround is an environment prerequisite and is
not embedded in this experiment or committed as a binary artifact.
