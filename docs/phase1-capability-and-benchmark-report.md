# Phase 1 Capability and Benchmark Evidence

Current-state clarification (2026-10-07): historical CJK sections below accurately describe the earlier offline-only fallback prototype. They are superseded by the latest addendum: an opt-in, disabled-by-default live route and fallback telemetry now exist, with one real page validated. This remains experimental; no real Vietnamese control cohort or bounded multilingual live A/B is available.

**Frozen official benchmark evidence cut:** 2026-10-03; **bounded candidate evidence updated:** 2026-10-07; **CDOI contract audit:** 2026-10-06
**Initial report HEAD:** `2bebedacbef0a948e82201139a78a9cd0ef19944` (individual benchmark source attestations are listed with their runs)
**Physical Extraction decision:** **FREEZE WITH EXPLICIT E2E LIMITATION**
**Cross-team adoption:** **CONFIRMATION REQUIRED**

## Executive summary

Classic has a valid frozen 180-page reference and a separately evaluated full-corpus table candidate. Span-aware representation plus safe serialization reduces Table ED from 0.701108 to 0.625952 on the exact 50 table-bearing pages, with unchanged text, reading order, formula, coverage, and warning counts; this implementation is recommended for the Classic code path while the original run remains preserved as the immutable reference. CJK investigation confirms a real language-coverage configuration gap, but a seven-page global `ch_sim,en` A/B improves Chinese while regressing English and mixed-language text, so language routing remains experimental. Formula enrichment remains experimental: it has strong targeted quality evidence, but a single slow page reached the 2,048-token cap and still cost 57 seconds with a 1,024 cap. No formula candidate is promoted.

PaddleOCR-VL 1.6 provides a large conditional quality advantage on the 179 pages where it returned valid predictions: text, formula, tables, table structure, and reading order all improve in this paired population. That is not a valid full-180 E2E baseline. Washington Post page 42 repeatedly exceeds the 300-second resource limit. Its execution is a serial sequence of 102 VLM generations; one generation took about 121 seconds. Token caps 4096/2048/1024 all timed out at page level, and the installed predictor only supports batch size 1. The deeper cause is unresolved. E2E is therefore a validated experimental specialist backend, not an operationally complete replacement.

The official E2E model path is about 6.25× the Classic GPU-assisted backend's mean wall time per attempt (about 6.02× among successful E2E pages). This is a backend runtime comparison, not a GPU-vs-CPU speedup. The strict 180-page Classic scores are useful as the current baseline, with a provenance qualification: the run recorded a dirty source snapshot based on commit `5730460`, and `base.py` in that attestation is not byte-identical to final HEAD. The run achieved exact 180/180 coverage and is reported below as the valid post-fix run artifact, but not as a clean immutable-HEAD reproduction.

**Freeze rationale:** Freeze Phase 1's extraction, safety, and benchmark infrastructure, with Classic as the measured baseline and E2E explicitly experimental/incomplete. Keep the Classic source-snapshot qualification and formula/language gaps visible as follow-up items. Do not claim universal backend superiority, a production router, or an official 180-page E2E score.

The CDOI `DocumentExtractionContract` 1.0.0 / ExtractionPackage v1 is now treated as authoritative. This checkout still has no evidenced public package producer or KP adapter; therefore the physical extraction phase can be frozen with the E2E limitation, but cross-team contract adoption is not complete. See the dedicated contract status at the end of this report.

## 1. Benchmark population

The primary population is `representative-v2`, from `benchmarks/manifests/omnidocbench-representative-v2.json`.

| Property | Value |
| --- | ---: |
| Selected pages | 180 |
| Manifest SHA-256 | `bb99b04e425a6b337252c7fa56dbf01fae94623181b06ab39d8b223abbe16fc6` |
| Frozen subset identity | `899191e7471ae5c826a6a07ff7edf3c7c8facec72764196ef9f3f49a8265a93b` |
| Dataset annotation SHA-256 | `a45cd84b04ad8b793e775089640e6b681209abea33ead54c1828ddca35fae496` |
| Dataset semantic hash | `31e7a7b96fcf2f823aaf81afc53b15e9bb0413c2e6a52dc3d7bacd0615716f89` |
| Source image inventory | 1,651 images; SHA-256 `4da40bb41705f9194fc7605c445855a0977b1da62945cb295e05b0ad7c5db915` |
| Evaluator revision | `193627ae9e97d89188468ed1ee3b7a856ff76044` |

Eligibility is resource-policy based, not a manually selected “easy” set. The annotation snapshot contains 1,651 records and 2,852 relations. Integrity analysis found 53 dangling relation records / 82 dangling endpoints affecting five pages; those five pages were excluded. Of the remaining 1,646, 31 pages exceeded the production 40,000,000-pixel cap, leaving 1,615 eligible pages. The frozen 180-page stratified sample was selected from those 1,615. The manifest records source, language, layout, and task metadata. It does not provide a reliable native/digital-versus-scanned label; all benchmark inputs supplied to these runs are page images.

Selected page metadata includes data-source groups: PPT2PDF 28, academic literature 24, books 31, colorful textbooks 16, exams 20, historical document 1, magazines 16, newspapers 16, notes 13, research reports 15. Task/layout groups include 50 table-bearing, 35 formula-bearing, 48 text-heavy, 82 complex-layout, 98 single-column, 20 double-column, 6 three-column, 17 `1andmore_column`, and 39 other-layout pages. These are annotations/manifest groups, not runtime model detections.

No historical 1,651-page score is mixed into the primary comparison.

## 2. Classic baseline

Run artifact: `.benchmarks/runs/omnidocbench/classic-current-valid-20261003T153500Z/`.

Coverage is **180 selected / 180 attempted / 180 valid predictions**, with zero missing, unexpected, duplicate, or canonical-validation failures. Evaluator pairing used the run-scoped frozen GT and the pinned evaluator. The run used the GPU-assisted Classic configuration (`device=cuda`, Docling visual route for all pages).

| Metric | Score | Denominator / aggregation |
| --- | ---: | --- |
| Text Edit Distance | 0.589397 | 168 pages with metric instances |
| Table Edit Distance | 0.701108 | 50 table-bearing pages |
| Table TEDS | 0.407739 | 64 table instances |
| Table structure TEDS | 0.649114 | 64 table instances |
| Reading-order Edit Distance | 0.596823 | 178 pages with metric instances |
| Formula Edit Distance | 0.985389 | 35 formula-bearing pages |

These are evaluator-specific page/table aggregates; they must not be reinterpreted as a single overall score. The runtime record reports 1,168.63 seconds of page runtime and 1,169.29 seconds wall time: mean 6.492 s/page, median 4.320 s, p95 18.935 s, max 75.466 s. There were 115 success and 65 success-with-warnings statuses, zero failed pages, 76 warning occurrences on 65 pages. The most common warning classes were structure rows synthesized from corroborating OCR evidence, structured tables without a matching layout table region, and table regions without a detected row/column grid. Two pages reported zero OCR tokens for detected text/formula regions. Warning status is not equivalent to invalid output; all 180 canonical predictions validated.

**Source provenance qualification:** run metadata recorded source commit `5730460693ba0d8a008b950a5b1c61f1a26e5207`, a dirty source tree, and a source snapshot hash. Comparing the attested files with final HEAD found `src/doc_extraction/pipelines/base.py` differs from the final committed file. Thus this is a valid 180-page run artifact for its attested working-tree source, but not a clean, byte-identical final-HEAD reproduction. No full rerun is warranted in this evidence-only turn; preserve this qualification in any reuse of the scores.

## 3. Conditional E2E quality

The official run is `.benchmarks/runs/omnidocbench/e2e-gpu-v3-20261003T065100Z/08-full-180-20261003T065030Z/`. It attempted all 180 pages; 179 succeeded and page `newspaper_TheWashingtonPost-2025-01-08@magazinesclubnew_page_042.png#42` timed out. The strict full-coverage gate withheld official full-180 E2E scoring.

For additional, explicitly conditional analysis, the evaluator was run on the exact 179 successful E2E IDs. Classic predictions were filtered to those same IDs, and matching GT was filtered from the run-scoped 180-page GT. Both runs used evaluator revision `193627ae9e97d89188468ed1ee3b7a856ff76044`. Page 42 is excluded. Artifacts: `.benchmarks/diagnostics/phase1-evidence-179/{classic,e2e}/`.

| Metric | Classic on common pages | E2E on common pages | E2E − Classic | Metric denominator |
| --- | ---: | ---: | ---: | ---: |
| Text Edit Distance | 0.591128 | 0.045949 | -0.545178 | 167 pages |
| Table Edit Distance | 0.701108 | 0.567469 | -0.133639 | 50 pages |
| Table TEDS | 0.407739 | 0.844484 | +0.436745 | 64 table instances |
| Table structure TEDS | 0.649114 | 0.871228 | +0.222113 | 64 table instances |
| Reading-order Edit Distance | 0.594637 | 0.164918 | -0.429719 | 177 pages |
| Formula Edit Distance | 0.985389 | 0.079500 | -0.905889 | 35 pages |

Lower edit distance is better; higher TEDS is better. The table gives paired-population aggregate comparisons; the metric denominators differ because not every page has every metric. These are **179-page conditional results**, not an official 180-page E2E baseline.

### Paired page-level direction

| Metric | E2E better | Classic better | Ties | N |
| --- | ---: | ---: | ---: | ---: |
| Text ED | 162 | 5 | 0 | 167 |
| Table ED | 41 | 9 | 0 | 50 |
| Table TEDS | 61 | 3 | 0 | 64 instances |
| Table structure TEDS | 44 | 10 | 10 | 64 instances |
| Reading-order ED | 129 | 6 | 42 | 177 |
| Formula ED | 35 | 0 | 0 | 35 |

This is descriptive evidence within this frozen population. It is not a universal ranking or a causal explanation of any individual prediction.

## 4. Difficulty-stratified comparison

Groups below are derived from manifest/annotation metadata. “Text-heavy” means the manifest's text-block count threshold (at least 11); the category is not an inferred runtime characteristic. Only valid common predictions are scored.

| Category | Population | Metric and paired N | Classic | E2E | E2E better / Classic better / ties |
| --- | ---: | --- | ---: | ---: | ---: |
| Text-heavy | 48 | Text ED, 47 | 0.5299 | 0.0441 | 46 / 1 / 0 |
| Table-bearing | 50 | Table ED, 50 | 0.7011 | 0.5675 | 41 / 9 / 0 |
| Table-bearing | 50 | TEDS, 64 instances | 0.4077 | 0.8445 | 61 / 3 / 0 |
| Formula-bearing | 35 | Formula ED, 35 | 0.9854 | 0.0795 | 35 / 0 / 0 |
| Multi-column (`double`, `three`, `1andmore`) | 43 | Text ED, 41 | 0.5936 | 0.0125 | 41 / 0 / 0 |
| Multi-column | 43 | Reading ED, 42 | 0.6474 | 0.1120 | 37 / 0 / 5 |
| Newspaper | 16 | Text ED, 15 | 0.3128 | 0.0155 | 15 / 0 / 0 |
| Newspaper | 16 | Reading ED, 15 | 0.6363 | 0.1188 | 14 / 1 / 0 |
| Complex layout (not single-column) | 82 | Text ED, 79 | 0.5769 | 0.0376 | 77 / 2 / 0 |
| Complex layout | 82 | Reading ED, 80 | 0.6020 | 0.1315 | 66 / 3 / 11 |
| Single-column | 98 | Text ED, 88 | 0.6039 | 0.0534 | 85 / 3 / 0 |
| Single-column | 98 | Reading ED, 97 | 0.5885 | 0.1925 | 63 / 3 / 31 |

There is no dependable scanned/native split in the manifest, so no such comparison is claimed. The timeout reduces the newspaper common population to 15. These strata support a future routing hypothesis, especially for visually dense/formula/table pages, but do not establish a production policy.

