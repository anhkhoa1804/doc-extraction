# Output format

## Schema version

Every serialized `Document` carries a `schema_version` (currently
**1.1.0**). Bump it whenever the serialized shape changes in a way a
consumer could notice; the change history lives in
`src/doc_extraction/schemas/version.py`. A result file found on disk months
later can then be interpreted — or rejected — without guessing which
revision of the code produced it.

## Directory layout

Every run writes to `outputs/<document_id>/`, never next to the input file:

```
outputs/<document_id>/
  metadata.json       # RunMetadata — see below
  logs/pipeline.jsonl # one JSON line per stage invocation
  rendered/           # page-NNN.png — only pages that actually needed pixels
  layout/             # per-page LayoutResult JSON   (visual route only)
  ocr/                # per-page OCRResult JSON      (visual route only)
  tables/             # per-page TableResult JSON    (all routes with tables)
  assembled/          # per-page Page JSON, all routes
  final/
    document.json     # the full canonical Document
    document.md       # human-readable Markdown export (lossy)
  inspection/
    index.html        # written by `doc_extraction inspect`
```

Note that `rendered/` may contain only *some* pages: the digital-PDF route
renders individual pages on demand when they fail text-quality checks (see
[architecture.md](architecture.md)), rather than all-or-nothing.

`document_id` is `<slugified filename stem>-<first 8 hex chars of sha256>`
(`utils/ids.py`). The hash suffix makes re-runs land in the same directory
(reproducible) while two different files sharing a name cannot collide.

## `metadata.json` (`schemas.document.RunMetadata`)

```json
{
  "input_filename": "FROGSLEAP_BUSINESS LICENSE.pdf",
  "input_path": "FROGSLEAP_BUSINESS LICENSE.pdf",
  "file_hash_sha256": "536811a9...",
  "file_type": "pdf",
  "route": "scanned_pdf",
  "route_reason": "text layer present (100% of sampled pages) but 100% of sampled pages fail text-quality checks (> 34%) — likely broken font CMap; routing to the visual/OCR path",
  "text_profile": {
    "page_count": 2,
    "sampled_pages": [0, 1],
    "text_page_ratio": 1.0,
    "suspicious_page_ratio": 1.0,
    "per_page": { "0": { "mixed_script_word_ratio": 0.4, "suspicious": true, "reasons": ["..."] } }
  },
  "pipeline": "baseline",
  "backend": "baseline",
  "model_versions": { "doc_extraction": "0.1.0", "pymupdf": "1.28.2", "docling": "2.120.3" },
  "config_snapshot": { "...": "the full PipelineConfig used for this run" },
  "timestamp": "2026-08-20T12:00:00+00:00",
  "runtime_seconds": 74.09,
  "device": "cpu",
  "errors": [],
  "warnings": ["page 1: SUSPECT native text retained: ..."]
}
```

`route_reason` and `text_profile` record *why* a file took the route it did,
including the per-page evidence. `config_snapshot` is the entire resolved
config, and is machine-independent (`cache_dir` is relative), so a run can be
reproduced from the metadata alone.

## Canonical document (`schemas.document.Document`)

```
Document
 ├── schema_version: str
 ├── document_id: str
 ├── metadata: RunMetadata
 ├── assets: dict[str, str]
 └── pages: list[Page]
      ├── index: int                  # 0-based position; ALWAYS defined
      ├── width / height: float
      ├── dpi: int | None             # set for rendered pages
      ├── coordinate_unit: "pt" | "px" | "emu" | "none"
      ├── coordinate_origin: "top-left"
      ├── is_rendered_page: bool      # False for DOCX bodies / XLSX sheets
      ├── source_route / source_backend: str | None   # provenance
      ├── notes: list[str]            # per-page warnings & quality verdicts
      ├── rendered_image_path: str | None
      ├── elements: list[Element]
      ├── tables: list[Table]
      └── reading_order: list[str]    # Element.id, in reading order
```

### Page numbering semantics — nullable, never fabricated

Two distinct notions, deliberately not conflated:

* **`Page.index`** — 0-based position within `Document.pages`. Always
  present. This is a list position, *not* a claim about rendered pages.
