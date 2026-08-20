# 001 — PDF text-layer quality

## Question

A PDF can carry a text layer that is present and plentiful but decoded
wrongly, because the embedded font's `ToUnicode` CMap is broken. A
character-count heuristic cannot see this: the garbage is exactly as long as
the real text would be.

**Can a cheap, explainable signal — no OCR, no model, no rendering —
separate correctly-decoded text from this kind of corruption on our own
corpus, with enough margin to be trustworthy?**

This matters because the failure is silent. Nothing looks broken downstream;
the pipeline just emits confident nonsense.

## Method

`scripts/calibrate_text_quality.py` extracts the text layer of the first 3
pages of every PDF at the repo root and computes the signals defined in
`src/doc_extraction/ingest/text_quality.py`. No labels were used to fit
anything — the thresholds were chosen after looking at the observed
distribution, and the corrupt document was already known from the phase-1
smoke test.

## Reproduce

```bash
.venv/Scripts/python.exe scripts/calibrate_text_quality.py \
    --input . --max-pages 3 --json experiments/001_pdf_text_quality/results.json
```

CPU-only, no network, runs in under a second.

## Files

- `config.yaml` — thresholds used (mirrors `configs/cpu.yaml`)
- `results.json` — per-page signal values for all 10 PDFs at the repo root
- `observations.md` — what the numbers show
