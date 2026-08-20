# Backends

## Status legend

Every backend below is labelled with one of these, and the labels are meant
literally:

| Status | Meaning |
|---|---|
| **Validated locally** | Installed here, run end-to-end on the real corpus, CPU-only |
| **Implemented, unvalidated** | Code exists and is exercised by tests, but has not been run against a real workload in this environment |
| **Optional / not installed** | Adapter exists and reports unavailable; installing it is documented but was not done here |
| **Planned** | Interface only; no implementation ships |

Reference environment: Windows, CPU-only. `torch.cuda.is_available()` is
**False** (CPU-only torch 2.8.0+cpu; GPU driver caps at CUDA 11.2). Repo and
all caches live on a data drive, not the OS drive (which has <8 GB free).

## GPU status

**No GPU path in this repository has been validated.** `configs/gpu.yaml`
documents the intended shape of a GPU config and says so in its own header.
Nothing in the default path, the test suite, or the local validation
sequence requires CUDA. Before trusting `device: cuda`, check:

```bash
python -c "import torch; print(torch.cuda.is_available())"
```

## Summary

| Backend | Role | Status | CPU | Model download |
|---|---|---|---|---|
| `pymupdf-native` | Digital-PDF text | **Validated locally** | yes | none |
| `pymupdf_tables` | Digital-PDF table structure | **Validated locally** | yes | none |
| `native-office` | DOCX/XLSX/PPTX | **Validated locally** | yes | none |
| `docling` | Whole-document; also layout+OCR components | **Validated locally** | yes | ~1.5 GB |
| `table_transformer` | Table structure on rendered pages | **Validated locally** | yes | ~110 MB |
| `mineru` | Whole-document | Optional / not installed | — | multi-GB |
| `paddleocr` | OCR + layout + tables | Optional / not installed | — | ~1 GB |
| `vlm` | Document VLM | **Planned** (no implementation) | — | several GB |

---

## PyMuPDF native text (`pymupdf-native`) — Validated locally

**Purpose**: text blocks, headings (by relative font size) and image
placeholders from a born-digital PDF's text layer.

**Install**: core dependency (`pip install -e .`). No model, no download.

**Strengths**: essentially free (sub-second for a 40-page document), exact
character positions, no OCR error.

**Weaknesses**: completely at the mercy of the PDF's own encoding. If the
embedded font's `ToUnicode` CMap is wrong, this returns confident garbage —
which is precisely why `ingest/text_quality.py` exists and why this backend
is never trusted without a quality check.

**License**: PyMuPDF is AGPL-3.0 (or a commercial licence from Artifex).
**This is the most restrictive licence in the default dependency set** — it
matters if this code is ever distributed as part of a closed product. It
does not affect internal research use.

## PyMuPDF native tables (`pymupdf_tables`) — Validated locally

**Purpose**: table detection and structure for the digital-PDF route, from
vector ruling lines and text alignment.

**Install**: core dependency. No model, no download.

**Measured**: ~20–70 ms per page. On the sample corpus it recovers table
structure from digital PDFs that phase 1 flattened into paragraph text
entirely — see
[experiments/002_digital_pdf_tables](../experiments/002_digital_pdf_tables/).

**Weaknesses / limitations**:
* **Row spans are not recovered** (always `row_span=1`). PyMuPDF treats rows
  independently and does not mark vertical merges. Column spans *are*
  recovered, from its `None` cell placeholders.
* Borderless tables laid out with tab stops are often missed.
* Dense multi-column text is occasionally detected as a spurious table.

**Fallback when this is not enough**: render the page and use
`table_transformer`, which sees the same visual evidence a human does.

**License**: as PyMuPDF above.

## Native office (`native-office`) — Validated locally

**Purpose**: DOCX / XLSX / PPTX via `python-docx`, `openpyxl`, `python-pptx`.

**Install**: core dependencies. No model.

**Strengths**: exact structure — real heading levels, real list items, real
merged-cell spans (both row and column), real sheet/slide boundaries.

**Weaknesses**: DOCX exposes no rendered pagination (see
[output-format.md](output-format.md)); `page_number` is `None` there by
design. Getting true DOCX pagination requires a layout engine (LibreOffice
or Word), which this project deliberately does not require — the dependency
cost is large and the benefit is limited to a page-number field.

**License**: MIT (python-docx, python-pptx), MIT (openpyxl).

## Docling — Validated locally

**Purpose**: primary whole-document backend, and the default component
backend for layout + OCR on the visual route.

**Install**:
```bash
pip install -e ".[docling]"
```
On Windows you will hit a packaging snag first — see [setup.md](setup.md)
for the two-command `antlr4-python3-runtime` fix (an `omegaconf` transitive
dependency, unrelated to Docling itself).

