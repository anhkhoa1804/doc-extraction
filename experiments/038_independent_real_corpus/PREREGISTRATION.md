# Experiment 038 preregistration

**Status:** frozen before policy outcomes and before any held-out
counterfactual inference.

## Hypothesis and lineage

035 established a real region/crop ownership boundary. 036 showed that some
blocked crops are recoverable but broad forced admission is unsafe. 037 showed
that a small synthetic corpus cannot activate this question. 038 asks whether
a selective pre-treatment policy can generalize on independent real documents.
035 and 036 remain immutable; 037 remains blocked historical evidence.

## Frozen corpus

DocLayNet validation (official 1.0.0 core archive), selected and split by
`acquire_doclaynet.py` under `CORPUS_PROTOCOL.md`.  The source-document group
is `(collection, doc_name)`.  Exactly 10 groups are development and 10 are
held-out test, with no group overlap.  Only `precedence == 0` annotation rows
are eligible.  The exact manifest, source/member SHA-256 values, page IDs,
and table IDs are frozen before treatment.

## Pre-treatment features

Allowed: raw and normalized production role; layout confidence; region area
fraction and aspect ratio; page region count; OCR child count; route;
independently available page-level detector evidence; existing production
ownership candidates and provenance.  Forbidden: GT geometry as a feature,
forced-crop detector/structure outputs, post-treatment ownership, or any
valid-recovery outcome.

## Activation and policies

The unchanged production baseline first determines natural D2-like candidates.
No policy work occurs if development D2 is zero or inadequate.  If activated,
development may compare only role-normalization-only, a transparent frozen
rules selector, and abstain-all.  A learned classifier is disallowed unless a
separate preregistered amendment demonstrates sufficient development size.

## Counterfactual and ownership outcome

For admitted candidates only, the existing 036 crop-counterfactual helper and
assessment contract are reused: valid structure, isolated ownership, GT IoU
>= 0.3, and no existing production-table overlap IoU > 0.1.  Existing owners
are never overwritten; material overlap or ambiguous ownership abstains and
preserves rejected provenance.  Detection, structure, ownership, relevance,
conflict, canonical-IR delta, and runtime remain separate measures.

## Estimands and held-out rule

Primary estimand, if measurable: valid recovery among admitted divided by all
held-out recoverable D2-like candidates.  Secondary estimands are admission,
invocation, abstention, control false-positive, conflict, and compute rates.
No production budget is invented; sensitivity/Pareto summaries are reported.
After development selection, `FROZEN_POLICY.md` and `frozen_policy.json` are
written.  Held-out evaluation then runs exactly once with no threshold,
feature, control, split, or exclusion changes.

## Failure handling

Operational failures remain in denominators and are classified.  Empty or
insufficient D2 populations stop the study without manufacturing labels or
reusing 036 outcomes.  Raw predictions remain ignored; compact manifests and
reports are tracked.
