# PaddleOCR-VL 1.6 Pretrained Baseline Attempt

**Status: full representative-v2 quality baseline BLOCKED; no full-population metrics were produced.**

## Five-page smoke (diagnostic only)

| Metric | Value | N | Status |
|---|---:|---:|---|
| text_block_edit_distance | 0.099504 | 4 | NOT A BASELINE |
| table_edit_distance | 0.380612 | 2 | NOT A BASELINE |
| table_teds | 0.900866 | 2 | NOT A BASELINE |
| table_structure_teds | 0.933827 | 2 | NOT A BASELINE |
| reading_order_edit_distance | 0.226050 | 5 | NOT A BASELINE |
| formula_edit_distance | 0.051649 | 2 | NOT A BASELINE |

The smoke set had 5/5 successful predictions, no warnings, and a 204.765 second wall time. It was deliberately diagnostic, selected to cover several failure types, so these scores cannot be generalized or compared to the 180-page baseline.

## Failure-analysis bridge

Classic's highest-level symptoms are high text/reading-order/table/formula Edit distances. A concrete empty-output trace was followed through OCR result, canonical page elements, and the benchmark serializer: the classic page had five formula-labelled regions with null text and zero OCR tokens, so the empty Markdown was not introduced by the final benchmark serializer. The smoke output for this page was nonempty (its text ED changed from 1.0 to 0.19436 on this page only). This is a page-level observation, not evidence of general improvement or of the classic backend's precise internal root cause.

For tables, classic aggregate TEDS is 0.398111 and structure-only TEDS 0.632317. The higher structure score is consistent with content mismatch after structure is partly recognized, but does not isolate OCR/cell segmentation/normalization. One wide/rotated page has a negative per-page TEDS diagnostic; this needs evaluator/protocol investigation rather than a causal claim. The 5-page E2E smoke includes only two table pages and is not a useful comparative estimate.

Formula Edit distance is 0.985389 over 35 pages for Classic. This identifies a weak benchmark result, not whether formulas were missed, serialized incorrectly, or mismatched against annotations. The smoke subset's formula score has N=2 and cannot resolve that ambiguity. Reading-order ED is 0.584992 over 178 pages; order versus missing text and annotation alignment remain entangled.

## Candidate audit and selection

| Candidate | Assessment | Fit / limitation | Runtime and license note |
|---|---|---|---|
| PaddleOCR-VL 1.6 (~1.0B card listing) | CANDIDATE FOR IMMEDIATE BASELINE; smoke-tested, full baseline blocked | Official page parsing pipeline emits block labels/content/geometry/order; table HTML can be adapted. Consumed output lacks cell-level geometry/confidence; all claims remain model-output dependent. Vietnamese performance is not established. | Runs on L4, but observed page call exceeded 300s; hard cancellation absent. Model card declares Apache-2.0; dependency distribution review remains open. |
| DeepSeek-OCR-2 (3B) | CANDIDATE FOR FUTURE | Document-to-Markdown/grounding, multilingual; output is less directly region-structured for the present canonical mapping. | Official card's usage examples set `trust_remote_code=True`; 3B VRAM/runtime not tested here. Apache-2.0 on card. |
| olmOCR 2 (7B) | CANDIDATE FOR FUTURE, not selected | Document OCR, tables/equations/reading order, Markdown output and training code; page-level geometry mapping is limited. | 7B path is materially heavier for an L4 first trial; Apache-2.0 project/model listing, exact selected-weight terms still require checking. |
| dots.mocr (3B) | NOT SUITABLE FOR THIS DATA RUN pending rights review | Broad multilingual parsing and structured graphics output, but would require separate adapter and license review. | Custom license agreement restricts unauthorized digitization/scanning of copyrighted publications; benchmark image rights have not been verified. |

Selection rationale: PaddleOCR-VL 1.6 has an official page-level pipeline, explicit structured regions/tables and successful local execution on the L4. Its own model card reports OmniDocBench v1.6 evaluation; benchmark-specific optimization/exposure is therefore a generalization concern, not evidence of data leakage. The same local OmniDocBench protocol still provides an apples-to-apples engineering test if the full run becomes safely executable.

## Backend and canonical mapping

