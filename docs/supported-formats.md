# Supported formats

This matrix describes the current production pipeline, not an aspirational
capability claim. `SUPPORTED` means covered by focused tests; `PARTIAL` means
the route exists with documented limitations; `UNSUPPORTED` means the CLI
rejects the input or no implementation exists.

| Format | Ingestion/text | OCR/layout | Tables | Locator/provenance | Status |
| --- | --- | --- | --- | --- | --- |
| Born-digital PDF | PyMuPDF native text, quality-gated | Per-page visual fallback when configured backend is available | Native ruled-table finder | PDF page + points | PARTIAL |
| Scanned PDF | Rendered page input | Docling component backends | Visual Table Transformer route | PDF page + pixels/DPI | PARTIAL |
| Raster image | Image route | Docling component backends | Visual Table Transformer route | Image-local pixels | PARTIAL |
| DOCX | Native `python-docx` objects | Not invoked | Native tables | Logical body; rendered page is null | SUPPORTED |
| XLSX | Native `openpyxl` cells | Not invoked | Sheet grid | Logical sheet locator | SUPPORTED |
| PPTX | Native `python-pptx` shapes | Not invoked | Native tables where exposed | Slide locator | SUPPORTED |
| Legacy DOC/XLS/PPT | Detected | Not invoked | Not invoked | Rejection reason | UNSUPPORTED |

All routes emit canonical `Document` output, route metadata, structured stage
logs, and warnings where degradation is known. Visual routes require optional
model dependencies and cached model artifacts; absence is a controlled backend
availability failure, not evidence that a document contains no text.