## 5. Formula deep dive

Classic formula ED is 0.985389 on 35 formula-bearing pages. E2E is better on all 35 common pages in the conditional analysis. That establishes a strong observed quality gap; it does **not** establish that Classic is inherently incapable of formula extraction.

Source trace in `src/doc_extraction/backends/docling_backend.py`:

1. The configured Docling pipeline enables OCR and constructs `EasyOcrOptions` from configured languages (`en`, `vi`).
2. The frozen baseline has no explicit formula-enrichment enablement and uses Docling's default-disabled path. An opt-in repository configuration was added for the candidate experiment; `configs/gpu.yaml` remains unchanged.
3. The adapter maps formula labels to canonical formula elements and propagates available item text; it does not intentionally discard populated formula text. Markdown serialization emits formula text when present and otherwise cannot recover it.
4. The known Chinese empty-output case produced five formula-labeled regions, zero projected OCR tokens, five null-text formula elements, and one-byte Markdown. This is direct evidence of an empty upstream/recognition result for that case, but does not locate why Docling/EasyOCR returned no formula text.

Assessment: **STRONGLY INDICATED CODE/CONFIG GAP**, exact cause **UNKNOWN**. Configured languages `en, vi` are mismatched to a simplified-Chinese source, and optional formula enrichment is disabled; neither alone is confirmed as the causal mechanism. The corpus-wide formula score also includes English cases, so language mismatch cannot explain the whole result. No supported specialist formula path was identified as already available and merely dropped by the adapter. Do not call this a confirmed code bug or a proven capability ceiling. Any language/formula-enrichment change requires a separately versioned configuration experiment and evaluator comparison.

**Follow-up evidence (2026-10-06):** An opt-in `docling_formula_enrichment` configuration path and explicit local `artifacts_path` were added without changing `configs/gpu.yaml` (default remains disabled). With offline local CodeFormulaV2 assets, the same five-page baseline/candidate comparison completed 5/5 valid pages. Baseline had 24/24 formula elements null; the candidate produced text in 24/24. Pinned Formula ED changed **0.948077 → 0.261277** (N=5); Text ED changed 0.462014 → 0.461115 (N=5); Reading-order ED changed 0.564606 → 0.284848 (N=5). Formula ED improved on four pages and was unchanged on the page with no detected formula elements. There were no table metric instances in this cohort. Baseline Markdown matched the stored current-baseline Markdown byte-for-byte on all five pages. Candidate model startup warned that its configured pad token ID is outside the tokenizer vocabulary; despite that warning, all outputs validated and the evaluator result improved. This is strong evidence of a **configuration/path-selection gap for already-detected formulas**, not evidence that formula detection gaps are solved or that a new 180-page configuration is validated.

The original five-page candidate averaged 16.950 s/page versus 14.968 s/page for its paired baseline (+1.982 s/page, +13.2%; totals 84.749 s versus 74.840 s). The earlier 35-page expansion attempt stopped after two pages (113.08 s and 97.31 s); no metrics were calculated. Its Pillow `DecompressionBombWarning` was initially attributed to an unknown formula intermediate. Source tracing and controlled reproduction corrected that attribution: `build_omnidocbench_manifest.py::verify_manifest` opens every dataset image to read dimensions before selecting the explicit page subset. The warning concerns a distinct 145,456,564-pixel source image (`jiaocaineedrop_jiaocai_needrop_en_3222.jpg#2382`) rejected by the frozen 40M-pixel policy; the verifier reads `Image.size` and does not decode or supply that image to Formula enrichment. It is a manifest-validation warning, not a crop, duplicate, or leaked formula intermediate. The warning is not suppressed.

**Bounded formula performance profile and extension (2026-10-06/07):** Installed-source path is `StandardPdfPipeline._init_models` → `BasePipeline._enrich_document` → `BaseItemAndImageEnrichmentModel.prepare_element` → `CodeFormulaVlmModel.__call__` → `AutoInlineVlmEngine.predict_batch` → the selected local engine's `predict_batch` → `TransformersEngine` processor/device transfer and `vlm_model.generate()` → batch decode → formula text written back to the same Docling item → Classic canonical mapping/Markdown. `prepare_element` expands the detected formula box by 0.18 and crops at scale 1.67; the formula stage batches up to five elements. The model call supplies `max_new_tokens=2048` directly in each `VlmEngineInput` in installed `code_formula_vlm_model.py`; this is not exposed by the current repository config. The transformer engine sends prepared tensors to its configured device, calls `generate()` under inference mode, trims the prompt tokens and batch-decodes the result.

An opt-in in-process wrapper profiled the exact `baseline` backend route with local CodeFormulaV2 artifacts. The two-page profile recorded two initialization events, one associated with each page (1.098 s and 1.026 s; repository `docling-project/CodeFormulaV2`, configured revision `main`, local model content hash `4b04e77a…`). The 12-formula page was processed in batches of 5, 5, and 2: batch wall times 5.840/9.629/3.308 s, of which `generate()` took 5.700/9.502/3.257 s. The separate 2-formula page used one batch: 4.269 s wall, 4.221 s in `generate()`. Crop preparation was milliseconds per region (max there 2533×202 = 511,666 pixels). The repository caches component backends per process; installed `DocumentConverter` also caches pipelines by pipeline class/options hash. The observed per-page initialization events are therefore not explained by a simple absence of cache code. No cache miss/recreation trace was retained, so this remains an unresolved reuse question and not a confirmed inefficiency.

A single-page profile of a slow two-formula page (`page-39551bb3-1b65-4562-b258-1bc97898cdf9.png#0`) measured 172.386 s in Docling layout/conversion within a 176.96 s extraction. It recorded one 16.930 s CodeFormulaV2 initialization, crop preparation of 0.162 s for two crops (3747×1625 = 6,088,875 px and 2314×207 = 478,998 px), and one two-region generation batch taking 97.151 s, including 96.948 s in `generate()`. Input sequence width was 605; the returned padded sequence width was 2653, exactly 2048 new sequence positions, matching the installed CodeFormulaVlmModel's hard-coded `max_new_tokens=2048`. Per-region token counts remain unavailable, so this proves the batch reached the generation cap but not which individual region reached it. Output character counts were 4108 and 133; character counts are not token counts. Roughly 58 s of the enclosing Docling conversion remains unallocated by this wrapper. The profile does not prove that cap saturation alone caused the long call, but it makes long autoregressive generation a concrete, measured contributor. The actual crop preparation was bounded and fast; the unrelated 145.46 MP warning was not a formula intermediate.

The 145.46 MP warning is not the resource issue that it first appeared to be. Remaining cost variability is real: the additional five-page formula-enabled extension succeeded 5/5 in 57.448 s total (mean 11.490, median 7.871, p95/max 31.401 s); one page spent 29.205 s in combined Docling layout/conversion. The same five pages were rerun with enrichment disabled: baseline total page runtime was 27.409 s (mean 5.482, max 18.605 s). Candidate adds 30.039 s over these five pages. The pooled ten-page comparison combines **two separate, matched five-page A/B cohorts**: within each cohort the baseline and candidate used identical source snapshots, environment, inputs and all inference options except `docling_formula_enrichment` (off vs on); source snapshots differ between the cohorts (`3e64ed…` for the initial five, `76bb2f…` for the extension five). A metadata defect was found in the derived merged evaluation folders: their aggregate `baseline/run_metadata.json` inherited the enabled candidate config and a five-page count. It is not used as provenance. All 10 merged Markdown predictions were byte-verified against the appropriate parent run outputs, and the pinned evaluator was rerun explicitly on each merged prediction directory against the exact ten-page run-scoped GT. The parent records yield totals of 142.197 s candidate versus 102.249 s baseline (+39.948 s, +39.1%); this is a small, variable sample, not a corpus runtime estimate. Formula ED changed **0.974038→0.388683** (10 pages; delta −0.585356); it improved on 9 pages, regressed on 0, and was unchanged on the page with no canonical formula detection. Text ED changed **0.496402→0.493653** (10; delta −0.002750; 3 improved, 0 regressed, 7 tied). Reading-order ED changed **0.598613→0.390758** (10; delta −0.207855; 7 improved, 2 regressed, 1 tied). All 42 candidate canonical formula elements across these ten pages had non-null text. Per-page canonical comparisons found identical element IDs/types/order indices/bboxes, reading-order arrays, and tables within each matched pair; only formula-element text changed, with no non-formula text changes. Thus the metric movement is not an explicit reading-order sequence rewrite. These are targeted observations, not a representative corpus estimate. The merge/provenance caveat and exact parent-run hashes are documented in `.benchmarks/diagnostics/phase1-formula-combined-10-20261006/provenance-audit.json`. Other artifacts: `.benchmarks/diagnostics/phase1-completion-formula-local-20261006/`, `.benchmarks/diagnostics/phase1-formula-profile-baseline-route-20261006/`, `.benchmarks/diagnostics/phase1-formula-extension-baseline-5-20261006/`, and `.benchmarks/diagnostics/phase1-formula-extension-5-20261006/`.

**Direct paired 20-page experiment (2026-10-07):** `phase1-formula-20-direct-20261006` used exactly 20 frozen representative-v2 IDs, identical order/input hashes/run-scoped GT, evaluator revision `193627ae9e97d89188468ed1ee3b7a856ff76044`, source snapshot `76bb2fcf…`, local CodeFormulaV2 safetensors hash `4b04e77a…`, CUDA device, and the same non-formula settings. The only config difference was `docling_formula_enrichment=false` (config SHA `79efe429…`) versus `true` (SHA `ee7cc606…`). Both arms completed 20/20 with valid canonical documents and exact coverage.

| Metric | Enrichment off | Enrichment on | Delta | Denominator |
| --- | ---: | ---: | ---: | ---: |
| Formula ED | 0.984693 | 0.451075 | −0.533618 | 18 formula-annotated pages |
| Text ED | 0.583445 | 0.527920 | −0.055525 | 20 pages |
| Reading-order ED | 0.646221 | 0.408107 | −0.238114 | 20 pages |
| Table metrics | N/A | N/A | N/A | 0 tables |

Formula ED improved on 17/18 scored pages, regressed on 0, and tied on 1; text improved on 9/20, regressed on 0, tied on 11; reading order improved on 16/20, regressed on 2, tied on 2. Canonical structure was unchanged in all 20 paired pages: IDs, types, boxes, element order/reading-order data, tables, and every non-formula text value matched. The baseline had 103 canonical formula elements, all null; the candidate populated text on all same 103 elements. A formula-bearing annotated page (`jiaocaineedrop_jiaocai_needrop_en_1253.jpg#1996`) still had zero detected formula elements in both arms, so enrichment does not solve detection recall. The two pages with zero `equation_*` GT labels are visibly equation-bearing pages; they are annotation-mismatch checks, not valid visual-negative controls and cannot establish false-positive rate. No table metric was computable.

The cost is large and reproducible on this deliberately formula-heavy cohort: baseline total/mean/median/p95/max was 74.624/3.731/2.627/5.501/17.132 s; candidate was 555.773/27.789/13.758/94.436/96.533 s (7.45× total runtime). The candidate added 481.149 s across 20 pages; three pages took 83–97 s, versus 2.37–4.13 s for those baseline pages. Candidate runtime was dominated by Docling's combined layout/conversion stage. Model warnings remain visible (`pad_token_id=128002` outside vocabulary size 32,000; checkpoint embedding/head values disagree with configured tying). Artifacts: `.benchmarks/diagnostics/phase1-formula-20-direct-20261006/` and the one-page bounded profile `.benchmarks/diagnostics/phase1-formula-profile-slowoutlier-20261007/`.

