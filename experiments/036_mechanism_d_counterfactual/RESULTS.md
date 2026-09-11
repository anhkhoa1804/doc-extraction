# Experiment 036 — Results

## Execution record

The preregistered 34 strict-D2 treatment cases and all 145 eligible frozen Phase 13 non-table controls completed successfully. Five of the 150 Phase 13 pages had no non-`table` layout region; these pre-inference exclusions are recorded in `population_manifest.json` and are not part of the control denominator.

The intended L4 was unavailable in this session: `nvidia-smi` could not communicate with the NVIDIA driver and showed no usable GPU workload. Execution therefore used one CPU worker from `/home/leanhkhoa150204/.venvs/doc-extraction-linux312`, with `torch 2.13.0+cpu`, `transformers 5.16.1`, `timm 1.0.29`, and the locally cached production model IDs `microsoft/table-transformer-detection` and `microsoft/table-transformer-structure-recognition`. `HF_HUB_OFFLINE=1` and `TRANSFORMERS_OFFLINE=1` prevented model drift or downloads. The smoke and all full-arm raw records are isolated under ignored `results/`.

The shell session time limit interrupted several CPU control invocations after completed case files had been written. The runner resumes only absent/non-success records; it did not rerun any successful case. This is an execution-scheduling incident, not a data exclusion or methodology change.

## Primary and secondary results

| Metric | Treatment (N=34) | Eligible controls (N=145) |
| --- | ---: | ---: |
| Specialist invocation succeeded | 34 (100.0%) | 145 (100.0%) |
| Crop detector found >=1 table | 14 (41.18%) | 38 (26.21%) |
| Forced-crop structure valid | 31 (91.18%) | 104 (71.72%) |
| Isolated ownership established | 31 (91.18%) | 104 (71.72%) |
| Valid recovery / false positive | **17 (50.0%)** | **104 (71.72%)** |
| Duplicate ownership | 8 (23.53%) | 3 (2.07%) |

`17 / 34` is the preregistered primary valid-recovery fraction. It requires valid grid geometry, isolated owner mapping, GT IoU >=0.3, and no overlapping current-production table; it is not the 033 eligibility count and it is not merely a detection count.

Detector-plus-valid-grid evidence is 14/34 treatments and 23/145 controls. Applying the same no-duplicate and GT-geometry checks leaves 7/34 treatments for that more selective, **post-analysis descriptive** intersection; it is not a newly promoted decision rule. The observed control rate demonstrates why forced structure recognition alone cannot be admitted into production.

Case runtime across the 179 full-arm records was 2,875.5174 seconds total; min 0.169 s, median 1.264 s, max 122.758 s. CPU mean case runtime was 16.06 s. CUDA VRAM is `null` by design because CUDA was unavailable. The post-036 forensic audit corrected a stale earlier aggregate (2,876.291 seconds) after the final two resumed control records landed; no scientific outcome count changed.

Machine-readable aggregate: `summary.json`. Raw per-case records contain crop geometry, source hashes, model/device metadata, detector boxes, structures, conflict checks, and runtime, and intentionally remain untracked.
