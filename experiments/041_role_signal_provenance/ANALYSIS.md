# Experiment 041 analysis status

## Executive conclusion

Experiment 041 cannot execute its primary identification study on the frozen
039 development population. Every one of the 15 development `document_index`
regions is already a frozen D2 region, leaving zero independently selected
same-role negative controls. Consequently 040's `2/15` `document_index`
recovery result remains an outcome among known D2 failures, not a safety or
false-positive estimate. No 041 baseline provenance replay, treatment, or role
normalization routing counterfactual was run. The appropriate scientific
decision is `REFINE_EXPERIMENT`: expand or redesign the development population
to obtain natural same-role controls, while preserving the 039 held-out set.

## Verified facts

* 039 manifest: 269 records, 136 development, 133 held-out, 17 development
  groups, and six development categories.
* 039 development baseline layouts contain 15 raw `document_index` regions.
* The 15 identities are exactly the frozen D2 identities listed in
  `CONTROL_POPULATION.md`.
* Therefore eligible same-role controls are `0/15`.
* 040 previously verified 28 unique D2 units, 766 controls, four valid
  recoveries, 342/766 material control false positives, and 20/794
  operational failures. Those values are not 041 outcomes.
* `heldout_accessed = false` for 041 execution: no held-out page was processed,
  replayed, used for feature generation, or used to select a case.

## Hypothesis status

| hypothesis | status | reason |
| --- | --- | --- |
| H1 `document_index` is a mechanism-specific signal | INCONCLUSIVE | 040 D2 enrichment exists, but same-role controls are 0/0 and the role may be a source-family proxy. |
| H2 D2 implies specialist absence | INCONCLUSIVE | 041 did not obtain baseline invocation telemetry; D2 semantics do not imply absence. |
| H3 wrong-role mechanism | PLAUSIBLE ONLY | 040's 3/3 wrong-role recoveries are descriptive and no 041 routing counterfactual ran. |
| H4 universal table re-treatment | REJECTED | 040's broad intervention caused 342/766 material control false positives and 372/766 harmful/conflict outcomes including operational failures. |
| H5 geometry-only selection | WEAKENED | 040's area rule selected 3 controls and recovered 0/7 D2 units; it is not an identified mechanism. |

## What was not learned

No 041 estimate exists for same-role control false-positive exposure, page-wide
baseline invocation distribution, routing changes under role normalization, or
end-to-end evidence impact. Reporting zero for any of those would confuse
non-execution with a negative scientific result.

## Recommendation

Do not run another crop intervention on the current population. Freeze a new
development-only corpus expansion containing naturally occurring
`document_index` controls across independent groups and categories, with the
control-selection rule fixed before any treatment. Then run Module B provenance
and Module C routing-only analysis before re-opening Module A. The 039 held-out
records remain reserved for the final policy evaluation and must not be used to
repair this missing-control design.