**Updated assessment (2026-10-07):** The 20-page A/B still establishes a substantial targeted gain for already-detected formula elements, not improved detection recall. A new slow-page profile resolved per-region lengths: one of two formulas stopped at EOS after 47 tokens; the other generated 2,048 tokens without EOS/pad and reached the configured cap. Both regions were passed in one batched `generate()` call, which took 96.327 seconds; the page's Docling pipeline took 99.349 seconds. A diagnostic-only 1,024 cap reduced this page's total runtime from 111.92 to 57.05 seconds and the shared generation call from 96.33 to 42.05 seconds; the long region reached both caps while the short region stopped at 47 tokens. Formula ED on this one page changed from baseline 1.0 to 0.987522 at 2,048 and 0.977049 at 1,024, while Text ED remained 1.0 and Reading-order ED 0.8. This is a one-page exploratory result, not a general quality claim; the slow output remains cap-terminated and the lower bound was applied only by an in-process diagnostic wrapper because Docling 2.124 hard-codes 2,048 in its stage. The model parameters, input, and output tensors were on `cuda:0`. Formula enrichment therefore remains **EXPERIMENTAL, NOT PROMOTED**; broader paired cap validation and visual false-positive controls remain necessary. The earlier 58-second timing discrepancy remains unexplained; the 145.46 MP warning was unrelated manifest scanning.

## 6. Table deep dive

Two high-confidence producer defects were exposed and addressed in the current implementation/tests:

* Table-contained tokens were emitted both as table/cell text and sibling ordinary text. The ownership logic now suppresses only text actually assigned to table cells; titles/footnotes inside the outer table box are not automatically swallowed.
* A visual layout label could be emitted as `TABLE` despite no matching structured table, creating an invalid table reference. The fallback preserves the observed region as `OTHER` plus layout-label evidence and warning rather than fabricating a reference.
* Conversely, a structured table with no matching layout table region could be omitted from the page. The current producer retains the structured table owner; it does not fabricate a layout match.
* Table Transformer’s installed structure model includes a `table spanning cell` class, but the adapter previously ignored it. The adapter now preserves high-confidence, in-grid, non-overlapping contiguous spans; adversarial tests reject boundary-crossing/ambiguous cases and ensure ordinary/no-grid tables remain safe. Bounded one-, five-, and twenty-page evaluations show improvements on observed span-bearing tables (details below). This is a confirmed implementation omission with direct model-output evidence, not a claim that all span failures are fixed.

The fixes are protected by focused table/conformance regressions and did not change the public canonical schema. The latest full Classic run has table ED 0.701108, TEDS 0.407739 and structure TEDS 0.649114. These weak remaining scores are not themselves a diagnosis. TEDS structure exceeds full TEDS, consistent with content/text matching being harder than structure alone, but that difference does not identify whether a particular residual error comes from OCR, grid detection, spans, or a model limitation. Current run warnings additionally show real residual table reconstruction uncertainty (rows synthesized from OCR; unmatched layout/structure objects; no detected grid on some table-labeled regions). Further fixes require per-example image/structure diagnosis, not score chasing.

The historical ownership A/B artifacts cover 178 pages. They show unchanged table aggregate metrics in that comparison, while text/reading aggregates differ. A separate Python/Torch extraction environment mismatch exists, so those changes are **observed**, but causal attribution to the ownership fix is **NOT ESTABLISHED**. On `jiaocaineedrop_jiaocai_needrop_en_397.jpg#1830`, Markdown changed 1160→878 bytes, text ED .342857→.328407, reading ED .500000→.642857, while table metric was unchanged. Output inspection showed the table remained represented; the mixed metric movement is not a clean improvement claim.

**Table serialization ablation (2026-10-06):** A generic correctness defect was found: Markdown pipe tables cannot faithfully represent merged-cell spans or cell text containing `|`/line breaks. `Table.to_markdown()` now uses escaped HTML table markup for those cases; ordinary tables retain byte-identical pipe Markdown, and overlapping cells fail closed. This change does not alter detection, cell text, or ownership. An offline, strict 180-page replay used retained canonical documents only when the legacy serializer reproduced the current baseline Markdown exactly; four verified pages were re-rendered and the other 176 predictions remained byte-identical controls. Exact run-scoped GT and pinned evaluator were used. Table ED changed **0.701108 → 0.683837** (50 pages, delta −0.017270); TEDS **0.407739 → 0.407777** (64 instances, +0.000038); structure TEDS **0.649114 → 0.649596** (64 instances, +0.000482). Text, reading-order and formula metrics were unchanged. Per-page table ED improved for three of the four replacements (0.771102→0.756703; 0.649860→0.322981; 0.739203→0.216965); the Chicago Tribune replacement had no per-page table-ED value. This is a **serialization-only candidate replay**, not a fresh extraction baseline: it demonstrates a measurable, mechanism-linked table metric gain on the frozen population, but does not replace the official Classic baseline artifact. Artifacts: `.benchmarks/diagnostics/phase1-completion-table-export-attested-20261006/`.

**Table Transformer span ablation (2026-10-06):** Source inspection of the cached structure-recognition model confirmed its sixth label is `table spanning cell`; the prior backend ignored it and emitted only unit cells. The backend now preserves non-overlapping contiguous span detections as explicit cell row/column spans, while ignoring ambiguous/single-slot detections. A one-page validation on `jiaocaineedrop_jiaocai_needrop_en_3751.jpg#2485` produced a valid 3×6 table with 17 cells and an explicit 1×2 merged cell; its Table ED changed **0.649860→0.301242**, TEDS **−0.022727→0.023810**, and structure TEDS **0.590909→0.666667**. This is direct evidence that the model emitted a span and the adapter preserved it, but remains a single-page diagnostic.

A predeclared five-page extension on difficult GT span-bearing pages completed 5/5 valid and showed Table ED **0.856285→0.783827** (5 pages); mean per-table TEDS **0.111428→0.119991** and structure TEDS **0.199584→0.216040** (10 instances). Four model spans appeared across two pages; three other pages emitted no spans/table. This was a selected diagnostic, not a corpus estimate.

**Broader span/serialization validation (2026-10-06):** A deterministic 20-page cohort was selected from the frozen manifest using the 15 span-annotated pages with the highest frozen table error plus five table-bearing controls without GT span annotations. To remove the previous source-snapshot mismatch, a fresh 20/20 control was extracted at clean HEAD `caf0ac6dff53306cd1c69185a619f95305898bd6` in a disposable worktree, with the same image hashes, `configs/gpu.yaml` hash, Python/package environment, run-scoped 20-page GT and pinned evaluator. Its only attested worktree dirt was the `.cache` symlink used to share already-installed model artifacts; no tracked source files were modified. The candidate also completed 20/20 with valid canonical outputs and was scored explicitly from its candidate prediction directory (not the metadata-selected baseline comparator directory). No table-ED regressions were observed: **5/20** pages improved, **15/20** tied, **0/20** regressed. Those five changed pages exactly match the pages where candidate canonical inference emitted spans (10 merged cells total); the other span-annotated pages and all controls emitted no explicit spans and their table ED was unchanged. Aggregate Table ED changed **0.769833→0.665829** (20 pages; −0.104005); TEDS **0.301810→0.305264** (20 pages; +0.003455); structure TEDS **0.463780→0.467456** (20 pages; +0.003675). Text ED was unchanged at **0.713435** on 15 eligible pages; reading-order ED unchanged at **0.793014** on 20 pages. The cohort is deliberately enriched for hard span cases and is not a corpus estimate. Candidate runtime was 154.0 s versus 148.4 s for the clean-HEAD control, with 20/20 success in each. The candidate includes both preservation of recognized spans and the already-tested safe HTML serializer; this A/B does not isolate those two code changes from each other. Neither official config nor frozen baseline was changed. The paired control/candidate identity and metric provenance are captured in `.benchmarks/diagnostics/phase1-table-spans-20-20261006/paired-head-control-comparison.json`; predictions remain in the two run directories.

**Current table conclusion:** Span preservation is a strong, locally reproducible implementation candidate and is appropriate to retain in source with its tests; the 20-page targeted run supports the mechanism and shows no selected-cohort regressions. The five-page-per-table metrics in earlier probes and 20-page/page-denominator metrics are not comparable to the official 180-page aggregate. A new full Classic baseline is not generated here; any refresh should occur only as a separately attested run after candidate review. Serialization-only replay remains a distinct candidate result (4 changed page exports among 180) and should not be conflated with this extraction change.

## 7. Reading order and text/OCR

Classic reading-order ED is 0.596823 on 178 pages. The evaluator's order sequence includes recognized content; missing/extra elements can therefore increase this score even when the physical ordering algorithm is not the sole defect. Observed difficult groups include three-column pages (ED 0.7313), table-hard pages (0.7901), simplified Chinese text (0.7469), and newspaper pages (0.6580). The code has an explicit column-aware geometric reading-order stage and canonical explicit order references. No single corpus-wide reading-order implementation defect is established from these aggregates. Dominant residual class remains **UNKNOWN / mixed content and ordering errors** pending targeted page inspection.

Classic text ED is 0.589397 on 168 pages. Recomputing per-page errors from the frozen run artifact gives: English **N=77, mean 0.1860**; simplified Chinese **N=77, mean 0.9688, median 0.9932, 21 pages at ED 1.0**; mixed Chinese/English **N=12, mean 0.7584**; traditional Chinese **N=1, mean 0.9946**; other **N=1, mean 0.0026**. These are arithmetic means of per-page edit distances, not the aggregate metric's denominator-weighted score. The frozen config requests OCR languages `en, vi`. In a stored image-route forensic record with the same config hash, one visually dense two-column Chinese page with **three GT text-block annotations** produced only one OCR token (`"4 ,"`); its run record identifies Docling 2.124/EasyOCR 1.7.2. The first cache scan missed Docling's packaged model directory; a local EasyOCR `zh_sim_g2.pth` checkpoint is present at `.cache/docling/EasyOcr/zh_sim_g2.pth`, and Docling maps `ch_sim` to that asset. The production config still omits Chinese. A paired seven-page CPU A/B confirms that this mismatch is actionable for some Chinese pages but does not justify global multilingual configuration: Chinese Text ED improved modestly overall, while English and mixed-language groups regressed under `ch_sim,en` (full numbers in the latest addendum). System Tesseract exposes only `eng`, `osd`, and `vie`. Other residual causes include omitted layout regions, recognition errors, ownership, and order/serialization.

### Newly identified Classic bottleneck: OCR language coverage

The error stratification plus stored OCR trace made language support a high-confidence broad Classic opportunity. The follow-up found the local CJK checkpoint and ran a strict seven-page paired A/B without downloading a model. It confirms a baseline configuration omission and shows language-specific quality trade-offs, not a universally safe global config. A CPU-only Tesseract OSD probe then covered all 179 English, mixed, and Chinese-language pages in the frozen manifest (83 simplified Chinese, 1 traditional Chinese, 13 mixed, 82 English). `Han` was returned for 63/84 Chinese pages and 2/95 English-or-mixed pages: descriptive script-label precision 96.9%, recall 75.0%, specificity 97.9%; one English OSD result was unavailable and fell back to the non-Han route. On the original seven-page A/B cohort, OSD labels select exactly the three pure-Chinese candidate outputs and retain baseline outputs for mixed/English pages; replaying those saved outputs yields the same Text ED as the GT-language oracle, .602618 vs baseline .639547. This supports a **bounded page-level routing candidate**, not a production router: output-level route quality is measured on only seven pages, the signal misses one quarter of Chinese pages, false-positive impact is not yet measured on the broader cohort, and there were no Vietnamese controls.

## 8. E2E strengths and Classic strengths

### E2E observed strengths

On the exact 179-page common set, E2E has lower text, formula, table-edit, and reading-order error, and higher table TEDS/structure TEDS. The paired counts and metric denominators are in Sections 3–4. Examples include the known Classic-empty Chinese page (`page-062fc21c-6b9c-40be-8d0e-7a617509a9bc.png#0`): Classic text/reading ED 1.0/1.0 versus E2E text 0.19436 and reading 0.0. This is one observed example; text remained imperfect.

