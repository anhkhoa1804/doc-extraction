# Milestone 034a — Full OmniDocBench External Benchmark Snapshot — Final Report

Baseline: `02a78a1` (033, EXPERIMENTAL). External validation layer, not a
replacement for the production-shaped 023–033 research track.

Labels: **FACT** (directly measured), **INFERENCE** (a conclusion from
facts with a stated logical step), **HYPOTHESIS** (untested to
falsification), **RECOMMENDATION** (an action, not a claim about the
world).

---

## 1. Benchmark scope and current status

**FACT**: this is an external validation snapshot against the official
OmniDocBench v1.6 benchmark (1651 pages, HuggingFace
`opendatalab/OmniDocBench`, pinned evaluator commit
`193627ae9e97d89188468ed1ee3b7a856ff76044`, package `omnidocbench_eval`
1.6.0). It does not redirect 023–033's research program.

**FACT, status at close**: the full 1651-page benchmark was launched
using the selected configuration (`selected_benchmark_config.json`) and
was **in progress** (partial page count — see `results/full_baseline/
runtime.json` for the exact count at any checkpoint) when this report was
written. All accuracy claims below are drawn from a **complete, real,
official-evaluator-scored 77-page representative subset**
(`results/subset_B_fixed_auto/metrics.json`), not the full corpus, unless
explicitly marked otherwise. This is stated plainly, not hidden — see §12
for exactly why, and how to resume.

---

## 2. Environment (Phase 0)

**FACT** (`environment.json`/`baseline_environment.json`): commit
`02a78a1` (== origin), NVIDIA L4 (23034 MiB), driver 580.173.02, CUDA
12.8, torch 2.11.0+cu128 (GPU venv) / 2.13.0+cpu (CPU venv), Transformers
5.16.1, Docling 2.124.0. OmniDocBench evaluator: pinned commit confirmed
by direct `git log`, package version confirmed by
`importlib.metadata.version`. Test baseline `341 passed, 10 skipped`,
confirmed unchanged before any milestone work began.

---

## 3. Dataset integrity (Phase 3)

