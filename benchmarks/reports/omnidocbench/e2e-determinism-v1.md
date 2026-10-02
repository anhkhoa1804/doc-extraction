# E2E Determinism v1

Status: **NOT RUN**. The L4 was occupied by an unrelated process (12,426 MiB in use) during this turn; it was not interrupted. Determinism cannot be inferred from the earlier metric aggregates or from worker lifecycle unit tests.

The planned experiment is 10 predeclared pages from the unchanged representative-v2 manifest, each run twice with identical model revision, config, preprocessing, device, and decoding settings. It compares raw worker output, canonical content (excluding timestamps/runtime), serialized Markdown bytes, and official page-level metrics. Coverage must include text-heavy, table-bearing, equation/formula-bearing, complex-layout, and known hard/regression cases. No level of determinism is claimed yet.