### Classic observed strengths and complementary cases

Classic is substantially cheaper and has deterministic physical structure/validation guarantees. It remains useful for predictable, lower-cost extraction and fallback/specialist roles. English-language text group ED is 0.1860; multiple pages show Classic beating E2E on paired metrics. At `jiaocaineedrop_jiaocai_needrop_en_397.jpg#1830`, Classic table ED is .59574 versus E2E .88691 even though E2E has better text/read order on that page. On `yanbaopptmerge_1c5f17c3dfa38c45b86802b9d014da18.pdf_1372.jpg`, Classic text ED .01575 and reading ED .25 versus E2E 1.0/1.0. The cause of the E2E catastrophic result is unknown; retaining Classic as a first-class backend is warranted. The examples support complementarity, not routing thresholds.

## 9. Runtime and hardware cost

### Backend wall-clock comparison

| Backend/run | Mean per attempt | Median | p95 | Max | Coverage/failures |
| --- | ---: | ---: | ---: | ---: | --- |
| Classic, 180-page run | 6.492 s | 4.320 s | 18.935 s | 75.466 s | 180/180 valid |
| E2E, 180 attempts | 40.566 s | 29.165 s | 93.608 s | 300.832 s | 179 success, 1 timeout |
| E2E successful pages only | 39.112 s | 29.165 s | 91.377 s | 186.747 s | 179/179 successful |

The all-attempt mean multiplier is **6.25×** (E2E/Classic); successful-only is **6.02×**. This is a backend comparison. Both official runs used GPU-assisted execution on an L4; it is not a GPU-vs-CPU speedup.

### Hardware use and CPU-only Classic sample

The official Classic config requested `cuda`; the E2E worker used the L4. Existing timeout telemetry for page 42 reports worker CPU near one saturated core, RSS peak about 2.33–2.63 GiB, GPU utilization median around 18–19% (p90 around 24%, samples up to 100%), and GPU memory observed up to 9,108 MiB in those diagnostic traces. These observations indicate low/moderate average GPU activity and CPU saturation but do not identify a specific hardware bottleneck by themselves.

A separate five-page CPU-only Classic sample was run with `CUDA_VISIBLE_DEVICES=''` and `configs/cpu.yaml`, on the same frozen newspaper pages used in the token-cap experiment. It completed 5/5 in 1,016.12 seconds; mean 203.225 s, median 201.413 s, p95/max 265.400 s. One page had one table reconstruction warning; no extraction failures. At the time, stored GPU-assisted full-run times were used to form a descriptive ratio, but a later fresh matched GPU sample found Markdown content differs on all five pages. Therefore that earlier 6.01× figure is **not a valid speedup comparison** and is superseded by the non-equivalence finding in the addendum. CPU-only Classic is supported but costly for dense newspaper images; a same-output CPU/GPU acceleration factor remains unestablished. No L4 was used for the CPU-only run; repeated PyTorch “pin_memory but no accelerator” warnings are expected configuration noise.

### Model compute vs plumbing

E2E page `pipeline_predict` accounts for mean 27.125 s across the 179 successful pages; canonical mapping, validation, JSON decoding, and serialization are negligible in the per-page traces. Parent model-artifact attestation averages 5.879 s/page (about 1,052.27 seconds total over 179), and post-page run-metadata/model-version attestation averages 5.908 s/page (about 1,057.45 seconds total). These are recurring per-page costs, not one-time startup. Together they are about 11.79 s/page, roughly 30% of successful-page mean E2E wall time. Worker startup/model load is persistent-worker setup and must not be multiplied by pages when interpreting totals. Attestation is a separate future plumbing optimization; it does not explain the pathological generation operation.

## 10. E2E pathological timeout

The official config remains PaddleOCR-VL 1.6, `max_new_tokens=4096`, local recognition batch size 1, 300-second operation deadline. Page 42 has 119 detected layout regions, 113 crops, and 102 VLM inputs processed serially. Generation dominates the public `pipeline.predict()` interval. In the diagnostic/reference trace, batch 16 took about 120.6 seconds at 4096; the 4096/2048/1024 token-cap experiment measured about 120.753/60.756/30.131 seconds for that batch, yet all three full-page settings still timed out at about 300 seconds. The 4096 non-benchmark extended diagnostic reference completed in about 433.8 seconds. Region batching above one is not supported by the installed local predictor and is clamped; the guard was not bypassed. Lower-resolution diagnostics at 13.26, 7.46, and 3.31 megapixels also timed out. Actual token counts for the pathological generation were unavailable; the 22,300 decoded characters are not a token count.

Classification: **known pathological runtime characteristic; deeper model/decoder cause UNKNOWN**. The timeout is correctly enforced, the isolated worker is terminated, scratch state is cleaned, and no prediction is published. The official E2E result remains **179/180; full-180 quality WITHHELD**. No additional cap/batching/resolution experiments are justified in this phase.

## 11. Security and reliability evidence

Implemented evidence includes input byte/unit/runtime/temp/pixel/output limits; archive member, expansion, compression-ratio, traversal, symlink, drive/path-collision, encryption and CRC defenses; DTD rejection; image pixel checks for direct and embedded images; OCR output caps; and fail-closed run publication. E2E inference runs in an isolated worker process with bounded IPC, hard deadline, process-group cleanup and scratch cleanup. Tests cover malformed/truncated/oversized worker responses, invalid canonical output, crashes/timeouts and cleanup. This is **process isolation, not an OS sandbox**; native libraries and the ordinary in-process Classic path do not gain general force-kill isolation from that design.

The benchmark path verifies frozen manifest identity, run-scoped GT pairing, exact IDs, duplicates/missing/unexpected outputs, canonical validity and evaluator revision. A partial E2E run is not scored as a complete 180-page benchmark. The 179-page conditional report is explicitly scoped and separately paired.

## 12. Contract and integration ownership

The authoritative CDOI public boundary is `DocumentExtractionContract` 1.0.0, implemented/payload-named `ExtractionPackage v1`, according to the CDOI owner-supplied specification facts for this audit. Internal Extraction `Document` 1.4.0 is distinct from that package and from KP `DocumentIR`. The public API remains `doc_extraction.cli.process_file(path, config, output_root=...)`, which returns/writes only the internal canonical Document; the Web Acquisition seam does not implement the package producer.

The actual normative specification file/revision, producer implementation, KP adapter, `DocumentIR`, EvidenceRef resolver, and `cdoi_doc_extraction_adapter_v1` source were not found in this checkout or accessible sibling workspace. Thus the contract is **defined and authoritative**, but adoption is **not established**. Extraction lacks explicit run ID, source size, guaranteed MIME, section model, cell IDs and structured ContractIssue/ErrorEnvelope mapping; KP-side validation, adaptation, EvidenceRef preservation and incompatible-version rejection are unverified. See [`contract-adoption-audit.md`](contract-adoption-audit.md) and [`cdoi-teammate-confirmation-checklist.md`](cdoi-teammate-confirmation-checklist.md). Do not call this “contract undefined”; do not claim cross-team adoption until producer and consumer test evidence is supplied.

## 13. Bug-vs-capability matrix

| Capability | Classic metric/signal | Observed failure | Root-cause class | Fixable locally? | E2E evidence | Recommended phase |
| --- | ---: | --- | --- | --- | --- | --- |
| Text | ED .589397 / N168 | Large language/layout-dependent misses; Chinese group ED .9688 | **STRONGLY INDICATED** language/config gap; mixed recognition/layout causes otherwise **UNKNOWN** | Language config is configurable; quality fix not proven | Conditional ED .045949 / N167; E2E better 162/167 | Phase 2: controlled language/config and per-page error study |
| Reading order | ED .596823 / N178 | Multi-column/table/dense pages; metric also reflects missing/extra elements | **UNKNOWN** as a general defect; no corpus-wide confirmed ordering bug | Existing deterministic stage exists; targeted defect only if isolated | Conditional ED .164918 / N177; E2E better 129, ties 42 | Phase 2: targeted diagnosis, avoid rewrite |
| Tables | ED .701108 / N50 | OCR/cell-content errors; unmatched structure warnings | Two prior **CONFIRMED CODE BUGS** fixed; residual root cause **UNKNOWN / capability gap indicated** | Ownership/reference defects fixed; remaining accuracy mechanism not isolated | Conditional ED .567469 / N50; E2E better 41 | Phase 2: inspect representative residuals |
| Table structure | TEDS .407739 / 64 instances; structure .649114 | Missing/misaligned structure and content; warnings show no-grid/unmatched cases | Fixed producer ownership cases; other failure mechanisms **UNKNOWN** | Locally fixable only when a concrete invariant violation is reproduced | Conditional TEDS .844484, structure .871228 / 64 instances | Phase 2: separate structure-model vs OCR errors |
| Formula | ED .985389 / N35 | Formula labels with null text; known Chinese page has 5 such elements and 0 projected OCR tokens | **STRONGLY INDICATED CODE/CONFIG GAP**; exact cause not established | No safe fix proven; formula enrichment/language requires config experiment | Conditional ED .079500 / N35; E2E better 35/35 | Phase 2: bounded formula/language config experiment |
| Geometry | No official quality metric | Canonical bbox validity is tested; source-pixel alignment accuracy not scored | **UNKNOWN** quality | Conformance guarantees structure/finite coordinates, not accuracy | E2E canonical outputs validated; no comparable geometry score | Phase 2 only if an evaluation method/use case is defined |

## 14. Routing evidence matrix

These are hypotheses from this dataset, not routing rules.

| Document characteristic | Classic evidence | E2E evidence | Runtime cost | Routing hypothesis |
| --- | --- | --- | --- | --- |
| Simple/native-like text | English text group ED .1860; Classic is deterministic and cheaper | Strong text quality on common set, but slower | E2E mean attempt 6.25× Classic | Prefer Classic as low-cost first pass where output checks pass; “native” is not directly labeled/measured |
| Complex table | Current ownership/reference invariants fixed; table performance still mixed | TEDS/structure strongly higher on conditional 64 objects, but Classic wins some pages | E2E materially slower | E2E is a candidate specialist for complex visual tables; keep Classic fallback |
| Formula-heavy | Classic formula ED .9854, likely language/enrichment gap but root cause open | Formula ED .0795 on 35 paired pages | E2E slower; one overall timeout elsewhere | E2E candidate specialist, retain explicit failure handling |
| Dense newspaper | Classic CPU-only sample is expensive but works; GPU-assisted run completed | Very strong conditional newspaper text/order on 15 pages; Washington Post page 42 times out | E2E can exceed 300 s on a page | Possible E2E benefit, but only with runtime gate/fallback; no automatic selection |
| Scanned visual page | Classic visual route exists; quality depends on OCR language/layout | E2E often improves text/layout measures conditionally | E2E higher mean/p95 and timeout risk | Route only after future validated profile/quality signal, not scan status alone |
| Uncertain layout | Classic has explicit layout/order diagnostics and canonical validation | E2E can resolve some failures, also has catastrophic regression | E2E cost and failure isolation matter | Candidate confidence/evidence gate could be explored later; no router now |

## 15. Experiment ledger

Each row refers to the existing run/test/report artifacts; this ledger is an inventory, not a claim that all were rerun for this report.

