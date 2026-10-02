# OmniDocBench Representative Baseline

**Status: INVALID / BLOCKED AT PREFLIGHT. No quality baseline was produced.** The frozen subset and dataset audit are reproducible, but one in-policy extraction failure prevented complete predictions. Per the frozen gate, the 14 successful-page outputs are not scored as a substitute population.

| Metric | Value | N | Aggregation | Direction | Status |
| --- | ---: | ---: | --- | --- | --- |
| Text block normalized Edit distance | — | — | official end-to-end | lower | NOT COMPUTABLE |
| Table Edit distance | — | — | official end-to-end | lower | NOT COMPUTABLE |
| Table TEDS | — | — | official end-to-end | higher | NOT COMPUTABLE |
| Table structure TEDS | — | — | official end-to-end diagnostic | higher | NOT COMPUTABLE |
| Reading-order Edit distance | — | — | official end-to-end | lower | NOT COMPUTABLE |
| Formula Edit distance | — | — | official end-to-end | lower | NOT COMPUTABLE |
| Formula CDM | — | — | official CDM toolchain | higher | NOT COMPUTABLE |

## 1. Dataset identity

- Dataset: local OmniDocBench 1.6 snapshot at `experiments/034a_omnidocbench_snapshot/dataset/full`.
- Annotation records/pages: 1,651.
- Annotation SHA-256: `a45cd84b04ad8b793e775089640e6b681209abea33ead54c1828ddca35fae496`.
- Semantic annotation SHA-256: `31e7a7b96fcf2f823aaf81afc53b15e9bb0413c2e6a52dc3d7bacd0615716f89`.
- Referenced image inventory: 1,651 files; inventory SHA-256: `4da40bb41705f9194fc7605c445855a0977b1da62945cb295e05b0ad7c5db915`.
- Image reference validation found no missing referenced images, duplicate image names, or orphan images. All page identities `(image_name, page_no)` were unique. There are 1,355 non-null benchmark sample IDs; remaining pages use the explicit image/page fallback identity.
- Five pages with unresolved relation endpoints were excluded by the pre-run manifest builder, with indices and reasons recorded in the manifest. This is annotation-integrity eligibility, not outcome-based selection.
- Dataset license/usage: **UNVERIFIED**. The evaluator repository's license does not establish dataset rights.

## 2. Dataset integrity validation

The manifest builder audited every annotation reference, image path and image hash. It found 2,852 relation records; 53 relation records (82 endpoints) across five pages could not be resolved to annotation IDs. Those five pages were listed as eligibility exclusions before extraction. No selected sample had unresolved relation references. The source snapshot was not modified.

## 3. Subset definition

The committed manifest is [`omnidocbench-representative-v1.json`](../../manifests/omnidocbench-representative-v1.json), versioned as `omnidocbench-subset/1`. It defines 180 pages with deterministic iterative marginal stratification over source, language, layout, hard subset/special issue, table/formula presence, text density and mixed content. SHA-256 tie-breaking uses seed `4601`; the final sample order is dataset-index order. Subset identity is `d978722b84c85e895396a166b1e13bcacfc55a8c135c7a23df56cd7df62d8917`; manifest file SHA-256 is `737fe8fc2963956d5f38e3477396bf97e36c56b1c5e76e00e2fe52086d5a341d`.

Selection was frozen before prediction generation. The first 15 manifest entries were used for the operational preflight. No sample was replaced after observing model output.

## 4. Subset composition

The 180-page frozen subset covers all ten source categories in the eligible population: book 30, PPT2PDF 28, academic literature 24, exam paper 21, colorful textbook 17, magazine 16, newspaper 16, research report 14, note 13 and historical document 1. Language coverage is English 82, simplified Chinese 83, mixed English/Chinese 13, traditional Chinese 1, other 1. Layout coverage is single-column 97, other-layout 40, double-column 20, 1-and-more-column 17 and three-column 6. Annotation properties overlap and are recorded in the manifest; counts must not be summed across dimensions.

An outcome-independent image-header check against the production limit found 8 of the 180 selected images exceed 40,000,000 pixels. Their exact page IDs are recorded in the JSON report. The representative population therefore cannot yield a complete baseline under the current hard input policy without an explicitly authorized production-policy or protocol decision.

## 5. Evaluation protocol

