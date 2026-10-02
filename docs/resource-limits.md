# Resource limits and input safety

Each `doc-extraction` run has one `limits` policy. The CLI (`run` and
`compare`) and the documented Python API (`process_file`) use the same policy
before route selection and parser/model work begins. Configure it in the YAML
passed through `--config`, or construct `PipelineConfig(limits=...)` in
Python.

## Default policy

| Limit | Default | Protected boundary | Behavior when exceeded |
| --- | ---: | --- | --- |
| `max_input_bytes` | 100 MiB | before hashing, routing, or parsing | reject input |
| `max_document_units` | 100 | PDF pages, XLSX sheets, PPTX slides | reject before extraction |
| `max_runtime_seconds` | 300 s | route, page, stage, and assembly boundaries | fail at the next safe boundary |
| `max_temp_bytes` | 512 MiB | private input snapshot plus pipeline raster reservations | reject before copying/writing beyond the reservation |
| `max_image_pixels` | 40,000,000 | standalone raster, declared OOXML image, and PDF raster dimensions | reject before pixel decoding/allocation |
| `max_archive_members` | 10,000 | OOXML ZIP central directory | reject container |
| `max_archive_uncompressed_bytes` | 250 MiB | declared and streamed OOXML ZIP expansion | reject container |
| `max_archive_compression_ratio` | 100:1 | individual OOXML ZIP member | reject container |
| `max_ocr_output_bytes` | 16 MiB | combined Tesseract stdout/stderr while reading | terminate owned process group and fail |

The defaults bound a normal multi-page business document while preventing a
single request from allocating hundreds of megabytes of decoded raster or
unbounded OOXML XML. They are hard positive values: `null` does not mean
unlimited, and zero/negative configuration is rejected by Pydantic.

Example deployment override:

```yaml
limits:
  max_input_bytes: 52428800
  max_document_units: 50
  max_runtime_seconds: 120
  max_temp_bytes: 268435456
  max_archive_members: 5000
  max_archive_uncompressed_bytes: 134217728
  max_archive_compression_ratio: 80
  max_image_pixels: 20000000
  max_ocr_output_bytes: 8388608
```

## Failure behavior

A hard resource cutoff raises `ResourceLimitExceeded`, writes
`metadata.json` with `status: "failed"`, and records a structured
`resource_violation` containing `limit_name`, `limit`, `actual`, and
`detail`. It is never downgraded to `success_with_warnings`; no successful
canonical document is claimed. An oversized input is not hashed merely to
name its failed-run directory. Safe failed retries unpublish generated
`final/document.json` and `final/document.md`; intermediate diagnostics remain.
Unsafe output paths or an active writer are rejected without diagnostic
writes through that destination. Never infer success from an old artifact:
check run metadata and the call/CLI result.

## Archive safety

DOCX, XLSX, and PPTX are ZIP containers. The preflight inspects their central
directory without extracting members, rejects traversal/absolute/Windows-drive/
symlink entries, duplicate and NFC-normalized-colliding names, and encrypted
entries. It applies central-directory quotas, then streams members to verify
local headers, CRC, and actual expansion before any extraction backend opens
the package. DTDs are rejected in XML/relationship members and XML parts
declared by `[Content_Types].xml`, including non-XML filename extensions.
Declared image parts must be valid PNG/JPEG/TIFF/BMP/GIF within the pixel
limit. Unsupported vector/EPS image parts fail rather than invoking a
converter. This service does not recursively extract nested archives.

The source is opened once as a regular file and copied into a private,
bounded snapshot; validation, hashing, routing, and parsing use that snapshot.
Replacing the submitted path cannot substitute an unvalidated container.
The snapshot is removed on Python-managed exit, including errors. A hard
process kill requires deployment cleanup of stale temporary directories.

## Runtime semantics and limitation

The deadline is enforced before and after route selection, page work,
layout/OCR/table stages, and canonical assembly. Tesseract receives the
remaining deadline directly as a subprocess timeout. Combined stdout/stderr
is capped during reading; deadline or output-cap failure kills the owned
POSIX process group, reaps the direct child, closes pipes, and propagates a
hard failure. A descendant that deliberately starts a separate session is
outside this guarantee and requires worker isolation.

Docling, PyMuPDF, Pillow, and Office-library calls run in process. Python
cannot safely kill an arbitrary in-process C extension without risking process
corruption, so these calls may run until they return and then fail at the next
guard boundary. The optional `paddleocr_vl` backend is the exception: it runs
in a persistent child process/session, and the parent enforces the remaining
operation deadline by killing and verifying the owned process group. Its
private worker scratch directory is polled against the remaining temp budget;
this is not a kernel-enforced aggregate disk quota. Deployments needing hard
RSS or disk quotas still need an OS/container supervisor. A hard parent-process
kill requires deployment cleanup of stale temporary directories.

`max_temp_bytes` is not a filesystem-wide quota: it covers the input snapshot
and pipeline-generated raster reservations, not arbitrary parser caches,
model downloads, JSON/Markdown/log volume, or other workers. ZIP central
directory parsing itself and native PDF object-stream expansion have no
hard RSS ceiling. Set worker RAM, disk, wall-clock, and concurrency ceilings
externally; see [security-review.md](security-review.md).

## Operator example

A 2 GiB PDF is rejected at `max_input_bytes` before hashing or PDF parsing.
A 500-page PDF below 100 MiB is rejected at `max_document_units` before page
extraction. Raising either limit is an explicit deployment choice in YAML.
