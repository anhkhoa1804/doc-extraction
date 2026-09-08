# 029 — Deep Forensic Replay & Causal Attribution

**Status: COMPLETE. No production code changed. No historical scorer changed.**

See `FINAL_REPORT.md` for the full 18-section forensic report. This file is
the reproducibility index.

## What this milestone found, in one paragraph

028's four structurally-invalid tables and its false-negative document are
not SCAN-49 artifacts. Replayed across 31 arms / 1,378 document-arm pairs /
1,984 table instances spanning 023–025, **every one of 102 structurally-
invalid table instances (100%, not a sample) traces to one exact mechanism**
in `pipelines/base.py:505-576`: tier-3 row synthesis admits an OCR token by
testing whether its *center* lies inside `table.bbox`, then builds the
synthesized cell from the token's raw edges — which can extend past
`table.bbox` even when the center does not — and `table.bbox` is never
expanded afterward. The escape is small (1.1–14.4px at 200 DPI) and 100%
carries the synthesis marker `confidence == 0.5`. Separately, Layer 1's
order metric has a third blind spot beyond 027's table-serialization
finding: it never reads `Page.reading_order` at all, only raw element-list
order — 19 document-arm pairs exist where list order coincidentally looks
right while production's own computed reading order is wrong.

## Reproducibility

| script | artifact | phase |
| --- | --- | --- |
| `cohort_inventory.py` | `cohort_inventory.json` | 1 |
| `replay_all_arms.py` | `results/*.json`, `results/all_arms.json`, `results/all_tables.json` | 2 |
| `causal_attribution.py` | `causal_attribution.json` | 4/5 |
| `false_negative_case.py` | `false_negative_case.json` | 6 |
| `order_decomposition.py` | `order_decomposition.json` | 7 |
| `backend_stratification.py` | `backend_stratification.json` | 8 |
| `lineage.py` | `lineage.json` | 9 |
| `expanded_controls.py` | `expanded_controls.json` | 10 |
| `measurement_matrix.py` | `measurement_matrix.json` | 11 |

Input: gitignored `_runs/` trees of 023, 024, 025 (regenerable from those
milestones' own scripts). 028's four Layer-2 views (`table_text.py`,
`table_structure.py`, `page_order.py`, `structural_integrity.py`) are
**imported**, never copied. `_norm`, `score`, `document_text` are imported
from the frozen Layer-1 scorer.

CPU-only throughout. The GPU was PROTECTED (100% util, Research-No.1 PID
61016) for the entire milestone and was never touched — every artifact used
here already existed on disk from prior milestones.

**NO PRODUCTION CODE CHANGED.** `src/`, `configs/`, `tests/`,
`run_benchmark.py`, `run_ab.py` are byte-identical to the frozen baseline
(`b9b87d1`). No historical artifact was mutated — every read is read-only.
