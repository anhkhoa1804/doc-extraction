# Model and dependency licences

Evidence for a company legal review — **not legal advice, and no legal
conclusion is drawn here.** Every row records what the official source
says and links to it; the "needs legal review" column flags what a lawyer
should look at before this project ships as anything other than internal
research.

Scope note: licences change between releases. Every entry below was read
from the official source at the date noted and **must be re-verified at
the version actually pinned** before any distribution decision.

Verified 2026-08-24.

---

## The finding that matters most

**The most restrictive licence in this project is not a model — it is a
core, non-optional code dependency.**

`pymupdf` is AGPL-3.0 and sits in `pyproject.toml`'s `dependencies`, not
in an optional extra: it is imported for native PDF parsing on the digital
route and cannot be disabled by config. MinerU2.5's AGPL-3.0 weights are
the more visible concern but are strictly *optional* — the project runs
without them. PyMuPDF is not optional.

This was already documented in `docs/backends.md` ("**This is the most
restrictive licence in the default dependency set**") and is restated here
because it belongs in a licence review, not only in a backend note.

---

## Models / systems

| System | Code licence | Weights licence | Source | Needs legal review? |
|---|---|---|---|---|
| **Docling** (layout + TableFormer) | MIT | MIT | [docling-project/docling](https://github.com/docling-project/docling) | Low |
| **Table Transformer** (`microsoft/table-transformer-*`) | Apache-2.0 (`transformers`) | **MIT** (model cards) | HF model cards | Low |
| **PaddleOCR-VL** (0.9B) | Apache-2.0 | **Apache-2.0** | [HF model card](https://huggingface.co/PaddlePaddle/PaddleOCR-VL) — quoted: `license: apache-2.0` | Low |
| **dots.ocr** (3B) | MIT | **MIT** | [HF model card](https://huggingface.co/rednote-hilab/dots.ocr) — quoted: `License: mit` | Low |
| **MinerU2.5-2509-1.2B** | "MinerU Open Source License, based on Apache 2.0" (README) | **AGPL-3.0** ([model card](https://huggingface.co/opendatalab/MinerU2.5-2509-1.2B)) | official README + model card | **HIGH — see below** |
| **EasyOCR** | Apache-2.0 | Apache-2.0 | [JaidedAI/EasyOCR](https://github.com/JaidedAI/EasyOCR) | Low |

## Core code dependencies

| Package | Licence | Optional? | Needs legal review? |
|---|---|---|---|
| **pymupdf** | **AGPL-3.0** (or commercial from Artifex) | **NO — core dependency** | **HIGH** |
| pydantic, pyyaml, pillow | MIT / MIT / MIT-CMU | core | Low |
| python-docx, python-pptx, openpyxl | MIT | core | Low |
| transformers, torch | Apache-2.0 / BSD-3-Clause | optional (`[tables]`) | Low |

---

## The two items flagged HIGH

### 1. `pymupdf` — AGPL-3.0, core, non-optional

Present in every install. AGPL's network-use provision is the specific
clause to review for a hosted internal service. Artifex sells a commercial
licence, which is the usual route if AGPL is unacceptable.

Options a review might consider, recorded without recommending one:
- obtain the Artifex commercial licence;
- confirm internal-only deployment is acceptable under AGPL for the
  company's use;
- replace the native-PDF path with a differently-licensed parser
  (`pypdfium2` is BSD/Apache) — a real code change, not a config switch.

### 2. MinerU2.5 weights — AGPL-3.0

Note the split: MinerU's **code** is described in its README as "MinerU
Open Source License, based on Apache 2.0", while the **weights** on the
model card are AGPL-3.0. A review must treat those separately; using the
weights is the operative question.

**This is avoidable.** MinerU2.5 was the SOTA candidate this project
measured (see `docs/sota_comparison.md` — `TEDS_structure_only = 1.0000`
on all five residual hard tables), but two comparably-strong alternatives
are permissively licensed:

- **PaddleOCR-VL — Apache-2.0**, 0.9B (smaller than MinerU2.5), reported
  SOTA on OmniDocBench v1.5, and 96.33 overall on v1.6 per the vendor.
- **dots.ocr — MIT**, 3B, reported Table TEDS 88.6 (EN) / 89.0 (ZH).

**Recommendation for the A30 phase: benchmark PaddleOCR-VL and dots.ocr
first, not MinerU2.5.** If a permissively-licensed model matches MinerU2.5
on our residual failures, the AGPL question never needs answering. Only if
MinerU2.5 proves materially better does it become worth a legal review.
This is a licensing-led ordering of the experiment queue, and it costs
nothing to adopt.

---

## Enterprise-deployment properties

Relevant to §19 (no SaaS dependency, local inference, no external upload):

| System | Runs fully local? | External API required? | Weights obtainable offline? |
|---|---|---|---|
| Docling | Yes | No | Yes (HF cache) |
| Table Transformer | Yes | No | Yes |
| PaddleOCR-VL | Yes | No | Yes |
| dots.ocr | Yes | No | Yes |
| MinerU2.5 | Yes | No (a cloud API exists but is optional) | Yes |

All candidates support fully-local inference with no document leaving the
network — the property that actually matters for the enterprise target.
**Licence, not capability, is the discriminator here.**

---

## What is NOT established

- No opinion is offered on whether AGPL is acceptable for this company's
  deployment. That is the review's job.
- Vietnamese support for PaddleOCR-VL is **unverified**: the model card and
  abstract both say "109 languages" without naming Vietnamese, and the full
  list was not located in a primary source. Given this project's actual
  target corpus is Vietnamese/English, this is a **blocking verification
  item** for the A30 phase, tracked in `docs/gpu_host.md`.
- Licences for the OmniDocBench *dataset* itself are governed by its own
  terms and are out of scope here (research benchmark use only).
