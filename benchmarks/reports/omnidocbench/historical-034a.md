# Historical OmniDocBench 034a reference

This is a mined historical record, not the current production baseline. It is kept separate from representative-v2 and must not be read as a controlled regression comparison.

## Run identity

- Dataset: the same local OmniDocBench 1.6 annotation snapshot; 1,651 pages; annotation SHA-256 `a45cd84b…fae496`.
- Extraction: 1,651 attempts, 1,651 succeeded, zero failures; 13,665.459 seconds summed runtime and 13,687.102 seconds wall-clock; 8.2771 seconds/page mean.
- Device: CUDA; the 034a environment artifact reports NVIDIA L4, 23,034 MiB total. Extraction Python 3.12.14, Torch 2.11.0+cu128. Evaluator environment Python 3.11.16.
- Backend versions: doc-extraction 0.1.0, PyMuPDF 1.28.2, Docling 2.124.0, docling-core 2.93.0, EasyOCR 1.7.2, Transformers 5.16.1.
- Git revision: **unknown**; `run_metadata.json` has `git_commit: null`. Configuration file/hash were not recorded, although the resolved config snapshot is present in metadata. It used CUDA, 200 DPI, Docling layout/OCR and Table Transformer.
- Evaluator: pinned commit `193627ae9e97d89188468ed1ee3b7a856ff76044`; `quick_match`, page matching workers 4, TEDS workers 13.
- Stored outputs include 1,651 Markdown predictions, GT hashes, evaluator config, metrics and run summary. Scalar metrics are reproducible from stored metrics; text/table/formula/reading metrics can be rerun from stored predictions and the pinned evaluator. Exact extraction recreation is not possible to identify to source revision because its Git commit is absent.

## Historical metrics

Values below use the pinned report protocol's `ALL_page_avg` or page-level aggregate and denominators from the stored `notebook_metric_summary`.

| Metric | Value | Denominator | Aggregation | Direction | Status |
| --- | ---: | ---: | --- | --- | --- |
| Text block Edit distance | 0.583665 | 1,557 pages | ALL_page_avg | lower | REPRODUCIBLE WITH STORED OUTPUTS |
| Table Edit distance | 0.701800 | 458 pages | ALL_page_avg | lower | REPRODUCIBLE WITH STORED OUTPUTS |
| Table TEDS | 0.352645 | 458 pages | page average | higher | REPRODUCIBLE WITH STORED OUTPUTS; error-affected |
| Table structure-only TEDS | 0.564738 | 458 pages | page average | higher | REPRODUCIBLE WITH STORED OUTPUTS; error-affected |
| Reading-order Edit distance | 0.596676 | 1,638 pages | ALL_page_avg | lower | REPRODUCIBLE WITH STORED OUTPUTS |
| Formula Edit distance | 0.975595 | 313 pages | ALL_page_avg | lower | REPRODUCIBLE WITH STORED OUTPUTS |
| Formula CDM | — | — | not run | higher | NOT REPRODUCIBLE |

For context only, the evaluator also recorded instance averages: TEDS 0.322437 and structure-only TEDS 0.524703 over 665 table instances. These differ from the page averages because they use different aggregation units; they are not contradictory values for the same aggregation.

## Table evaluator errors

The table evaluator attempted 665 instances, recorded 94 errors, zero timeouts, and used 13 workers. All 94 stored error reasons are `AssertionError: can only join a started process`. Inspection of the pinned evaluator confirms an errored instance is retained with score `0.0`; consequently both table TEDS aggregates include zero scores for those cases. This is an evaluator/runtime-concurrency failure mode, not evidence by itself that extraction failed on those tables. The remaining 571 instances completed without a recorded error. The old TEDS values are therefore useful as historical recorded metrics but should be treated as error-contaminated.

The pinned runtime report documents 1,651 page matches, no page-match timeouts, and no quick-match fallback. Text/formula/table-edit/reading-order denominators are 1,557 / 313 / 458 / 1,638 pages respectively. Extraction warning counts were not retained in the historical runtime artifact; do not infer zero warnings.

## Comparability

Historical 034a used all 1,651 pages, older extraction code/configuration, and has no source commit identity. Representative-v2 uses a frozen 180-page subset of the same GT snapshot, excludes annotation-integrity cases and production-policy-ineligible images, and uses the current source commit/config. Even where metric definitions and evaluator commit match, populations and extraction configurations do not. No numerical historical-to-current delta is a controlled regression signal. Use this record as context; use future reruns of the exact v2 manifest for engineering regression detection.
