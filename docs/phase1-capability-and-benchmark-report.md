# Phase 1 Capability and Benchmark Evidence

**Benchmark evidence cut:** 2026-10-03; **CDOI contract audit:** 2026-10-06
**Initial report HEAD:** `2bebedacbef0a948e82201139a78a9cd0ef19944` (individual benchmark source attestations are listed with their runs)
**Physical Extraction decision:** **FREEZE WITH EXPLICIT E2E LIMITATION**
**Cross-team adoption:** **CONFIRMATION REQUIRED**

## Executive summary

Classic is a fast, useful visual/document-structure backend with enforceable canonical invariants and a valid 180-page extraction/evaluation result. Its best measured areas include English text on simpler layouts and some structured tables. It has substantial OCR/language, reading-order, formula, and table-content weaknesses; some invalid table ownership cases were confirmed implementation defects and have been fixed with regressions. Formula errors are not yet proven to be an immutable capability ceiling: the current route has OCR languages `en, vi`, no enabled formula enrichment, and a known Chinese case where all detected formula regions had null text, but the exact loss point is not established.

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
2. There is no explicit formula enrichment enablement in the repository's pipeline construction. In the inspected Docling version, formula enrichment defaults disabled.
3. The adapter maps formula labels to canonical formula elements and propagates available item text; it does not intentionally discard populated formula text. Markdown serialization emits formula text when present and otherwise cannot recover it.
4. The known Chinese empty-output case produced five formula-labeled regions, zero projected OCR tokens, five null-text formula elements, and one-byte Markdown. This is direct evidence of an empty upstream/recognition result for that case, but does not locate why Docling/EasyOCR returned no formula text.

Assessment: **STRONGLY INDICATED CODE/CONFIG GAP**, exact cause **UNKNOWN**. Configured languages `en, vi` are mismatched to a simplified-Chinese source, and optional formula enrichment is disabled; neither alone is confirmed as the causal mechanism. The corpus-wide formula score also includes English cases, so language mismatch cannot explain the whole result. No supported specialist formula path was identified as already available and merely dropped by the adapter. Do not call this a confirmed code bug or a proven capability ceiling. Any language/formula-enrichment change requires a separately versioned configuration experiment and evaluator comparison.

## 6. Table deep dive

Two high-confidence producer defects were exposed and addressed in the current implementation/tests:

* Table-contained tokens were emitted both as table/cell text and sibling ordinary text. The ownership logic now suppresses only text actually assigned to table cells; titles/footnotes inside the outer table box are not automatically swallowed.
* A visual layout label could be emitted as `TABLE` despite no matching structured table, creating an invalid table reference. The fallback preserves the observed region as `OTHER` plus layout-label evidence and warning rather than fabricating a reference.
* Conversely, a structured table with no matching layout table region could be omitted from the page. The current producer retains the structured table owner; it does not fabricate a layout match.

The fixes are protected by focused table/conformance regressions and did not change the public canonical schema. The latest full Classic run has table ED 0.701108, TEDS 0.407739 and structure TEDS 0.649114. These weak remaining scores are not themselves a diagnosis. TEDS structure exceeds full TEDS, consistent with content/text matching being harder than structure alone, but that difference does not identify whether a particular residual error comes from OCR, grid detection, spans, or a model limitation. Current run warnings additionally show real residual table reconstruction uncertainty (rows synthesized from OCR; unmatched layout/structure objects; no detected grid on some table-labeled regions). Further fixes require per-example image/structure diagnosis, not score chasing.

The historical ownership A/B artifacts cover 178 pages. They show unchanged table aggregate metrics in that comparison, while text/reading aggregates differ. A separate Python/Torch extraction environment mismatch exists, so those changes are **observed**, but causal attribution to the ownership fix is **NOT ESTABLISHED**. On `jiaocaineedrop_jiaocai_needrop_en_397.jpg#1830`, Markdown changed 1160→878 bytes, text ED .342857→.328407, reading ED .500000→.642857, while table metric was unchanged. Output inspection showed the table remained represented; the mixed metric movement is not a clean improvement claim.

## 7. Reading order and text/OCR

Classic reading-order ED is 0.596823 on 178 pages. The evaluator's order sequence includes recognized content; missing/extra elements can therefore increase this score even when the physical ordering algorithm is not the sole defect. Observed difficult groups include three-column pages (ED 0.7313), table-hard pages (0.7901), simplified Chinese text (0.7469), and newspaper pages (0.6580). The code has an explicit column-aware geometric reading-order stage and canonical explicit order references. No single corpus-wide reading-order implementation defect is established from these aggregates. Dominant residual class remains **UNKNOWN / mixed content and ordering errors** pending targeted page inspection.

