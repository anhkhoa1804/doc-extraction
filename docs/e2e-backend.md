# Optional E2E document backend

`paddleocr_vl` is an optional, whole-page document-parsing backend. The flow
remains `input artifact → backend → canonical Document → existing
serialization`; it does not introduce a downstream KP contract or alter the
canonical schema. The implementation currently accepts raster page images
only. It is an evaluation/integration backend, not the default production
route.

## Runtime and model identity

The adapter imports PaddleOCR lazily. Install it in an isolated environment
using the upstream PaddleOCR v1.6 pipeline requirements (PaddlePaddle GPU
3.2.1+ and `paddleocr[doc-parser]>=3.6.0` for the tested CUDA 12.6 stack).
The root `doc-extraction` environment does not acquire the Paddle runtime as a
dependency. The verified run used PaddlePaddle 3.2.1, PaddleOCR 3.7.0,
PaddleX 3.7.2, Python 3.12.14, and an NVIDIA L4. The model and layout weights
are resolved by PaddleX into its external model cache; their SHA-256 values
are recorded in benchmark run metadata when available. Model artifacts are
not committed.

The mapping preserves model-provided region text, labels, order, and valid
page-level boxes. HTML tables are mapped to canonical cells, including row and
column spans. The model does not provide cell boxes or confidence in the
consumed output; these remain null. An unparseable table is retained as text
with an explicit `E2E_UNSUPPORTED` page note. Coordinates are model input
pixels, top-left origin. The adapter does not synthesize confidence, page
numbers beyond the one-page raster locator, or missing geometry.

## Resource and failure behavior

Calls go through the existing `process_file` boundary, so existing file-size,
pixel, temporary-storage, and post-operation runtime checks still apply. The
backend does not resize/retile images to bypass the production pixel limit.
The Paddle pipeline executes in-process: the existing runtime limit is
checked after a backend call returns and therefore cannot interrupt a stuck
native/model inference. Hard cancellation of inference remains an isolation
release gate; this adapter does not claim otherwise. Backend exceptions are
recorded as extraction failures by the public processing path.

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

The model card recommends its page-level pipeline over its element-only
Transformers example; this implementation uses the page-level pipeline.
Official sources: [PaddleOCR-VL-1.6 model card](https://huggingface.co/PaddlePaddle/PaddleOCR-VL-1.6),
[PaddleOCR-VL pipeline documentation](https://www.paddleocr.ai/latest/en/version3.x/pipeline_usage/PaddleOCR-VL.html).
