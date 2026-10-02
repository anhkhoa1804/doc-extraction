# OmniDocBench Current Baseline v2

| Metric | Value | N | Aggregation | Direction | Status |
| --- | ---: | ---: | --- | --- | --- |
| Text block Edit distance | 0.573988 | 168 pages | `ALL_page_avg` | lower | MEASURED |
| Table Edit distance | 0.712518 | 50 pages | `ALL_page_avg` | lower | MEASURED |
| Table TEDS | 0.413877 | 50 pages | page average (`ALL`) | higher | MEASURED; range anomaly noted below |
| Table structure TEDS | 0.673171 | 50 pages | page average (`ALL`) | higher | MEASURED |
| Reading-order Edit distance | 0.584992 | 178 pages | `ALL_page_avg` | lower | MEASURED |
| Formula Edit distance | 0.985389 | 35 pages | `ALL_page_avg` | lower | MEASURED |

## Executive Summary

| Dimension | Result |
| --- | ---: |
| Dataset pages | 1,651 |
| Dataset-integrity exclusions | 5 |
| Production-policy eligible pages | 1,615 / 1,646 dataset-valid |
| Production-policy rejection rate | 31 / 1,646 = 1.882% |
| Representative-v2 pages | 180 |
| Extraction success rate | 180 / 180 = 100% |
| Warning rate | 0 / 180 = 0% |
| Text Edit distance | 0.573988 (N=168) |
| Table TEDS | 0.413877 (N=50 pages) |
| Table structure TEDS | 0.673171 (N=50 pages) |
| Reading-order Edit distance | 0.584992 (N=178) |
| Formula Edit distance | 0.985389 (N=35) |
| Device | NVIDIA L4, CUDA 13.0 |
| Runtime | 1,190.221 s wall (19m 50.2s) |

The frozen population passed dataset, eligibility, prediction/ground-truth alignment, evaluator, status, and per-page metadata checks. These are benchmark results under the pinned OmniDocBench 1.6 protocol, not a general claim about extraction quality. No production extraction behavior or resource limit was changed.

## 1. Dataset Identity

- Local snapshot: `experiments/034a_omnidocbench_snapshot/dataset/full` (OmniDocBench 1.6).
- Annotation file SHA-256: `a45cd84b04ad8b793e775089640e6b681209abea33ead54c1828ddca35fae496`.
- Semantic annotation SHA-256: `31e7a7b96fcf2f823aaf81afc53b15e9bb0413c2e6a52dc3d7bacd0615716f89`.
- Image inventory: 1,651 references, SHA-256 `4da40bb41705f9194fc7605c445855a0977b1da62945cb295e05b0ad7c5db915`.
- Integrity audit: all 1,651 referenced images resolve; zero duplicate image names and zero orphan images. Five records have dangling relation endpoints and remain excluded by the frozen annotation-integrity rule.
- Dataset license/usage status was not independently verified here; the snapshot is not redistributed by this report.

## 2. Dataset Integrity Validation

The committed v2 manifest records the annotation and image-inventory identities and retains all five annotation-integrity exclusions. The run recorder independently revalidated the manifest against the local snapshot. No dataset files were modified.

## 3. Subset Definition

Manifest: `benchmarks/manifests/omnidocbench-representative-v2.json`.

- Manifest SHA-256: `bb99b04e425a6b337252c7fa56dbf01fae94623181b06ab39d8b223abbe16fc6`.
- Subset identity: `899191e7471ae5c826a6a07ff7edf3c7c8facec72764196ef9f3f49a8265a93b`.
- Selection: deterministic iterative marginal stratification over source, language, layout, hard-subset, special-issue, table/formula presence, text density, and mixed-content labels; SHA-256 of seed and image path breaks ties; final order is dataset index.
- Seed: `4602`; target and actual size: 180.
- Selection was generated and frozen before inference, using annotation metadata and the production image-pixel policy only. No predictions or outcomes were used.
- Selected source counts: PPT2PDF 28; academic literature 24; book 31; colorful textbook 16; exam paper 20; historical document 1; magazine 16; newspaper 16; note 13; research report 15.
- Selected language counts: English 82; simplified Chinese 83; mixed English/Chinese 13; traditional Chinese 1; other 1.
- Selected layout counts: single-column 98; other layout 39; double-column 20; 1+ columns 17; three-column 6. The manifest also records hard-subset and special-issue counts.

