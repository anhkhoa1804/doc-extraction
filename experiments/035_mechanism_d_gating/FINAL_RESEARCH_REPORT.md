# 035 final decision — Mechanism D

## Decision

Mechanism D is real in this production pipeline: 34 of 665 OmniDocBench GT
tables (5.11%) satisfy the frozen strict D2 definition, namely a relevant
region exists but is non-`table` labelled and therefore cannot own a table in
the final IR. This is a measured region/crop-gating loss, **not** proof that
Table Transformer was absent from whole-page detection.

It is a production correctness and observability defect at the IR ownership
boundary, but the evidence does not justify broad label relaxation yet. The
frozen 033 shape rule makes 11/34 D2 cases eligible only as an upper bound;
it fires on 55/105 eligible non-table regions, and Phase 13 found five
table-labelled regions on the frozen no-GT-table sample (three harmless,
two ambiguous). No recovery intervention was executed, so recovery benefit is
not measured.

## Phase 16 — root-cause distribution

The full 665-table funnel is D0=561, D1=41, D2=34, D4=25, D6=3, D7=1,
and D3=0. Thus direct strict gating is 5.11%; upstream misses and specialist /
structure failures are separate non-D causes (10.38% combined). The 34 D2
records associate with wrong role labels (picture=14, text=10,
document_index=7, code=1; remaining records are multi-region cases), not a
single established upstream cause.

- Geometry/shape: 11/34 D2 match the frozen rule. This is eligibility
  association, not a causal explanation or demonstrated recovery.
- Role ambiguity: the wrong-label distribution strengthens 032's concern,
  but OmniDocBench does not prove a particular role-map bug caused each D2.
- Occlusion: proxy-occluded pages have D2=0/37 versus 34/628 clean. The
  proxy is page-level and not a true stamp label, so this weakens a broad
  stamp explanation without overturning 030's route/OCR/layout finding.
- Route/OCR/layout and contamination: these remain supported historical
  mechanisms, but this corpus did not identify them as the cause of each D2.
- Unresolved: causal attribution within D2 requires controlled reruns with
  route/layout labels and instrumented per-region specialist outcomes.

## Phase 18 — production options

| Option | Benefit / mechanism | Cost and evidence | Decision |
|---|---|---|---|
| No change | Preserves present precision/cost | Leaves measured 34/665 region-ownership losses | Not sufficient alone |
| Conservative region-gate repair | Normalize audited roles and make ownership/provenance explicit | Addresses known label/role ambiguity; needs regression corpus | Production engineering candidate |
| Shape-gated admission | At most 11/34 become eligible | 11/34 is not recovery; 55/105 non-table fires show substantial exposure | Research experiment only |
| Broader page-level specialist invocation | May separate page detection from IR ownership | Compute and false-positive/ownership effects unmeasured; D2 does not prove absence of page invocation | Research experiment only |
| Role/label normalization | Addresses 032's independent mapping defect candidate | Strong source/history evidence; require route-specific tests | Production candidate after regression tests |
| Provenance/instrumentation | Records region gate, page-level detection, crop invocation and owner assignment | Low semantic risk; directly resolves remaining ambiguity | Prioritize now |

## Phase 19 — reassessment of 031–034

| Prior claim | Reassessment |
|---|---|
| 031: table-label gating exists | **Strengthened** — D2=34/665 full population |
| 031: label flips can matter | **Strengthened** at region ownership; page-level non-invocation remains unproven |
| 030: stamp alone is insufficient | **Strengthened** within this proxy-limited corpus |
| 030: route/OCR/layout interaction stronger | **Unchanged** — not retested causally here |
| 032: role ambiguity is a production candidate | **Strengthened** by wrong-label distribution, not proven causal per case |
| 033: shape rule is not a recovery oracle | **Strengthened** — 55/105 exposure and only upper-bound eligibility |
| 034a: external table scores do not diagnose ownership | **Strengthened** — 571/665 TEDS coverage is distinct from this 665/665 funnel |

## Phase 20 — production decision

Production should first add provenance and deterministic role normalization,
then run a controlled per-region counterfactual: for a preregistered D2 set,
invoke Table Transformer on the same crop, retain page-level detections
separately, and score final ownership, structural validity, and non-table
false positives. Do not relax the hard gate, promote 033, or claim 11/34
recovery before that experiment. 035 therefore closes as **PARTIALLY_VALIDATES
Mechanism D as a real, secondary production correctness issue**.

Evidence: `phase13_identity_ledger.json`, `false_positive_tables.json`,
`table_region_matching.json`, `table_failure_funnel.json`,
`table_shape_on_gt.json`, `stamp_occlusion_analysis.json`,
`specialist_invocation_map.json`, `external_metric_reconciliation.json`, and
`counterfactual_gating.json`.
