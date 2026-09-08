# Milestone 032 — Role Ambiguity & Evidence-Based Routing

Research-only, CPU-only, read-only over historical IR plus a small set of
synthetic adversarial controls. `src/` is untouched. See `FINAL_REPORT.md`
for the full report.

## Question

Does the current document IR/routing architecture lose useful uncertainty
by collapsing upstream region-role evidence into a single hard label too
early?

## Answer (short)

Yes, measurably — and no, not yet safely actionable. The evidence vector
(`table_shape_score`) is strictly more stable than the observed detector
label across repeated extraction arms of the same document, for the
documents where a direct comparison is possible (`role_stability.json`).
But this milestone's own 20-case synthetic adversarial test
(`adversarial_controls.json`) found a more severe false-positive mode than
031 ever tested: ordinary single-column prose can satisfy the current
scoring rule using row-based evidence alone. Decision: **EXPERIMENTAL**.

## Scripts (run in this order to reproduce)

```
python role_contract.py              # Phase 1-2: IR schema + label-map audit
python role_ambiguity_population.py  # Phase 3: real population, by category
python role_evidence_schema.py       # Phase 4: evidence-vector dimensions
python role_transition_matrix.py     # Phase 6: route-flip transitions
python role_stability.py             # Phase 7: evidence vs role stability
python negative_controls.py          # Phase 11: extends 031's hard-negative search
python adversarial_controls.py       # Phase 12: 20 synthetic role cases
python routing_policy_results.py     # Phase 9-10: 4 policies compared
python provenance_design.py          # Phase 15: additive provenance shape
python production_assessment.py      # Phase 16-18: cost + architecture + readiness
python recommendation.py             # Phase 19: research-frontier reassessment
```

All scripts are deterministic (verified byte-identical across two runs,
see `FINAL_REPORT.md` §22) and read from this repo's existing 023-031
artifacts plus their own prior-script outputs within `experiments/
032_role_ambiguity/`. No production code was modified.