| Experiment | Question / method | Result and artifact | Evidence strength | Established | Not established |
| --- | --- | --- | --- | --- | --- |
| Input/security hardening | Bound untrusted files, archives, images and subprocess output | `docs/security-review.md`, `docs/resource-limits.md`, security tests | Confirmed implementation/tests | Defined limits and rejection paths | General OS sandboxing; RSS cap for all native libraries |
| Canonical boundary/conformance | Validate internal Document invariants | schema v1.4.0, backend conformance helpers/tests | Confirmed | Structure, references, nulls, order and failure validation | External cross-team contract |
| Evaluator strict pairing | Prevent subset/full-GT mismatch | `tests/test_omnidocbench_subset_pairing.py`; `experiments/005_omnidocbench/evaluate.py` | Confirmed by tests | Run-scoped exact GT, no silent full-dataset fallback | Any score on a failed-coverage run |
| representative-v2 construction | Freeze eligible sample and exclusions | `benchmarks/manifests/omnidocbench-representative-v2.json` | Hash-attested | 180 fixed IDs, eligibility/resource exclusions | Generalization beyond selected population |
| Classic table ownership | Prevent duplicate table-cell/sibling text | base pipeline and ownership tests; historical paired artifacts | Confirmed invariant, causal metric effect not established | Ownership behavior and regression protection | Global score improvement caused by change |
| Unmatched table handling | Avoid dangling/fabricated table refs; retain unmatched structured table | `2bebeda`, `tests/test_orphan_ocr_recovery.py` | Confirmed targeted defect/fix | Canonical references preserved on tested cases | Full metric effect of final committed implementation |
| Classic forensic trace | Observe layout/OCR/formula/canonical stage aggregates | `docs/visual-forensics.md`, `src/doc_extraction/utils/visual_forensics.py` | Confirmed implementation; underlying failure cause partial | Detect zero OCR projection and stage gaps | Why upstream OCR returns zero on all cases |
| Classic current 180 run | Score frozen population | `.benchmarks/runs/omnidocbench/classic-current-valid-20261003T153500Z/` | Valid coverage; source snapshot caveat | 180/180 valid and listed metrics/runtime | Byte-identical clean final-HEAD rerun |
| Classic ownership A/B | Compare stored pre/post pages | `.benchmarks/diagnostics/classic-postfix-paired-completed178-20261003/` | Observed; environment confounded | Outputs/metrics differed on some pages | Causal attribution |
| E2E integration/isolation | Run PaddleOCR-VL behind process/IPC boundary | `docs/e2e-backend.md`, E2E tests and run records | Confirmed tests and runtime | Hard timeout/cleanup/validated protocol | Full OS sandbox |
| E2E GPU preflight/smoke/20-page | Validate model/env, small smoke and preflight | `e2e-gpu-v3-20261003T065100Z` subruns | Operationally observed | GPU/model/env and 20/20 preflight gates | Determinism (page 42 failed both repeats) |
| E2E official 180 attempt | Execute exact frozen IDs under 300 s | `.benchmarks/runs/omnidocbench/e2e-gpu-v3-20261003T065100Z/08-full-180-20261003T065030Z/` | Exact coverage accounting; incomplete outputs | 179 successes, one timeout; no full score | Official full-180 E2E quality |
| E2E timeout telemetry/phase timing | Locate page #42 cost | e2e v3 runtime/timeout diagnostic traces | Measured coarse stages | `pipeline.predict`/generation dominates; cleanup correct | Deepest decoder operation/cause |
| E2E token cap | Compare 4096/2048/1024 on 5 pages | isolated `e2e-config-experiments` records | Controlled single-variable experiment | Page 42 times out for all; slow batch duration decreases | Cap resolves page-level completion or quality tradeoff |
| E2E batching capability | Inspect local predictor >1 behavior | PaddleX 3.7.2 installed source audit | Direct source observation | Local predictor supports/clamps to batch 1 | Performance if dependency behavior were changed |
| Contract/KP source discovery | Find authoritative CDOI contract and verify producer/KP artifacts | `docs/contract-adoption-audit.md`, `docs/cdoi-teammate-confirmation-checklist.md` | Owner-supplied contract facts + bounded repo/sibling search | Specification is authoritative; implementation paths not found locally | That KP adoption or EvidenceRef resolution works |
| Acquisition seam | Check Artifact to public extraction API | `services/web-acquisition/src/web_acquisition/integration.py` | Direct source observation | Public `process_file` seam; no package adapter | External KP integration |
| CPU-only Classic timing | Run the five frozen newspaper pages with CUDA hidden | `.benchmarks/diagnostics/phase1-classic-cpu-newspapers-20261003/` | Measured small sample | CPU backend path works and is slow on dense pages | Corpus-wide CPU/GPU multiplier |

Historical 1,651-page metrics are intentionally excluded from the paired evidence above.

## 16. Phase 1 closure decision — physical Extraction scope

**FREEZE WITH EXPLICIT E2E LIMITATION** for the repository's physical extraction, security, and benchmark scope.

Phase 1 has sufficient evidence to freeze its safety boundaries, canonical internal model, public API seam, frozen representative-v2 manifest, strict run-scoped evaluator, Classic conformance behavior, and E2E isolated-worker experimental path. Classic has a complete 180/180 scored run artifact. E2E has validated model execution, isolation, cleanup, a 20/20 preflight, conditional paired quality evidence over 179 pages, and a reproducible timeout. The timeout is a real operational limitation and correctly prevents a full official score. Do not label E2E a production-ready replacement. This repository-level freeze does not assert adoption of the official CDOI package; that cross-team gate remains open as recorded below.

Two qualifications remain part of the frozen record: (1) the Classic full-run source attestation differs from final HEAD in `base.py`, so the scores are not a clean final-HEAD reproduction; (2) GPU determinism was not established because page 42 timed out in both determinism runs. Neither is hidden by the conditional analysis. If release policy requires a clean immutable-HEAD baseline or demonstrated E2E determinism, those are explicit acceptance gates before claiming those stronger properties—not reasons to fabricate or weaken existing scores.

## 17. Phase 2 backlog (not started)

### Correctness

* If an immutable-HEAD Classic score is required, run one controlled Classic 180-page reproduction from a clean, attested source snapshot; first resolve why the previous source attestation differs from final `base.py`.
* Consider a fresh current-source Classic 180-page extraction/evaluation only if an immutable post-serialization baseline is required; the current offline replay isolates the generic serializer change but is not a fresh extraction run.
* The table-span backend change has a promising mechanism-specific result in one direct probe, five-page extension, and clean-HEAD paired 20-page cohort. Adversarial tests cover span validity; the candidate bundle also includes safe HTML serialization, so the two effects are not isolated in the 20-page run. No full 180-page rerun was performed; any baseline refresh remains a separately attested decision.

### Optimization

* E2E page 42: deeper Paddle/PaddleX/model decoder profiling remains an external/model-library investigation. Do not change batch guard, timeout, token cap or image semantics without a separately frozen configuration experiment.
* Measure whether per-page model and run-metadata attestations can be safely cached once per worker/run (currently ~11.79 s/page combined); keep provenance guarantees intact.

### Hybrid routing

* Test a small, predeclared routing hypothesis from document/layout signals only after per-category denominators and failure behavior are specified. No router or score threshold is approved by this report.

### Integration

* Confirm the immutable source revision/hash and executable schema for the already-authoritative CDOI contract; implement the ExtractionPackage v1 producer and obtain KP validator/`DocumentIR`/EvidenceRef test evidence. Do not invent field semantics.

### Model research

* Formula enrichment passed a direct 20-page paired quality/coverage experiment for already-detected formula elements, but is **not promoted**: selected-cohort runtime was 7.45× baseline. A later one-page profile measured per-region lengths (2,048 positions with cap-length observed; 47 positions with EOS), and an isolated 1,024-cap diagnostic reduced that page's generation time by 56.4% but remained cap-terminated and is not broad enough to establish a safe limit. Fine-tuning and training-data creation remain **not started**.

## Evidence artifacts

The companion machine-readable summary is [`benchmarks/reports/phase1-capability-summary.json`](../benchmarks/reports/phase1-capability-summary.json). Run artifacts remain ignored local research data; this report does not commit predictions, model weights, caches, or profiler dumps.

## Addendum — final bounded Classic measurements (2026-10-03)

These experiments were performed after the original evidence cut. The repository remained at HEAD `00be1ed`; neither production config, model/dependencies, manifest, nor extraction source was changed. Before each GPU run, `nvidia-smi` showed an idle NVIDIA L4. After each run, memory returned to 0 MiB and no compute process remained.

### Matched Classic CPU/GPU timing sample

The CPU-only sample and a fresh GPU-assisted sample used the same five manifest page IDs, input hashes, source snapshot (`2bebeda`), Classic path and resource limits. The configs differed by device (`cpu` versus `cuda`); the output format was Markdown, and the GPU run retained canonical JSON for inspection. Both runs completed 5/5 pages with one warning on Chicago Tribune (the same table-row synthesis warning).

| Page | CPU seconds | GPU seconds | CPU/GPU ratio |
| --- | ---: | ---: | --- |
| Washington Post #42 | 201.413 | 101.706 | Not calculated |
| `newspaper_5a8b…#1` | 236.419 | 29.014 | Not calculated |
| `newspaper_8076…#1` | 124.803 | 13.407 | Not calculated |
| Boston Globe #33 | 265.400 | 27.354 | Not calculated |
| Chicago Tribune #32 | 188.088 | 24.612 | Not calculated |
| **Mean** | **203.225** | **39.219** | **Not calculated** |
| **Median** | **201.413** | **27.354** | **Not calculated** |
| **p95 / max** | **265.400 / 265.400** | **101.706 / 101.706** | **Not calculated** |

Markdown content differed on all five pages. Examples range from a short OCR line changing from `# 4` to `#L#ì#IlF.` to punctuation, word-order, and table-content differences on the newspaper pages. Thus outputs are classified **CONTENT DIFFERENCE**, not equivalent. CPU canonical JSON was not retained, so structural equality is **NOT COMPARABLE**. Per the experiment's stop rule, these timings are reported as a matched descriptive sample only; no acceleration ratio is valid. Difference cause is unknown (device-dependent recognition/numerics or other runtime variation are possibilities, not established causes). Do not call this a universal GPU speedup.

Artifacts: `.benchmarks/diagnostics/phase1-classic-cpu-newspapers-20261003/` and `.benchmarks/diagnostics/phase1-classic-gpu-matched-20261003/`.

### Formula capability experiment — evidence cut 2026-10-03 (historical; updated by the 2026-10-06 ablation in Section 5)

Source inspection confirms Docling 2.124.0's `PdfPipelineOptions.do_formula_enrichment` defaults to `False`; its CodeFormulaVlm default preset is `CodeFormulaV2`, `AUTO_INLINE`, repo `docling-project/CodeFormulaV2`, revision `main`, with `extract_formulas=True`. The stage is created only when code or formula enrichment is enabled. It processes formula-labeled items and writes the returned text back to the same item. The Classic adapter propagates public formula-item text when present. No local adapter behavior was found that deliberately clears valid formula text.

A 630,993,616-byte `model.safetensors` exists at `.cache/docling/docling-project--CodeFormulaV2/model.safetensors` (SHA-256 `4b04e77af34c4e682a7ab1617628340d658f3c3dcd12456dd2a7fff805cf79d2`). However, the installed `AUTO_INLINE` path, when the sole option `do_formula_enrichment=True` was enabled in an isolated process, attempted Hub snapshot resolution for revision `main`. With Hub traffic disabled to obey the no-download rule, it failed on all five pages with `LocalEntryNotFoundError: Cannot find an appropriate cached snapshot folder for the specified revision`. The separate Docling artifact directory therefore does not currently satisfy the runtime's Hub snapshot lookup. No page prediction was accepted; no model was downloaded.

The initial five-page selection included four pages with formula metrics and the known Chinese empty-output regression fixture, which has no formula metric entry. After seeing that denominator mismatch, one additional, manifest-selected formula-scored page was run as a bounded replacement: `jiaocaineedrop_jiaocai_needrop_en_1253.jpg#1996`. The resulting scored cohort is now five pages (the four original scored pages plus this replacement). The Chinese fixture remains a separate, unscored diagnostic and is not included in the five-page metric cohort.

