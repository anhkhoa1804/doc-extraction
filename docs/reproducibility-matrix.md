# Reproducibility matrix

What has actually been executed and observed, versus what merely exists in
code. The distinction is the point of this file: "implemented" and
"validated" are different claims, and a matrix that blurs them is worse than
none.

Status vocabulary, used strictly:

| Status | Meaning |
|---|---|
| **VALIDATED** | Executed here, output inspected, evidence recorded |
| **PARTIAL** | Executed, but with a caveat that limits the claim |
| **OBSERVED** | Ran, but not verified against an expected result |
| **UNVALIDATED** | Implemented; never executed in this environment |
| **BLOCKED** | Could not run; reason recorded |

Last updated: 2026-09-01, base commit `4edd395` plus working-tree changes.

## Execution environments

| Axis | Configuration | Status | Evidence |
|---|---|---|---|
| OS | Ubuntu 22.04.5, kernel 6.8.0-1066-gcp | VALIDATED | Full suite + pipeline runs |
| Python | 3.12.14 (uv-managed) | VALIDATED | 189 passed, 10 skipped |
| Python | 3.11.16 (evaluator only) | VALIDATED | Official evaluator exit 0 |
| Python | 3.10.12 (system) | — | Deliberately untouched |
| torch | 2.13.0+cpu | VALIDATED | CPU reference environment |
| torch | 2.11.0+cu128 | VALIDATED | Models + tensors on `cuda:0` |
| Windows | — | UNVALIDATED here | Prior results committed; not re-run on this machine |

## Routes

| Route | CPU | GPU | Evidence |
|---|---|---|---|
| `native_office` (DOCX/XLSX/PPTX) | VALIDATED | n/a — no model | IR semantics checked per format |
| `digital_pdf` (native text + tables) | VALIDATED | n/a — no model | Table dedup + per-page quality gate |
| `digital_pdf` + per-page fallback | VALIDATED | VALIDATED | Broken-CMap fixture, 87% token recovery |
| `scanned_pdf` | VALIDATED | VALIDATED | Same fixture, whole-document visual route |
| `image` | VALIDATED | VALIDATED | 18/18 OmniDocBench pages, route=`image` |

Neither office nor digital-PDF routes invoke a model, so "GPU" is not a
meaningful axis for them — that is the routing architecture working, not a
gap in coverage.

## Backends

| Backend | Installed | CPU | GPU | Notes |
|---|---|---|---|---|
| `pymupdf-native` | core | VALIDATED | n/a | |
| `pymupdf_tables` | core | VALIDATED | n/a | |
| `native-office` | core | VALIDATED | n/a | |
| `docling` (layout + OCR) | yes | VALIDATED | VALIDATED | `AcceleratorOptions(device=...)` |
| `table_transformer` | yes | VALIDATED | VALIDATED | Both checkpoints on `cuda:0` |
| `mineru` | no | UNVALIDATED | UNVALIDATED | Adapter reports unavailable |
| `paddleocr` | no | UNVALIDATED | UNVALIDATED | Adapter reports unavailable |
| `vlm` | n/a | — | — | Interface only, no implementation |

## OCR language packs

Changing `ocr_languages` requires a matching model prefetch — the config
alone is not enough, and the failure is a hard `FileNotFoundError` rather
than silent degradation (see `docs/reproducible-environment.md`).

| Languages | Model | Status |
|---|---|---|
| `en` | `english_g2.pth` | VALIDATED |
| `en`, `vi` | `latin_g2.pth` | VALIDATED — repository default |
| `ch_sim`, `en` | `zh_sim_g2.pth` | VALIDATED — see experiments/007 |

## Cold / warm

| Measurement | Status | Evidence |
|---|---|---|
| Cold start (includes model load) | VALIDATED | `scripts/profile_pipeline.py` |
| Warm steady state | VALIDATED | Per-stage, CPU and GPU |
| Model-load cost | PARTIAL | Derived as `cold - warm`, not measured directly |

## Host / container

| Target | Test suite | Smoke | Status |
|---|---|---|---|
| Host (CPU venv) | 189 passed, 10 skipped | VALIDATED | |
| Docker CPU | 189 passed, 10 skipped | VALIDATED | Identical to host; requires `--user $(id -u):$(id -g)` for bind mounts |
| Docker GPU | — | — | BLOCKED — needs host NVIDIA Container Toolkit |

