# E2E Inference Isolation v2

Persistent supervised worker uses a private POSIX process group and bounded framed JSON IPC. On timeout the parent kills the owned process group, waits, verifies termination, cleans private scratch and rejects any result; next page gets a fresh worker. The worker is process-isolated, not an OS sandbox. Scratch aggregate usage is sampled rather than kernel quota-enforced.

The existing 300-second operation limit includes cold startup/model initialization, preprocessing, inference, postprocessing, IPC and parent validation. Wall time can include bounded teardown after the deadline. No policy override was introduced.

- Five-page smoke: 5/5 success, zero warnings, 270.481 s; diagnostic only.
- Twenty-page preflight: 20/20 success, zero warnings, exact GT alignment, 841.741 s; median 29.227 s/page, p95 81.964 s/page.
- Timeout fixture: 5 worker-specific tests pass; combined backend/worker suite 14 pass. Child process disappearance, process-group cleanup, scratch cleanup, timeout state, and restart tested.
- 180-page run: 178 success, two runtime timeouts; no worker remained afterward; L4 returned to 0 MiB.

Run `e2e-paddleocr-vl16-isolation-full180-v2-20261002T115500Z`; source snapshot `a65d5d7a2aa7e77071fc0ff678ec1dbcf4bc4b4e27081f69d8457fd2fdcb4638`; source HEAD `8eaa386da5c5b1ce3a3b75158669d83c1792c351` (dirty tree recorded); subset `bb99b04e425a6b337252c7fa56dbf01fae94623181b06ab39d8b223abbe16fc6`; model/layout weight hashes and package versions are in `e2e-isolation-v2.json`.
