# Untrusted-document security review

Review date: 2026-10-01. Baseline: `48445ea3f276df2430075883cf37e175a0b9c8d0`.
This is a code/test audit of the Linux production entry point, not a security
certification or a parser sandbox. Research remains closed.

## Threat model and execution boundary

Uploaders control bytes, basenames, extensions, PDF metadata/actions, Office
member names/content types/relationships, XML, image headers, and extracted
text. A mutable submitted file can change while a request is running.
Uploaders must not control service configuration, PATH, executables, Python
imports, model checkpoints/caches, output-root ownership, or arbitrary local
input paths. Configuration and the explicit API output directory are operator
authority. A service wrapper must authorize input paths before calling this
library: this extractor is not an arbitrary-path access-control system.

`cli.process_file` and CLI `run`/`compare` are the guarded boundary. Low-level
Office/PDF parsers and backend methods are internal and assume validated input;
calling them directly bypasses preflight. Operator diagnostics are not upload
APIs. Historical evaluator subprocesses are not in the production route.

Data flow:

1. One open regular file -> size-bounded, private snapshot (0700/0600).
2. Snapshot -> content/header, PDF count, streamed ZIP/XML/image preflight.
3. Snapshot -> route -> native Office/PyMuPDF or configured visual backend.
4. Rendered RGB images -> OCR/layout/table -> canonical assembly.
5. Private output tree -> descriptor-anchored atomic writes; one writer per run.
6. Escaped/bounded operational messages; separate extracted content artifacts.

No document text is passed to a shell, evaluated as Python, used to choose a
dynamic import, or used as an executable name in application code. Backend
choice is an explicit operator enum/factory. Tesseract receives an argv list;
its absolute input path refers to a generated image, not a document token.

## Concrete findings and fixes

Severity describes actual reachability; conditional local filesystem attacks
are not claimed to be remote-code execution through an ordinary upload.

### F1 — Output symlink overwrite (HIGH, conditional local attacker)

Affected path: JSON/Markdown/stage/log writers. Attacker-controlled input:
pre-existing output-file or parent-directory symlinks. Failure: `open("w")`
followed the link and overwrote a separate file; directly reproduced with a
small victim file. Exploitability requires control of the output filesystem.
Fix: `utils/safe_io.py` traverses with directory descriptors and `O_NOFOLLOW`,
refuses non-regular/multi-link targets, writes private random temporary files,
and replaces relative to the retained descriptor. Logs use no-follow append.
Regression: API tests cover metadata/log/assembled/final symlinks, directory
escape, target replacement between open/commit, and parent replacement during
a write. Victims remain unchanged; no file appears in the external directory.
Residual: output trees must be service-owned. This is not a same-UID sandbox;
pre-existing directory permissions are not repaired automatically.

### F2 — Validation/consumption race (MEDIUM)

Affected path: preflight -> hashing -> routing -> parser reopens. Input: a
mutable submitted pathname. Failure: replacement after validation changes what
is parsed. Fix: `snapshot_input` copies one opened regular file under size/time/
temporary budgets; all later reads use it. `compare` also uses a bounded
snapshot before hashing for directory naming. Regression: overwrite the source
inside the route hook and assert the original document is parsed; reject FIFO
input without waiting for a writer; forbid hashing an oversized comparison.
Residual: concurrent writes to the same opened source inode can produce an
inconsistent copy, but that copy itself is validated and hashed before parsing.

### F3 — Ambiguous ZIP names and incomplete preflight (LOW policy gap)

Affected path: `_check_archive`. Input: Windows-drive paths, duplicate names,
NFC/separator-normalized collisions, local-header inconsistencies. Failure:
the old checker accepted `C:/...` and duplicate XML members and trusted only
central metadata. No filesystem extraction exploit was demonstrated: the
application reads ZIP members, never `extract`/`extractall`. Fix: reject these
names and encrypted members; stream every member to verify headers/CRC/actual
size before any backend consumes it. Regression: API rejection matrix covers
these attacks, traversal/UNC/ADS, symlink entries, expansion/member/ratio quotas,
and a corrupt local header. Nested ZIP payload remains opaque and inert.
Residual: ZIP central-directory construction allocates inside Python before
member counting; the input-size cap is not a hard RSS cap.