## Benchmarks

| Benchmark | Device | Contention | Status |
|---|---|---|---|
| OmniDocBench demo, 18 pages | GPU | CLEAN | VALIDATED — 18/18, evaluator exit 0 |
| OmniDocBench demo, 18 pages | CPU | LIMITED (one co-tenant at 118% of 800%, stable) | VALIDATED — 70.01 s/page |
| OmniDocBench demo, 18 pages | CPU | CONTENDED | PARTIAL — earlier attempts, 77.7 and 99.3 s/page, timing unusable |
| OmniDocBench demo, `ch_sim`+`en` | CPU | CONTENDED | PARTIAL — accuracy valid, timing not (experiment 007) |
| OmniDocBench full, 1651 pages | — | — | BLOCKED — see experiments/006 |
| Synthetic fixture, 2 pages | CPU + GPU | CLEAN | VALIDATED — verified idle window |
| enterprise-hardcases, 14 cases × 3 strategies | CPU | LIMITED (one GPU co-tenant, loadavg 1.4–3.1) | VALIDATED — see experiments/008 |
| enterprise-hardcases, VLM arm | — | — | BLOCKED — GPU PROTECTED all session |

**Every benchmark row carries a contention classification.** A timing taken
while another project was using the machine is not a benchmark, and pooling
one with a clean measurement produces a speedup number that is simply wrong.

## Resource governance

| Capability | Status | Evidence |
|---|---|---|
| GPU state query (no CUDA init) | VALIDATED | `nvidia-smi` subprocess; 17 unit tests |
| Classification CLEAR/LIMITED/PROTECTED | VALIDATED | Synthetic states + live GPU |
| `device: auto` refuses a busy GPU | VALIDATED | Live: refused a co-tenant at 100% util |
| `device: auto` uses an idle GPU | PARTIAL | Unit-tested; live CLEAR case not exercised (GPU was occupied throughout) |
| Per-stage device recorded in logs | VALIDATED | Was hard-coded `cpu` for every run; fixed and tested |
| Log-based profiler (cold/warm) | VALIDATED | 8 tests; flags its own unreliable estimates |
| Determinism, native + office routes | VALIDATED | 5 tests; byte-identical modulo run-extrinsic fields |
| Determinism, visual route | OBSERVED | Identical across 3 repeats; not asserted (model kernels not controlled) |
| docling↔Table-Transformer coordinate agreement | VALIDATED | Was 1.333× off with wrong y-offset; fixed, 4 tests |
| docling table cell text in OCR tokens | VALIDATED | Was 0 tokens for tables; now 61 on a 12×5 table |
| Decision recorded in `metadata.json` | VALIDATED | `device_decision` with co-tenant PID and VRAM |
| Explicit `cpu`/`cuda` never overridden | VALIDATED | Test asserts no probe occurs |

## Bottleneck

Measured over the 18-page CPU run (`scripts/profile_pipeline.py`):

| Stage | Share of logged time |
|---|---|
| `layout` (docling) | **98.6%** |
| `table` (table_transformer) | 0.9% |
| `render` (pymupdf) | 0.5% |
| ocr / reading_order / assemble | <0.1% combined |

Layout is the only stage worth optimizing, and it is also the stage the GPU
accelerates most (8.9x warm). An Amdahl estimate from this profile predicts
~8.0x end-to-end; the measured 18-page speedup was 6.2x — consistent in
magnitude, with the residual most plausibly because the fixture's layout
speedup does not transfer exactly to dense real pages.

## Known gaps

* The private `data/` corpus is absent from this machine, so every
  corpus-calibrated claim (routing thresholds especially) is unverified here.
* No GPU run has been executed under a CLEAR (sole-tenant) GPU since the
  resource module was added, so `auto`'s CLEAR -> cuda branch is unit-tested
  but not yet observed live.
* Model-load cost cannot be separated on a heterogeneous corpus; the
  profiler reports this rather than estimating through it.
* OmniDocBench full 1651-page run: not executed. See experiments/006.
* No VLM has been screened on hardware: the GPU was PROTECTED by another
  project's job for the whole of session 3. See docs/backend-landscape.md for
  the recorded screening plan.
* `stamp_over_table` is recovered by no current strategy — native holds the
  occluded text, visual holds the grid. Indicated answer is fusion, untested.
