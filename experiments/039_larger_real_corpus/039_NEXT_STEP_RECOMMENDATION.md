# Experiment 039 next-step recommendation

## Decision

**Do not tune or deploy a selector yet. Proceed to a development-only,
instrumented per-region counterfactual feasibility study.** Make
`document_index` the primary mechanism-specific candidate, keep `picture`,
`text`, `list_item`, and `code` as explicit negative/control strata, and
reserve all 039 held-out groups for a later one-shot policy evaluation.

## Why this is the strongest next step

039 formally passes the frozen gate with 34 development D2 annotations, 11
source groups, five raw labels, six categories, and a largest-group fraction
of 29.4%. That is enough to justify policy design work, but not enough to
justify policy deployment. The activation is not homogeneous: 34 rows map to
26 pages and 28 unique matched regions, while 11 rows reuse one region for
multiple GT tables.

The best prospective signal is `document_index`: 24 D2 annotation rows arise
from 21 unique such regions spanning 11 groups and all six categories, and no
control region has that role. This is promising, not validated: it has no
same-role control negative, and the role may be a proxy for a specific
index/contents page family. Other labels are unsafe as universal triggers:
the observed D2-label union would expose 1,149/1,444 control regions, with
`text`, `picture`, and `list_item` especially common on normal controls.

Treatment value must be measured on 039 morphology rather than inherited from
036. 036 recovered 17/34 forced-crop cases but had 8/34 conflicts and
104/145 structurally valid control outputs in its eligible-control frame. 039
contains far more `document_index` cases, shared-region multiplicity, and
nearby production table objects. The recovery/conflict profile can therefore
be materially different.

## Required sequence

1. Freeze [`NEXT_EXPERIMENT_DESIGN.md`](NEXT_EXPERIMENT_DESIGN.md).
2. Add instrumentation in a separate output tree for table invocation mode,
   supplied crop, page-wide detector boxes, structure result, proposed owner,
   collisions, and per-stage timings. Do not change baseline IR semantics.
3. Rerun the unchanged no-treatment development pages only as an
   instrumentation-equivalence check. Compare final IR and baseline hashes;
   do not replace the frozen 039 baseline.
4. Run the preregistered alternate-crop counterfactual on the 28 unique
   development D2 region units and the deterministic development control
   frame. Score region-level and GT-table-level outcomes separately.
5. Stop without selector development if ownership conflicts, control output,
   or end-to-end IR damage exceed the frozen study limits.
6. Only if one mechanism-specific arm is favorable should a separate policy
   preregistration freeze features, policy family, threshold, cost, resolver,
   and one-shot held-out protocol.

## Explicit non-decisions

039 is `039_READY_FOR_POLICY_DESIGN`, not “policy works.” No 039 forced-crop
result, 039 recovery rate, 039 false-positive rate, or deployment threshold
exists yet. The raw baseline, manifest, D2 definition, and adequacy criterion
remain frozen.
