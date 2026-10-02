# E2E Inference Isolation and Paired Baseline

| Dimension | Classic | E2E | Status |
|---|---:|---:|---|
| Success rate | 180/180 (100%) | 178/180 (98.889%) | two hard timeouts |
| Timeout rate | 0% | 1.111% | measured |
| Text ED | 0.573988 (N=168) | 0.044909 (N=166 conditional) | not same full denominator |
| Table TEDS | 0.413877 (N=50) | 0.842940 (N=50 conditional) | conditional |
| Table structure TEDS | 0.673171 (N=50) | 0.872107 (N=50 conditional) | conditional |
| Reading-order ED | 0.584992 (N=178) | 0.165855 (N=176 conditional) | not same full denominator |
| Formula ED | 0.985389 (N=35) | 0.079500 (N=35 conditional) | conditional |
| Runtime/page | mean 6.609 s | mean 41.977 s | E2E ~6.35x slower mean |

## 1. Repository state
Inference HEAD `8eaa386da5c5b1ce3a3b75158669d83c1792c351`; worktree dirty and recorded in `e2e-full-v2.json`. Source snapshot SHA-256 `a65d5d7a2aa7e77071fc0ff678ec1dbcf4bc4b4e27081f69d8457fd2fdcb4638`. After inference, the timeout diagnostic was corrected to report elapsed time for the whole guarded operation (the run artifact had displayed worker-request elapsed against the full configured limit), and Ruff import sorting was applied. Neither change affects inference, predictions, mapping, or the 300-second policy.

## 2. Inference isolation architecture
Parent supervises one persistent worker in a private POSIX process group using bounded framed JSON IPC. Worker cannot publish predictions or mutate run metadata. Timeout kills only the owned group and the next page restarts a clean worker.

## 3. Hard timeout semantics
Existing `max_runtime_seconds=300` covers cold model startup, preprocessing, inference, postprocessing, IPC and parent validation. The parent does not rely on cooperative model cancellation. Page wall time includes teardown after the operation deadline.

## 4. Worker lifecycle
Startup/ready/completed/failure/timeout and restart paths are covered by deterministic fixture tests. A timed-out worker is not reused.

## 5. Cleanup verification
Tests verify descendant PID disappearance and scratch cleanup. After the full run no worker/fixture process remained and L4 memory returned to 0 MiB.

## 6. Reproducibility attestation
Run `e2e-paddleocr-vl16-isolation-full180-v2-20261002T115500Z`; manifest SHA `bb99b04e425a6b337252c7fa56dbf01fae94623181b06ab39d8b223abbe16fc6`; config SHA `ea3e0415e6e7699c081dfc7a3d2abcf9344c02db704865beb91ef783e1102748`; evaluator `193627ae9e97d89188468ed1ee3b7a856ff76044`. Model hashes and package versions are recorded in JSON. Device L4, CUDA 12.6; model `PaddlePaddle/PaddleOCR-VL-1.6`.

## 7. Five-page smoke
5/5 completed, zero warnings, 270.481 s; diagnostic only, not a quality comparison.

## 8. Timeout stress test
5 worker-specific tests and 14 combined worker/backend tests pass. Forced timeout, group cleanup, child disappearance, scratch cleanup, restart, output cap and failure behavior exercised.

## 9. 20-page preflight
20/20 completed, zero warnings, 841.741 s; exact prediction/GT alignment and evaluator execution passed.

## 10. Full 180-page E2E run
178 success; two timeouts. The frozen set is incomplete, so **NO FULL PAIRED QUALITY BASELINE**.

## 11. Operational coverage
Success 98.889%; timeout 1.111%; other failures 0; warnings 0; policy rejections 0.

## 12. Official quality metrics
Conditional only; see table below. No missing page was replaced with empty output; exact 178 prediction/GT alignment passed.