Optional backend `paddleocr_vl` is registered at the existing backend boundary. It imports the runtime lazily; maps model-provided labels/text/order and valid page boxes into existing `Page`/`Element`; converts parseable HTML tables into canonical `Table`/`Cell`; leaves unknown geometry and confidence null; retains malformed table output as text with an `E2E_UNSUPPORTED` note. It accepts raster page images only. No canonical schema or KP fields changed. Smoke tests use deterministic fake model output; model integration is the external smoke/run artifact.

## Resource and output limitations

L4: NVIDIA L4, 23034 MiB; NVIDIA driver 580.178.04; nvidia-smi CUDA 13.0; tested Paddle GPU wheel CUDA 12.6; PaddlePaddle GPU 3.2.1 / PaddleOCR 3.7.0 / PaddleX 3.7.2; batch size 1; official pipeline defaults and safetensors weights. Sampled VRAM during the interrupted run reached 15028 MiB (not a profiler-captured peak; an earlier single sample reached 20552 MiB).

## Full-population attempt

The exact frozen 180-page manifest was used. 158 predictions were written; processing exceeded the configured 300-second runtime boundary on `newspaper_TheWashingtonPost-2025-01-08@magazinesclubnew_page_042.png#42`. The in-process Paddle worker did not terminate on interruption. The attempt was stopped, outputs preserved locally, and no partial scoring was run. The directory is labelled incomplete and unscored; it is ignored by Git.

Configured runtime check is post-operation for this in-process backend; it therefore does not provide hard cancellation. A worker isolation/cancellation boundary is required before a repeat. No resource limit was changed or bypassed.

## Fine-tuning gate

**Decision: FINE-TUNING NOT YET JUSTIFIED.** The same-manifest pretrained result is absent, so there is no reproducible quality or failure-mode advantage on which to base training. A future adaptation study could examine Chinese/English text recognition, reading order, table cell content/structure, and formula transcription, but only after a valid pretrained baseline and rights-cleared labeled data exist.

## Training-data plan (not collected)

For a later physical-extraction dataset, define page-image and document/page identity, text-region polygons/boxes and verbatim content, region type, reading-order edges/indices, table region and cell grid with spans/cell text, formulas (LaTeX/string plus region geometry), and headings/paragraph grouping where annotation consistency is achievable. Store source/license/consent and split by source document to avoid page leakage. Do not include KP entities, relations, ontology labels, or semantic field answers.

## Interpretation

OBSERVED: five smoke pages converted successfully and yielded nonempty outputs; the 180-page run hit an uninterruptible long inference operation; the classic empty-output case is upstream of benchmark Markdown serialization.

INFERRED: a page-level E2E parser may help some visually complex pages; a classic/E2E hybrid could be worth considering only after paired full-subset evidence and operational isolation.

NOT ESTABLISHED: full-population E2E quality, superiority to Classic, subgroup generalization, causal bottleneck attribution, production readiness, or a fine-tuning benefit.

## Reproducibility

Classic run: `representative-v2-full-20261002T080500Z`; frozen manifest SHA-256 `899191e7471ae5c826a6a07ff7edf3c7c8facec72764196ef9f3f49a8265a93b`; config SHA-256 `ea3e0415e6e7699c081dfc7a3d2abcf9344c02db704865beb91ef783e1102748`; upstream evaluator revision `193627ae9e97d89188468ed1ee3b7a856ff76044`. Smoke run metadata and per-page hashes remain in the ignored local run directory; the full partial directory is `e2e-paddleocr-vl16-representative-v2-20261002T093653Z`. Reports are generated by `benchmarks/scripts/build_e2e_research_reports.py`.

## Limitations

This is a blocked pretrained baseline, not a valid current full-population quality result. The existing runtime guard is post-return for in-process inference. Preflight metadata recorded model revision `676e2aa`, but that value's exact upstream identity was not verified; local cache weight hashes were measured after the run and were not captured as invocation-time hashes. The source tree was dirty during execution, so the recorded Git commit does not uniquely identify the as-run E2E source snapshot. OmniDocBench image licensing is unverified, so source images and prediction text are not committed. The official model card reports its own OmniDocBench evaluation; this does not establish generalization outside that benchmark family.