Classic text ED is 0.589397 on 168 pages. By manifest language group, English is 0.1860 over 76 paired pages, simplified Chinese 0.9688 over 77, and mixed Chinese/English 0.7584 over 13. The OCR config is `en, vi`. This makes language coverage a **strongly indicated configuration gap**, especially for Chinese, but aggregate values do not prove that language support is the only cause. Existing warning/forensic evidence identifies at least one all-zero OCR projection on text/formula regions. Other possible observed causes include omitted layout regions, duplicate/ownership handling, recognition errors, and order/serialization. Serialization is deterministic and canonical validation catches structural invalidity, but neither fact establishes transcription fidelity.

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
* Continue only with page-specific reproduced table/order/text defects; do not change the validator or chase aggregate score alone.

### Optimization

* E2E page 42: deeper Paddle/PaddleX/model decoder profiling remains an external/model-library investigation. Do not change batch guard, timeout, token cap or image semantics without a separately frozen configuration experiment.
* Measure whether per-page model and run-metadata attestations can be safely cached once per worker/run (currently ~11.79 s/page combined); keep provenance guarantees intact.

### Hybrid routing

* Test a small, predeclared routing hypothesis from document/layout signals only after per-category denominators and failure behavior are specified. No router or score threshold is approved by this report.

### Integration

* Confirm the immutable source revision/hash and executable schema for the already-authoritative CDOI contract; implement the ExtractionPackage v1 producer and obtain KP validator/`DocumentIR`/EvidenceRef test evidence. Do not invent field semantics.

### Model research

* Only after a stable separately versioned E2E configuration and quality/runtime acceptance gate: evaluate formula/language adaptation or specialist models. Fine-tuning and training-data creation remain **not started**.

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

### Formula capability experiment

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

**Formula classification:** **FORMULA RESULT REMAINS UNRESOLVED.** Evidence strongly indicates a current configuration/model-resolution gap: formula enrichment is disabled, and the supported installed stage cannot resolve the available Docling-cache files as its requested Hub snapshot offline. It is not established whether enabling the supported recognizer would fix the 0.985389 corpus result, nor whether its output would be accurate. Do not call this a proven capability ceiling or a confirmed adapter defect.

Artifacts: `.benchmarks/diagnostics/phase1-formula-baseline-20261003/`, `.benchmarks/diagnostics/phase1-formula-baseline-replacement-20261003/`, and `.benchmarks/diagnostics/phase1-formula-candidate-codeformulav2-20261003/`. The candidate directory is failure-only diagnostic metadata; it contains no candidate prediction set.

### Updated decisions

* **Matched hardware cost:** mean wall time was 203.225 s/page CPU and 39.219 s/page GPU-assisted on the same five pages, a descriptive wall-clock ratio of about **5.18×**. Markdown differed on all five pages and CPU canonical JSON was not retained; output equivalence is not established, so this is **not a validated hardware speedup**.
* **Formula decision:** **FORMULA RESULT REMAINS UNRESOLVED**; candidate comparison was blocked at model snapshot resolution. Any follow-up must first establish an approved, hash-pinned, offline-loadable CodeFormulaV2 artifact path, then repeat only the five-page baseline/candidate comparison. No network download, config promotion, or further GPU run is authorized by these results.
* **GPU decision:** **NO MORE GPU WORK REQUIRED** for Phase 1. The missing formula candidate is a local dependency/cache-resolution prerequisite, not a reason to spend more shared GPU time now.
* **Phase 1 decision:** remains **FREEZE WITH EXPLICIT E2E LIMITATION**. Classic remains 180/180 valid as previously reported; E2E remains 179/180 incomplete with full quality withheld. Fine-tuning remains **NOT STARTED**.

## Official CDOI Contract Adoption Status

**Official identity:** `DocumentExtractionContract` 1.0.0 = `ExtractionPackage v1`. The official contract is now treated as authoritative. **Repository adoption status: SPECIFICATION AVAILABLE; IMPLEMENTATION UNCONFIRMED.** The current producer still emits only internal `Document` 1.4.0; the contract producer and KP `DocumentIR`/EvidenceRef adapter are not present in the inspected workspace. Exact field mapping, stable cell identity, source/run provenance, structured issues, FATAL conversion, unknown-field/version rejection and KP preservation need owner-confirmed paths and tests.

The authoritative user-supplied contract facts resolve the former “contract source unknown” blocker, but do not constitute implementation evidence. The repository's completed physical extraction/benchmark work can be frozen separately; **cross-team contract adoption cannot yet be claimed**. See [the field-level audit](contract-adoption-audit.md) and [the teammate checklist](cdoi-teammate-confirmation-checklist.md). In particular: do not add `document_revision_id`; keep URLs, artifact/job IDs and retrieval timestamps Acquisition-owned; keep semantic/KG ontology KP-owned; and preserve the distinct internal schema and legacy producer adapter boundaries.

**Overall adoption gate:** **CROSS-TEAM CONTRACT CONFIRMATION REQUIRED.** This does not reopen the measured Classic/E2E physical-extraction work; it prevents claiming that the public CDOI/KP interchange has been implemented or accepted.