| Metric | Classic | E2E | Delta | N | Status |
|---|---:|---:|---:|---:|---|
| Text ED | 0.573195 | 0.044909 | -0.528286 | 166 | CONDITIONAL |
| Table ED | 0.712518 | 0.567469 | -0.145049 | 50 | CONDITIONAL |
| Table TEDS | 0.413877 | 0.842940 | +0.429063 | 50 | CONDITIONAL |
| Table structure TEDS | 0.673171 | 0.872106 | +0.198935 | 50 | CONDITIONAL |
| Reading-order ED | 0.582641 | 0.165855 | -0.416786 | 176 | CONDITIONAL |
| Formula ED | 0.985389 | 0.079500 | -0.905889 | 35 | CONDITIONAL |

Table values are official page-level `ALL` aggregation across 50 table-bearing pages. Separately, 64 matched table instances yield TEDS Classic 0.398111, E2E 0.844484; structure-only 0.632317 vs 0.871228. Formula CDM was not run.

## 13. Classic vs E2E
Only conditional 178-page results share the exact filtered ground truth, outputs, and pinned evaluator. Do not subtract conditional E2E from the full 180-page Classic score.

## 14. Paired page-level analysis
Text ED lower for 161/166 pages; formula lower for 35/35; reading-order lower for 128/176; table edit lower for 42/50. All per-page paired values are in JSON. One large text/reading-order regression remains unexplained.

## 15. Failure-mode comparison
OBSERVED: two timeouts; one completed yanbaoppt page has E2E text/reading-order ED 1.0 despite nonempty Markdown with some overlapping prose and near-zero Classic error. HYPOTHESIS: reading-order or sequence alignment/serializer interaction; not confirmed. Timed-out page quality is unknown.

## 16. Runtime/resource comparison
E2E wall 7557.275s (~2h 5m 57s); mean 41.977s, median 29.055s, p95 95.895s, range 12.326–300.819s. Classic wall 1190.221s. E2E peak GPU use observed ~20,580/23,034 MiB; 0 MiB after exit.

## 17. Production viability
**PROMISING BUT NEEDS OPTIMIZATION.** Conditional quality is materially better on most measured tasks, but 2 timeouts and ~6.35x mean runtime remain; this is not production approval.

## 18. Fine-tuning decision
**FINE-TUNING NOT YET JUSTIFIED.** Complete paired coverage has not been achieved; first investigate the timeout pages and the large paired regression.

## 19. Tests
Focused worker/backend/attestation tests: 16 passed before the diagnostic correction; the new elapsed-time helper has its own deterministic clock test. Changed-file Ruff passes. Full suite/build results are recorded in final validation.

## 20. Remaining risks
Two unscored timeout pages; process isolation is not an OS sandbox; scratch size is polled rather than kernel quota; one substantial page regression is uncharacterized. This measures one pretrained model revision and adapter, not broad generalization.

### Timed-out pages
- `page-affbb0cc-d616-481d-b493-80ed1ccb5a10.png` page 0: runtime limit; 300.620s page wall; no prediction accepted.
- `newspaper_TheWashingtonPost-2025-01-08@magazinesclubnew_page_042.png` page 42: runtime limit; 300.819s page wall; no prediction accepted.

### Source category analysis (successful pages, groups N >= 5)
| Source | N pages | Text N | Text ED | Reading N | Reading-order ED |
|---|---:|---:|---:|---:|---:|
| PPT2PDF | 28 | 26 | 0.0092 | 28 | 0.1845 |
| academic_literature | 24 | 21 | 0.0145 | 23 | 0.1308 |
| book | 30 | 27 | 0.0564 | 30 | 0.1883 |
| colorful_textbook | 16 | 16 | 0.0929 | 16 | 0.2144 |
| exam_paper | 20 | 19 | 0.0203 | 20 | 0.0328 |
| magazine | 16 | 16 | 0.0453 | 16 | 0.1509 |
| newspaper | 15 | 15 | 0.0155 | 15 | 0.1188 |
| note | 13 | 12 | 0.1140 | 12 | 0.1364 |
| research_report | 15 | 13 | 0.0811 | 15 | 0.3329 |
