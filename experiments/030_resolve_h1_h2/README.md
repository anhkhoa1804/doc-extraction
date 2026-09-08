# 030 — Resolve H1 and H2

**Status: COMPLETE. No production code changed. No historical scorer or
artifact changed.** H1 and H2 were extracted verbatim from the frozen 029
report (`hypotheses.json`), not from memory, and pushed to falsification
using direct source/IR/paired-artifact evidence.

See `FINAL_REPORT.md` for the full causal falsification study. This file is
the reproducibility index.

## Verdicts, in one line each

- **H1** (stamp/occlusion elevates row-synthesis escape via detector bbox
  undershoot): **PARTIALLY_SUPPORTED, confidence MEDIUM.** The correlational
  rate-elevation is confirmed (29.31% vs 4.70%, exact reproduction of 029);
  the mechanistic severity claim is contradicted (stamp/occlusion defects
  are *smaller* in magnitude, 1.10–1.47px, than non-stamp defects, up to
  15.40px). A cleaner, unconfounded trigger was found instead: OCR-recognizer
  choice alone flips the defect on/off on the same non-stamp document
  (`hc_encoding_vi`, 0px under EasyOCR vs 14.4–15.4px under four other
  recognizers).
- **H2** (the escape defect is spatially bounded and never crosses into a
  neighboring table): **SUPPORTED, confidence HIGH.** 0 of 265 re-derived
  escaping cells intersect any other table. The evaluator was independently
  proven capable of detecting contamination via a deliberately constructed
  adversarial case, so the null result is not a broken-checker artifact.

## Priority reassessment

**Unchanged.** Table-label gating under stamp/occlusion (025's Class D)
remains the higher-value research target — H2's SUPPORTED verdict removes
the one scenario (contamination found) that would have elevated
row-synthesis above it, and H1's weakened stamp/occlusion story does not
touch gating, which is a structurally separate code path
(`base.py:747` vs `base.py:505-576`).

## Reproducibility

| script | artifact | phase |
| --- | --- | --- |
| `hypotheses.py` | `hypotheses.json` | 0 |
| `falsification_matrix.py` | `falsification_matrix.json` | 1 |
| `resolve_h1.py` | `h1_resolution.json` | 2 |
| `resolve_h2.py` | `h2_resolution.json` | 3 |
| `negative_evidence.py` | `negative_evidence.json` | 4 |
| `paired_comparisons.py` | `paired_comparisons.json` | 5 |
| `orthogonality.py` | `orthogonality.json` | 6 |
| `provenance.py` | `provenance.json` | 7 |
| `severity_impact.py` | `severity_impact.json` | 8, 10 |
| `counterfactuals.py` | `counterfactuals.json` | 9 |
| `adversarial_controls.py` | `adversarial_controls.json` | 11 |
| `verdicts.py` | `verdicts.json` | 12, 13 |
| `research_lineage_update.py` | `research_lineage_update.json` | 14 |

Input: `experiments/029_deep_forensic_replay/results/all_tables.json` and
`causal_attribution.json` (read, never modified), plus direct re-reads of
the same frozen `document.json` files 029 replayed (023–025's gitignored
`_runs/` trees). No new extraction; CPU-only throughout. The GPU was
PROTECTED (Research-No.1 workload) for the entire milestone.

**NO PRODUCTION CODE CHANGED.** `src/`, `configs/`, `tests/`,
`run_benchmark.py`, `run_ab.py` are byte-identical to the frozen baseline.
`experiments/029_deep_forensic_replay/` is untouched — verified via
`git status --porcelain`.
