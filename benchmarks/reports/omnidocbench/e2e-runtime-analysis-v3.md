# E2E Runtime Analysis v3

## Evidence from the previous run

The exact previous record is `e2e-full-v2.json`, run `e2e-paddleocr-vl16-isolation-full180-v2-20261002T115500Z`, on the frozen representative-v2 manifest (`bb99b04e…16fc6`). It completed 178/180 pages, timed out on two, had no other failures or warnings, and used 7,557.275 seconds wall time. Completed-page runtime was mean 41.9768 s, median 29.0548 s, p95 95.895 s, and max 300.8192 s. The prior observed GPU peak was 20,580 MiB; post-run usage was 0 MiB.

## Timeout-page inspection

| Page | Dimensions / bytes | Dataset metadata | Evidence |
| --- | ---: | --- | --- |
| `page-affbb0cc-d616-481d-b493-80ed1ccb5a10.png#0` | 1700×2200 / 278,172 | book, simplified Chinese, single column, `equation_hard`; 5 text blocks plus header/page number | The 3.74 MP input is small and below policy. The hard-equation tag is observed; its causal effect is unknown. |
| `newspaper_TheWashingtonPost-2025-01-08@magazinesclubnew_page_042.png#42` | 2800×4734 / 4,025,897 | newspaper, English, `other_layout`; 72 text blocks, 51 title annotations and other regions | Dense page and higher pixel count are observed, but 13.26 MP remains below the 40 MP limit. |

Both operations reached the unchanged 300-second hard boundary. The old run did not retain preprocessing/inference/postprocessing subphase timings; exact bottleneck attribution is therefore UNKNOWN. The two cases differ substantially in raster size, so a single pixel-size explanation is not supported.

## Instrumentation and current blocker

The worker now records timings for process startup, pipeline initialization, weight attestation, input hashing, the public `predict()` call, result JSON decoding, table parsing, canonical mapping, validation, parent request roundtrip, and termination/cleanup. Table parsing is included inside the inclusive canonical-mapping duration. Paddle’s public `predict()` boundary does not expose separate preprocessing, inference, or internal decoding phases; those remain explicitly opaque.

At the 2026-10-02 15:23:14 UTC environment check, the L4 had 12,426/23,034 MiB in use and 20% utilization by an unrelated process (PID 147482). It was left untouched. No model inference, 5-page smoke, 10-page determinism run, 20-page preflight, or v3 rerun was launched on the shared GPU. CPU execution would change the requested device condition and is not a substitute for the same-device determinism and performance gate.

No speculative preprocessing, decoding, or model changes were made. Runtime bottleneck: UNKNOWN pending a run with the new instrumentation on an available L4.