## 4. Coverage Population

The denominator is 1,646 pages after the five objective annotation-integrity exclusions. Under the unchanged `configs/gpu.yaml` production policy (`max_image_pixels=40,000,000`), 1,615 pages are eligible and 31 are rejected. Thus 98.118% of dataset-valid pages are policy-eligible. Including the five invalid annotations, 1,615/1,651 (97.820%) of the raw snapshot is both dataset-valid and eligible.

## 5. Policy Rejections

All 31 rejections are `max_image_pixels`; no other policy rule rejected a page. Source counts: colorful textbook 12, exam paper 10, newspaper 8, historical document 1. Language counts: simplified Chinese 15, English 12, mixed 3, traditional Chinese 1. Layout counts: other layout 16, double-column 6, single-column 6, 1+ columns 2, three-column 1. The exact IDs, hashes, dimensions, and pixel counts are in the manifest and result JSON. These are input-coverage exclusions, not extraction errors or quality scores. Production limits were not raised or bypassed.

## 6. Representative-v2 Composition

The 180 selected pages span all ten non-empty source categories in the eligible set and multiple language/layout/hard-subset strata. Some rare annotation categories necessarily have N=1–3; they are retained in the manifest but are not treated as stable subgroup estimates. The subset is deterministic and stratified, not a simple random sample; its overall aggregate describes this frozen representative population and should not be interpreted as a design-weighted estimate of all 1,615 eligible pages.

## 7. Evaluation Protocol

- Evaluator: pinned upstream OmniDocBench commit `193627ae9e97d89188468ed1ee3b7a856ff76044`.
- Matching: `quick_match`, one worker; matched page count 180, zero fallback/timeouts.
- Table TEDS: one worker, 120-second per-case timeout; 64 table instances, zero timeouts and zero evaluator errors.
- Formula CDM and BLEU/METEOR were disabled. Formula CDM toolchain was unavailable; it is not computed here.
- Edit-distance values are normalized edit errors (lower is better); TEDS values are similarity (higher is better). Table TEDS and structure-only TEDS reported above use the evaluator's page-level `ALL` aggregation over table-bearing pages. Instance-average values are separate aggregations and are retained in JSON.
- No composite score is calculated.

## 8. Configuration

- Extractor source commit: `f7ad85fa9b7c5064cf4b31736f3f9768e4196f64`.
- Production config: `configs/gpu.yaml`, SHA-256 `ea3e0415e6e7699c081dfc7a3d2abcf9344c02db704865beb91ef783e1102748`; resolved config hash `8698fb2d97d295d3bfcd0584507ca7b9b4ebb61860c1caef9c64fb66a87922c6`.
- Python 3.10.12; Linux `6.8.0-1069-gcp`, glibc 2.35.
- Device: NVIDIA L4, 23,034 MiB; driver 580.178.04; CUDA runtime 13.0; PyTorch 2.14.0+cu130.
- Recorded extraction packages: Docling 2.124.0, docling-core 2.93.0, EasyOCR 1.7.2, PyMuPDF 1.28.2, Transformers 5.16.1. The run JSON carries the full resolved configuration and version map.
- Routes: image 180/180. Configured layout/OCR backend: Docling; table backend: Table Transformer.

## 9. Preflight

