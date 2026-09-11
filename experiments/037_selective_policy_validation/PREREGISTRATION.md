# Experiment 037 preregistration

**Status:** frozen design; no held-out counterfactual inference has been run
at the time this file was created.

## Question

Can a pre-treatment selective policy capture recoverable strict-D2 regions
while avoiding the unsafe forced-crop admission demonstrated in 036?

## Population and split

The population and document-disjoint split are built by
`build_population.py` under `CORPUS_PROTOCOL.md`.  035/036 identities are
explicitly prohibited from the manifest.  A treatment candidate is a source
GT table whose best 035-compatible relevant layout region is not labelled
`table`; a control is the frozen largest eligible non-table region.  A
candidate's GT geometry is used only for outcome scoring, never as a feature.

## Frozen pre-treatment feature contract

Only these features may be used: raw and normalized role; layout confidence;
region area fraction; aspect ratio; region index; count of page layout
regions; OCR child count; route; and independently available page-level
detector evidence.  Forced-crop structure, forced-crop detector output, GT
geometry, post-treatment ownership, and any outcome-derived field are
prohibited predictors.

## Policy families and selection protocol

Development may compare only: (A) role-normalization-only, (B) a transparent
rules policy over the frozen features, and (C) abstain-all.  A learned model is
not allowed: the expected candidate population is too small to support one.
The final policy is chosen using development outcomes only and written to
`FROZEN_POLICY.md` and `frozen_policy.json` before any held-out
counterfactual call.

## Outcome and ownership rules

The 036 frozen `assess_forced_crop` criteria are reused: valid structure,
isolated ownership, GT IoU >= 0.3, and no existing production-table overlap
IoU > 0.1.  The resolver never overwrites a production owner; an existing
material overlap or ambiguous owner is rejection/abstention with provenance.
Results separately report admission, invocation, detection, structure,
ownership, GT relevance, conflict, valid recovery, final canonical-IR delta,
and runtime.

## Estimands and decision

Primary: held-out `valid recovery among admitted / all held-out recoverable
strict-D2 candidates`, when the denominator is nonzero.  Secondary rates:
control false positive among admitted controls, conflict among admitted cases,
admission/invocation burden, and abstention.  No production budget is assumed;
the analysis reports a sensitivity/Pareto table.  The test run is executed
once after policy freezing.  Its all-candidate outcome calls are solely a
one-shot measurement oracle for the recall denominator and are not policy
tuning.

## Failure handling and no post-hoc changes

Operational failures remain records with their original denominator.  Missing
or invalid source data is documented, not replaced.  No test-driven feature,
threshold, control, split, or definition changes are allowed.  If no strict
D2 candidate occurs, the result is an inability to validate selectivity—not
evidence that the production gate is safe.
