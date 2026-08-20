# 002 — Digital-PDF table structure

## Question

Phase 1 ran table-structure detection only on the scanned/image route.
Digital PDFs had their tables flattened into paragraph-shaped text blocks,
losing all row/column structure.

**How much table structure can be recovered from born-digital PDFs using
only the PDF's own vector ruling lines and text layer — no rendering, no
OCR, no model?**

The alternative (rendering every digital page and running Table Transformer
over it) costs seconds per page and needs an OCR pass to fill cell text.
If the native path works, it is orders of magnitude cheaper.

## Method

`src/doc_extraction/backends/pymupdf_table_backend.py` wraps PyMuPDF's
`find_tables()`, which keys on vector ruling lines and text alignment, and
maps the result onto the canonical `Table`/`Cell` IR. Merged cells are
recovered from PyMuPDF's `None` placeholders as `col_span`.

Run over all 10 unique PDFs at the repo root and count tables and cells.

## Reproduce

```bash
.venv/Scripts/python.exe -m doc_extraction run --input . --config configs/cpu.yaml
.venv/Scripts/python.exe scripts/build_failure_report.py --input outputs/
```

Table counts per document appear in `outputs/failure_report/documents.csv`;
every extracted table is dumped as CSV under
`outputs/failure_report/tables/`.

## Files

- `config.yaml` — config used
- `results.json` — per-document table/cell counts
- `observations.md` — findings and known limitations