The first 15 manifest pages were run before the full population. All 15 extracted successfully with zero warnings/failures; exact prediction alignment passed and the pinned evaluator matched all 15. The preflight happened to contain zero table-bearing pages, so it did not validate table metric execution. The full 180-page run subsequently exercised tables and completed 64 TEDS instances without errors or timeouts.

## 10. Current Extraction Run

- Run ID: `representative-v2-full-20261002T080500Z`.
- Attempts/success/failure: 180 / 180 / 0.
- Success with warnings: 0; warning count: 0.
- Every page record includes sample/page/document identity where available, input and prediction hashes/IDs, route, status, warning list/count, errors, and runtime.
- Prediction filenames and selected GT were validated as an exact set before evaluation. The evaluator matched exactly 180 pages. The result recorder verified complete selected-manifest execution, prediction alignment, and zero extraction/evaluator failures.
- `current_population_valid=true` in the machine-readable result.

## 11. Official Metrics

| Metric | Value | Denominator | Aggregation | Direction |
| --- | ---: | ---: | --- | --- |
| Text block Edit distance | 0.5739880899 | 168 pages | `ALL_page_avg` | lower |
| Table Edit distance | 0.7125178639 | 50 pages | `ALL_page_avg` | lower |
| Table TEDS | 0.4138769497 | 50 pages | page average, `ALL` | higher |
| Table structure-only TEDS | 0.6731710442 | 50 pages | page average, `ALL` | higher |
| Reading-order Edit distance | 0.5849918953 | 178 pages | `ALL_page_avg` | lower |
| Display-formula Edit distance | 0.9853894477 | 35 pages | `ALL_page_avg` | lower |
| Formula CDM | — | — | not run | higher |

The source annotations do not define every task on every page; each metric denominator is therefore smaller than 180. Missing-task pages are not filled with empty predictions or silently counted. The official evaluator emitted three individual table-level TEDS scores below zero; its pinned implementation computes `1 - tree_edit_distance / max_node_count`, and this run retained those raw official outputs. This range anomaly is explicitly preserved in the per-table output and is a caveat for interpreting/comparing TEDS, not an extraction failure. No table-evaluator case failed.

## 12. Per-Page Analysis

The JSON preserves all 180 page records and page-level metric values where the corresponding ground-truth task exists. Denominators are: text 168, table edit/TEDS 50, reading order 178, formula 35. Ranking rule: descending normalized Edit distance for error metrics; ascending per-page mean TEDS for tables; ties are ordered by page ID. Twenty-three text pages, six table-edit pages, 22 reading-order pages, and 27 formula pages have Edit distance exactly 1.0.

Worst examples (not causal diagnoses):

- Text, error 1.0: `page-062fc21c-6b9c-40be-8d0e-7a617509a9bc.png#0` (book, simplified Chinese); also `page-39551bb3-1b65-4562-b258-1bc97898cdf9.png#0` (PPT2PDF), `page-34e4675f-4b7f-4bc3-8624-c399423d2c66.png#0` (book), and others. There are 23 tied pages at 1.0.
- Table edit error 1.0: `page-d29fe4d2-832a-4ad6-ac80-dc01cf8b0e16.png#0`; `jiaocaineedrop_jiaocai_needrop_en_2272.jpg#2193`; `..._397.jpg#1830`; `..._482.jpg#1851`; and two others.
- Lowest page-mean TEDS: `page-50ffe5d2-cd27-449a-a813-d4a8c44b12ea.png#0` (-0.0369), `yanbaor2_1492d25d79af850815ea449254ea62418c3c7fd582792b5191e1879671ba1219.pdf_88.jpg#4297` (-0.0321), and `jiaocaineedrop_jiaocai_needrop_en_3751.jpg#2485` (-0.0227). Values are raw upstream results; see range caveat above.
- Reading-order error 1.0 includes `page-062fc21c-6b9c-40be-8d0e-7a617509a9bc.png#0`, `page-39551bb3-1b65-4562-b258-1bc97898cdf9.png#0`, and `page-112859dc-07d9-473a-a027-94904db8fd84.png#0` (22 ties total).
- Formula error 1.0 includes `page-14cd673f-d86d-45a7-a13e-2b4e1d91c08f.png#0`, `page-4b8f8a9d-e061-4207-a42e-ebf9b7090099.png#0`, and `page-39551bb3-1b65-4562-b258-1bc97898cdf9.png#0` (27 ties total).