| Page | Formula elements | Text-bearing / null | Baseline Formula ED | Candidate ED |
| --- | ---: | ---: | ---: | ---: |
| `PPT_MMAT5390Lecture1_page_023.png#23` | 2 | 0 / 2 | 0.948718 | N/A — candidate initialization failed |
| `book_zh_CNASGL0072018_extracted_page_48.png#48` | 8 | 0 / 8 | 1.000000 | N/A — candidate initialization failed |
| `docstructbench_llm-raw-scihub-o.O-j.physletb.2004.06.101.pdf_3.jpg#3` | 12 | 0 / 12 | 1.000000 | N/A — candidate initialization failed |
| `exam_paper_en-file-putnam-archive_2013_Problems_2013_page_002.png#2` | 2 | 0 / 2 | 1.000000 | N/A — candidate initialization failed |
| `jiaocaineedrop_jiaocai_needrop_en_1253.jpg#1996` | 0 | 0 / 0 | 0.791667 | N/A — not included in candidate attempt |

The five scored baseline pages have a descriptive mean Formula ED of **0.948077 (N=5)**. Across these outputs, 24 canonical formula elements were present and all 24 had null text; the replacement page had zero canonical formula elements despite a scored GT formula metric. The Chinese diagnostic fixture separately had five formula elements, all null, and no Formula ED entry. The candidate attempt used the original four scored pages plus that diagnostic fixture; pipeline initialization failed before extraction on all five, so candidate runtime/metrics are unavailable and no valid candidate predictions were published. The replacement page was not run under the candidate config. This is **not** evidence that CodeFormulaV2 recognition itself is ineffective; candidate inference never occurred.

**Formula classification at that time:** **FORMULA RESULT REMAINS UNRESOLVED.** The enabled stage could not resolve the separate Docling cache through Hub snapshot lookup. This was a path-resolution failure before inference, not evidence about recognition quality. The 2026-10-06 experiment below resolved the local path by passing the supported `artifacts_path`; its limited results supersede the then-current claim that no candidate inference had occurred, but do not establish full-corpus impact.

Artifacts: `.benchmarks/diagnostics/phase1-formula-baseline-20261003/`, `.benchmarks/diagnostics/phase1-formula-baseline-replacement-20261003/`, and `.benchmarks/diagnostics/phase1-formula-candidate-codeformulav2-20261003/`. The candidate directory is failure-only diagnostic metadata; it contains no candidate prediction set.

### Updated decisions

* **Matched hardware cost:** mean wall time was 203.225 s/page CPU and 39.219 s/page GPU-assisted on the same five pages, a descriptive wall-clock ratio of about **5.18×**. Markdown differed on all five pages and CPU canonical JSON was not retained; output equivalence is not established, so this is **not a validated hardware speedup**.
* **Formula decision as of 2026-10-03:** **FORMULA RESULT REMAINS UNRESOLVED**; the candidate comparison was blocked at model snapshot resolution. The later five-page candidate succeeded with locally pinned artifacts and is recorded in Section 5; it remains a candidate, not a promoted official configuration.
* **GPU decision:** only bounded Classic formula/table diagnostics were run in this evidence update. The L4 was verified idle before each GPU experiment and released after extraction; no E2E or full-population benchmark was run.
* **Phase 1 decision:** remains **FREEZE WITH EXPLICIT E2E LIMITATION**. Classic remains 180/180 valid as previously reported; E2E remains 179/180 incomplete with full quality withheld. Fine-tuning remains **NOT STARTED**.

## Official CDOI Contract Adoption Status

**Official identity:** `DocumentExtractionContract` 1.0.0 = `ExtractionPackage v1`. The official contract is now treated as authoritative. **Repository adoption status: SPECIFICATION AVAILABLE; IMPLEMENTATION UNCONFIRMED.** The current producer still emits only internal `Document` 1.4.0; the contract producer and KP `DocumentIR`/EvidenceRef adapter are not present in the inspected workspace. Exact field mapping, stable cell identity, source/run provenance, structured issues, FATAL conversion, unknown-field/version rejection and KP preservation need owner-confirmed paths and tests.

The authoritative user-supplied contract facts resolve the former “contract source unknown” blocker, but do not constitute implementation evidence. The repository's completed physical extraction/benchmark work can be frozen separately; **cross-team contract adoption cannot yet be claimed**. See [the field-level audit](contract-adoption-audit.md), [the teammate checklist](cdoi-teammate-confirmation-checklist.md), and [the teammate-ready handoff](cdoi-teammate-confirmation-handoff.md). In particular: do not add `document_revision_id`; keep URLs, artifact/job IDs and retrieval timestamps Acquisition-owned; keep semantic/KG ontology KP-owned; and preserve the distinct internal schema and legacy producer adapter boundaries.

**Overall adoption gate:** **CROSS-TEAM CONTRACT CONFIRMATION REQUIRED.** This does not reopen the measured Classic/E2E physical-extraction work; it prevents claiming that the public CDOI/KP interchange has been implemented or accepted.

### Addendum — OSD-routed CJK OCR output-level pilot (2026-10-07)

This CPU-only, isolated diagnostic uses a deterministic 15-page cohort selected from the frozen representative-v2 manifest (manifest SHA-256 `bb99b04e425a6b337252c7fa56dbf01fae94623181b06ab39d8b223abbe16fc6`; evaluator revision `193627ae9e97d89188468ed1ee3b7a856ff76044`). The cohort contains eight simplified-Chinese pages, three mixed Chinese/English pages, and four English pages. It deliberately includes OSD misses and false positives. GT language was used only to stratify evaluation and group results after extraction. Runtime routing used only Tesseract OSD's script result: `Han` selects local EasyOCR `ch_sim,en`; other or unavailable results retain `en,vi`. No Vietnamese-labeled pages exist in this frozen population, so Vietnamese safety remains unknown.

An initial fresh baseline run exposed a separate canonical producer defect: Docling emitted a physical region labeled `table` with zero rows, zero columns, and no cells; the adapter attempted to construct an invalid canonical `Table` and failed page validation. The current source preserves that physical region as an `OTHER` element with text/bbox/order and diagnostic `docling_label`, without fabricating a table grid/reference. It infers dimensions only when real cell extents exist. Two focused regressions were added. The failed 14/15 run is retained as a failure reproduction and was not scored; a fresh after-fix paired baseline completed 15/15 valid.

| Stratum | Pages | Baseline Text ED | OSD-route Text ED | Route better / worse / tied | Baseline Reading ED | OSD-route Reading ED |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| Simplified Chinese | 8 | 0.980634 | 0.647890 | 5 / 0 / 3 | 0.764329 | 0.505281 |
| Mixed Chinese/English | 3 | 0.541552 | 0.326498 | 1 / 0 / 2 | 0.714286 | 0.714286 |
| English | 4 | 0.367679 | 0.336871 | 1 / 0 / 3 | 0.359244 | 0.296744 |
| **All pages** | **15** | **0.729363** | **0.500673** | **7 / 0 / 8** | **0.646297** | **0.491472** |

The table reports evaluator `ALL_page_avg`; all arms use the same exact IDs and GT. Full Text ED is 0.729363→0.500673 and Reading-order ED 0.646297→0.491472 (N=15 each). Table ED changes 0.802837→0.597028 on only three table-scored pages; TEDS 0.422955→0.734962 and structure TEDS 0.638590→0.904701 on four instances are incidental small-N observations, not evidence of a table effect. Formula ED is 1.0 in both arms on two scored pages. Both baseline and routed replay have 15 valid prediction files; the CJK model produced 8/8 valid routed outputs. One page, `page-39551bb3-1b65-4562-b258-1bc97898cdf9.png#0`, remains a one-byte newline prediction in both arms, so routing did not fix every empty-output case.

In this selected cohort, OSD routed six of eight Chinese pages and missed two (one labeled Latin, one Japanese); it also routed one mixed page and one English page. Thus the cohort has six true routes, two Chinese misses, and two false positives. Five Chinese pages improved and three tied; overall, seven pages improved, eight tied, none worsened. Full-manifest OSD scan remains descriptive (Han on 63/84 Chinese and 2/95 English-or-mixed: precision 96.9%, recall 75.0%, specificity 97.9%); this cohort's false positives show that aggregate scan precision does not guarantee subset-level behavior.

The exact 15-image CPU OSD replay took 20.259 sec total (mean 1.351, median 1.371, max 1.646 sec/page). Replacing the eight Han-routed page runtimes with their candidate runtimes gives 571.335 sec model/extraction page time versus 578.338 sec baseline (−7.003 sec); adding the measured OSD pass yields an estimated 591.594 sec, about **+2.3%**. This is a composed estimate, not a single end-to-end routed run. OSD overhead is about 20.8% of the frozen Classic mean page runtime (6.492 sec), so it is not negligible for latency-sensitive use. The selected-cohort quality movement may justify further validation, but not production promotion.

Config SHA-256s: baseline `133c78c47501cbe858a97c88f61ea86414bfac83ce2350b0d8f7bfe668e6f3e9`; CJK candidate `f2e4bcccc3e1e7a48c7e5614318d044b7b36d6ca4bb84d1ded7cc3a760a77f51`. The config difference is the OCR-language list only. The routed composite is an isolated saved-output replay under `.benchmarks/diagnostics/phase1-cjk-route15-20261007/`, with strict 15-page run-scoped GT and per-page config/prediction hashes. It is not an official benchmark result.

### Table default-path verification and new correctness guard

The promoted table implementation is the actual default path: `PipelineConfig.table_backend` defaults to `table_transformer`, CLI backend construction selects it without an override, and `Document.to_markdown()` calls `Table.to_markdown()` for table elements. Assembly and evaluator serialization use this same document method. A regression now exercises span-preserving HTML through `Document.to_markdown()` itself. The new unstructured Docling-table handling fix is a separate correctness guard and was not part of the already-scored 180-page candidate source snapshot; no new full-corpus metric is claimed for it.

### Updated decisions

* **Table: PROMOTED** as the recommended Classic implementation, based on the prior exact 50-page gate and separate 180-page candidate validation; frozen baseline remains recoverable.
* **CJK page routing: EXPERIMENTAL / OFFLINE-SUPPORTED.** The 15-page paired cohort has a large text/order gain and no page-level metric regressions, but the result is bounded, OSD misses/false positives exist, CPU overhead is measurable, and Vietnamese controls are absent. Do not implement or promote yet. Next useful gate: a predeclared 30-page stratified routed comparison including OSD-Han Chinese, OSD misses, English/mixed false positives, and explicit Vietnamese controls from a separately labeled local control set if available; otherwise keep Vietnamese safety explicitly unknown.
* **Formula: EXPERIMENTAL. E2E: unchanged (179/180; full quality withheld). CDOI: SPECIFICATION AVAILABLE; IMPLEMENTATION UNCONFIRMED. Fine-tuning: NOT JUSTIFIED.** No GPU was used for this routed CJK continuation.

## Addendum — bounded candidate research update (2026-10-07)

This update changes no frozen official benchmark, manifest, evaluator, E2E configuration, or Classic production configuration. It records only isolated experiments under `.benchmarks/diagnostics/`.

### Formula enrichment: direct paired 20-page result and cost

The direct paired 20-page experiment is now the strongest local evidence for Formula enrichment. It used exact paired source/manifest/GT/model/evaluator identity and changed only `docling_formula_enrichment`. Both arms were 20/20 valid. Formula ED changed **0.984693 → 0.451075** (18 annotated pages; 17 improved, 0 regressed, 1 tied); Text ED **0.583445 → 0.527920** (20 pages); Reading-order ED **0.646221 → 0.408107** (20 pages). The 103 canonical formula elements were identical in both arms and all changed from null text to populated text; all non-formula text and canonical structure remained identical. This supports a real enrichment gain conditional on formula detection, not improved detection recall. One annotated page still had no canonical formula element in either arm. The two zero-annotation controls visually contain equations, so false-positive rate remains unmeasured.

