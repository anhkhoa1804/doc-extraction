# Experiment 037 status

**State: `BLOCKED_NO_DEVELOPMENT_ACTIVATION` (not a completed validation).**

037 has a frozen, document-group-disjoint source population: 15 independent
synthetic source PDFs, split into 7 development and 8 held-out documents.
None is an OmniDocBench/035/036 identity.  The source-geometry and split
contracts are tracked in `population_manifest.json` and are locked by
`tests/test_037_population.py`.

Pre-treatment baseline discovery was attempted sequentially on CPU because no
CUDA device was available.  Six of the seven development documents completed
the production baseline.  In every completed development record the
source-table-overlapping layout region was labelled `table`, so there were
**0/6 discovered strict-D2 candidates**.  The seventh document,
`ord_financial_report_en`, was interrupted during Docling model setup by the
execution environment's short process lifetime; it is an explicit operational
incomplete record, not an exclusion or a negative result.

No forced-crop counterfactual has been invoked for 037.  No held-out
counterfactual, final policy, `FROZEN_POLICY.md`, or performance result exists.
Selecting a policy from zero triggered development candidates—or using 036's
outcomes to fill that gap—would violate the preregistration.  Likewise,
relabeling synthetic tables to manufacture D2 cases would test an artificial
intervention, not selective generalization.

The next activation requirement is a new document-group-disjoint corpus with
enough naturally occurring strict-D2 candidates in development.  It must have
source table geometry, relevant non-table controls, and a runtime environment
that can finish the unchanged baseline (an available L4 is preferred).  Until
then the production recommendation remains the frozen 035/036 one:
provenance/instrumentation first; no broad table-gate relaxation or selective
crop policy deployment.
