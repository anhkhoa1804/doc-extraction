# 003 — Backend disagreement (baseline vs Docling)

## Question

There is no ground truth for this corpus, so "which backend is better" is
not answerable here. The answerable question is:

**Where do two independent systems disagree about the same page, and does
that disagreement point at pages worth a human's attention?**

Disagreement is a cheap unsupervised proxy for difficulty. Agreement is weak
evidence of correctness; disagreement is a strong pointer at something.

## Method

`doc_extraction compare` runs both systems over the same input and
`evaluation/disagreement.py` computes, per page:

- element / table count deltas
- text similarity (difflib ratio over reading-order text)
- bbox match rate and mean IoU (greedy IoU matching, threshold 0.5)
- reading-order rank correlation over matched regions

Splitting "found the same regions" from "read them the same way" from
"ordered them the same way" is deliberate — a page can score perfectly on
region detection and still be badly wrong in reading order.

## Reproduce

```bash
.venv/Scripts/python.exe -m doc_extraction compare \
    --input FROGSLEAP_Impact_Module_TriAn_B2B_Sample.pdf \
    --config configs/cpu.yaml --backends baseline docling
```

Docling costs ~35 s/page on CPU — target a single file, not the corpus.

## Files

- `config.yaml` — config used
- `results.json` — the `diff.json` produced by the run
- `observations.md` — findings
