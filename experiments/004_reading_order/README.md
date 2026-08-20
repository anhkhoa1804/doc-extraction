# 004 — Reading-order baseline failures

## Question

`stages/reading_order.py` is a geometric baseline: detect column gutters,
group into row bands, sort left-to-right within a band. It is deliberately
*not* a semantic reading-order model.

**Where does it visibly fail on real documents, and does it disagree with a
strong backend's ordering in ways worth investigating?**

The point is not to fix it in this phase. It is to establish an independent
ordering that can be diffed against a backend's, and to record concrete
failures so a future ordering model has targets.

## Method

Two sources of evidence:

1. **Direct inspection** of recovered text for phrase-level scrambling —
   Vietnamese official documents carry a fixed masthead phrase
   (`Độc lập - Tự do - Hạnh phúc`), which makes ordering errors visible
   without any ground-truth labelling.
2. **Rank correlation against Docling's ordering** over IoU-matched regions,
   from `doc_extraction compare` (see 003).

## Reproduce

```bash
.venv/Scripts/python.exe -m doc_extraction run --input "FROGSLEAP_BUSINESS LICENSE.pdf" --config configs/cpu.yaml
.venv/Scripts/python.exe -m doc_extraction inspect
# open outputs/<document_id>/inspection/index.html to see bbox overlays in order

.venv/Scripts/python.exe -m doc_extraction compare \
    --input FROGSLEAP_Impact_Module_TriAn_B2B_Sample.pdf \
    --config configs/cpu.yaml --backends baseline docling
```

## Files

- `config.yaml` — config used
- `results.json` — the observed cases
- `observations.md` — findings
