# Observations — 002 Digital-PDF table structure

Run over the 12 files at the repo root (10 unique documents), CPU-only,
2026-08-20.

## Result: native table extraction recovers structure that was previously lost entirely

Phase 1 ran table detection only on the scanned/image route, so **every
digital PDF reported 0 tables**. With PyMuPDF's native table finder wired
into the digital route:

| Document | Route | Pages | Tables | Cells | Runtime |
|---|---|---|---|---|---|
| FROGSLEAP_COMPANY PROFILE.pdf | digital_pdf | 40 | 31 | ~120 | 3.5 s |
| FROGSLEAP_Impact_Module_TriAn_B2B_Sample.pdf | digital_pdf | 5 | 3 | 85 | 0.8 s |
| Partnership Proposal.pdf | digital_pdf | 8 | 2 | 126 | 0.8 s |
| GEP-2025-Proposal.docx.pdf | digital_pdf | 4 | 2 | 51 | 0.4 s |
| FROGSLEAP PARTNERSHIP PROPOSAL.pdf | digital_pdf | 9 | 0 | 0 | 0.7 s |
| [IE_GEP] 2025 Letter… .pdf | digital_pdf | 1 | 0 | 0 | 0.1 s |

Across the whole corpus (including native office): **~74 tables and ~1370
cells**, where phase 1 produced tables only from XLSX/DOCX.

## Cost

Table extraction adds roughly **20–70 ms per page** and requires no model
download, no rendering, and no OCR. The alternative — rendering each page and
running Table Transformer — measured **~6–7 s per page** on CPU for the same
job, plus an OCR pass to fill cell text.

That is roughly a **100× cost difference** for born-digital pages, which is
why the native finder is the default on the digital route and Table
Transformer is reserved for pages with no usable text layer.

## Cross-check against Docling

On `FROGSLEAP_Impact_Module_TriAn_B2B_Sample.pdf`, baseline and Docling
**agree exactly on table count** (3 vs 3, `table_count_delta = 0`) and are
close on cells (85 vs 80). Runtime differs sharply: 0.6 s vs 36.3 s.

Agreement between two independent implementations is meaningful evidence
that the tables are really there — though it says nothing about whether
either got the *contents* right, since neither was checked against ground
truth.

## Limitations confirmed in practice

* **Row spans are never recovered.** Measured across the 69 tables this
  backend produced on the digital route: **73 cells with `col_span > 1`, and
  exactly 0 cells with `row_span > 1`.** That is the documented limitation
  showing up exactly as predicted — PyMuPDF treats rows independently and
  does not mark vertical merges, so a vertically merged cell appears as one
  populated cell with empty cells beneath it. Table Transformer on a
  rendered page is the fallback when row spans matter. (For contrast, the
  native-office backend does recover both span directions.)
* **Two documents with 0 tables** (`FROGSLEAP PARTNERSHIP PROPOSAL.pdf`,
  9 pages) — not verified by hand whether those documents genuinely contain
  no tables, or contain borderless ones the finder misses. **This is the
  most important open question from this experiment** and is exactly the
  kind of silent miss the finder is documented as prone to.
* The 40-page deck yielding 31 tables on a slide-export PDF is suspicious in
  the other direction: slide layouts with aligned text boxes can be detected
  as spurious tables. Not yet checked by hand either.

## Follow-up worth doing

Manually label tables on ~10 pages spanning the corpus (including the two
zero-table documents) and measure precision/recall of the native finder
against that. Until then, the counts above establish that structure is being
recovered — not that it is being recovered correctly.
