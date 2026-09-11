# Post-036 Next-Experiment Design — Independent Selective-Policy Validation

036 must not be reused to tune and evaluate a selector on the same cases. The next experiment should be a new, preregistered selective-policy validation on a document-group-disjoint corpus with ground truth, not a production rollout and not an implicit “037” claim before registration.

## Question

Can a frozen selector recover a meaningful fraction of counterfactually recoverable blocked-table cases while keeping a preregistered control-crop false-positive and ownership-conflict cost within an explicitly chosen operating budget?

## Required design

1. Build an independent corpus split by source document (never page), into development and held-out test sets. It must be disjoint from the 036 treatment/control identities. If 035/036 records are used descriptively, they cannot participate in feature/threshold selection or headline held-out evaluation.
2. Freeze candidate features before labels/outcomes are inspected: deterministic normalized role, layout confidence/provenance, raw crop geometry, independently computed page/crop detector evidence, and pre-existing ownership candidates. Do not use forced-crop structure success as a selector feature, because it is the treatment outcome.
3. Treat deterministic role normalization as one separately specified arm; any learned/evidence classifier needs a development-only feature contract, document-group split, fixed seed, and frozen model/version.
4. Preregister a cost function and acceptance gates before development analysis: valid recovery benefit, control false-positive rate within the defined crop/control frame, duplicate/cross-owner rate, specialist invocations, runtime, and an explicit reject/abstain outcome. The numerical production budget requires product-owner authorization; do not infer one from 036.
5. Define an ownership conflict resolver before execution: never replace an existing owner automatically; reject/abstain on material overlapping table ownership or ambiguous multi-owner mapping; preserve provenance for every rejection.
6. Evaluate end-to-end canonical IR, not only crop structure: owner assignment, duplicate avoidance, table-cell geometry, reading order, serialization, and existing production regression corpus must all pass.
7. Reserve the held-out test split for one frozen-policy execution. No threshold changes, control substitutions, or post-hoc exclusions after development results.

## Decision outcomes

- If an independently frozen arm meets its preregistered benefit/cost/conflict gates on held-out data, it becomes a candidate for a separate production-change review.
- If none does, retain provenance/instrumentation and no semantic gate change.
- Broad non-table crop invocation, shape-rule admission, and a selector tuned on 036 remain out of scope.