## 13. Stratified Analysis

Diagnostic means below average the evaluator's per-page values within each annotation source category; they are not the official pooled/page-macro aggregate. Only groups with metric N≥5 are shown. Small groups are retained in the machine result but not interpreted.

| Source category | Text Edit N / mean | Table TEDS diagnostic N / mean | Reading-order Edit N / mean |
| --- | ---: | ---: | ---: |
| Academic literature | 21 / 0.1542 | 7 / 0.5684 | 23 / 0.4091 |
| Book | 28 / 0.6643 | 5 / 0.5808 | 31 / 0.6379 |
| Colorful textbook | 16 / 0.8032 | 6 / 0.3849 | 16 / 0.6811 |
| Exam paper | 19 / 0.4847 | 6 / 0.2571 | 20 / 0.5226 |
| Magazine | 16 / 0.6324 | — | 16 / 0.5539 |
| Newspaper | 16 / 0.2965 | — | 16 / 0.6551 |
| Note | 12 / 0.9782 | — | 12 / 0.8231 |
| Research report | 13 / 0.9847 | 13 / 0.4337 | 15 / 0.7688 |

Differences are descriptive and may reflect selected pages, annotation density, task availability, or page difficulty. No significance test or causal explanation is claimed. Language/layout/subset/special-issue diagnostics are included in JSON with their Ns.

## 14. Route/Backend Analysis

All 180 pages used the `image` route. Layout/OCR used Docling; table handling used Table Transformer. There is no within-run route comparison and no routing threshold was changed. Route-level quality differences are therefore not estimable from this run.

## 15. Warning and Failure Analysis

- Extraction: 180 success, 0 success-with-warnings, 0 failed; 0 warning pages and 0 warnings.
- Evaluation: 180 pages matched; zero match fallbacks/timeouts; TEDS: 64 table instances, 0 errors, 0 timeouts.
- Policy rejection (31 pages) is reported separately from extraction/evaluation failure (both zero).
- Warning/error categories: none were emitted for this run.

## 16. Runtime Analysis

- Wall time: 1,190.221 s; summed per-page runtime: 1,189.563 s.
- Mean 6.6087 s/page; median 4.4045; p95 19.5529; min 0.7567; max 78.5691.
- Device: L4/CUDA 13.0; all pages ran sequentially through the configured production pipeline.
- Full eligible-population runtime extrapolation: **NOT RELIABLE TO EXTRAPOLATE**. The subset is marginally stratified rather than proportionally sampled, and page runtime has a long tail (0.76–78.57 s); a simple multiplication would imply false precision.

## 17. Historical vs Current Comparison

The 1,651-page 034a full run remains a separate historical reference. Its source Git commit and config-file hash are unknown, it used 13 TEDS workers and had 94/665 TEDS worker errors assigned zero, and it evaluated a different population. It is not a controlled comparison to v2.

For a valid same-population descriptive comparison, stored 034a Markdown predictions were re-evaluated on the exact frozen v2 180-page GT subset with the same pinned evaluator, `quick_match`, one matching worker, and one TEDS worker. Exact prediction alignment and all 180 matches passed. Metric denominators match current v2. The paired metric values/deltas are in `comparison-034a-v2.md`. Because the historical extraction commit/config identity is unknown, those are not causal regression/improvement claims.

## 18. Error Taxonomy

