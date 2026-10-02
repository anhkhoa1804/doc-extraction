# Classic vs E2E v1

**Comparison status: NOT DIRECTLY COMPARABLE.** Classic completed all 180 pages; E2E did not. No metric deltas are calculated.

| Metric | Classic (N) | E2E full (N) | Delta | Status |
|---|---:|---:|---:|---|
| Text Edit distance | 0.573988 (168) | — | — | E2E full not measured |
| Table Edit distance | 0.712518 (50 pages) | — | — | E2E full not measured |
| Table TEDS | 0.398111 (64 tables / 50 pages) | — | — | E2E full not measured |
| Table structure TEDS | 0.632317 (64 tables / 50 pages) | — | — | E2E full not measured |
| Reading-order Edit distance | 0.584992 (178) | — | — | E2E full not measured |
| Formula Edit distance | 0.985389 (35) | — | — | E2E full not measured |
| Success rate | 100% (180) | 87.8% written predictions, incomplete | — | Not comparable; prediction file count is not success rate |
| Warning rate | 0% (180) | — | — | E2E aggregate metadata absent after interruption |
| Runtime | 1190.221 s (180) | >300 s/page operation observed | — | Different/incomplete workload |

The five-page smoke metrics are reported separately. They are not used as the E2E column above because their selected population differs from the complete frozen baseline population.