### F4 — Hard limit swallowed by PDF fallback (HIGH availability)

Affected path: `_apply_page_fallback`. Input: a native PDF with a broken text
layer that invokes visual fallback. Failure: `ResourceLimitExceeded` became
retained native text plus a warning, bypassing the hard-failure contract.
Fix: propagate resource and unsafe-output exceptions. Regression: a real
broken-CMap fixture with a tiny raster limit fails via `process_file`; metadata
identifies `max_image_pixels`, never `success_with_warnings`.
Residual: other in-process library failures can still produce documented
degraded fallback; deadlines cannot interrupt arbitrary C/model code.

### F5 — Implicit image converter and embedded pixel-limit gap (MEDIUM)

Affected path: unrestricted Pillow opening and dependency image decoding.
Input: EPS disguised as a raster input, or an OOXML declared image with huge
dimensions. Failure: Pillow EPS loading can hand content to Ghostscript;
Docling 2.124.0's Office handlers open image bytes unrestricted and save/load
them, while openpyxl also opens drawing-image bytes. Standalone pixel preflight
did not cover those embedded images. Fix: whitelist PNG/JPEG/TIFF/BMP/GIF at
public preflight and rendering; inspect declared OOXML image parts before
dependency decoding; enforce dimensions and verification. Regression: tiny
malformed/truncated/EPS and huge-BMP fixtures fail before route/model creation,
including nonstandard `.bin` parts declared as images.
Residual: this explicitly rejects vector Office images. It does not audit all
dependency-internal format support, falsely declared part relationships, or
native PDF compressed-image/object allocation. Use isolated workers.

### F6 — OCR capture exhaustion and swallowed timeout (MEDIUM availability)

Affected path: Tesseract subprocess capture. Input: a document that causes a
large or slow OCR result. Failure: `capture_output=True` retained unlimited
stdout/stderr; timeout returned an empty OCR result instead of a hard failure.
Fix: `run_bounded` drains both pipes under a combined 16 MiB configurable cap
and real deadline, kills only its newly created process group, reaps the direct
child, closes pipes, and propagates the hard violation. Language probing also
has a 1 MiB output cap. Regression: literal shell-looking argv creates no
marker; oversized output fails; a child/grandchild timeout prevents a delayed
marker; both hard OCR cutoffs produce `failed` at the public API.
Residual: trusted executables/PATH/environment are prerequisites. A child that
creates another session can escape the group. Descendant zombie reaping is an
OS/init responsibility; no process-tree sandbox is claimed.

### F7 — Report HTML/Markdown and CSV interpretation (MEDIUM operator browser)

Affected path: failure-report filenames, HTML index, Markdown tables, inspector
image attribute, and diagnostic CSV. Input: document filename/identifier/text.
Failure: a filename containing an HTML tag was interpolated into the report;
identifier paths could leave report subdirectories. Fix: escape display markup,
slugify bounded generated names, escape attributes, and apostrophe-prefix CSV
strings beginning with common spreadsheet formula markers. Regression: a real
DOCX with a tag-like filename and malicious canonical IDs cannot create a file
outside the report root or inject a raw tag; formula text stays inert in CSV.
Residual: reports intentionally contain sensitive extracted text; do not host
them publicly. Canonical JSON/Markdown content remains unchanged and untrusted;
downstream rendering must apply its own escaping. Slug collisions are possible
in diagnostic names; reports are not authoritative content identities.

### F8 — Terminal/log control injection (LOW)

