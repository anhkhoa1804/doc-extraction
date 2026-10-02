# Conditional Classic vs E2E v2

**Full 180-page paired quality is unavailable**: two E2E predictions are missing. The values below condition on E2E completing, so the population is outcome-conditioned and not an unbiased estimate of the frozen manifest.

| Metric | Classic | E2E | Delta (E2E − Classic) | N | Status |
|---|---:|---:|---:|---:|---|
| Text ED | 0.573195 | 0.044909 | -0.528286 | 166 | CONDITIONAL |
| Table ED | 0.712518 | 0.567469 | -0.145049 | 50 | CONDITIONAL |
| Table TEDS | 0.413877 | 0.842940 | +0.429063 | 50 | CONDITIONAL |
| Table structure TEDS | 0.673171 | 0.872106 | +0.198935 | 50 | CONDITIONAL |
| Reading-order ED | 0.582641 | 0.165855 | -0.416786 | 176 | CONDITIONAL |
| Formula ED | 0.985389 | 0.079500 | -0.905889 | 35 | CONDITIONAL |

Per-page edit-distance deltas use the exact same success-conditioned predictions and GT; negative favors E2E. Text: 161 pages improve, 5 regress, 0 tie (N=166). Formula: 35 improve of 35. Reading order: 128 improve of 176. Table edit: 42 improve of 50.

Across 64 exactly paired table instances, mean TEDS was 0.398111 Classic vs 0.844484 E2E; structure-only was 0.632317 vs 0.871228. No composite score or significance test is reported.

Frozen manifest SHA `bb99b04e425a6b337252c7fa56dbf01fae94623181b06ab39d8b223abbe16fc6`, evaluator `193627ae9e97d89188468ed1ee3b7a856ff76044`. Full Classic 180-page metrics remain separate; no cross-population score delta is presented.
