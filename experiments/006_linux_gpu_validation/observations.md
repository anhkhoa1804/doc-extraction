# Observations — 006

## 1. The GPU path was correctly wired, and is now measured

`configs/gpu.yaml` claimed *"WIRED, NOT YET MEASURED"*. That claim was
accurate in both halves.

Wiring, verified by inspecting live objects rather than reading source:
both Table Transformer checkpoints report every one of their 28.8 M
parameters on `cuda:0`, and `DoclingBackend` sets
`AcceleratorOptions(device=...)`, which drives layout, TableFormer *and*
EasyOCR from the single `config.device` value.

The thing that actually blocked GPU execution was not the code at all — it
was that the environment had `torch 2.13.0+cpu` installed. `is_available()`
returned False because the *build* has no CUDA support, on a machine whose
GPU was completely idle. Worth stating explicitly because the two failure
modes ("no GPU" and "no CUDA build") present identically at the one-line
check that `configs/gpu.yaml` recommends.

## 2. Cold start dominates small runs — report warm numbers separately

On the 2-page fixture:

| stage | CPU | GPU | speedup |
|---|---|---|---|
| layout, page 0 (cold) | 31.96 s | 26.78 s | 1.19× |
| layout, page 1 (warm) | 13.99 s | **1.58 s** | **8.9×** |
| tables, page 0 (cold) | 3.22 s | 3.12 s | 1.03× |
| tables, page 1 (warm) | 0.84 s | **0.16 s** | **5.1×** |
| wall clock | 53.65 s | 37.71 s | 1.42× |

The difference between the first and second page of the *same run* is the
model load. Quoting `total_runtime / pages` for this workload would report
GPU inference as ~6× slower than it is.

This also confirms the caching added in `4edd395` is doing what its commit
message claims: page 1 does not re-pay the load. The measured load cost is
~18.5 s (docling) + ~4.0 s (Table Transformer) per process on CPU — which,
on a per-page benchmark corpus, is exactly the cost that commit removed.

## 3. GPU and CPU outputs are identical

Same text, same element counts, same table geometry, **0.000 px** bbox
delta. The GPU path is an optimization, not a different pipeline. This is
the precondition that makes a speedup number meaningful at all — a faster
path that produced different output would be a different experiment.

## 4. Honest accounting of what could *not* be measured cleanly

Both 18-page CPU runs overlapped an unrelated pre-registered research job on
this shared host (~333 % of 800 % CPU). The second run — launched
specifically as a clean control — came out **slower** (99.3 s/page) than the
first (77.7 s/page), because the neighbour's CPU share had grown in between.

So there is no trustworthy 18-page CPU number from this session, and none is
reported as one. The GPU figure (11.37 s/page) *is* trustworthy: it was taken
in a verified idle window, 39 minutes before the neighbour's GPU job started.

The committed Windows figure (58.29 s/page) is not a valid comparison either
— different machine, OS, torch and docling versions.

**The reportable CPU-vs-GPU result is the fixture one, measured in a verified
idle gap.** The 18-page CPU numbers are upper bounds and are labelled as such
in `results.json`.

This is a general lesson for this VM, not a one-off: a benchmark here needs a
recorded contention state, or it is not a benchmark. `results.json` now
records one per measurement.

## 5. Per-page cost varies by an order of magnitude

GPU, 18 real benchmark pages: min 3.64 s, median 8.05 s, max 43.27 s (a dense
newspaper page). A mean alone hides this. Any scheduling estimate for the full
1651-page set should use the distribution, not the mean — the tail is where
the time goes.

## 6. VRAM is workload-dependent, and my first estimate was 18× low

The synthetic fixture peaked at **906 MiB**. The real benchmark pages peaked
at **16592 MiB** — 72 % of the L4 — and held it for the whole run.

Extrapolating headroom from a small fixture would have been badly wrong. This
is the concrete reason the full benchmark was not launched while another
project's GPU job is resident: 16592 + 4264 MiB is 20856 of 23034 MiB.

Note also that the automated peak-VRAM figure in the run script was itself
wrong (8242 MiB) due to a field-splitting bug in the sampler's `awk`; the
correct value came from re-parsing the raw samples. Telemetry needs checking
too.

## 7. Failure modes observed on the fixture (taxonomy §44)

The broken-CMap fixture recovered **87 %** of source word tokens through the
visual fallback, against a native text layer that was 100 % garbage
(`ЅoҖѸ Йoa њa Йoi` for `Cong Hoa Xa Hoi`). The routing decision was correct
and valuable. The remaining errors are real research targets:

* **F2 (missed content)** — 10/77 tokens lost, concentrated on the numeric
  line (`Ma so doanh nghiep 0000000000 Dang ky lan dau ngay thang nam`).
* **F7 (reading order)** — `Giay` and `Ky` were emitted at the *end* of the
  page text rather than in line 2, having been detected as separate regions.
* **F4 (table false positive)** — a 4×2 table was detected on both pages of a
  document containing **no table at all**, with all 8 cells empty. This is the
  "dense text mistaken for a table" case named in the roadmap, reproduced in a
  minimal fixture — which makes it a usable regression case.

## 8. A false negative in the quality gate, confirmed empirically

`clean_digital.pdf` page 2 decodes Vietnamese as
`C·NG HÒA XÃ H·I CH· NGH·A` — diacritics collapsed to U+00B7 — and the gate
scores it **not suspicious**. This is the documented limitation ("cannot
detect a CMap that maps letters onto other plausible Latin letters") showing
up in practice: the damaged text stays single-script, so every signal passes.

It is a fixture artefact rather than a corpus finding — the base-14 font has
no Vietnamese glyphs — but it is a genuine demonstration that the gate's
recall is not 1.0, and a candidate hard case for the failure-case set.

## 9. Documentation held up well

Every documented behaviour checked against source or execution matched,
including several that would have been easy to get wrong: the DOCX
"no fabricated pagination" contract (`page_number=None`,
`is_rendered_page=False`), the XLSX sheet-vs-page distinction, the EMU
coordinate unit for PPTX, and the "~1.5 GB models" and "~35 s/page CPU"
figures. The Docling `DOCLING_ARTIFACTS_PATH` download-disabling behaviour is
documented in `docs/setup.md` and the Kaggle notebook, and is exactly what
happened.

The two things that did not hold were dependency completeness (`timm`) and
cross-platform provenance (the dataset byte hash), both now fixed.
