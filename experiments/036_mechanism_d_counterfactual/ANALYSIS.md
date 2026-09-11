# Experiment 036 — Analysis and Production Decision

## What the experiment demonstrates

Explicitly calling the existing Table Transformer on a blocked D2 region crop can create a valid, GT-relevant, isolated table owner: 17 of 34 frozen D2 cases meet the preregistered valid-recovery definition. This is direct evidence that the region/crop ownership boundary in 035 leaves recoverable evidence behind.

It does **not** justify broad crop admission. The same forced-crop structure path generated a structurally valid, isolated table on 104 of 145 no-GT-table control crops (71.72%). Moreover, 8/34 treatment cases overlap a pre-existing production table strongly enough to be duplicate/cross-region ownership risks. Table Transformer structure success is therefore neither a table truth oracle nor a safe ownership decision.

The detector observation is more selective than forced structure (14/34 D2; 38/145 controls), but its 23/145 detector-plus-valid-control count remains substantial. It was collected as a separate layer, not tuned into a new policy. No threshold or composite rule was selected after outcomes.

## Relation to 035

036 strengthens 035's central conclusion that Mechanism D is real and specifically actionable at the ownership boundary. It also strengthens the conservative part of that conclusion: broad hard-gate relaxation and 033-shape admission remain unjustified. The result is downstream evidence; 035's D2 definition, counts, proxy-occlusion null result, and final report remain frozen and unchanged.

## Production recommendation

Recommended next production action: **B — provenance/instrumentation only**, plus the already-separate deterministic role-normalization candidate only after its route-specific regression suite is defined. Add auditable per-region fields for the label gate, supplied crop, detector boxes, structure result, proposed owner, and collision decision. This makes future selective policies measurable without silently changing IR semantics.

Do not yet make any semantic production change that broadly invokes Table Transformer on non-table regions, relaxes `region.label.lower() == "table"`, auto-promotes forced-crop structure, or promotes the 033 shape rule. The measured 50.0% D2 recovery benefit is outweighed by a 71.72% false-positive rate on this preregistered non-table-crop control arm and a 23.53% treatment duplicate/conflict rate. A future selective policy would need an independently preregistered classifier, held-out controls, explicit conflict resolver, and end-to-end IR ownership regression tests before any deployment consideration.

## Limitations

The false-positive estimand is one largest non-table region from each eligible frozen Phase 13 page; it is not a corpus-wide rate over every region. The 5 pages with only table-labelled regions are excluded from this arm but remain accounted for by 035 Phase 13. CPU execution measures functional behavior and wall time but cannot establish L4 VRAM or throughput. The crop detector/structure checkpoints are the existing production backend models and thresholds, but model-loading warnings about unexpected batch-norm tracking keys were consistent normal checkpoint-load reports rather than execution failures.