Affected path: CLI filenames/errors and stage diagnostics. Input: newline,
escape, format-control characters and long exception messages. Failure:
terminal output accepted source control sequences. Fix: bounded escaped
operational strings; JSONL still uses JSON encoding, not string concatenation.
Regression: a filename with newline and ESC produces visible escapes, not a
terminal control sequence. Residual: escaping is not PII redaction; error
messages and filenames may be sensitive. Private diagnostic storage and access
policy are required; canonical text is not sanitized.

### F9 — Competing writers and stale success publication (MEDIUM integrity)

Affected path: deterministic run-directory reuse and assembly failure. Input:
simultaneous/repeated processing of the same destination. Failure: workers
could overwrite each other's metadata; a failure after assembly left a
successful canonical JSON behind. Fix: nonblocking per-run `flock` covers both
normal and failed preflight writes; ordinary failed runs unpublish only the
generated final JSON/Markdown, retaining intermediate diagnostics. Regression:
competing writers, including an oversized rejected input, cannot overwrite an
active sentinel; a failure injected after real assembly leaves failed metadata
and no successful final artifacts. Locks/snapshots/atomic files clean up on
Python-managed exits. Residual: unsafe destinations cannot receive metadata;
process kill can leave temporary files. Published outputs require metadata and
successful call/CLI result, not mere filename existence.

## Verified parser/subprocess scope

Audited versions: Python 3.10; PyMuPDF 1.28.2; Pillow 12.3.0; python-docx 1.2.0;
python-pptx 1.0.2; openpyxl 3.1.5; lxml 6.1.3; defusedxml 0.7.1;
Docling 2.124.0. These are the audit environment, not universal safe versions.

Installed python-docx and python-pptx explicitly set `resolve_entities=False`.
openpyxl uses a no-entity lxml parser and defusedxml where installed. The public
boundary additionally rejects DTDs in filename/declared XML parts, including
UTF-16. File/http entities and an expansion payload are tested on actual DOCX,
XLSX, and PPTX packages; routing is asserted not to occur. No blanket XML library
vulnerability is claimed. Package relationships are read as data; native
Office routes do not fetch external hyperlinks or execute macros.

PyMuPDF is used in PDF preflight, route/text inspection, native extraction,
native table finding, and rasterization. Application code invokes no JavaScript
engine, link-opening operation, embedded-file extraction, or external renderer.
A native PDF containing a URI link and traversal-named embedded attachment is
processed without extracting the attachment. This is not proof against all
malicious MuPDF binary inputs: compressed objects and native allocations remain
parser attack surfaces. Raster allocations use conservative rounded dimensions
and explicit RGB/no alpha; huge page geometry fails the raster guard.

Pillow bomb warnings/errors remain enabled. Header verification and dimension
checks happen before model creation; malformed raster data fails explicitly.
In-process decode/model calls are not hard-cancellable. Embedded or multi-frame
content not visited by the supported route has no completeness guarantee.

No production application call uses `shell=True`, `os.system`, or `os.popen`.
Tesseract has bounded group-owned capture; GPU probing uses fixed nvidia-smi
argv and a timeout; environment diagnostics invoke fixed Docker argv. Those
operator probes still trust installed executables and capture their output in
memory. The historical OmniDocBench wrapper takes operator paths/cwd/environment
and uses argv, not source text; it is not an upload execution path. Dependency
converters/model provisioning require separate deployment control, not an
application-wide no-subprocess/no-network claim.

## Dependency advisory and distribution gates

