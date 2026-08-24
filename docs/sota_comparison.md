# SOTA comparison: MinerU2.5 vs. the residual table failures

**Result: A — MinerU2.5 solves the residual failures.** This is a SOTA
integration / capability gap, **not a research gap**.

Measured directly on this machine, not inferred from published numbers.
Prior state: `docs/residual_failure_corpus.md` had 2 cases classified
`[F] unresolved` because no third model's output existed. It does now.

---

## 1. System audited

| Property | Value | Source |
|---|---|---|
| Model | `opendatalab/MinerU2.5-2509-1.2B` | official HF model card |
| Architecture | Qwen2-VL based, 1.2B params, BF16 checkpoint | model card |
| Parsing design | Decoupled coarse-to-fine: Stage I global layout on a 1036×1036 thumbnail, Stage II native-resolution crops per region | [arXiv 2509.22186](https://arxiv.org/html/2509.22186v1), quoted |
| Table interface | **End-to-end document parsing only** — no standalone table detection/structure API | official README |
| Code license | MinerU Open Source License, Apache-2.0 based | official README |
| **Weights license** | **AGPL-3.0** | model card |
| Documented CPU support | Pipeline backend and HTTP clients only — **not** the hybrid/VLM engines | official README |
| Documented VRAM | Pipeline 4 GB; **hybrid/VLM engines 8 GB** | official README |
| Documented RAM | 16 GB minimum, 32 GB recommended | official README |
| Windows support | Python 3.10–3.12 | official README |

### Environment reality check

| Requirement | Documented | This machine | Verdict |
|---|---|---|---|
| VRAM (VLM) | 8 GB | RTX 3050, **4 GB** | fails |
| Working CUDA | Volta+ | driver 462.62 → CUDA 11.2 max; `torch 2.8.0+cpu`, `cuda available: False` | **no usable GPU** |
| RAM | 16 GB min | **15.8 GB** | marginally below |
| Disk (full `mineru[all]`) | ~20 GB | C: 8.5 GB free, D: 76 GB free | needs D: redirect |
| Python | 3.10–3.12 | 3.12.10 | OK |

On paper this environment cannot run MinerU2.5. It was run anyway, by
taking the **thinnest possible path** rather than the documented one:
`mineru-vl-utils[transformers]` (lightweight wrapper — httpx/pillow/
pydantic/loguru/tqdm core) driving the checkpoint through plain
`transformers` on CPU in float32, in an **isolated `.venv-mineru`** so the
190-test baseline could not be disturbed, with `HF_HOME` redirected to D:.
Total footprint: 2,323.6 MB of weights. The documented "VLM engines do not
support pure CPU" refers to the packaged engines (vLLM/SGLang), not to the
transformers path, which runs — slowly but correctly.

## 2. Decisive experiment — the two unresolved cases

Both are 2×2 borderless grammar-box tables on `..._en_2901`, the two cases
that had blocked any verdict. Prior measurements: Table Transformer
returned no grid (`None`) / a wrong `2×1` at 1×, 2× **and** 3× scale;
Docling's TableFormer returned nothing on either crop.

| Case | GT | Docling TableFormer | Table Transformer | **MinerU2.5** |
|---|---|---|---|---|
| `en_2901[0]` | 2×2 | nothing | `None` @1×/2×/3× | **TEDS 0.7639, structure-only 1.0000** |
| `en_2901[1]` | 2×2 | nothing | `2×1` @all scales | **TEDS 0.9881, structure-only 1.0000** |

Both structures **exactly correct**. Our pipeline scores 0.0000 on both.
TEDS computed with the official evaluator's own `src.metrics.table_metric.TEDS`,
same implementation used for every other number in this project.

`en_2901[0]`'s content TEDS (0.7639) is below its perfect structure score
because the ground truth encodes fill-in-the-blank underscores (`____`)
which MinerU renders as an empty cell — a serialization difference on a
genuinely blank cell, not a structural error.

## 3. Generalization to the rest of the residual set

All five residual hard tables, MinerU2.5 vs. the two incumbents:

| Table | GT | Docling | Table Transformer | MinerU2.5 (crop) | MinerU2.5 (full page) |
|---|---|---|---|---|---|
| `en_2901[0]` | 2×2 | ✗ | ✗ `None` all scales | **1.0000** struct | — |
| `en_2901[1]` | 2×2 | ✗ | ✗ `2×1` all scales | **1.0000** struct | — |
| `jiaocaineedrop_46` | 2×7 | ✗ on crop | ✓ exact on crop (0.943 det) | **1.0000** struct, TEDS 0.9018 | **1.0000** struct, TEDS 0.9018 |
| `page-d29fe4d2` | 4×4 | ✗ on crop | `6×4` on crop | **1.0000** struct, TEDS 0.9283 | — |
| `page-28657a85` | 1×3 | ✗ on crop | `1×2` @1×, `1×3` @2×/3× | **✗ no table block** | **1.0000** struct, TEDS 0.9800 |

**MinerU2.5 achieves `TEDS_structure_only = 1.0000` on all five**, with
content TEDS 0.76–0.99, against 0.0000 from the current pipeline on every
one.

### A finding that changes how it must be integrated

`page-28657a85` inverts between the two columns: on a tight ground-truth
crop MinerU classified the region as ordinary **text** and emitted no
table at all, while on the **unmodified full page** it produced the
exactly-correct 1×3 table (TEDS 0.98).

This is the opposite of `TableTransformerBackend`, which *needs* a crop
(0.0675 → 0.9434 confidence on the same kind of region). The explanation
is architectural and matches MinerU2.5's own published design: it already
performs coarse-to-fine internally (global layout, then native-resolution
crops), so pre-cropping strips the page context its layout stage uses and
duplicates work it does anyway.

**Integration rule, measured not assumed: feed MinerU whole pages, never
pre-cropped table regions.** This is encoded in
`MinerUVLTableBackend.native_tables`' docstring and contract.

It also means the earlier crop-only reading of this case ("MinerU also
fails on the 1×3") was an artifact of the diagnostic method, and is
corrected here rather than left standing.

### Methodological caveat, stated plainly

The crop column used **ground-truth bboxes** to cut the region — an
oracle-assisted diagnostic, not a production path. The full-page column is
the production-realistic one, and it is where the two detection-dependent
cases (`jiaocaineedrop_46`, `page-28657a85`) were confirmed end-to-end
with no ground-truth assistance at all: MinerU's own layout stage found
and correctly labelled both tables, including the one our Docling layout
labels `picture`.

## 4. Compute cost

CPU-only, float32, 8 threads, RTX 3050 unused (no usable CUDA).

| Measure | Value |
|---|---|
| Model size on disk | 2,323.6 MB |
| Parameters | 1.156 B |
| Model load | ~26 s (once per process) |
| Per table crop | 53.9 s – 226.1 s |
| **Per full page (end-to-end)** | **181.7 s and 219.6 s** |
| Current pipeline, per page | ~70 s (100-page run mean) |

**MinerU2.5 costs roughly 2.6–3× the current pipeline's per-page time on
this hardware, with no GPU.** Published throughput on an A100 is 2.12 fps —
about three orders of magnitude faster than this CPU path — so these
numbers characterise *this* environment, not the model.

Practical consequence: a 100-page validation at ~200 s/page is ~5.5 hours
CPU-only. That is why the composition A/B below is scoped as the next
step rather than run here.

## 5. Limitations

- **No aggregate benchmark comparison was run.** Per the task's explicit
  instruction, this project's 100-page subset score is *not* compared
  against MinerU's published full-OmniDocBench numbers as if they were
  equivalent measurements. The comparisons above are same-image,
  same-ground-truth, same-TEDS-implementation, and nothing broader is
  claimed.
- **n = 5 tables.** Enough to resolve the specific `[F] unresolved`
  classification (which needed exactly one counterexample per case), not
  enough to characterise MinerU's behaviour on this corpus generally.
- **Structure is perfect; content is not.** Content TEDS ranges 0.76–0.99.
  Whether the residual content gap is OCR, serialization, or ground-truth
  encoding (as with the `____` case) is not analysed here.
- MinerU was run through `transformers` on CPU, which is *not* the
  officially supported deployment path for the VLM engine. Results should
  be reproducible on any GPU box via the supported vLLM/SGLang path, but
  that was not verified here.
- **AGPL-3.0 weights.** A materially different licensing obligation from
  this repo's other model dependencies; requires review before any
  redistribution or hosted deployment.

## 6. Conclusion

**RESULT A.** One modern SOTA candidate solves every residual failure the
two incumbent structure models could not — with perfect structure on all
five, including both cases that had held the `[F] unresolved` label.

Therefore, updating `docs/residual_failure_corpus.md`'s classification:

| Case | Was | Now |
|---|---|---|
| `en_2901[0]` | `[F] unresolved` | **`[B] missing integration`** |
| `en_2901[1]` | `[F] unresolved` | **`[B] missing integration`** |

**Zero cases remain in `[E] possible research gap` or `[F] unresolved`.**
The residual table-extraction problem in this project is now fully
accounted for as pipeline defects and missing SOTA integration.

Per the task's own decision rule — a research gap requires multiple
independent model families to fail on a clearly-defined, reproducible
capability, with pipeline/adapter errors ruled out — **no research gap
exists here.** A third model family succeeds where two failed.

The honest summary: *the remaining error was caused primarily by not
having integrated a modern document-parsing VLM, existing SOTA already
solves it, and therefore the highest-value next work is integration and
its compute/quality tradeoff — not research.*

## 7. What was built, and what comes next

Built (smallest viable surface area, **no change to the canonical IR,
composition algorithm, reading order, evaluator, or existing backends**):

- `MinerUVLTableBackend` in `src/doc_extraction/backends/mineru_backend.py`,
  exposing `native_tables(page) -> list[Table]` — the exact duck-typed hook
  `pipelines/base._gather_extra_table_candidates` already looks for, so the
  existing N-way composition can consume MinerU as an additional candidate
  with no algorithm change.
- `parse_html_table()` — MinerU's `<table>` HTML into a canonical `Table`,
  honouring `colspan`/`rowspan` via an occupancy grid, using only the
  standard library.
- 12 tests (`tests/test_mineru_backend.py`) covering parsing, spans,
  bbox normalisation, and the laziness/availability contracts. Suite:
  190 → **202 passing**.

Next, in order:

1. **Composition A/B**: current best-of-two vs. best-of-three on the
   20-page subset (table TEDS, structure-only, Edit_dist, text,
   reading-order, runtime, and specialist-invocation count). ~1 h CPU.
2. **Selective invocation.** At ~3× the per-page cost, running MinerU on
   every page is the wrong production design. The natural gate is the
   condition this whole investigation has been characterising — regions
   where the cheap specialists disagree or produce nothing. That is an
   *engineering* optimisation with a measurable cost/quality curve, not a
   research question.
3. Only then consider a broader (100-page) validation, and only on
   hardware where MinerU is not CPU-bound.

---

# Production candidate matrix (A30-class target)

Added when the compute target moved off the development laptop. **The
laptop's 4 GiB RTX 3050 / CUDA-11.2 / CPU-only-torch limits are NOT inputs
to these decisions** — a model that cannot run on the laptop is marked
"requires GPU-host validation", never rejected.

Evidence types are kept strictly separate below:
**[P]** published result (primary source) · **[M]** our direct measurement
· **[I]** our inference. Nothing published is compared against our subset
scores as if equivalent.

## End-to-end document parsers

| | PaddleOCR-VL | dots.ocr | MinerU2.5 | Docling (current) |
|---|---|---|---|---|
| Params | 0.9B | 3B (1.7B LLM) | 1.2B | ~200M-class stack |
| Architecture | NaViT dynamic-res encoder + ERNIE-4.5-0.3B; PP-DocLayoutV3 (RT-DETR) layout | Qwen2.5-VL based, single unified model for layout + content | Qwen2-VL based; decoupled coarse-to-fine (1036² thumbnail layout → native-res crops) | RT-DETR layout + TableFormer + EasyOCR |
| **Weights licence** | **Apache-2.0** [P] | **MIT** [P] | **AGPL-3.0** [P] | MIT [P] |
| Languages | 109 claimed [P]; **Vietnamese unverified** | EN/ZH + 100 demonstrated [P] | EN/ZH focus | via EasyOCR (incl. `vi`) [M] |
| OmniDocBench | v1.5 SOTA overall/text/formula/table/reading-order [P]; 96.33 overall v1.6 (vendor) [P] | Table TEDS 88.6 EN / 89.0 ZH; overall edit 0.125 EN / 0.160 ZH [P] | 95.69 overall v1.6 (Pro) [P]; Table TEDS 93.42 / TEDS-S 95.92 [P] | our pipeline: table TEDS 0.4514 on 100-page subset [M] |
| Table capability | strong [P] | strong [P] | **struct 1.0000 on all 5 of our residual hard tables** [M] | baseline [M] |
| Formula | yes [P] | comparable to much larger models [P] | yes [P] | **not active in our baseline** [M] |
| Reading order | yes (absolute order predicted) [P] | SOTA [P] | yes [P] | geometric heuristic [M] |
| Inference | PaddleOCR / vLLM / transformers; quantised variants | transformers / vLLM | transformers / vLLM / SGLang | native |
| CPU support | yes | yes (slow) | transformers path works [M] | yes [M] |
| VRAM | not stated [P] | not stated [P] | 8 GiB for VLM engines [P] | ~CPU-friendly |
| Integration complexity | medium (new stack) | medium | **low — adapter already exists** [M] | zero (current) |
| Production suitability | **highest** (permissive + smallest + multilingual) [I] | high (permissive, larger) [I] | **licence-gated** [I] | current baseline |

**All four run fully locally with no external API** — the enterprise
constraint (§19) does not discriminate between them. **Licence and
verified language support do.**

## Table / layout / OCR specialists

| | Table Transformer | TableFormer (Docling) | PP-DocLayoutV3 | EasyOCR |
|---|---|---|---|---|
| Role | table detection + structure | table structure | layout | OCR |
| Licence | MIT weights, Apache-2.0 code [P] | MIT [P] | Apache-2.0 [P] | Apache-2.0 [P] |
| Status here | active [M] | active [M] | not integrated | active [M] |
| Known limitation | single-scale DETR; needs a crop (0.0675→0.9434 on same region) [M]; nondeterministic across processes [M] | returns nothing on all 5 residual hard crops [M] | — | Chinese needs `ch_sim`; cannot combine with `vi` [M] |

## Ordering for the A30 phase

1. **PaddleOCR-VL first** — Apache-2.0, smallest, strongest published
   OmniDocBench numbers, claims the multilingual coverage this project
   actually needs. Gate: **verify Vietnamese directly.**
2. **dots.ocr second** — MIT, permissive fallback if Vietnamese fails.
3. **MinerU2.5 only if a permissive model is materially worse** — it is
   the one we have measured [M] and it has a working adapter, but AGPL-3.0
   weights need legal review before production. Do not spend that review
   until the benchmark shows it is worth it.

This ordering is licence-led on purpose and costs nothing: if a permissive
model matches MinerU2.5 on our residual failures, the AGPL question never
needs answering. See `docs/model_licenses.md`.
