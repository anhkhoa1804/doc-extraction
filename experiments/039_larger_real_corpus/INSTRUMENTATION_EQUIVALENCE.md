# 039 Instrumentation Equivalence Gate

Status: **PASS**

The observational table-invocation telemetry was evaluated at commit
`94415663c288bb13f67ccd9f42d68ac893de648e` on the CPU environment. The
deterministic development-only sample was:

| image id | role | invocation mode observed |
| ---: | --- | --- |
| 2819 | known development D2 table page | `LABELLED_CROP` |
| 2788 | development table page | `LABELLED_CROP` |
| 2673 | development non-table control page | `PAGE_WIDE` |
| 2780 | development non-table control page | `LABELLED_CROP` |

All four records completed in both arms and all four instrumented versus
un-instrumented pairs were equivalent. The comparison canonicalized only
arm-specific rendered-image paths, timestamps, and runtime fields. Final IR,
table and cell geometry, ownership, reading order, warnings, errors, and
fallback decisions were compared otherwise exactly.

The instrumented telemetry files were complete with two records per sample:
the table-specialist decision and page assembly. Focused unit tests also cover
`NOT_INVOKED`, model-load failure recording, and the distinction
`PAGE_WIDE != LABELLED_CROP != NOT_INVOKED`.

Evidence reference: ignored raw output at
`results/instrumentation_equivalence_v4/equivalence_summary.json`.

The runner explicitly rejected held-out records; `heldout_accessed=false`.
No treatment or selector was executed; `treatment_executed=false`. The frozen
039 baseline output and index were not overwritten.

This is an engineering/observational equivalence result only. It does not
establish treatment recovery, policy safety, or held-out performance.
