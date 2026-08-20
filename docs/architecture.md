# Architecture

## Pipeline

```
input documents
    -> file/type detection            ingest/classifier.py
    -> route selection                ingest/dispatcher.py   (quantity + quality gates)
    -> format-specific parsing        pipelines/office.py, pipelines/pdf.py
    -> table structure                stages/table.py        (native or visual backend)
    -> PDF/image rendering (if any)   stages/render.py       (whole doc, or one page)
    -> OCR (if needed)                stages/ocr.py
    -> layout analysis                stages/layout.py
    -> reading order                  stages/reading_order.py
    -> assembly / export              stages/assemble.py
    -> canonical structured document  schemas/document.py
```

Every stage writes its own intermediate artifact to
`outputs/<document_id>/<stage>/` (see [output-format.md](output-format.md)).
There is no single `extract()` call: `cli.py`/`pipelines/*.py` orchestrate
stages, but each stage is independently callable and independently
inspectable.

## Routing: quantity *and* quality

The central design decision of this pipeline. "Does this PDF have a text
layer" is not the same question as "is this PDF's text layer usable", and
conflating them produces the worst available failure mode: confident,
plentiful, wrong output that nothing downstream can detect.

```
PDF
 │
 ├─ quantity gate ── too little text ────────────────► scanned_pdf (render + OCR)
 │
 ├─ quality gate ─── text present but mostly corrupt ─► scanned_pdf (render + OCR)
 │                   (broken font CMap, symbol soup)
 │
 └─ passes both ────────────────────────────────────► digital_pdf (native)
                                                        │
                                                        └─ per-page quality check
                                                           └─ bad page? render + OCR
                                                              that page only
```

`ingest/text_quality.py` implements the quality assessment: word-level
script mixing, unexpected-script ratio, replacement/control characters,
alphabetic ratio, and digit-in-word ratio. All are computed from
already-extracted text — no rendering, no OCR, no model — so the check is
cheap enough to run on **every page**, which is what makes the per-page
fallback affordable. The signals, their thresholds, and their limitations
are documented in that module and calibrated in
[experiments/001_pdf_text_quality](../experiments/001_pdf_text_quality/).

The per-page fallback is the pipeline's one piece of genuinely adaptive
computation: on the sample corpus, a 40-page document had 2 bad pages, so
2 pages were rendered and OCR'd while 38 took the near-free native path.

When no OCR backend is available, a suspicious page is **kept with its
native text and explicitly marked** in `Page.notes` (`SUSPECT ...`) and in
`metadata.json`'s `warnings`. It is never silently presented as trustworthy.

## Two ways to produce a Document

The same canonical IR is populated by two paths:

### 1. The baseline modular pipeline (`run`, default `--backend baseline`)

This repo's own composition of swappable stages (`pipelines/base.py` defines
the `LayoutBackend` / `OCRBackend` / `TableBackend` Protocols):

* **native_office** (DOCX/XLSX/PPTX) — parsed directly from each format's
  object model. No rendering, no OCR. See `pipelines/office.py` for the
  pagination semantics each format supports.
* **digital_pdf** — text blocks from PyMuPDF's text layer, **plus table
  structure from PyMuPDF's native table finder** (vector ruling lines + text
  positions). Still no rendering and no OCR: on the sample corpus this
  recovers 33 tables across the digital PDFs in well under a second each.
  Text falling inside a detected table is removed from the loose-text
  elements so table content is not duplicated in the IR.
* **scanned_pdf / image** — `stages/render.py` rasterizes, then
  `pipelines/base.run_scanned_page_pipeline` runs layout + OCR (Docling) and
  table structure (Table Transformer) and merges the results.
* `stages/reading_order.py` is **our own** geometric baseline, deliberately
  independent of whatever ordering a backend supplies — you cannot study
  reading-order disagreement if the only ordering available comes from the
  system under study.
* `stages/assemble.py` builds the canonical `Document` and writes
  `assembled/` and `final/`.

### 2. Whole-document backends (`compare`, or `run --backend <name>`)

`backends/docling_backend.py`, `mineru_backend.py`, `paddleocr_backend.py`,
`vlm_backend.py` each run their own library's complete pipeline and adapt the
result into the same canonical IR, tagged with `source_backend`. Where a
backend has its own reading order (Docling does), it is preserved as-is
rather than recomputed — the point is to diff it against ours.

`baseline` is available as a `compare` arm too: this repo's pipeline is one
system under comparison, not a privileged reference.

## Table backends: native vs visual

| Route | Backend | Cost | Spans | Cell text |
|---|---|---|---|---|
| digital_pdf | `pymupdf_tables` | ~50 ms/page, no model | col only | from text layer |
| scanned_pdf / image | `table_transformer` | ~6 s/page on CPU | grid geometry | from OCR tokens |

Using Table Transformer on a born-digital page would mean rendering it,
running two DETR models, and OCR-ing the cells to recover structure the file
already describes exactly. The native finder is the right default for that
route; the visual one is the fallback when there is no usable text layer.

## Known limitations (measured, not hypothetical)

* **Row spans are not recovered from digital PDFs.** PyMuPDF's finder treats
  rows independently. A vertically merged cell becomes one populated cell
  plus empty cells beneath it.
* **Borderless tables** laid out purely by tab stops are frequently missed by
  the native finder, and dense multi-column text is occasionally detected as
  a spurious table.
* **DOCX has no rendered pagination** without a layout engine; represented as
  one logical page with `page_number=None`. See
  [output-format.md](output-format.md).
* **Reading order is geometric only.** It detects column gutters and orders
  row bands, but has no notion of continuation. On the sample corpus this
  produces visible artifacts — see
  [experiments/004_reading_order](../experiments/004_reading_order/).
* **The quality gate cannot detect a CMap that maps Latin letters onto other
  plausible Latin letters.** Such text stays single-script and passes every
  signal. Detecting it needs a language model or an OCR cross-check.
* **OCR "tokens" from the Docling component backend are block/line
  granularity**, not word-level — Docling's stable public API exposes text
  items, not its internal word-level OCR results.

## Module map

| Module | Responsibility |
|---|---|
| `ingest/classifier.py` | Content-based file type detection (magic bytes + zip introspection; no libmagic dependency) |
| `ingest/text_quality.py` | Cheap, explainable assessment of whether extracted text is correctly decoded |
| `ingest/dispatcher.py` | Route selection using both quantity and quality evidence |
| `pipelines/office.py` | Native DOCX/XLSX/PPTX parsing |
| `pipelines/pdf.py` | Digital-PDF native parsing (+ native tables, + per-page fallback) and scanned-PDF orchestration |
| `pipelines/image.py` | Standalone image orchestration |
| `pipelines/base.py` | Backend Protocols + shared scanned-page merge logic |
| `stages/*.py` | One file per stage; thin orchestration + logging + intermediate-output writing around a backend call |
| `backends/*.py` | Concrete backends, or documented-unavailable stubs |
| `schemas/*.py` | Canonical IR (pydantic v2) + `schema_version` |
| `evaluation/metrics.py` | Descriptive per-document counts |
| `evaluation/disagreement.py` | Pairwise structural comparison between backends |
| `evaluation/compare.py` | Comparison report (JSON + HTML) |
| `evaluation/inspect_html.py` | Single-document HTML inspector |
| `utils/` | Hashing, IDs, structured stage logging, JSON (de)serialization |
