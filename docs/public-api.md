# Public API

## Supported entry points

* CLI: `doc-extraction run --input <file-or-directory> [--config <yaml>]`.
* Python: `doc_extraction.cli.process_file(path, config, output_root=...)`.

Both return or write the canonical `Document` defined in
[`output-format.md`](output-format.md). `compare` and `inspect` are operator
tools, not downstream interchange contracts.

## Inputs and outputs

Inputs are PDF, DOCX, XLSX, PPTX, or supported raster images. Format-specific
coverage is stated in [`supported-formats.md`](supported-formats.md).

For a successful extraction, `process_file` returns a `Document` and writes:

* `metadata.json` — route, configuration snapshot, versions, status, warnings,
  and errors;
* `final/document.json` — canonical serialized IR; and
* `final/document.md` — a lossy human-readable view.

`process_file` raises on failure after writing `metadata.json` with
`status="failed"` whenever the output directory can be established. The CLI
continues over sibling inputs and returns non-zero if any input fails.

## Compatibility

The canonical schema version is carried by `Document.schema_version`.
Consumers must preserve null semantics: unknown geometry, confidence, and
rendered page numbers remain null; logical OOXML locators must not be coerced
to PDF page numbers.

No authoritative ExtractionPackage v1 schema is available locally. This
repository therefore does not claim a substitute external contract. Future
KP/CDOI integration must supply that authority and adapt from `Document` at a
narrow public boundary.