The adapter invokes the pinned upstream OmniDocBench evaluator at commit `193627ae9e97d89188468ed1ee3b7a856ff76044`, using its end-to-end prediction/GT matching and metric implementations. The configured tasks include text-block normalized Edit distance, table Edit distance/TEDS (including structure-only TEDS), display-formula Edit distance and reading-order Edit distance. They are official end-to-end metrics only when the complete frozen population is paired and evaluation completes without evaluator errors.

Layout detection is not measured by this Markdown end-to-end path; it requires the separate detection evaluator and matching predictions. Formula CDM was disabled and is not measured. No composite or weighted score is used. The prediction adapter serializes canonical pages to Markdown; tables are represented as Markdown pipe tables for the upstream table conversion path. Ground truth is selected using the copied subset JSON, never the entire snapshot.

| Metric/task | Supported by dataset | Supported by current adapter | Supported by pinned evaluator | Measurable in the complete current run |
| --- | --- | --- | --- | --- |
| Text block normalized Edit distance | Yes | Yes, Markdown text blocks | Yes | No; preflight blocked |
| Layout detection | Yes, box annotations | No detection-prediction adapter in this run | Yes, separate task | No |
| Table Edit distance | Yes | Yes, Markdown pipe tables | Yes | No; preflight blocked |
| Table TEDS / structure-only TEDS | Yes | Yes, Markdown table conversion | Yes | No; preflight blocked |
| Formula Edit distance | Yes, formula annotations | Yes, display-formula output path | Yes | No; preflight blocked |
| Formula CDM | Yes, formula annotations | Candidate format exists, disabled here | Yes, requires external toolchain | No |
| Reading-order Edit distance | Yes | Yes, Markdown block ordering | Yes | No; preflight blocked |
| Other official metrics | Some require additional task-specific outputs | Not all are mapped | Some available in upstream | No |

## 6. Configuration

The attempted run used the production CPU configuration `configs/cpu.yaml` without benchmark-specific extraction changes. Config SHA-256: `133c78c47501cbe858a97c88f61ea86414bfac83ce2350b0d8f7bfe668e6f3e9`. Device was CPU; Docling layout/OCR and Table Transformer table backend were enabled. `max_image_pixels` is the production hard limit of 40,000,000 in default, CPU and GPU configs. Python was 3.10.12 on Linux; recorded versions: doc-extraction 0.1.0, PyMuPDF 1.28.2, Docling 2.124.0, docling-core 2.93.0, EasyOCR 1.7.2, Transformers 5.16.1 and Torch 2.14.0. Source commit: `94e7a15696c7e01dcb703315ae04ab7611b3c815`.

## 7. Preflight results

Run ID: `representative-v1-preflight-20261002T071028Z`. Fourteen of 15 pages completed successfully, with zero extraction warnings; one page failed explicitly. The input `page-8f6792bd-b5e4-435e-b1b0-1b2daa3f7234.png#0` is 5,556 × 8,073 = 44,853,588 pixels, exceeding the configured 40,000,000-pixel hard cap. Its input SHA-256 is `33c95a984c3f22a6534c7fa003d12616fb7ac6344d19367fc00080507ec42ddd`.

The runner produced 14 prediction files and a failed-page status record, then returned nonzero as designed. The evaluator's strict preflight was also run: it rejected exactly the one absent prediction from the frozen 15-page GT subset and did not execute metrics. A prior invocation that omitted the subset GT exposed a runner default bug (it tried to pair 15 predictions against all 1,651 pages); this was fixed and tested. The corrected invocation now selects the run's frozen `ground_truth_subset.json` automatically.

## 8. Aggregate metrics

All quality metrics are **NOT COMPUTABLE** because the complete preflight population has no prediction for one selected page. The 14-page success subset is not substituted for the frozen population. No official evaluator metrics were generated, and no score is published.

## 9. Per-page analysis

Per-page extraction status, route, warnings/errors, runtime, input hash and prediction hash were recorded for all 15 preflight attempts. Fourteen have `status=success`, route `image`, zero warnings; one has `status=failed`, route `unknown`, and the resource-limit error above. No per-page quality metrics exist because the evaluator correctly refused the incomplete pair. The run directory retains the individual prediction and stage artifacts locally under `.benchmarks/runs/omnidocbench/representative-v1-preflight-20261002T071028Z/` (ignored, not committed).

No best/worst quality page, degradation ranking, or high-error flag is reported: those require official per-page metrics. The frozen screening rules, if a valid run becomes possible, are normalized Edit distance ≥0.95 and TEDS ≤0.10; these are review flags, not statistical outlier claims.

