# PaddleOCR-VL 1.6 isolated runtime manifest

This optional runtime is separate from the root project dependency graph. The
root `uv.lock` controls the extraction package; the following tested runtime
versions were installed into `.cache/e2e/paddleocr-vl-1_6-venv` and are not
committed as model/data artifacts:

```text
Python                         3.12.14
PaddlePaddle GPU               3.2.1 (CUDA 12.6 wheel)
PaddleOCR                      3.7.0
PaddleX                        3.7.2
NumPy                          2.3.5
Pillow                         12.1.0
Safetensors                    0.7.0
OpenCV contrib                 4.10.0.84
```

The environment was exercised on NVIDIA L4, driver 580.178.04. The Paddle
wheel reports CUDA 12.6; `nvidia-smi` reports driver CUDA compatibility 13.0.
No root `pyproject.toml` dependency was added for this backend.

Install into a separately created Python 3.12 environment using the upstream
CUDA wheel index and official pipeline dependency instructions:

```bash
python3.12 -m venv .cache/e2e/paddleocr-vl-1_6-venv
.cache/e2e/paddleocr-vl-1_6-venv/bin/python -m pip install \
  paddlepaddle-gpu==3.2.1 \
  --index-url https://www.paddlepaddle.org.cn/packages/stable/cu126/
.cache/e2e/paddleocr-vl-1_6-venv/bin/python -m pip install \
  'paddleocr[doc-parser]==3.7.0' 'paddlex==3.7.2'
```

The actual transitive package inventory is recorded at benchmark run time as
`pip freeze` metadata; its digest and key backend versions belong in the run
attestation. An exact offline package lock including CUDA wheel URLs/hashes is
not yet maintained. For strict environment recreation, preserve the generated
freeze output alongside the local run artifact and validate the wheel/index
provenance before deployment. Do not install this environment into the core
service image by default.

Weights are resolved into PaddleX's external model cache. The benchmark runner
records both model and layout weight SHA-256 before inference; the worker
rechecks hashes after model loading and rejects an identity mismatch.