* **`Element.page_number` / `Table.page_number`** — the 1-based **rendered**
  page number, or **`None`** when the source format does not define one
  without being rendered.

`None` means *unknown*, and is used rather than defaulting to 1:

| Format | `is_rendered_page` | `page_number` |
|---|---|---|
| PDF (either route) | `True` | 1-based page |
| PPTX | `True` | 1-based slide |
| XLSX | `False` | 1-based sheet |
| **DOCX** | `False` | **`None`** |

DOCX page breaks are computed by a renderer from fonts, margins and
widow/orphan rules; python-docx cannot know them. Claiming "page 1" would
silently corrupt any downstream analysis keyed on page number, so the field
is null and `Page.notes` says why.

### Coordinate convention

Uniform across **every** backend — a consumer never has to ask which
convention produced a box:

* **Origin**: top-left of the page.
* **+x** right, **+y** down.
* `x0 <= x1` and `y0 <= y1` always; `(x0, y0)` is top-left, `(x1, y1)` is
  bottom-right.
* **Units**: `Page.coordinate_unit` — `pt` (PDF points), `px` (pixels in the
  rendered image at `Page.dpi`), `emu` (PowerPoint English Metric Units), or
  `none` (DOCX/XLSX, which expose no spatial geometry).

Backends whose native output uses a bottom-left origin (some PDF and Docling
coordinates) convert on the way in — see `_bbox_from_docling` in
`backends/docling_backend.py`.

### Element

| Field | Meaning |
|---|---|
| `id` | Unique within the document (`p<page_index>-e<n>`); stable across serialization |
| `type` | `text \| heading \| paragraph \| list_item \| table \| image \| formula \| checkbox \| signature \| other` |
| `text` | Extracted/recognized text; `None` for non-text elements |
| `bbox` | See coordinate convention above, or `None` |
| `page_number` | 1-based rendered page, or `None` (see above) |
| `confidence` | `0..1` where the source backend provides one, else `None` |
| `source_backend` | e.g. `native-office`, `pymupdf-native`, `pymupdf_tables`, `docling`, `table_transformer` |
| `source_id` | Backend-specific identifier where meaningful (e.g. an image xref) |
| `parent_id` | Reserved for section nesting; unset today |
| `order_index` | Position in the order the backend emitted elements, before reading order was computed |
| `level` | Heading level / list depth, where known |
| `table_id` | Set when `type == table`; look up in the owning `Page.tables` |
| `extra` | Backend-specific extras (e.g. `sheet_name` for XLSX) |

Tables are **not** nested inside `Element`: a table element carries only
`table_id`, and the full `Table` lives in `Page.tables`. This keeps `Element`
flat and avoids a circular element↔table reference.

### Table

```
Table
 ├── id, bbox, page_number, source_backend, confidence
 ├── n_rows, n_cols
 └── cells: list[Cell]
      ├── row, col (0-based)
      ├── row_span, col_span
      ├── bbox: BBox | None
      ├── text
      └── is_header
```

`Table.to_grid()` materializes a dense `n_rows × n_cols` text grid (spanned
cells repeat into every covered position); `.to_markdown()` renders that.

**Span support differs by backend, and this is visible in the data:**

| Backend | `col_span` | `row_span` | Cell text |
|---|---|---|---|
| `native-office` (DOCX/XLSX/PPTX) | yes | yes | yes |
| `pymupdf_tables` (digital PDF) | yes | **always 1** — not recoverable | yes |
| `table_transformer` (visual) | grid only | grid only | filled from OCR tokens |

PyMuPDF's table finder treats rows independently and does not mark vertical
merges, so a vertically merged cell appears as one populated cell plus empty
cells beneath it. This is documented rather than papered over — see
`backends/pymupdf_table_backend.py`.

## Stage intermediates

`layout/page-NNN.json`, `ocr/page-NNN.json`, `tables/page-NNN.json` hold the
raw `LayoutResult` / `OCRResult` / `TableResult` dataclasses from
`pipelines/base.py`, **before** they are merged into the canonical
`Page`/`Element`/`Table` shapes in `assembled/`. Keeping both is the point: a
failure in the merge step is then distinguishable from a failure in the
backend call that produced the raw regions.