Runtime was **74.624 s / 20 pages** without enrichment versus **555.773 s / 20 pages** with it: mean 3.731 vs 27.789 s/page, p95 5.501 vs 94.436 s, max 17.132 vs 96.533 s, or **7.45× total runtime** for the selected formula-heavy cohort. This is a real cost, not an extrapolated corpus estimate. The candidate remains a separate configuration candidate and is not promoted.

The initial bounded slow-page profile measured a 97.151-second two-region generation batch inside a 176.96-second extraction; `generate()` accounted for 96.948 seconds. The returned padded sequence had 2,048 new positions, equal to the installed CodeFormula stage's hard-coded `max_new_tokens=2048`; exact per-region generated-token counts were unavailable. That first profile left about 58 seconds outside its wrapper timers. A later same-page profile added Docling `TimeRecorder` instrumentation and accounted 85.834 seconds inside `pipeline_total`, of which `doc_enrich` was 83.176 seconds and `generate()` 82.879 seconds; crop preparation was 0.162 seconds. Outer Docling conversion was 95.380 seconds, so 9.546 seconds remained outside `pipeline_total` in that rerun. The earlier ~58-second gap did not recur and cannot be retroactively assigned. The 145.46 MP Pillow warning came from manifest-wide dimension verification of a different, policy-excluded input, not an intermediate formula crop.

The later two-page profile saw one `DoclingBackend`, one converter, one `StandardPdfPipeline` instance, one CodeFormula initialization (1.086 seconds), and a pipeline-cache miss on the first page followed by a cache hit on the second. The second page completed in 6.988 seconds, with `generate()` 4.372 seconds. This confirms reuse in the current same-process profile. An older two-init trace conflicts and remains unresolved, not proof of a cache bug. An earlier per-region inference attempt was interrupted by unrelated GPU use; that partial output is invalid. The corrected opt-in profile harness now reads EOS/pad IDs from the effective generation config and reports returned per-row lengths. The subsequent slow-page profile measured region 0 at 2,048 positions with no EOS/pad and region 1 at 47 positions ending with EOS. The latter is direct cap-length evidence for that region, not proof that a lower cap preserves quality.

Installed Docling 2.124's `CodeFormulaVlmModel.__call__` constructs `VlmEngineInput(max_new_tokens=2048)` directly. The generic CodeFormula runtime options expose a `max_new_tokens` setting, but this installed stage does not pass that setting through. Thus a smaller generation cap is not an ordinary repo YAML change; testing it requires a separately versioned dependency patch/fork or a supported future Docling release, with output-quality validation. A bounded CPU inventory found 2,066 `equation_isolated` labels with LaTeX text on 313 of the 1,651 OmniDocBench pages; 1,807 labels occur on 278 pages outside the frozen 180 selected page IDs. This is a potential adaptation signal, not permission to train on benchmark pages: any future split must exclude the full selected test population and group by source document. The current environment lacks `peft` and `bitsandbytes`; no fine-tuning was started. Since fine-tuning would not address the measured generation cost, it is deferred behind runtime diagnosis.

### Table spans and serialization: candidate disposition

