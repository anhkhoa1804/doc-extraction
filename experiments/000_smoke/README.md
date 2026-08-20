# 000 — CPU smoke test over the whole corpus

## Question

**Does the baseline pipeline run end-to-end, CPU-only, over every real
sample document without failing or silently degrading?**

This is the regression baseline the other experiments are measured against.

## Reproduce

```bash
.venv/Scripts/python.exe -m doc_extraction run --input . --config configs/cpu.yaml
.venv/Scripts/python.exe scripts/build_failure_report.py --input outputs/
```

No GPU, no network once models are cached.

## Files

- `config.yaml` — the CPU config used
- `results.json` — per-document route, page/element/table/cell counts, runtime
- `observations.md` — findings