## 10. Stratified analysis

Not computed. Reporting quality by source/language/layout from an incomplete, ordered 15-page preflight would be misleading. Frozen strata and full selected counts remain in the manifest.

## 11. Route/backend analysis

Observed preflight route was `image` for all 14 successful pages; the rejected image has route `unknown` because routing did not begin. Backend configuration was the baseline route with Docling and Table Transformer. No metric-by-route analysis is available.

## 12. Runtime analysis

The 15-page preflight took 497.045 seconds wall-clock. Per attempted page, recorded mean was 33.1313 s, median 32.8682 s and p95 70.6263 s; these are operational preflight statistics, not representative-subset estimates. No full-1,651 runtime estimate is issued because the first manifest pages are an ordered preflight slice and include a hard-limit failure. The environment emitted PyTorch `pin_memory` warnings because no accelerator was present; these are environment stderr warnings, not extraction `RunMetadata` warnings.

## 13. Warning/error analysis

Extraction metadata warnings: 0 pages, 0 warning strings. Extraction failures: 1 page, categorized by the actual exception as `max_image_pixels` resource-limit rejection. PyTorch's no-accelerator `pin_memory` warning appeared on stderr during model execution; it did not enter extraction warning metadata. No other warning category is inferred.

## 14. Failure cases

The selected image that exceeds `max_image_pixels` is the decisive failure. The extractor rejects it before visual inference, which is expected production safety behavior. This is not an evaluator defect and not a reason to mutate production limits. The issue is a coverage incompatibility between the frozen benchmark population and the production input policy.

Offline dimension inspection shows this is not isolated: 8/180 selected pages exceed the same cap. This predicts at least 8 missing predictions if the frozen set is run unchanged under the current configuration; it does not claim anything about their extraction quality.

## 15. Benchmark limitations

- A complete representative extraction/evaluation was not run.
- This runner measures only the pinned end-to-end metric path, not layout detection.
- Formula CDM is disabled; it requires the evaluator's external rendering/toolchain setup.
- The current CPU configuration cannot process any selected image over its 40-million-pixel safety limit.
- The manifest excludes five annotation-integrity cases; no model outcome influenced those exclusions or subset selection.
- Local dataset licensing/usage remains unverified.

## 16. Full-benchmark runtime estimate

Not issued. Extrapolating from an ordered 15-page preflight with one immediate resource rejection would not be a sound estimate of the 180-page stratified set or all 1,651 pages.

## 17. Recommendation on full 1,651-page run

**NOT YET JUSTIFIED.** First resolve the production-policy/benchmark coverage incompatibility through an explicitly approved production-level policy decision or benchmark-compatible preprocessing protocol. Do not simply raise the resource cap or resample away the failing page to obtain a score.

## 18. Reproducibility

The authoritative population is the committed manifest and its subset identity/hash above. The preflight run timestamp was `2026-10-02T07:19:07.477058+00:00`; its JSON machine record is [`representative-v1.json`](representative-v1.json). The source run commit, CPU config hash, backend versions and evaluator commit are recorded in both the machine record and the original ignored run metadata. The local ignored run directory contains raw predictions and per-page runtime/status records; no benchmark dataset binaries are committed.

## 19. Tests and validation

The evaluation-default defect is covered by focused tests: representative runs resolve their copied subset GT by default, and an explicit GT path overrides it. The evaluator was then invoked on the actual preflight artifacts and failed closed on the single missing expected prediction. Final test, lint, and build results are reported in the handoff; no score can pass the quality gates until all 180 frozen pages produce aligned predictions.

### Quality gates

| Gate | Result | Evidence |
| --- | --- | --- |
| Dataset integrity | PASS | 1,651 image refs resolve; inventory/hash frozen |
| Subset reproducibility | PASS | committed 180-page manifest, deterministic builder/verifier |
| Prediction/GT alignment | FAIL | 1 of 15 preflight predictions missing |
| No missing predictions | FAIL | 14 predictions for 15 frozen preflight pages |
| No unexpected predictions | PASS for produced files | strict validator found none, but population gate fails |
| Evaluation protocol verified | PARTIAL | pinned official evaluator available; complete run not reached |
| Run metadata complete | PASS | status/warning/route/runtime/hash recorded for all attempts |
| Per-page metadata complete | PASS | 15 of 15 attempted pages recorded |
