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
| `max_temp_bytes` | 512 MiB | before each PDF raster is written | reject the raster allocation |
| `max_image_pixels` | 40,000,000 | standalone image and PDF raster dimensions | reject before pixel allocation |
| `max_archive_members` | 10,000 | OOXML ZIP central directory | reject container |
| `max_archive_uncompressed_bytes` | 250 MiB | cumulative declared OOXML ZIP expansion | reject container |
| `max_archive_compression_ratio` | 100:1 | individual OOXML ZIP member | reject container |

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
```

## Failure behavior

A hard resource cutoff raises `ResourceLimitExceeded`, writes
`metadata.json` with `status: "failed"`, and records a structured
`resource_violation` containing `limit_name`, `limit`, `actual`, and
`detail`. It is never downgraded to `success_with_warnings`; no successful
canonical document is claimed. An oversized input is not hashed merely to
name its failed-run directory.

## Archive safety

DOCX, XLSX, and PPTX are ZIP containers. The preflight inspects their central
directory without extracting members, rejects traversal/absolute/symlink
entries, and applies member-count, declared-uncompressed-size, and
compression-ratio limits before `python-docx`, `openpyxl`, or `python-pptx`
opens the package. This service does not recursively extract nested archives.

## Runtime semantics and limitation

The deadline is enforced before and after route selection, page work,
layout/OCR/table stages, and canonical assembly. Tesseract receives the
remaining deadline directly as a subprocess timeout, which terminates that
child when it expires.

Docling, PyMuPDF, Pillow, and Office-library calls run in process. Python
cannot safely kill an arbitrary in-process C extension or model inference
without risking process corruption, so a call already in progress may run
until it returns; the run then fails at the next guard boundary and no later
page is started. Deployments requiring a wall-clock hard kill must run each
document in an isolated worker process with an external supervisor. This
repository does not claim that isolation today.

## Operator example

A 2 GiB PDF is rejected at `max_input_bytes` before hashing or PDF parsing.
A 500-page PDF below 100 MiB is rejected at `max_document_units` before page
extraction. Raising either limit is an explicit deployment choice in YAML.
