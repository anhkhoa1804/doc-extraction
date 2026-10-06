# Public API

## Supported entry points

* CLI: `doc-extraction run --input <file-or-directory> [--config <yaml>]`.
* Python: `doc_extraction.cli.process_file(path, config, output_root=...)`.

Both return or write the canonical `Document` defined in
[`output-format.md`](output-format.md). `compare` and `inspect` are operator
tools, not downstream interchange contracts.

Every `run`, `compare`, and `process_file` invocation is subject to the same
document resource policy. Defaults, YAML/Python overrides, archive defenses,
and timeout semantics are documented in
[`resource-limits.md`](resource-limits.md).

## Inputs and outputs

Inputs are PDF, DOCX, XLSX, PPTX, or supported raster images. Format-specific
coverage is stated in [`supported-formats.md`](supported-formats.md).

For a successful extraction, `process_file` returns a `Document` and writes:

* `metadata.json` — route, configuration snapshot, versions, status, warnings,
  and errors;
* `final/document.json` — canonical serialized IR; and
* `final/document.md` — a lossy human-readable view.

For baseline visual debugging, `PipelineConfig(visual_forensics=True)` also
requests a bounded, best-effort `diagnostics/classic_visual_trace.json` artifact.
This opt-in control does not enter canonical `config_snapshot` or change
extraction settings/schema. See [visual-forensics.md](visual-forensics.md) for
observed vs unavailable stages, privacy bounds and model-free reproduction.

`process_file` raises on failure after writing `metadata.json` with
`status="failed"` whenever the output directory can be established. The CLI
continues over sibling inputs and returns non-zero if any input fails.
`UnsafeOutputPath` is an exception to diagnostic publication: symlinked/
non-regular destinations and competing writers are rejected without writing
failure metadata through that path or overwriting the active writer.

Production output writes require Linux/POSIX directory descriptors,
`O_NOFOLLOW`, and `flock`; unsupported platforms fail closed. New output
directories are private (0700); files are 0600. Existing directory ownership
and permissions must be managed by the operator. Output roots and model
caches must not be writable by uploaders. See
[security-review.md](security-review.md) for tested guarantees and limitations.

## Compatibility

The canonical schema version is carried by `Document.schema_version`.
Consumers must preserve null semantics: unknown geometry, confidence, and
rendered page numbers remain null; logical OOXML locators must not be coerced
to PDF page numbers.

The internal canonical `Document` schema is version 1.4.0 and is distinct from
the authoritative CDOI `DocumentExtractionContract` 1.0.0 / ExtractionPackage
v1. This package's public API still emits only the internal Document; it does
not claim public-contract compatibility or produce the package. Adoption gaps
and the producer/KP confirmation checklist are recorded in
[`contract-adoption-audit.md`](contract-adoption-audit.md) and
[`cdoi-teammate-confirmation-checklist.md`](cdoi-teammate-confirmation-checklist.md).
