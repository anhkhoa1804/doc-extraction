# Optional E2E document backend

`paddleocr_vl` is an optional, whole-page document-parsing backend. The flow
remains `input artifact → backend → canonical Document → existing
serialization`; it does not introduce a downstream KP contract or alter the
canonical schema. The implementation currently accepts raster page images
only. It is an evaluation/integration backend, not the default production
route.

## Runtime and model identity

The parent adapter does not import PaddleOCR. It launches the current Python
interpreter as a persistent, single-purpose worker; that environment must
contain the optional runtime. The tested isolated environment used Python
3.12.14, PaddlePaddle GPU 3.2.1 (CUDA 12.6 wheel), PaddleOCR 3.7.0, PaddleX
3.7.2, and an NVIDIA L4. See
[`paddleocr-vl-environment.md`](../experiments/005_omnidocbench/paddleocr-vl-environment.md)
for the pinned runtime manifest. Model and layout weights are resolved by
PaddleX into its external cache; inference is refused unless their hashes can
be computed before the worker is started, and the worker verifies the same
hashes after loading. Weights are not committed.

The mapping preserves model-provided region text, labels, order, and valid
page-level boxes. HTML tables are mapped to canonical cells, including row and
column spans. The model does not provide cell boxes or confidence in the
consumed output; these remain null. An unparseable table is retained as text
with an explicit `E2E_UNSUPPORTED` page note. Coordinates are model input
pixels, top-left origin. The adapter does not synthesize confidence, page
numbers beyond the one-page raster locator, or missing geometry.

## Resource and failure behavior

Calls go through the existing `process_file` boundary. Input-byte, image-pixel,
and temp-reservation checks happen in the parent before worker launch. One
persistent worker is loaded lazily and reused for pages; it runs in a new POSIX
session, receives only the input snapshot path/hash for each request, and
returns a length-bounded JSON page over a dedicated protocol pipe. Worker
stdout/stderr are not forwarded into protocol or logs. A timeout kills the
worker process group, waits for it, verifies that the group is gone, then
removes its private scratch directory. The next page starts a new worker.
Startup/model load on the first page, preprocessing, inference, output mapping,
and parent validation all consume that page's remaining `max_runtime_seconds`;
the model remains warm for subsequent pages. The private worker scratch folder
is monitored against the remaining `max_temp_bytes` budget and the worker has
a per-file `RLIMIT_FSIZE` ceiling. The scratch monitor is sampled while the
parent waits for protocol output; it is not a kernel-enforced aggregate
filesystem quota. PaddleX model-cache files are read-only inputs to this
policy and are outside per-run temporary storage.

Per-run backend timings are written separately at
`diagnostics/backend_phase_timings.json`; they are not added to the canonical
`Document` schema. Timed boundaries include worker startup/initialization,
weight attestation, input hashing, the public `pipeline.predict()` call,
result JSON decoding, table parsing, canonical mapping/validation, page
serialization, parent roundtrip, and timeout cleanup. Paddle's public
`predict()` call combines internal image preprocessing, model inference, and
internal decoding; those phases are deliberately reported as one opaque
interval, not guessed sub-timings. The parent roundtrip residual also includes
serialization, IPC, and scheduling overhead, so it is not a pure transport
measurement.

This is process isolation and hard cancellation, not an OS sandbox: the worker
runs under the service account and can read files that account can read. The
adapter does not pass it output paths, run metadata paths, or mutable policy
objects, but a compromised native/model runtime could still exercise the
account's ambient filesystem permissions. Deployments requiring filesystem
confinement need an OS container/sandbox policy. Use
`shutdown_paddleocr_vl_workers()` for explicit cleanup in long-lived Python
applications; CLI and benchmark runner close the worker at command completion,
and an `atexit` cleanup is registered as a final fallback.

## Security and licensing notes

The selected model card identifies PaddleOCR-VL-1.6 weights as Apache-2.0 and
distributes safetensors. The official PaddleOCR pipeline is used instead of
loading arbitrary pickle checkpoints or enabling an unreviewed remote-code
path. Package and model license notices still require deployment-level
review. This research baseline does not make a closed-product distribution
claim; the repository's existing PyMuPDF licensing release gate remains
separate.

## Evaluation status

The benchmark adapter uses the frozen OmniDocBench representative-v2 sample
manifest and the pinned evaluator. Per-page `Document` output is serialized
through the same canonical OmniDocBench adapter as the classic backend. The
result measures this complete mapping path, not a vendor-reported model-card
score. See `benchmarks/reports/omnidocbench/e2e-pretrained-v1.md` for the
run, metric denominators, limitations, and comparison.

The later runtime-analysis pass added phase timing and preserved the v2
timeout/regression cases. Its v3 smoke, determinism, performance preflight, and
full rerun are explicitly recorded as blocked/not run when the shared L4 is
occupied; instrumentation alone does not establish a new paired baseline.

The model card recommends its page-level pipeline over its element-only
Transformers example; this implementation uses the page-level pipeline.
Official sources: [PaddleOCR-VL-1.6 model card](https://huggingface.co/PaddlePaddle/PaddleOCR-VL-1.6),
[PaddleOCR-VL pipeline documentation](https://www.paddleocr.ai/latest/en/version3.x/pipeline_usage/PaddleOCR-VL.html).
