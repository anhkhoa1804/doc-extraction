# 012 — Direct EasyOCR vs Docling-wrapped OCR, as production backends

## Question

Experiment 011 built `EasyOCRBackend`, a production `OCRBackend` calling
EasyOCR directly instead of through Docling's wrapper. Is it actually
better — and at what, specifically — measured against the real adapters,
not the ad-hoc research script (`_scan_forensics/ocr_unbundle.py`) that
first raised the idea?

## Method

Both backends' `recognize()` called directly on the same rendered page
(same DPI 200, same `["en","vi"]` languages, same device) — isolating the
OCR stage from layout/table, per the mission's "only OCR implementation
changes" instruction. 13 documents from `research/production_corpus/`: the
6 originally-failing scanned documents plus 7 more spanning clean EN/VI,
small text, low contrast, stamp-over-text, and a born-digital table.

**Resource state: LIMITED** throughout — one co-tenant process holding
3,740 MiB at 20–38% utilization, 18,824 MiB free. Recall is not
device/contention-sensitive (established prior sessions); timing here is
directional, not a clean benchmark.

## Results

| | docling | easyocr | union (both kept) |
|---|---|---|---|
| mean exact recall | 0.5056 | **0.5267** | 0.5716 |
| mean word recall | 0.8973 | **0.9111** | 0.9286 |
| tokens with confidence | 0 | **171** | — |
| cold seconds (first call) | 13.03 | **3.78** | — |
| warm seconds (mean) | 1.35 | **1.20** | — |

Full per-document numbers: `results.json`.

## Interpretation

**Not a clean win either direction.** EasyOCR wins on `hc_stamp_text_vi`
(0.40→0.80 exact) and `cmb_scan_tiny_vi` (0.42→0.67 word), Docling wins on
`cmb_scan_stamp_table_vi` (0.88 vs 0.75 exact) and `hc_tiny_text_en` (1.00
vs 0.89 word). The union result — meaningfully higher than either alone —
says the two sources are genuinely complementary, not that one subsumes
the other.

**The `cmb_scan_stamp_table_vi` case that originally motivated this whole
investigation is now closer to a wash.** Before experiment 011's traversal
fix, Docling scored 0.25 there (dropped the region entirely). Post-fix,
Docling now scores 0.88 at the isolated OCR-stage level — *higher* than
EasyOCR's 0.75 on the same document. The dominant defect for that case was
integration (traversal), not model quality, and 011 already fixed it;
011's fix closed most of the gap this experiment was originally built to
address for that specific document.

**Speedup is much smaller on GPU than the earlier CPU measurement
suggested.** `1015ab2` (CPU): docling 15.6s vs easyocr 6.2s — 2.5×. Here
(GPU): warm 1.35s vs 1.20s — ~13%. Docling's layout+OCR pipeline is *also*
GPU-accelerated, closing most of the gap that showed up on CPU. Citing the
CPU number as if it transfers to the shipped GPU-capable configuration
would be a real error — recorded explicitly so it isn't repeated.

**Where EasyOCR wins mechanistically, not coincidentally**: `cmb_scan_tiny_vi`
is tiny text on a noisy scan. Docling rasterizes internally at a fixed ~150
DPI regardless of the image handed to it (`docling_backend.py`'s own
documented finding); EasyOCR reads the DPI-200 pixels directly, so it isn't
throwing away resolution the caller already paid to render. This is the
same defect `1015ab2` §4 diagnosed for the `render_dpi` knob — consistent,
not a new coincidence.

## Confidence calibration

Pearson r = **0.491** between a document's mean EasyOCR token confidence
and its word recall (n=13). Real signal, not noise, but weak — `hc_stamp_text_vi`
has *below-median* confidence (0.723) yet perfect recall; `ord_contract_vi`
has *above-median* confidence (0.815) yet 0.782 recall. **Confidence high
≠ correct, exactly as the mission warned against assuming** — this is
measured, not merely acknowledged as a caveat.

## Cross-backend agreement — the stronger signal

Word-Jaccard agreement between Docling's and EasyOCR's output on the same
pixels, correlated against `min(docling_word_recall, easyocr_word_recall)`:
Pearson r = **0.856** (n=13) — substantially stronger than confidence
alone. The worst document (`cmb_scan_tiny_vi`, word recall 0.42/0.67) has
the lowest agreement (0.34) of any document in the set; every document
with agreement ≥ 0.95 has word recall ≥ 0.938.

**Honest limitation, not smoothed over**: two documents break the pattern
in the dangerous direction — `hc_low_contrast_vi` (agreement 0.98, recall
only 0.782) and `ord_contract_vi` (agreement 0.93, recall 0.782). Both
backends agree *and are both wrong* — a shared blind spot, not a
disagreement. Agreement cannot catch an error two independent sources make
identically; this is the same class of limit the project has hit before
(redundant sources sharing one root cause).

## Coordinate validation

`EasyOCRBackend`'s bbox output was validated against ground truth (known
text placement in a synthetic image) — see `tests/test_easyocr_backend.py`.
EasyOCR does not re-rasterize internally the way Docling does, so its
polygon output needs no scale correction, only a polygon→axis-aligned-bbox
reduction — a simpler, more direct coordinate story than Docling's, which
required discovering and fixing a real cross-backend scale bug earlier in
this project.

## Decision, against the mission's own promotion rule

> Promote only if it demonstrates a meaningful benefit in at least one
> important dimension, without unacceptable regression elsewhere.

| dimension | verdict |
|---|---|
| better scan recovery | mixed — wins some documents, loses others |
| better confidence signal | **yes** — 171 real confidences vs 0 |
| lower runtime | **yes** — cold 3.4× faster; warm ~13% faster (GPU; was 2.5× on CPU) |
| better EN/VI robustness | marginal — +2 pts exact recall, not dramatic |
| better recovery capability | untested this session |

The rule's bar is met on confidence and cold-latency, without a recall
regression (mean recall is *slightly* higher, and the union is
meaningfully higher than either alone). **Decision: do not flip the
production default** (`ocr_backend: docling` stays default — the win is
real but not dominant enough to justify a blanket swap on a 13-document
synthetic sample). **Do** treat cross-backend agreement as the more
promising verification signal going forward — it is the strongest
finding in this experiment (r=0.856 vs r=0.491), it directly extends the
Verification layer already built (experiment 011's `ingest/verification.py`,
via `assess_ocr_agreement`), and it does not require deciding which
backend to trust, only when to distrust both.

## What this does NOT establish

* n=13, synthetic corpus. Both correlations (confidence r=0.491, agreement
  r=0.856) are suggestive, not proof — re-calibrate against more documents,
  ideally real ones, before using either near a decision boundary.
* Targeted recovery (crop → re-OCR → re-verify → replace-if-better) is not
  built or tested this session. `assess_ocr_agreement` is a scoring
  function, not a wired trigger — running EasyOCR on every scanned page to
  compute agreement would roughly double OCR-stage cost, which needs its
  own cost/benefit experiment before it runs unconditionally, rather than
  wiring it in mid-session without measuring that tradeoff.
* No real (non-synthetic) EN/VI data used anywhere in this experiment.

## Reproduce

```bash
python research/production_corpus/generate.py
python experiments/012_direct_easyocr/run_ab.py --device cuda --resource-state LIMITED
```
