# 021 — The corpus's worst document is misclassified, and the two backends are one backend

## Current Baseline

`git rev-parse HEAD` at start: `c4e5b55`. `pytest -q`: **304 passed, 10
skipped** (interpreter: `~/.venvs/doc-extraction-gpu312/bin/python` — the
in-repo `.venv` is a stale Python 3.10 without numpy and cannot collect the
suite; noted because milestone 018's own "291 passed" was recorded from a
different interpreter). GPU preflight **CLEAR** before the one GPU workload
this milestone ran (3 MiB / 23034 MiB used, 0% utilization, no compute
processes); postflight re-checked, nothing leaked.

Two findings, one measurement. Both concern `cmb_scan_tiny_vi` — the
production corpus's only 0.00-recall document, and per milestone 018 "the
last major failure class with zero recovery progress across three
consecutive milestones" (now four).

## Finding 1 — `cmb_scan_tiny_vi` is not a tiny-text failure

**OBSERVED.** The document is labelled `T-TINY` ("text below what the render
DPI resolves"). Every recovery attempt so far followed from that label, and
all of them failed. From `_scan_forensics/recovery_dpi.json` (re-read, not
re-run):

| arm | megapixels | exact recall | word recall | chars read |
|---|---|---|---|---|
| global_200 (shipped default) | 3.87 | 0.000 | 0.417 | 93 |
| global_300 | 8.70 | **0.333** | **0.625** | 98 |
| global_400 | 15.47 | 0.000 | 0.389 | 68 |
| global_600 | 34.80 | 0.000 | 0.292 | 59 |
| targeted_600 (crop regions, read at 600) | 0.93 | 0.000 | 0.000 | 16 |

Word recall **peaks at 300 DPI and then falls monotonically**: 0.625 →
0.389 → 0.292, while pixel cost rises 4×→9×. Characters read fall 98 → 59.
A resolution limit does not behave this way; nine times the pixels
recovering two thirds the characters is the signature of something else.

**The competing hypothesis, tested.** A *normalization ladder*: fold away
one hypothesised cause at a time, cumulatively, and rescore. The rung where
recall jumps owns the failure. EasyOCR, 200 DPI, device `cuda`:

| rung | exact recall | word recall | per-string hits |
|---|---|---|---|
| raw | 0.000 | 0.625 | `. . .` |
| +NFC | 0.000 | 0.625 | `. . .` |
| +casefold | 0.000 | 0.667 | `. . .` |
| +whitespace | 0.000 | 0.667 | `. . .` |
| +punctuation | 0.000 | 0.667 | `. . .` |
| **+diacritics** | **0.333** | **0.903** | `. . Y` |
| **+confusables** (`l`/`I`/`1`) | **0.667** | **0.944** | `Y . Y` |

The text EasyOCR actually returns at the shipped 200 DPI default:

```
QUY CHẾ QUẢN LÝ CHI TIÊU NỘl BỘ Dieu Phạm vi ap dung Quy che nay áp dung
cho toan bộ nhan sư thupc công ty va cac chi nhanh Dieu 2 Tham quyén phe
duyet Khoan chi trên 50.000.000 dóng phải ducc Tong Giam dõc phe duyet
bang vIn bản.
```

Against required `Quy chế này áp dụng cho toàn bộ`: every word is present.
`che`≠`chế`, `nay`≠`này`, `toan`≠`toàn` — tone marks dropped, glyphs
correct. `NỘl BỘ` is `NỘI BỘ` with a lowercase `l` for `I`.

**INTERPRETATION.** The document does not score 0.00 because the text was
too small to read. It scores 0.00 because **94.4% of the required words are
recovered and then corrupted at the character level** — Vietnamese tone
marks lost, plus one `l`/`I` glyph confusion. The failure class is
`T-DIACRITIC`, which this project's own hardcase taxonomy already declares
as a known-real mechanism and marks **"not yet"** built
(`research/hardcases/README.md`). Four milestones of DPI-shaped recovery
made no progress because they targeted a mechanism that was never the
cause.

**LIMITATION.** n=1 document, 3 `must_contain` strings. The ladder measures
which normalization recovers a match; it does not prove a recognizer exists
that would emit the diacritics correctly (Finding 2 bears on that, but does
not settle it either). The third string (`Điều 1. Phạm vi áp dụng`) fails at
every rung including the top: OCR genuinely dropped the token `1`, a real
content loss, not a character-level one. So the honest decomposition of this
document's 0.00 is **2/3 character-level corruption, 1/3 genuine token
loss** — not 3/3 character-level.

**Reproducibility.** A fresh render + re-OCR (`--fresh --device cuda`)
reproduced the recorded text **byte-identically** (230 chars) and every
ladder number exactly. This failure is deterministic, not sampling noise.

## Finding 2 — the two backends share one recognizer

**OBSERVED.** `src/doc_extraction/backends/docling_backend.py:221`:

```python
# EasyOCR (not docling's RapidOCR default) specifically for proper
# Vietnamese ("vi") support — see docs/backends.md.
pipeline_options.ocr_options = EasyOcrOptions(lang=self.ocr_languages)
```

Docling's OCR *is* EasyOCR. Both the `docling` backend and the `easyocr`
backend added in milestone 012 resolve Vietnamese through the same
`latin_g2` recognition weights (experiment 007 established that EasyOCR
serves `vi` from `latin_g2`). They differ in **segmentation and wrapping** —
which is real, and is exactly what milestone 018's `order_recovery`
exploits (Docling merged the region into 2 items; direct EasyOCR returned 7
line detections) — but at the **character** level they are one engine and
fail identically.

The fingerprint is already in this repo's recorded results. Experiment 013's
Correlated Errors table:

| document | agreement | Docling word recall | EasyOCR word recall |
|---|---|---|---|
| `ord_contract_vi` | 0.93 | 0.782 | 0.782 |
| `hc_low_contrast_vi` | 0.98 | 0.782 | 0.782 |

Byte-identical recall on both documents. Two genuinely independent models
agreeing to three decimal places on two different documents is not what
independence produces.

**INTERPRETATION.** Experiment 013 described these as "an error two
**independent** sources make identically" and concluded that "any production
use of agreement as a trust gate must accept this failure mode explicitly."
The mechanism is not bad luck to be accepted — it is **architectural
non-independence**, and it is fixable. `assess_ocr_agreement` (shipped in
`7aab649`) can detect segmentation and merge disagreements; it is
**structurally blind** to any error the shared recognizer makes, which
includes the whole Vietnamese diacritic class of Finding 1. Agreement
between these two paths is evidence about *layout wrapping*, not about
*character correctness*, and the signal's scope should say so.

**Not a novelty claim.** `_scan_forensics/ocr_unbundle.py`'s own docstring
already calls EasyOCR "*the same recognizer docling itself wraps*." The fact
was known in one corner of the repo while experiment 013's README and the
shipped agreement signal were framed on the opposite assumption. This
milestone's contribution is connecting the two, not discovering either.

**LIMITATION.** The identical-recall evidence is n=2 documents, and word
recall is a coarse enough metric that two different recognizers *could*
coincide on it. The decisive evidence is the source line, not the table.

## Consequences

1. **`RERENDER_HIGH_DPI` is falsified as the recovery action for this
   document** — not untested, falsified, with a monotonic negative trend
   across four DPI settings. Milestone 018's recovery-policy table lists
   `RERENDER_HIGH_DPI / VLM_REGION` for the tiny-text row; the first half
   should be struck.
2. **The VLM decision test is, for the first time in this project, actually
   satisfied for a specific case.** Milestones 018 and 019 both correctly
   declined VLM work because deterministic evidence could in principle
   recover the case. Here it cannot: both deterministic paths share a
   recognizer that lacks the capability, so no rearrangement of existing
   evidence recovers the diacritics. This does **not** mean a VLM is the
   answer — it means a *genuinely independent Vietnamese-capable
   recognizer* is the missing evidence source, and a VLM is one candidate
   among several (PaddleOCR, VietOCR, Tesseract `vie`), none of which are
   currently installed.
3. **Cross-backend agreement's documented scope is wrong** and should be
   narrowed to what it can actually witness.

## What We Should NOT Build

* **Any further DPI-based recovery for `cmb_scan_tiny_vi`** — four arms,
  monotonic negative trend. Closed, per the stop-condition rule.
* **A diacritic-restoring post-processor** (fold-and-rematch, or a
  Vietnamese language model that re-accents unaccented text). It would move
  this benchmark's number without adding information — the accents would be
  *guessed from a language prior*, not *read from the page*, which is the
  same class of confident-and-wrong output the project's central design
  decision exists to prevent. Recall would rise; correctness would not.
* **A second recognizer wired in before it is measured.** Finding 2 says the
  evidence source is missing, not that any particular replacement supplies
  it.

## Next 3 Actions

1. **Measure one genuinely independent Vietnamese-capable recognizer** on
   `cmb_scan_tiny_vi` and the two `0.782/0.782` correlated-error documents.
   Cheapest honest test first (Tesseract `vie`, a different engine family
   entirely), then PaddleOCR/VietOCR, then a VLM only if the cheap engines
   also fail. The question is narrow and falsifiable: *does any independent
   recognizer read these tone marks off these pixels?* If none does, the
   information is not on the page at 200 DPI and the case is genuinely
   unrecoverable — also a decisive result.
2. **Narrow `assess_ocr_agreement`'s documented scope** to segmentation-level
   disagreement, and correct experiment 013's "independent sources" framing.
   Documentation-only; no behavior change, since the signal's *measured*
   behavior was always this.
3. **Build the `T-DIACRITIC` hardcase** the taxonomy already declares — a
   controlled Vietnamese-diacritic case at several point sizes, to establish
   the glyph size at which tone marks stop surviving. This turns a one-document
   anecdote into a measurable boundary.

## Promotion Decision

| | decision |
|---|---|
| Finding 1 (misclassification) + Finding 2 (shared recognizer) | **ACCEPTED as diagnosis** — no code shipped |
| `T-TINY` label on `cmb_scan_tiny_vi` | **RETRACTED** — should be `T-DIACRITIC` + partial token loss |
| `RERENDER_HIGH_DPI` for this class | **REJECTED** with evidence |

No production code changed this milestone. The output is a corrected
diagnosis and one reproducible measurement script; the repository's failure
taxonomy is now wrong in a documented, specific way rather than wrong in an
unexamined one.

## Reproduce

```bash
# no GPU needed — rescoring recorded text
python research/experiments/_scan_forensics/diacritic_ladder.py

# fresh render + re-OCR (GPU preflight is the caller's responsibility)
python research/experiments/_scan_forensics/diacritic_ladder.py --fresh --device cuda
```

Raw output: `research/experiments/_scan_forensics/diacritic_ladder.json`.
Prior DPI arms re-read from `_scan_forensics/recovery_dpi.json`.