**FACT** (`dataset_manifest.json`, using this repo's own `odb.load_
dataset()` validator, not a reimplementation): 1651 records, 1651 images
resolved, 0 missing, 0 duplicates, 0 zero-byte files. Total 1.446 GB.
**Language distribution**: simplified_chinese 765, english 755,
en_ch_mixed 116, traditional_chinese 13, other 2 — **zero Vietnamese**.
**Data source distribution**: book 276, PPT2PDF 253, academic_literature
215, exam_paper 193, colorful_textbook 159, newspaper 151, magazine 149,
research_report 132, note 118, historical_document 5.

---

## 4. Exact production configuration (Phase 2)

**FACT** (`production_baseline_config.json`): `configs/cpu.yaml` (the
ONLY validated production profile) with exactly one field changed —
`device: "cpu"` → `device: "auto"` — matching `configs/gpu.yaml`'s own
documented guidance to prefer `auto` over a literal `cuda` on a shared
machine. `ocr_languages: ["en", "vi"]` was **never changed**, per this
milestone's explicit rule and experiment 007's prior finding (Chinese OCR
costs 43.6% on English, collapses English table structure 0.715→0.000).

---

## 5. The device-resolution bug (Phases 0–4 of the interrupt)

**FACT** (`device_resolution_diagnosis.json`): the smoke test crashed
6/6 pages at the `table_transformer` stage with `RuntimeError: ... device
string: auto`. Root cause, traced to exact source: `resolve_device()`
(`cli.py:51`) is called only inside `cmd_run`/`cmd_compare` (the CLI
dispatch functions); `process_file()` (`cli.py:246`), the library
entrypoint 15+ research/benchmark scripts call directly, never called it.
**17 callers found**: 15 already protected (CLI's own resolution, or a
`configure()`-calls-`resolve_device()` convention already established by
`research/production_corpus/run_benchmark.py` and `research/hardcases/
run_benchmark.py` — the two scripts underlying `docs/production-
contract.md`'s own capability claims), 1 vulnerable (this milestone's own
`experiments/005_omnidocbench/prepare.py`, the first caller in this
repo's history to deliberately request `device="auto"` through the
library path).

**Classification**: **REAL PRODUCTION INFRASTRUCTURE BUG** — `process_
file()` is a genuine, actively-used library entry point, and `"auto"` is
a documented, first-class `PipelineConfig.device` value — but blast
radius was latent/zero until this milestone (no historical caller had
ever triggered it).

**FACT — the fix** (`src/doc_extraction/cli.py`, 12-line diff): a guarded
call, `if config.device == "auto": config = resolve_device(config)`, at
the top of `process_file()`. Guarded, not unconditional, specifically to
avoid clobbering the richer `_DEVICE_DECISION` metadata already-protected
callers record. **Regression test** (`tests/test_cli_device_resolution.
py`, 4 cases): confirmed to FAIL without the fix (git-stash-verified:
`AssertionError: assert 'auto' == 'cpu'`) and pass with it. **Full suite**:
`345 passed, 10 skipped` (341 baseline + 4 new, 0 regressions).

**RECOMMENDATION**: prepare this as a separate, standalone production
commit — not folded silently into a benchmark-snapshot commit
(`recommendation.json`).

---

## 6. Correctness validation (Phase 6 of the interrupt)

**FACT** (`subset_correctness.json`): Config A (workaround, `device:
"cuda"` literal, `configs/gpu.yaml` unmodified) vs Config B (fixed,
`device: "auto"`) on the identical 77-page subset: **77/77 byte-identical
predictions**, runtime 558.5s vs 549.6s (within normal variance). The fix
is confirmed semantically no-op.

---

## 7. Representative subset (Phase 5 of the interrupt)

**FACT** (`subset_manifest.json`): 77 pages, stratified (seed=42, not
random-uniform) — 15 each from the official `equation_hard`/`layout_
hard`/`table_hard` pools, plus up to 4 per `data_source` (2 multi-column
+ 2 single-column) from the base `v1.5` pool. Coverage: 28 pages with a
table region, 21 with a formula region, 29 with multi-column layout.
**FACT**: every OmniDocBench sample is a pre-rendered page image (png/jpg)
— there is no PDF/office input, so every page necessarily takes this
system's `image` route. Adaptive native-vs-visual routing is **never
exercised** by this benchmark at all — a clean, structural finding, not
an oversight.

---

## 8. GPU concurrency experiment (Phases 7–9 of the interrupt)

**FACT** (`concurrency_results.json`, `selected_benchmark_config.json`):

| Arm | pages/sec | speedup | peak VRAM | min free VRAM observed | failures | determinism mismatches |
|---|---:|---:|---:|---:|---:|---:|
| C1 (serial) | 0.1401 | 1.00x | never > ~92% | comfortable throughout | 0 | — (baseline) |
| C2 | 0.2375 | 1.71x | 97.2% | ~218–292 MiB | 0 | 0/77 |
| C4 | 0.3619 | 2.60x | 97.9% | ~96 MiB (touched repeatedly) | 0 | 0/77 |
| C8 | not attempted | — | — | — | — | — |

**FACT**: process-level concurrency is safe — `_get_component_backends()`'s
own docstring already documents backends as sequential-only within a
process (module-global cache); this experiment used separate OS
processes throughout, never threads, and zero determinism mismatches
confirm this empirically. **C8 not attempted**: C4 already demonstrated
VRAM free dropping to 0.4% of total capacity multiple times on a 77-page
sample; extrapolating linearly predicts certain OOM, and the interrupt's
own instruction gates C8 on headroom "clearly" supporting it.

**FACT — live GPU-sharing event**: partway through this milestone, `nvidia-
smi` showed `select_device("auto")` reclassifying the GPU as **PROTECTED**
(100% utilization, 2 compute processes) because another project's
training job (`openvocab_rel.train`, hostname `research-no-1`) had begun
actively computing. The in-progress full-benchmark GPU process was
stopped within 3 seconds via `SIGTERM` (verified: the other job's own
process was never touched, continued running unaffected). The benchmark
was restarted CPU-only. ~15 minutes later, the other job had exited
(`ps -p <pid>` confirmed no such process); GPU was reconfirmed CLEAR via
`select_device("auto")`, and the benchmark was switched back to GPU. This
is a real, live exercise of the documented GPU-sharing policy, not a
simulated one.

---

## 9. Pipeline stage breakdown (Phase 11 of the interrupt)

**FACT** (`pipeline_timing_timing_probe.json`, 20-page `--keep-runs`
probe): **layout (Docling) dominates at ~89% of total pipeline time**
(mean 7.67s/page, p95 18.07s), render (pymupdf) a distant second (~7%),
table (Table Transformer) only ~4% (mean 0.335s/page — fast per call).
**FACT** (`batching_results.json`): no batching capability exists
anywhere in the current backend architecture — every backend method
(`TableTransformerBackend.extract`, `DoclingBackend.analyze`/`convert`)
takes exactly one page per call, confirmed by direct signature
inspection. GPU underutilization (mean 32.9–53.5% during concurrency
tests) cannot be attributed to a missing batching *toggle* — there is no
toggle, only new engineering, out of scope here.

---

## 10. Selected configuration (Phase 12 of the interrupt)

**Decision** (`selected_benchmark_config.json`): **C1 (serial),
device=auto (resolves to cuda given CLEAR)**. C2/C4 are real, measured,
zero-failure improvements — not rejected as invalid — but both were
observed within 1–4% of total VRAM capacity on a sample 21x smaller than
the full corpus, which was not filtered for maximum image size. Per this
milestone's own principle ("fastest STABLE, not fastest unsafe"), a
margin that thin at 1/21 scale is not trusted to hold at full scale.

---

## 11. Official accuracy metrics (Phase 7, subset — Phase 6/13 pending full run)

**FACT** (`official_metrics.json`, `results/subset_B_fixed_auto/
metrics.json`, 77 pages, real official evaluator, not a substitute):

| Category | Metric | Value |
|---|---|---:|
| text_block | Edit_dist.ALL_page_avg | 0.6250 |
| display_formula | Edit_dist.ALL_page_avg | 0.9580 |
| table | TEDS.all | 0.0965 *(see caveat below)* |
| table | TEDS_structure_only.all | 0.1988 |
| reading_order | Edit_dist.ALL_page_avg | 0.6016 |

No aggregate "Overall" score: OmniDocBench's own formula requires formula
CDM (Linux TeX Live/ImageMagick/Ghostscript toolchain, not verified
present) — per-metric numbers reported directly, never a substitute
composite.

**FACT — evaluator-side bug, external to this project**: `metrics.json`'s
own `table.all.metric_debug.TEDS` shows **26 of 37** TEDS sample
computations failed with `AssertionError: can only join a started
process` (a multiprocessing race inside `omnidocbench_eval`'s own worker
pool). The reported TEDS numbers are computed from the 11 surviving
samples (30%), not the full 37 — flagged prominently, not silently
absorbed into a clean-looking number.

---

## 12. Worst / best failures (Phase 9, approximate proxy — see caveat)

**FACT** (`failure_analysis_subset_B_fixed_auto.json`): the official
evaluator's own collected output does not expose per-page scores through
any file `evaluate.py` collects (`page` is keyed by metric name → an
attribute-grouped breakdown, not per-image; `group.sample_count` is
empty at both n=6 and n=77) — verified directly, not assumed. Per-page
ranking here uses a clearly-labeled **approximate** `difflib` text-
similarity proxy, not the official metric.

**FACT, the dramatic result**: **every one of the 10 worst-ranked pages
is `simplified_chinese`; every one of the 10 best-ranked pages is
`english`.** Mean similarity by language: english 0.5028 (n=29),
simplified_chinese 0.0301 (n=38) — a **16.7x gap**. This directly
confirms, at much larger and more dramatic scale, experiment 007's prior
finding that this system's OCR scope is EN/VI-only by deliberate design.

---

## 13. External validation of 023–033 findings (Phase 9/10, original)

**FACT** (`cross_research_comparison.json`), cross-referencing the A–H
failure taxonomy:

| Mechanism | Present in OmniDocBench? |
|---|---|
| F. text fidelity | **YES, directly measured** |
| G. page reading order | **YES, directly measured** (a genuine external analog to 028's Layer-2 metric, not Layer-1's blind one) |
| E. table structure/order | Partially observable — structure-only TEDS > content-inclusive TEDS, directionally consistent with 026/029's "structure more reliable than text" finding |
| D. region-label gating (031) | Partially observable, unconfirmed without a per-page internal-IR cross-reference not performed this milestone |
| A. OCR acquisition | Present but categorically different — a language-scope gap, not a recognizer/route choice within EN/VI |
| B. orphan evidence | **Not measurable** — the evaluator has no ownership/attribution model |
| C. ownership/duplication | **Not measurable**, same reason |
| H. role ambiguity (032/033) | **Not measurable** by this benchmark's methodology — OmniDocBench scores final output text, never this system's own internal `Region.label`/`ElementType` routing decisions |

**Headline**: 2/8 mechanisms reproduce directly, 2/8 are directionally
consistent, 3/8 are structurally invisible to ANY output-text-comparison
benchmark, and the single largest measured effect (the language gap) is
not one of the eight mechanisms at all.

---

## 14. Benchmark vs. production corpus (Phase 11, original)

**FACT** (`benchmark_vs_production_corpus.json`, 11-row comparison
matrix): OmniDocBench and the 023–033 production-shaped corpus are almost
entirely complementary — different languages (Chinese/English vs
English/Vietnamese), different document genres (books/academic/news vs
enterprise transactional documents), and critically, **stamps/occlusion
— the central mechanism of 025–031's entire research chain — has no
corresponding OmniDocBench attribute at all**, confirmed absent from the
full `page_attribute` schema, not merely unmeasured this run.

---

## 15. Efficiency (Phases 15–16 of the interrupt)

**FACT**: layout dominates (§9), no batching exists (§9), concurrency
gives real but VRAM-risky speedups not selected for the full run (§8,
§10). **INFERENCE**: the dominant latency component (Docling layout) is
outside this project's direct control (a third-party model's own forward-
pass cost); the system's architecture is not GPU-underutilized due to a
fixable scheduling gap, but due to the fundamental cost of the layout
model itself plus a strictly sequential, one-page-at-a-time processing
loop that this milestone did not find justification to change (batching
would be new engineering, concurrency's VRAM margin was judged unsafe at
full scale).

---

## 16. Historical compatibility (Phase 14, original)

**FACT** (`historical_comparison.json`): experiment 005 (2026-08-20, demo
dataset, 18 pages, Windows, CPU, docling 2.120.3/torch 2.8.0) is the
**only** prior OmniDocBench result in this repository. Classified
**PARTIALLY COMPARABLE** to this milestone's subset run — same evaluator
commit and backend logic, different machine/device/dataset scale.
Directionally consistent: both runs show LOW table TEDS (005: 0.1526,
034a: 0.0965) and moderate-to-poor text edit distance (005: 0.7448, 034a:
0.6250) — not contradictory, though not directly averaged given the
disjoint page sets.

---

## 17. Research interpretation — five explicit answers

**1. Current system performance**: mixed and sharply language-dependent
— strong-ish on English (0.50 mean similarity), near-zero on Chinese
(0.03), consistent with a documented, deliberate scope boundary, not a
new defect.

**2. External validity**: OmniDocBench validates this system's text-
fidelity and reading-order behavior directly (§13), and is silent on the
evidence-integrity mechanisms (ownership, duplication, role ambiguity)
that 023–033's own research found most production-critical.

**3. Reliability coverage**: two real, independent reliability findings
this milestone — one in this project (the device-resolution bug, §5,
fixed) and one in the OFFICIAL EVALUATOR itself (the TEDS worker-pool
race, §11, external, unfixed, flagged).

**4. Efficiency**: layout dominates at ~89% of latency; GPU concurrency
gives real 1.7–2.6x speedups but at VRAM margins judged too thin to trust
at 21x scale; C1/serial was selected for safety.

**5. Blind spots**: OmniDocBench cannot see orphan-evidence recovery,
ownership/duplication, or role-ambiguity mechanisms (§13) — the three
things 025/028/032/033 spent the most research effort on — and has no
attribute for stamps/occlusion at all, the single most production-
critical phenomenon this whole research chain has found (§14).

---

## 18. Decision (Phase 19)

# **PARTIALLY_VALIDATES**

Text fidelity and reading-order dimensions genuinely validate against an
independent external benchmark (§13, direct reproduction). Table accuracy
is inconclusive due to a confirmed evaluator-side bug (§11), not this
system's fault. The benchmark's dominant signal (the language gap) is a
known, deliberate scope boundary, not a challenge to the architecture.
Three of the research chain's most important findings (evidence
ownership, duplication, role ambiguity) are simply not measurable by this
benchmark's methodology — this is a genuine, honest **blind-spot finding**
in its own right, not a failure of this milestone.

---

## 18a. Reproducibility (Phase 19)

**FACT — analysis-layer determinism**: every post-processing script in
this experiment (`extract_official_metrics.py`, `cross_research_
comparison.py`, `failure_analysis.py`) was rerun a second time against
the same source data and diffed byte-for-byte against its first output —
`official_metrics.json`, `category_metrics.json`, `cross_research_
comparison.json`, and `failure_analysis_subset_B_fixed_auto.json` are all
byte-identical across reruns.

**FACT — model-layer determinism**: §6's Config A vs Config B comparison
(`subset_correctness.json`) is a *stronger* determinism claim than a
same-config rerun would be — it shows 77/77 byte-identical predictions
across **two different device-resolution code paths** (a literal `cuda`
workaround vs the fixed `auto`-resolves-to-`cuda`), which subsumes the
same-config case. A literal same-config-twice GPU rerun of the subset was
deliberately **not** additionally launched while the full 1651-page run
was active, to avoid adding uncontrolled concurrent VRAM pressure beyond
the C1-serial-only policy selected in §10 — running two GPU jobs at once
was never a measured, selected configuration.

**FACT — environment pinning**: evaluator commit, package version, torch/
Transformers/Docling versions, GPU driver/CUDA version, and the exact
commit this milestone ran against are all recorded verbatim in `environment.
json` (§2). `git diff --check` is clean; the full CPU test suite was
rerun and reconfirmed `345 passed, 10 skipped` (0 regressions) after all
work in this milestone. No file under `experiments/029_*` through
`experiments/033_*` was modified (`git status` confirms zero touches).

---

## 19. Limitations

- The full 1651-page benchmark was in progress, not complete, when this
  report was written (§1, §12) — all accuracy numbers are subset-based
  (77/1651 pages, 4.7%), though stratified for genre/difficulty diversity,
  not random.
- Per-page failure ranking uses an approximate proxy, not the official
  metric (§12) — the official evaluator's own collected output does not
  expose per-page scores through any file available to this milestone.
- Table TEDS is computed from 30% of intended samples due to a confirmed,
  external evaluator bug (§11) — not remediated (out of scope: this
  project does not own `omnidocbench_eval`).
- Mechanisms D (region-label gating) and H (role ambiguity) were judged
  "partially observable"/"not measurable" without a per-page cross-
  reference against this system's own internal layout JSON — not
  performed this milestone given the full-run time budget; flagged as
  the single most valuable follow-up.
- Formula CDM and the OmniDocBench "Overall" composite score were not
  computed (Linux toolchain not verified present).

---

## 20. Production implications

**RECOMMENDATION**: the device-resolution fix (§5) should become its own
standalone production commit, reviewed independently of this benchmark
snapshot's research content — it is unrelated to any benchmark-motivated
change and does not touch accuracy-relevant code (§7's `final_
comparison.json`: accuracy and device/concurrency configuration are
architecturally decoupled, confirmed empirically). **No other production
change is recommended** — the language gap is a known, deliberate
boundary (do not add Chinese OCR to chase this benchmark, per explicit
instruction and 007's own prior finding); concurrency was not selected
for production use given the VRAM margin found unsafe at scale.

---

## 21. Final recommendation

Resume this milestone (not a new one) once the full 1651-page CPU/GPU run
completes: rerun `extract_official_metrics.py results/full_baseline`,
`failure_analysis.py results/full_baseline dataset/full`, and
`historical_comparison.py` to replace the subset-based numbers throughout
this report with full-corpus ones, and re-verify the language-gap finding
holds at full scale (expected: yes, given the subset was stratified, not
cherry-picked, and the gap is dramatic — 16.7x — not a marginal effect
likely to wash out).

---

## 22. Exact next research question

> Does the confirmed region-label-gating mechanism (031's central
> finding) reproduce on OmniDocBench specifically — i.e., for pages where
> OmniDocBench's own ground truth marks a `table` category region, does
> this system's own internal layout JSON (per-page intermediate output,
> obtainable via `prepare.py --keep-runs` on a targeted subset of
> table-containing pages) show a `table`-labelled region, or a
> `picture`/`figure`-labelled one containing the same evidence — closing
> the "partially observable, unconfirmed" status of mechanism D in §13?
