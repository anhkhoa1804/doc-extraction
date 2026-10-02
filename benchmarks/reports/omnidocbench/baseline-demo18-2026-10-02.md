# OmniDocBench demo baseline — 2026-10-02

This is an 18-page smoke baseline, not a representative full-benchmark result.
The selected data are the existing OmniDocBench 1.6 demo. The two local demo
copies were verified identical by ground-truth hash and page-image hashes.
No benchmark data were downloaded for this run.

## Reproduction identity

- Extractor commit: `e6835cd1529a87823680e2d698fe0251e286538e`
- Environment: Python 3.10.12, CPU
- Configuration: `configs/cpu.yaml`; canonical JSON and SHA-256 are in the
  companion result JSON.
- Official evaluator: pinned OmniDocBench commit
  `193627ae9e97d89188468ed1ee3b7a856ff76044` (version 1.6)
- Dataset identity: `OmniDocBench_demo.json`, SHA-256
  `a0686ff3e2ce76b4e60c308bc28700683d3c62a0fd47149355e8b197db238dc6`; all
  18 image hashes are recorded in the JSON.
- Pairing: each expected image-basename prediction was checked for uniqueness,
  presence, and unexpected Markdown files before evaluation.
- Machine-readable result:
  [`baseline-demo18-2026-10-02.json`](baseline-demo18-2026-10-02.json)

## Execution

| Measure | Result |
| --- | ---: |
| Pages attempted / succeeded / failed | 18 / 18 / 0 |
| Extraction wall time | 1,241.146 s |
| Mean time per page | 68.949 s |
| Device | CPU |
| Official page matching | 18 pages; 0 timeout fallbacks |
| Table metric execution | 10 table instances; 0 errors; 0 timeouts |

The runner did not retain extraction warning counts; they are unknown, not
zero. Evaluation-side fallbacks and table errors/timeouts were zero.

## Official end-to-end metrics

These values come from the pinned upstream end-to-end evaluator configured by
the adapter. `Edit_dist` is normalized edit distance (lower is better). TEDS
is a similarity (higher is better). The upstream implementation exposes both
table-instance aggregation and a page roll-up; both are retained rather than
collapsing them into one number.

| Task / metric | Result | Evaluator denominator |
| --- | ---: | ---: |
| Text block — Edit_dist, `ALL_page_avg` | 0.741836 | 18 pages |
| Display formula — Edit_dist, `ALL_page_avg` | 0.996032 | 2 annotated pages |
| Table — Edit_dist, `ALL_page_avg` | 0.655976 | 9 table-bearing pages |
| Table — TEDS, table-instance mean (`all`) | 0.444202 | 10 table instances |
| Table — TEDS, page roll-up (`page.ALL`) | 0.424403 | 9 table-bearing pages |
| Table — TEDS structure-only, instance mean | 0.744446 | 10 table instances |
| Table — TEDS structure-only, page roll-up | 0.729940 | 9 table-bearing pages |
| Reading order — Edit_dist, `ALL_page_avg` | 0.599695 | 18 pages |

No overall/composite score is reported. The adapter’s end-to-end text metric is
not an isolated OCR-recognition metric. Layout detection is not computed by
this prediction/evaluation path. Formula CDM and BLEU/METEOR were disabled.
Therefore neither an overall official aggregate nor a layout-detection score
is claimed.

## Limitations

- The 18 pages are the complete demo subset, useful as a smoke baseline but
  too small to characterize the system broadly.
- This run is protocol-backed for the configured upstream end-to-end metrics,
  but does not cover all OmniDocBench task categories or aggregates.
- The prediction runner’s legacy run metadata did not contain a source Git
  revision. The evaluator-side recorder was given the then-current clean
  revision explicitly; the result JSON records this caveat.
- The full local 1,651-page snapshot was not run. The demo run alone took about
  20.7 minutes; the full snapshot has a different GT file/hash and needs a
  separate validated manifest before selection.
- The dataset license was not verified locally. The evaluator checkout’s
  Apache-2.0 license does not establish the dataset’s license.