**Models**: layout + reading order, TableFormer for tables, and a pluggable
OCR engine. **Docling 2.120's default OCR engine is RapidOCR**, whose
bundled language packs have no dedicated Vietnamese model, and the generic
`latin` pack does not reliably handle Vietnamese tone marks. This repo
therefore configures **EasyOCR** (`EasyOcrOptions(lang=config.ocr_languages)`)
and declares `easyocr` explicitly in the `[docling]` extra. First run
downloads ~1.5 GB to `DOCLING_ARTIFACTS_PATH` / `HF_HOME`; prefetch with:
```bash
python -m docling.cli.tools models download -o .cache/docling
python -m docling.cli.tools models download easyocr --easyocr-lang en --easyocr-lang vi -o .cache/docling
```

**Measured on CPU**: ~15 s for a 1-page PDF; ~35 s per page on the
render+layout+OCR path.

**Weaknesses**: its public per-page component API is not designed for
"call layout and OCR separately, cheaply". `DoclingBackend.analyze()` /
`.recognize()` work around this by feeding single rendered page images
through the ordinary `convert()` entrypoint and caching the result, so the
first of the two calls pays for the whole per-page conversion. Text items
are block/line granularity, not OCR word tokens.

**License**: MIT.

## Table Transformer — Validated locally

**Purpose**: table detection + structure on **rendered** pages
(`microsoft/table-transformer-detection` and
`-structure-recognition` via `transformers`).

**Install**: `pip install -e ".[tables]"` (just `transformers` + `torch`).

**Measured on CPU**: ~6–7 s per page (both models). ~110 MB downloaded to
`HF_HOME` on first use.

**Weaknesses**: geometry only — it never produces text. Cell text is filled
afterwards by matching OCR tokens to cell bboxes
(`pipelines/base._fill_table_cell_text`), so a page with weak OCR yields
empty cells; that is an OCR failure, not a Table Transformer failure.

**License**: `transformers` Apache 2.0; model weights MIT per the model cards.

## MinerU — Optional / not installed

**Purpose**: alternative whole-document backend (layout + OCR + tables +
formulas), a common comparison point against Docling.

**Why not installed here**: the pip package name has moved between
`magic-pdf` (pre-1.0) and `mineru` (1.0+), so a version pin in this repo
would likely be wrong by the time anyone uses it — check upstream at install
time. Model weights run to multiple GB, which was not a reasonable
opportunistic download in this environment.

**Install**: verify the current package name and quickstart on the MinerU
GitHub repo, update the pin in `pyproject.toml`, then
`pip install -e ".[mineru]"`, and point its model cache at `.cache/`.

**License**: **AGPL-3.0** — verify against the current release before
depending on it beyond research use. More restrictive than Docling's MIT.

**Current behaviour**: `MinerUBackend.is_available()` returns `False`;
`.convert()` raises `BackendUnavailableError` naming `docs/backends.md`.
The module imports cleanly without MinerU installed (covered by tests).

## PaddleOCR / PP-Structure — Optional / not installed

**Purpose**: alternative OCR + layout + table-structure backend, notable for
strong multilingual OCR and a mature table pipeline.

**Why not installed here**: PaddlePaddle is a second deep-learning framework
alongside the torch stack already present — a large unrelated download — and
has a history of Windows install friction (Visual C++ redistributable
requirement, numpy pin conflicts).

**Install**: `pip install -e ".[paddle]"`, then confirm
`paddle.utils.run_check()` passes before relying on it; that command
surfaces the VC++ redistributable problem explicitly.

**License**: Apache 2.0.

**Current behaviour**: `PaddleOCRBackend` implements all three component
Protocols plus `WholeDocumentBackend`; every method raises
`BackendUnavailableError` until installed.

## Document VLM — Planned

**Purpose**: a locally-deployable document VLM (PaddleOCR-VL, MinerU-VLM, or
a Qwen2-VL-class model) as a qualitatively different comparison arm.

**Why nothing ships**: a usable document VLM needs several GB of VRAM. This
environment has no usable CUDA at all. Shipping an integration nobody here
can execute would be worse than documenting the gap honestly.

**What implementing it involves**: `backends/vlm_backend.py` defines the
`WholeDocumentBackend`-shaped stub. A real implementation adds its deps to
the `[vlm]` extra, loads the model once in `__init__`, and adapts its output
into the canonical IR the way `docling_backend.py` does.

**Current behaviour**: `is_available()` always returns `False`; `.convert()`
raises `BackendUnavailableError` explaining why.

## Choosing a backend

| `run --backend` | What runs |
|---|---|
| `baseline` (default) | This repo's modular pipeline: native parsing + native tables, with Docling/Table-Transformer on the visual route |
| `docling` | Docling's whole-document `convert()` |
| `mineru` / `paddleocr` / `vlm` | Raises `BackendUnavailableError` until installed per this page |

`compare --backends` accepts the same names plus `baseline`. Component
backends (`table_transformer`, `pymupdf_tables`) are exercised *inside* the
baseline route and are not standalone whole-document arms.
