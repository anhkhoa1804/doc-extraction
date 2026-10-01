# 045 — acquisition-time observation capture

This experiment runs the current scanned-image pipeline twice over the frozen
044 development population. A is uninstrumented; B supplies an opt-in
`ObservationLedger`. B captures backend-returned layout, OCR, and raw table
candidate objects before cell filling and before page merge, then records the
existing post-merge reconciliation view. It does not use persisted stage
artifacts as its observations.

The earliest practical common boundary is the component-backend interface:
`run_layout`, `run_ocr`, and `run_table` return result objects. For Docling,
these are near-raw public adapter results; its private upstream object graph
is intentionally not claimed as captured. Table cell candidate text is
captured before `_fill_table_cell_text` mutates it from OCR evidence.
