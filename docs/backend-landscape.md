# Backend landscape

Candidate document-parsing systems, screened against **this project's** target:
English + Vietnamese enterprise documents on a shared NVIDIA L4.

Nothing here is integrated. This is the screening record that decides what is
worth integrating, per §86: a candidate must answer *what problem does it
solve, why can't the existing pipeline solve it, what is the marginal benefit,
what is the cost*.

Status vocabulary is strict:

| Status | Meaning |
|---|---|
| **IN PRODUCTION** | Integrated, benchmarked here, validated |
| **SCREENED — CANDIDATE** | Researched from primary sources; not yet run here |
| **SCREENED — DEFERRED** | Researched; a specific reason not to pursue now |
| **REJECTED** | Researched; a specific reason not to pursue at all |

## Currently integrated

| Backend | Role | Status | Evidence |
|---|---|---|---|
| `pymupdf-native` | digital PDF text + native tables | IN PRODUCTION | 88% mean recall on enterprise-hardcases at 0.5 s / 14 docs |
| `native-office` | DOCX / XLSX / PPTX | IN PRODUCTION | IR semantics verified per format |
| `docling` | layout + OCR (component), whole-document | IN PRODUCTION | visual route 66% mean recall; 8.9× warm speedup on GPU |
| `table_transformer` | table detection + structure | IN PRODUCTION | grid geometry; cells filled from OCR tokens |

## Candidates

Figures are as reported by the projects themselves. Where a number is a
*claim* rather than something measured here, it is labelled as such — several
are easy to misread.

| System | Arch | Size | Licence | Languages | VI? | Claimed benchmark | Notes |
|---|---|---|---|---|---|---|---|
| **PaddleOCR-VL** | VLM (NaViT encoder + ERNIE-4.5-0.3B) | 0.9–1.0B | Apache-2.0 | 109 (v1.0) → 111 (v1.5) | secondary sources say yes; **not named in the primary papers** | OmniDocBench v1.6 **96.33%** (claimed) | Strongest candidate. Notably strong on the mechanisms this project cares about: seal recognition NED **0.138** vs Qwen3-VL-235B's 0.382; scanned 93.43%; skewed 91.66% |
| **MinerU2.5** | decoupled VLM | ~1.2B | AGPL-3.0 | CN/EN focus | not stated | OmniDocBench **90.67** overall (claimed) | Licence is the blocker, not the model — AGPL is the same constraint PyMuPDF already imposes |
| **dots.ocr** | single VLM, layout+text | ~1.7B | — | multilingual | not stated | text edit distance 0.048 (claimed) | Close to MinerU2.5 on text; no VI evidence |
| **olmOCR 2** | VLM | ~7B | Apache-2.0 | EN-centric | unlikely | olmOCR-Bench **82.4 ± 1.1** (claimed) | EN-centric; larger than needed for this workload |
| **Marker / Surya** | pipeline + specialist models | small | GPL/commercial | multilingual | partial | — | Licence needs checking before any integration |

### The VRAM figure that is easy to misread

PaddleOCR-VL's paper reports **~43.7 GB VRAM** with vLLM on an A100. That is
**vLLM's preallocated KV-cache pool** (its default is ~90% of the device), not
the model's footprint. A 0.9B model in BF16 is roughly **2 GB of weights**.

This distinction decides whether the model fits an L4 at all. Taken at face
value the answer is "no"; taken correctly it is "comfortably, with room for a
co-tenant". Any deployment here must set `gpu_memory_utilization` explicitly
rather than accept the default.

## Benchmark landscape

| Benchmark | Covers | Languages | Useful here for |
|---|---|---|---|
| **OmniDocBench** v1.6 | text, formulas, tables, reading order; 10 document types | EN, simplified CN, EN-CN mixed — **no Vietnamese** | comparing against published systems; generalization |
| **olmOCR-Bench** | ~1,400 docs, ~7,000 unit-test assertions | EN-centric | OCR robustness |
| **enterprise-hardcases** (this repo) | 14 mechanisms, EN/VI enterprise documents | EN, VI, mixed | **production quality** |
| ViOCRVQA / Viet-Doc-VQA / VNDoC | Vietnamese text in images, VQA-style | VI | future VI evaluation; VQA framing needs adapting |

**No public benchmark measures this project's target population.** OmniDocBench
has no Vietnamese at all, and experiment 007 showed its aggregate here was
dominated by Chinese. That is the entire justification for
`enterprise-hardcases` existing, and for treating OmniDocBench as a
generalization check rather than a production metric.

## Screening verdicts

**PaddleOCR-VL — SCREENED, CANDIDATE, not yet run.**
It is the only candidate that is simultaneously small enough for a shared L4
(~2 GB weights), permissively licensed (Apache-2.0), and specifically strong on
the failure mechanisms this corpus is built around — seals and stamps above
all, where it reportedly beats a 235B general VLM by a wide margin. That maps
directly onto `stamp_over_table`, the one case no current strategy recovers.

Not run this session for one reason: the GPU was **PROTECTED** by another
project's job throughout (4.7 GB resident, 100% utilization, 2h34m+). Per the
resource policy, competing for it was not an option, and a VLM screening on
CPU would measure nothing useful.

The screening plan is recorded rather than executed:

1. 5–20 pages from `enterprise-hardcases`, covering clean / table / stamp /
   tiny-text / multi-column.
2. Measure recall on the same `must_contain` strings, so the number is directly
   comparable with the three strategies already measured.
3. Record VRAM, latency, and Vietnamese diacritic fidelity specifically.
4. Only then decide integration — as a **recovery-ladder step**, not a default.

**MinerU2.5 — DEFERRED on licence.** AGPL-3.0. The project already carries
AGPL obligations via PyMuPDF and is internal-research scoped, so this is not
disqualifying, but it should not be added casually while a permissively
licensed candidate of similar quality exists.

**olmOCR 2 — DEFERRED on fit.** ~7B and EN-centric. Larger than needed and
weaker on the half of the target population that is Vietnamese.

**dots.ocr — DEFERRED pending VI evidence.** Competitive on text, but no
Vietnamese evidence found in primary sources.

## What the evidence says about *where* a VLM belongs

Experiment 008 measured that adaptive routing spends **99% of its cost on 1 of
14 documents**. That is the shape of the argument for a VLM: not as a page-level
default, but as a rung on the recovery ladder reached only when the cheap gates
fail.

The one case that no current strategy recovers — `stamp_over_table`, where
native holds the occluded text and visual holds the grid — is also the case
where fusion, not substitution, is the indicated answer. A VLM added as a
*third opinion* on the ~7% of documents that reach that rung is a very
different cost profile from a VLM run on every page.

## Sources

Primary sources consulted:

- [OmniDocBench](https://github.com/opendatalab/OmniDocBench) — language coverage, evaluation dimensions, v1.5/v1.6 changes
- [PaddleOCR-VL](https://arxiv.org/html/2510.14528v1) — architecture, 109 languages, A100 throughput and the vLLM memory figure
- [PaddleOCR-VL-1.5](https://arxiv.org/html/2601.21957v1) — seal/scan/skew results
- [PaddleOCR-VL-1.6 model card](https://huggingface.co/PaddlePaddle/PaddleOCR-VL-1.6) — size, licence, outputs
- [MinerU2.5](https://arxiv.org/pdf/2509.22186) — OmniDocBench positioning
- [dots.ocr](https://arxiv.org/pdf/2512.02498) — multilingual layout parsing
- [ViOCRVQA](https://arxiv.org/abs/2404.18397), [Vietnamese DAR survey](https://arxiv.org/pdf/2506.05061) — Vietnamese resources