- **OBSERVED:** The Chinese textbook page `page-062fc21c-6b9c-40be-8d0e-7a617509a9bc.png#0` visibly contains Chinese prose and equations; its current prediction Markdown is empty, with text, reading-order, and formula Edit distance 1.0.
- **HYPOTHESIS:** language/script coverage may contribute; current config declares OCR languages `en` and `vi`, while this page is simplified Chinese. This is not confirmed as the cause; route/backend internals and upstream model language handling need targeted inspection.
- **OBSERVED:** `page-50ffe5d2-cd27-449a-a813-d4a8c44b12ea.png#0` visibly contains a rotated, dense table. Its prediction has a garbled numeric matrix; table TEDS is negative and structure-only TEDS is 0.84375.
- **HYPOTHESIS:** rotation/orientation or table text recognition may be involved. The score is outside the expected range, so evaluator behavior is also a competing explanation. Neither is confirmed as sole cause.
- **OBSERVED:** hard text/table/formula cases have high normalized edit errors; no run-level extraction failures or warnings explain these metric mismatches.
- No production code was changed in response to these examples.

## 19. Fine-Tuning / E2E Research Hypotheses

Prioritize a bounded visual-text recognition investigation for Chinese/formula-bearing pages, using the observed empty output and exact page images/predictions as evidence. Before any fine-tuning, determine whether the loss is OCR language coverage, routing, or annotation/evaluator alignment; compare intermediate outputs on these already selected pages. Separately, validate TEDS range behavior on the three negative-score tables before using TEDS deltas as a future regression gate.

## 20. Full 1,651-Page Run Recommendation

**NOT YET JUSTIFIED.** V2 is a useful frozen current-code baseline with broad strata, but it is not proportionally sampled, includes small strata, and policy excludes 31 pages. First use this baseline for a same-manifest engineering rerun and investigate the observed language/formula and TEDS-range issues. Do not claim the accepted-population aggregate from v2 estimates the full snapshot.

## 21. Reproducibility

- Frozen manifest and exact selected IDs/hashes: `benchmarks/manifests/omnidocbench-representative-v2.json`.
- Machine result: `benchmarks/reports/omnidocbench/representative-v2.json`.
- Raw predictions, page runtime records, exact GT subset, evaluator config/results, and copied per-page metric files are retained locally under `.benchmarks/runs/omnidocbench/representative-v2-full-20261002T080500Z/` (ignored, not committed).
- Exact source revision, config hashes, dataset hashes, run ID, package versions, GPU/CUDA details, per-page IDs/status/warnings/runtime/input and prediction hashes, evaluator revision/worker settings, metrics, denominators, and failures are in the machine result and raw run metadata.
- Historical full data: `benchmarks/reports/omnidocbench/historical-034a.json`; same-v2 paired historical scores: local ignored run `.benchmarks/runs/omnidocbench/historical-034a-on-v2-20261002T090000Z/`.

## 22. Tests and Validation

- Focused benchmark suite (`test_omnidocbench.py`, manifest, comparison, and registry): 78 passed.
- Full repository suite: 503 passed, 13 skipped, 0 failed; 8 warnings (dependency deprecations and intentional security-fixture/Pillow warnings).
- Changed-file Ruff: passed. Root-wide historical lint was not run as a cleanliness claim.
- Mypy: unavailable in the current uv environment (`Failed to spawn: mypy`, executable absent).
- `uv build`: passed; source distribution and wheel built.
- `git diff --check`: passed.

## 23. Limitations

- Results cover 180 policy-eligible pages, not the full accepted population or 31 pixel-limit rejects.
- Subset is deterministic and stratified, not a probability sample; no weighted full-population estimate is reported.
- Formula CDM is unavailable; no layout detection metric is computed as a standalone task.
- TEDS page aggregation includes three individual out-of-range negative upstream scores; raw values are retained and require caution.
- Current run has zero warnings/failures; that does not demonstrate robustness on unsupported or policy-rejected inputs.
- Historical 034a source revision/config hash are unavailable. Same-v2 re-scoring permits descriptive same-input comparison only, not attribution.