An ephemeral `pip-audit` scan of the installed environment found urllib3 2.7.0
affected by CVE-2026-97687, -97688, and -97689. Only urllib3 was updated, to 2.8.0;
the Docling extra now requires that floor and the lockfile records it. Upstream
advisories describe the [streamed-deflate hang](https://github.com/urllib3/urllib3/security/advisories/GHSA-gh4c-6fx4-qh6g),
[chunk-header allocation](https://github.com/urllib3/urllib3/security/advisories/GHSA-vxq7-64xx-v4gw),
and [proxy TLS issue](https://github.com/urllib3/urllib3/security/advisories/GHSA-8988-9cw3-xx77).

After that update, the installed-environment scan still reports Accelerate
1.14.0, [CVE-2026-69112 / GHSA-4j2p-28q2-5m79](https://github.com/advisories/GHSA-4j2p-28q2-5m79),
with no listed fixed version: untrusted sharded checkpoint metadata can select
paths/FIFOs. Document bytes do not select checkpoints in this application;
model/cache files must be provisioned and owned by the operator, never accepted
from uploaders. This is a verified supply-chain/deployment gate, not a proven
document-triggered exploit. The audit skips the unpublished editable project
and does not assess OS libraries, bundled MuPDF code, every optional backend,
or future dependency resolutions. Pin/sync the reviewed lock for deployment.

Installed PyMuPDF metadata states AGPL-3.0/commercial dual licensing; upstream
[licensing documentation](https://pymupdf.readthedocs.io/en/latest/about.html#license-and-copyright)
confirms the options. Release/legal ownership must approve an explicit
compliance, commercial-license, or replacement decision before closed-product
distribution. This is not a code vulnerability or a legal opinion. No parser
replacement was made.

## Deployment requirements and remaining limits

* Hardened writes require Linux/POSIX `dir_fd`, `O_NOFOLLOW`, `flock`, and owned
  local process groups. Unsupported platforms fail closed, not insecurely.
* Service-owned upload/output/cache roots; authorize submitted input paths;
  trusted PATH, configuration, model provenance, and no uploader cache writes.
* External per-document worker RAM, wall-clock, disk and concurrency ceilings.
  Snapshot/raster quotas are not global disk limits; parser expansion, model
  caches, JSON/log artifacts, and native C/model runtime remain outside them.
* Provision models before handling untrusted input; restrict worker network
  access and optional converters. No OS sandbox is implemented here.
* Private managed `TMPDIR`; cleanup stale `doc-extraction-input-*` after worker
  termination using deployment ownership/lifecycle rules. No broad deletion
  command is provided. Persistent stages intentionally remain for diagnosis.
* Use a job-owned output root for isolation between requests. Legacy document
  directory IDs include only eight hash characters; they are not cryptographic
  authorization or uniqueness guarantees. Full source SHA-256 is in metadata.
* The authoritative ExtractionPackage v1 contract is identified, but producer
  adoption and real KP/CDOI validation remain unconfirmed as documented in
  `contract-adoption-audit.md`; internal security/conformance checks do not
  substitute for public-contract or KP consumer tests.

## Reproduction

Run `uv run pytest -q tests/test_security_boundaries.py`, then
`uv run ruff check src tests scripts`, `uv run pytest -q`, and `uv build`.
Tests use small controlled payloads, real native Office/PDF extraction, and
literal subprocesses/test doubles; they do not download models or use GPU.
Advisory scan: `uvx pip-audit --path .venv/lib/python3.10/site-packages
--format json --progress-spinner off` (tool is not a runtime dependency).

Final validation on this increment: **63 security tests passed**; full suite
**479 passed, 13 skipped**, no failures; Ruff passed; wheel and sdist built;
`git diff --check` passed. Three focused warnings are intentional duplicate-ZIP
fixture construction and two preserved Pillow bomb warnings. The full run also
reports five existing Torch/EasyOCR deprecation warnings. Below-limit native
format, schema, pipeline, CLI, and determinism regressions remain green.

A separate tiny traversal ZIP smoke test produced `ResourceLimitExceeded`,
`status=failed`, `archive_member_path` through the Python API and CLI (exit 1),
with no escaped file. Lockfile package-version comparison confirms only
urllib3 changed (2.7.0 -> 2.8.0); marker-list ordering also changed mechanically.
No historical artifact was deleted or moved. Failed-run cleanup applies only
to generated canonical publication files, not research evidence or source input.
