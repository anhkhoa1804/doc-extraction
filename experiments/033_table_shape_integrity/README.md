# Milestone 033 — Table-Shape Evidence Integrity & Routing Boundary Revalidation

Research-only, CPU-only. `src/` untouched. See `FINAL_REPORT.md` for the
full report.

## Question

Was 032's discovered role ambiguity fundamentally a role-classification
problem, or was a significant portion caused by an inadequate
table-shape evidence rule?

## Answer (short)

**Both** — as separate mechanisms. A substantial, demonstrated portion
(Chapter9-pattern banners, single-column prose) was a measurement defect
in `table_shape_score`'s row/column conjunction, now largely fixed by
Candidate E (`row_bands>=3 AND col_bands>=2 AND children_per_row_band>=1.5`).
But multi-column prose survives every candidate tested — a genuine
structural indistinguishability, not a threshold artifact. Decision:
**EXPERIMENTAL**.

## Scripts (run in this order to reproduce)

```
python known_failure.py              # Phase 2: minimal formal counterexample
python candidate_designs.py          # Phase 3: candidates A-E
python candidate_results.py          # Phase 4/7: measurement-safety + paired eval
python adversarial_results.py        # Phase 5/8: 46-case synthetic suite
python corpus_recheck.py             # Phase 6: full corpus re-search + real-prose sweep
python routing_policy_results.py     # Phase 10: policies re-evaluated
python threshold_robustness.py       # Phase 11: structural-floor sensitivity
python out_of_population_results.py  # Phase 12: document-family holdout
python provenance_safety.py          # Phase 13: provenance chain re-verification
python production_assessment.py      # Phase 14-16: downstream/cost/decision
python recommendation.py             # Phase 17: the central research question
```

All scripts are deterministic (verified byte-identical across two runs)
and read from 031/032's existing artifacts plus their own prior-script
outputs within `experiments/033_table_shape_integrity/`. No production
code was modified. No `production_patch/` directory was created (decision
was EXPERIMENTAL, not SHIP_CANDIDATE).
