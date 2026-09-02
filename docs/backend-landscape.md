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
value the answer is "no"; taken correctly, the weights fit easily.

**Both readings turned out to understate the real cost.** Measured here
(experiment 009): 1,840 MiB after load, but **12,992 MiB peak** during
full-page inference — vision tokens for a 1653x2339 image, not parameters. On
a shared 23 GB L4 that rules out co-tenancy with anything using more than
~9 GB. Region-level inference on a small crop is far cheaper, which is another
argument for the specialist role over the parser role.

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

**PaddleOCR-VL — SCREENED ON HARDWARE. Page parser REJECTED; table
specialist CANDIDATE.** See `experiments/009_vlm_screening/`.

Measured on the enterprise-hardcases corpus, scored identically to the three
routing strategies: **68% mean recall against adaptive's 93%, at ~40x the
compute** (1483 s for 10 cases vs 37 s for 14 documents). It strictly beats
every cheaper strategy on **1 of 10** cases and loses on 5.

Decisive per-case findings:

| Case | native | adaptive | VLM | note |
|---|---|---|---|---|
| `merged_cells` | 67% | 67% | **100%** | the only genuine win — recovers a merged header cell nothing else does |
| `stamp_over_text` | 100% | 100% | **0%** | a seal hides pixels; the text layer still has the text |
| `clean_vi` | 100% | 100% | **50%** | clean born-digital Vietnamese; dropped diacritic-dense strings |

**The Vietnamese result is disqualifying for a default.** Half the production
population is Vietnamese, and the model lost half of a *clean* page in it.
That is exactly the failure a benchmark with no Vietnamese cannot surface.

Real costs beyond the score: peak VRAM is **12,992 MiB** for full-page
inference (weights are only 1,840 MiB — vision tokens dominate), and its
`transformers` path calls a keyword (`inputs_embeds`) that exists in none of
the four transformers versions tested, requiring a shim plus a separate 6.8 GB
venv.

Retained as a **narrow table-structure candidate**, invoked by a gate when the
native grid is untrustworthy — not as a parser.

---

*Why it was selected for screening (pre-screening assessment, superseded by
the measurements above):* the only candidate simultaneously small enough for a
shared L4, permissively licensed, and reportedly strong on seals — which is
why it was the one candidate worth spending GPU time on. The seal claim did
not survive contact with this corpus: it scored **0%** on `stamp_over_text`.
The vendor's reported NED of 0.138 is for reading text *on* a seal, which is a
different task from recovering text *underneath* one.

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
