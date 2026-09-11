# Experiment 036 — Same-Crop Table Transformer Counterfactual

Status: preregistered before any 036 treatment inference. This experiment is downstream of, and does not amend, frozen Experiment 035.

## Population and immutable sources

The treatment population is every one of 035's 34 strict D2 GT-table identities: a relevant layout region exists but is not `table` labelled, so current production cannot make it a table owner. `population_manifest.json`, generated only from the frozen 035 matching evidence and source page runs, is the complete identity list, exact target region geometry, input hashes, and source-run paths. It must contain exactly 34 treatment cases or execution aborts.

The control frame is all 150 pages in 035's frozen, stratified Phase 13 no-GT-table sample. One control crop per *eligible* page is selected before treatment outcomes: among its non-`table` layout regions, choose the largest-area box (ties: lowest layout index). A page with no non-`table` region is excluded with an explicit `no_non_table_layout_region` record; its table-labelled false-positive evidence belongs to 035's separate Phase 13 analysis, not this non-table-crop arm. Thus the control false-positive estimand applies to one primary non-table region on each eligible frozen no-table page, not to all possible regions.

Source artifacts are `035_mechanism_d_gating/table_region_matching.json`, `non_table_sample_manifest.json`, and `final_evidence_index.json`; their SHA-256 values are frozen in the manifest. Source images are from 034a's full OmniDocBench snapshot.

## Treatment and measured layers

For each exact blocked crop, reuse the production `TableTransformerBackend` on the same source image. The experimental helper makes two observations without changing production behavior:

1. It runs the detector inside the supplied crop and records detector boxes separately.
2. It runs structure recognition on the supplied crop itself, exactly mirroring the production region path when a region is labelled `table`.

No labels, crop bounds, thresholds, model IDs, production page output, ownership gate, or 035 artifact may be altered. Current production output is read only to measure overlap conflict.

`specialist invocation` means the helper returned. `detection` means at least one crop-detector box. `structural validity` uses 035's geometric criterion: nonempty positive grid and fewer than 20% of cell boxes escaping the table box by more than one pixel. `isolated ownership` means a structurally valid forced-crop table would map to its supplied owner crop using the production merge IoU rule (>0.1). A treatment is a **valid recovery** only if at least one target has valid structure, isolated ownership, table-box IoU >=0.3 to the frozen GT table, and no existing production table has IoU >0.1 with it. This is intentionally stricter than detection or a valid grid.

For controls, a false positive is a structurally valid, isolated-owner forced-crop table on a no-GT-table page. Duplicate ownership and cross-region conflict mean an existing production table overlaps the proposed table by IoU >0.1.

## Estimands, compute, and execution

The primary estimand is valid recoveries / 34. Secondary quantities are invocation, crop-detection, structural-validity, isolated-ownership, duplicate/conflict, and control false-positive rates; all are separately reported. Case runtime, per-process CUDA peak allocation when available, device snapshot, model IDs/config thresholds, library versions, source hashes, and output path are recorded per run.

Execution is one worker and conservative GPU use: first one D2 smoke case, then all 34 treatments, then every eligible control recorded in the manifest. A completed success record is never rerun. Operational exceptions remain failure records; no difficult case may be removed. Raw case outputs live under `results/` and remain untracked; compact `summary.json`, documentation, code, and manifest are tracked.

## Exclusions and no-tuning rule

There are no outcome-based exclusions. A missing source image, missing frozen run, invalid bbox, unavailable model, or execution exception is recorded as a failure. The existing model IDs and its production thresholds (detection 0.7, structure 0.6) are fixed. No threshold, crop, control, owner criterion, shape rule, or classification rule will be changed after outcomes are inspected. Any unavoidable engineering correction will be documented as an engineering constraint, separately from methodology, and require rerunning the affected arm.