The table candidate combines preservation of recognized, contiguous, non-overlapping Table Transformer spans with safe HTML serialization for cells that Markdown pipes cannot represent. A clean-HEAD control and current-source candidate were compared on the same 20 manifest pages: both 20/20 valid. The targeted hard-case cohort changed Table ED **0.769833 → 0.665829** (20-page denominator; 5 better, 15 ties, 0 worse), TEDS **0.301810 → 0.305264** and structure TEDS **0.463780 → 0.467456** (20-page denominator for each); Text ED and Reading-order ED were unchanged on their eligible denominators. Candidate and control runtime was 154.0 and 148.4 seconds. A subsequent offline 2×2 replay of saved canonical documents attributed the Table ED result to an interaction: serializer-only was **0.769833 → 0.753490** (one page improved, no regressions), span-only with legacy flattening was **0.769833 → 0.769849** (one page regressed very slightly), and span plus safe serialization was **0.769833 → 0.665829** (five improved, no regressions). Across the baseline, serializer-only, span-only, combined arms respectively, TEDS was .301810/.301774/.301780/.305264 and structure TEDS .463780/.464718/.463780/.467456 (each with the evaluator's 20-page denominator); Text ED denominator was 15 and reading-order denominator 20. This isolates the export/representation interaction on the selected saved cohort. At that point it remained a candidate; the later exact 50-page gate and separate 180-page candidate validation below supersede that status.

The earlier offline serializer-only replay is distinct: four changed exports in the frozen 180 predictions reduced Table ED **0.701108 → 0.683837** (50 metric-bearing pages), with only tiny TEDS/structure changes and no other metric changes. It is a replay, not a fresh extraction. The span and serialization findings are promising, bounded implementation evidence; the official Classic scores remain the frozen reference.

The frozen representative-v2 sample contains **exactly 50 pages with GT table annotations** and 64 TEDS/structure instances. The exact 50-page candidate gate passed: Table ED **0.701108 → 0.625952** (10 improved, 40 tied, 0 regressed); TEDS **0.407739 → 0.409395** (+0.001656); structure TEDS **0.649114 → 0.651886** (+0.002772); text, reading order, and formula metrics were unchanged. The candidate was then run on all 180 frozen pages as a separate diagnostic candidate, with 180/180 valid, exact IDs, no missing/unexpected/duplicate pages, and the pinned evaluator. Full-corpus Table ED improved **0.701108 → 0.625952**; TEDS **0.407739 → 0.409395** (64 instances); structure TEDS **0.649114 → 0.651886** (64 instances). Text, reading order, and formula metrics were exactly unchanged. Runtime was 1,151.874 page-runtime seconds (mean 6.3993, p95 19.3168, max 74.1038) versus 1,168.630 seconds (mean 6.4924, p95 18.9351, max 75.4656) for the frozen run; warning occurrences/pages were identical (76/65). The candidate's overall table gain was not restricted to GT span-labeled pages: span pages (N16) Table ED .718957→.600244, 4 better/12 tied/0 worse; other table pages (N34) .692708→.638050, 6 better/28 tied/0 worse. At the per-table level, span-labeled instances (N21) TEDS .339194→.343356 and structure .463852→.471034; no-span-labeled instances (N43) TEDS .441215→.441646 and structure .739591→.740210. This meets the full-corpus gate; the span-preserving adapter plus safe serializer is **PROMOTED as the recommended Classic implementation**. The prior official run and scores remain immutable and recoverable; candidate artifacts are separate under `.benchmarks/diagnostics/phase1-table-combined-full180-20261007/`.

### Updated research decisions

* Formula enrichment: **EXPERIMENTAL; NOT PROMOTED**. The paired 20-page quality gain is large but runtime was 7.45×. Per-region profiling measured a 2,048-token cap hit; a one-page in-process 1,024-cap experiment halved generation time but remained slow and is too small to justify promotion. Docling's stage does not expose the cap through repository configuration.
* Table span/serialization: **PROMOTED as the recommended Classic implementation** after the exact 50-page gate and separate 180-page candidate validation passed with no text/reading-order/formula/coverage regression. The frozen official baseline artifacts are unchanged.
* CJK OCR: **CONFIGURATION_ERROR** is confirmed as a coverage omission (`en,vi` excludes Chinese); a local EasyOCR `zh_sim_g2` checkpoint was found. On seven paired pages, global `ch_sim,en` improved simplified-Chinese Text ED .958376→.872208 (N3) but worsened mixed .448081→.504336 (N2), English .352770→.513187 (N2), and overall .639547→.664524 (N7); global multilingual configuration remains rejected. A subsequent 15-page OSD-routed output pilot improved Text ED .729363→.500673 and Reading-order ED .646297→.491472 with 7 better/8 ties/0 worse; routing is **EXPERIMENTAL / OFFLINE-SUPPORTED**, not implemented or promoted.
* The 15-page route still misses two Chinese pages, has two false positives in its deliberately stratified cohort, leaves one output empty, costs about 1.35 CPU seconds/page, and has no Vietnamese controls. Full-manifest OSD precision/recall remains descriptive and is not a substitute for broader routed validation.
* This continuation ran only the exact 50 table-bearing page gate, its justified 180-page table candidate, seven-page CPU CJK A/B, one-page Formula 2,048 profile and one-page 1,024 diagnostic cap comparison. No E2E, Classic baseline, 20-page preflight, token-cap sweep, batching sweep, or fine-tuning was run. E2E remains 179/180 with the page #42 timeout and full 180-page quality withheld. Fine-tuning remains **NOT JUSTIFIED BY CURRENT LOCAL EVIDENCE**.
* Official CDOI status remains **SPECIFICATION AVAILABLE; IMPLEMENTATION UNCONFIRMED**. No contract/KP implementation was fabricated or inferred.

### Addendum — routed OCR empty-result reproduction and fail-closed replay (2026-10-07)

The reliability failure was reproduced on the exact page `page-4b8f8a9d-e061-4207-a42e-ebf9b7090099.png#0` with isolated CPU runs under the same representative-v2 source image, preprocessing path, evaluator, and environment; only the OCR-language configuration differed (`en,vi` versus `ch_sim,en`). Image size was 1654×2339 (3,868,706 pixels). Tesseract OSD reported `Han` (confidence 1.43); this page is tagged `equation_hard` and has 10 GT text-block annotations, used only for post-hoc analysis.

The baseline layout had nine regions (eight formulas plus a small `list_item` region), and its raw Docling `OCRResult` contained one token, `2`; canonical text survived as `- 2\n`. The routed candidate layout had eight formula regions, and its raw `OCRResult` had zero tokens. Docling emitted the explicit no-text-token page note, canonical text elements were absent, and Markdown serialized as a one-byte newline. Thus the first observed loss is at the Docling OCR-result boundary: this is **`OCR_EMPTY_RESULT`**, not post-processing, canonical assembly, or serialization loss. The layouts also differ between arms, so the output change cannot be attributed exclusively to the recognizer. No exception was raised by the full candidate page path. Direct calls with `ch_sim` alone also returned zero tokens; local EasyOCR source explicitly limits `ch_sim` compatibility to `en`, and `ch_sim,en,vi` raises a configuration `ValueError`. The public Docling/EasyOCR boundary does not reveal whether EasyOCR internally failed at text detection or recognition, so that deeper subcause remains unresolved. Cached `zh_sim_g2.pth` was used; no model was downloaded and no GPU was used.

A pure deterministic decision helper and offline saved-output composer were added for validation, not wired into `process_file` or production configuration. They select the baseline result when the specialized candidate is missing, invalid, throws, serializes to whitespace only, or carries Docling's explicit no-token warning for detected text/formula regions. The exact 50-page saved-output replay produced two fallback events among 28 Han routes (7.14%): the reproduced page had an eight-byte nonempty baseline and was restored; a second page was one-byte empty in both arms, so the baseline was retained but this did not recover content. Final candidate-created empty outputs were zero; the two remaining empty outputs matched baseline empties. This fallback is observable in the composer summary, but it has not yet been integrated or measured as a live extraction route.

Pinned evaluator replay on the same 50 IDs/GT changed the routed Text ED from **0.5447012 to 0.5445742** (N=47) after fallback; simplified-Chinese Text ED was **0.5808666** (N=29), mixed **0.5679873** (N=9), English **0.3304237** (N=8), and traditional Chinese **0.9945799** (N=1). Reading-order ED changed **0.5766375 to 0.5756852** (N=50). The fallback therefore preserves the aggregate quality signal and slightly improves these replay metrics, but this is a deterministic replay of existing predictions, not a new inference result, and does not catch nonempty-but-degraded OCR. Fallback frequency was 2/28 routed pages; one event repaired a candidate-created loss, one was a no-op against an already-empty baseline.

Vietnamese safety was checked only with in-memory synthetic raster controls because no real Vietnamese page images or labeled local corpus are present in the checkout. On three synthetic Latin-script controls, EasyOCR `en,vi` had normalized character similarities .920/.1.000/.978 to the known phrases, versus .653/.806/.913 for `ch_sim,en`. This confirms that globally sending Vietnamese text to `ch_sim,en` can damage diacritics, but it is not a real-page benchmark and provides no evidence for Chinese+Vietnamese mixed pages. No Vietnamese real-page metric is claimed.

**Decision:** CJK routing remains **EXPERIMENTAL, NOT PROMOTED**. The quality signal survives a fail-closed empty-result replay, and the observed empty candidate no longer has to replace a valid baseline output. However, the fallback is not integrated into live extraction, nonempty suspicious degradation is not detected, Vietnamese/mixed-language real controls are unavailable, and the 50-page revalidation was replay-only. The 180-page escalation is therefore not justified. Next useful work is a separately bounded integration design with explicit route/fallback telemetry plus real Vietnamese controls; if those artifacts are unavailable, keep the route as an offline specialist hypothesis rather than claiming multilingual safety.

The promoted table implementation remains **PROMOTED** and unchanged. Formula remains **EXPERIMENTAL** (~7.45× on the paired 20-page cohort), E2E remains **UNCHANGED** (179/180 with the repeatable page #42 timeout and full quality withheld), fine-tuning remains **NOT JUSTIFIED**, and CDOI remains **SPECIFICATION AVAILABLE; IMPLEMENTATION UNCONFIRMED**. No GPU or E2E inference was used in this reliability continuation.

### Addendum — opt-in live CJK OCR path and bounded failure-page validation (2026-10-07)

The CJK work has advanced from offline selection to a live, **disabled-by-default** extraction path. `experimental_cjk_ocr_routing: true` is the only enablement; the default configuration and production OCR languages remain unchanged. The experimental configuration currently requires baseline Docling OCR with `en,vi`. Docling remains the layout backend. The OCR stage runs bounded Tesseract OSD; only OSD `Han` selects the existing direct EasyOCR backend configured as `ch_sim,en`. OSD absence/errors use baseline OCR.

The specialized path returns per-page content-free diagnostics in `ocr/page-NNN.json`: OSD script/confidence and time, chosen backend/state, token/non-space-character counts, baseline/specialized timings, fallback reason, and total route time. It does not log OCR text again. Candidate validation rejects malformed tokens, non-finite/invalid geometry or confidence, empty text, replacement-character rate above 2%, outputs with no alphanumeric/Han characters, and a conservative text-collapse case (baseline at least 40 non-space characters and candidate below 50% of baseline). The collapse detector uses no GT. These thresholds are safety heuristics, not an OCR quality estimator.

The prior newline-only failure was reproduced at Docling's OCR-result boundary, but a focused live run of the new direct-EasyOCR route on that same source page did **not** reproduce it: OSD said `Han` (confidence 1.43), direct EasyOCR returned 57 tokens / 502 non-space characters, and the canonical page retained text (15 text-bearing elements; 17 total elements). The Docling baseline OCR result was retrieved from the layout-populated page cache in 0.000143 seconds; the direct CJK pass took 19.753 seconds, OSD 1.723 seconds, and total route time 21.477 seconds. Full page runtime was 65.416 seconds on CPU, including 40.993 seconds of baseline Docling layout/conversion and 2.185 seconds of table processing. This is one cold page, not a stable per-page runtime estimate. It had no fallback because the specialized direct OCR result was nonempty and passed the current checks. The candidate output was not newline-only.

Pinned one-page evaluation on the exact page/GT showed Text ED **0.997015→0.778947**, Reading-order ED **0.952381→0.666667**, and Formula ED **1.000000→0.950139**. These are diagnostic single-page measurements, not a cohort result. The route uses a different OCR adapter than the prior Docling-wrapped CJK experiment; this is a new candidate path, and its result should not be conflated with the old 50-page route metrics.

### Baseline-relative catastrophic-collapse guard replay

The conservative collapse rule was checked against saved output lengths from the prior exact 50-page route cohort. In 28 Han routes it triggered on one nonempty shrink (50→22 non-space characters, ratio .44) and on the two empty candidates. Post-hoc evaluation identified the shrink page as the only Traditional Chinese item in that cohort: its Text ED worsened **0.981132→0.994580** and Reading-order ED **0.904762→0.976190** under the candidate. The 0.5 threshold therefore restores baseline for an observed candidate degradation; this is evidence for the heuristic on that cohort, not proof of sensitivity to all degraded outputs.

The resulting saved-output replay had three fallback events among 28 Han routes (10.7%): one recovered the known candidate-created empty output against a nonempty baseline; one recovered the Traditional Chinese text-collapse case; one was a no-op because both outputs were empty. Text ED changed from the empty-only replay **0.544574→0.544288** (N=47), and Reading-order ED **0.575685→0.574257** (N=50). The two empty-only/final replays are offline scoring of stored predictions, not new inference. No candidate-created empty outputs remained after fallback, but one baseline-empty page remained empty. This supports fail-closed selection; it does not validate live-route coverage or missed degradation cases.

### Vietnamese control availability and escalation gate

The repository's local `data/` contains only README/manifest; its manifest describes private documents that are not present. The available `research/production_corpus` has Vietnamese PDFs/PNGs, but its own manifest explicitly marks the corpus as generated synthetic data. Those images may be used for supplementary integration smoke tests, not as real Vietnamese controls. The synthetic raster phrase stress tests continue to show `ch_sim,en` damaging Vietnamese diacritics relative to `en,vi`; no real Vietnamese-heavy, Vietnamese+English, or Vietnamese+Chinese page A/B is available locally. No test was excluded or relabeled to conceal this gap.

**Decision remains CJK EXPERIMENTAL — NOT PROMOTED.** The live one-page route proves the new path can produce usable output on the known failure page and the deterministic guard catches one saved nonempty collapse as well as empty/malformed/errors. It does not yet demonstrate multilingual safety, cohort-level output stability, route precision/recall under the new direct OCR path, or a useful live fallback rate. Do not run the 15–20/30/50/180 progression until real Vietnamese controls are available or an explicitly approved substitute data source is provided. The next blocker is data availability, not more speculative threshold tuning. Table remains **PROMOTED**; Formula **EXPERIMENTAL**; E2E **UNCHANGED**; CDOI **SPECIFICATION AVAILABLE; IMPLEMENTATION UNCONFIRMED**; fine-tuning **NOT JUSTIFIED**. No GPU was used.

### Addendum — 30- and 50-page OSD-routed CJK validation (2026-10-07)

This CPU-only validation uses isolated diagnostic artifacts under `.benchmarks/diagnostics/phase1-cjk-route30-20261007/` and `phase1-cjk-route50-20261007/`. Both cohorts are deterministic extensions of the frozen representative-v2 manifest (SHA-256 `bb99b04e425a6b337252c7fa56dbf01fae94623181b06ab39d8b223abbe16fc6`) and use pinned OmniDocBench evaluator revision `193627ae9e97d89188468ed1ee3b7a856ff76044`. The routing decision was made only from per-page Tesseract OSD output (`Han` selects local EasyOCR `ch_sim,en`; other or unavailable results retain `en,vi`). Ground-truth language labels were used only for cohort stratification and post-hoc analysis. These are candidate results, not official replacement baselines.

| Cohort | Chinese / mixed / English | Text ED, all scored pages | Reading-order ED | Page deltas (text; route better/worse/tied) | Runtime estimate |
| --- | ---: | ---: | ---: | ---: | --- |
| 30 pages | 18 / 6 / 6 | .773762 → .627035 (N=29) | .692217 → .615340 (N=30) | 11 / 3 / 15 | baseline 1,061.997 page-s; OSD 40.360s; composed route estimate 1,102.071s (+3.77%) |
| 50 pages | 32 / 10 / 8 | .791111 → .544701 (N=47) | .674164 → .576638 (N=50) | 20 / 3 / 24 | baseline 1,697.524 page-s; OSD 65.232s; composed route estimate 1,746.055s (+2.86%) |

On the 50-page cohort, simplified-Chinese Text ED improved `.954394 → .581072` (N=29; 18 better, 2 worse, 9 tied). Mixed-language improved `.639672 → .567987` (N=9; 1 better, none worse, 8 tied); English improved `.345828 → .330424` (N=8; 1 better, none worse, 7 tied). The single Traditional-Chinese page regressed `.981132 → .994580`. Reading-order improved overall `.674164 → .576638` (N=50; 16 better, 5 worse, 29 tied); most of the mean change is in simplified Chinese (`.717389 → .565849`, N=31), while mixed pages were unchanged and English improved slightly. There are no Vietnamese-labeled pages in the frozen representative-v2 set, so Vietnamese preservation is untested—not inferred from the English/mixed strata. The OSD route selected 28/32 Chinese pages and had two false-positive routes among 18 non-Chinese pages (one mixed and one English): selected-cohort precision 92.9%, recall 81.3%, specificity 88.9%. Traditional Chinese was routed but worsened.

The 30- and 50-page extraction arms had strict complete output coverage. However, the routed composite introduced a one-byte newline prediction for Chinese page `page-4b8f8a9d-e061-4207-a42e-ebf9b7090099.png#0`; its baseline output was non-empty. A separate pre-existing one-byte output persisted in both arms. This is an actual candidate reliability regression, not hidden by the aggregate evaluator scores. Per-page regressions also remain (three Text pages and five reading-order pages on the 50-page cohort). The estimated routing overhead is modest but is composed from separate OSD and extraction timings, not a single end-to-end timed execution. On this evidence the 50-page gate does **not** pass the stated reliability requirement; no 180-page CJK candidate was run.

The earlier 15-page addendum remains a valid pilot, while this 30/50-page sequence supersedes its proposed next step. The global `ch_sim,en` configuration remains rejected. Page-level OSD routing is **EXPERIMENTAL**, not promoted or implemented. The immediate blocker is to explain and prevent the newly empty routed output without using GT or page-specific exceptions, then repeat a bounded paired reliability check; Vietnamese safety additionally needs a separately labeled control set because the frozen benchmark has none. Do not promote based only on mean Text ED.

### Table default-path and producer regression hardening

The promoted span-aware table representation and safe serializer are exercised through the normal `Document.to_markdown()` method, not a benchmark-only switch; CLI configuration defaults to the Table Transformer backend and canonical table serialization delegates to `Table.to_markdown()`. A regression test now checks span-preserving output through that public default document path. During the fresh 15-page CJK baseline, one no-grid Docling table-label item caused canonical construction failure. The adapter now preserves that physical region as `OTHER` with its text, geometry, order, and observed label rather than fabricating an invalid empty table; focused tests cover empty grids and inferred dimensions from real cell extents. The failed 14/15 reproduction is retained but unscored; the fresh after-fix cohort passed 15/15. This correctness guard is not part of the already measured 180-page table candidate source snapshot, and no new corpus-wide metric is attributed to it.

### Updated decisions after CJK validation

* **Table: PROMOTED.** Full 180-page candidate evidence remains valid and unchanged; default-path regression coverage was strengthened.
* **CJK routing: EXPERIMENTAL, not promoted.** The 50-page paired data has a substantial aggregate Text/Reading-order signal and modest estimated CPU overhead, but a new empty routed output fails the reliability gate; Traditional Chinese regressed, per-page regressions exist, and there are no Vietnamese controls. Do not run 180 pages until the empty-output mechanism is understood and bounded controls pass.
* **Formula: EXPERIMENTAL** (~7.45× on the paired 20-page formula-heavy cohort). **E2E unchanged** (179/180, page #42 timeout, full 180-page quality withheld). Fine-tuning remains **NOT JUSTIFIED BY CURRENT LOCAL EVIDENCE**. **CDOI remains SPECIFICATION AVAILABLE; IMPLEMENTATION UNCONFIRMED.** No GPU was used for this CJK work.
