# 020 — Ground-truth whitespace fix, and why the table-quality-gate wiring doesn't transfer

**Question:** milestone 016/017/019's own "Next 3 Actions" named two items as
cheap and already fully diagnosed: (1) fix the `Ký hiệu` ground-truth
whitespace artifact in the recall metric, and (2) wire
`table_quality.assess_table`'s style/content-outlier gate to the
Table-Transformer/OCR path to close the stamp-contamination integration gap
exp019 found. This milestone executes (1) and investigates (2) — and (2)
turns out not to be executable as scoped, for reasons the prior milestones'
own evidence did not surface. Recording that precisely is this milestone's
main output.

**Baseline.** `git rev-parse HEAD` at start: `53bd302`. `pytest -q`: 304
passed, 10 skipped, 0 failed (the flaky `test_office_routes_are_deterministic`
noted in milestones 018/019 did not fail this run — confirmed still
unrelated, not chased). GPU preflight **CLEAR** (0 MiB, 0% util, no other
process) before both benchmark runs this milestone made. Machine is
single-tenant (no other users, `who` returns only this session).

Production corpus (58 docs), `adaptive`, `cuda`, before any change: mean
recall **0.9491**, 52/58 fully recovered — reproduced fresh, not assumed.

---

## 1. Ground-truth whitespace fix

**Diagnosis (from exp016, unchanged, re-verified here):** `research/production_corpus/generate.py` bakes the literal source-layout string
`"Ký hiệu: MQ/2026E    Số: 0004417"` (4 spaces between the two fields) into
`must_contain` for two documents (`cmb_scan_stamp_table_vi`,
`ord_invoice_png_vi`). No text extractor — native or OCR — reproduces a
run of 4 literal spaces as 4 characters; every real backend collapses
inter-field gaps to however many whitespace characters it actually
detected as glyphs, normally one. The extracted text was already correct;
the benchmark string was not comparable to what any real extractor can
produce.

**Fix:** whitespace-collapse (`re.sub(r"\s+", " ", ...)`) added to the
normalization function in both `research/production_corpus/run_benchmark.py`
(`_norm`) and `research/hardcases/run_benchmark.py` (`_normalize`), applied
symmetrically to extracted text and to `must_contain`/`must_not_contain`
strings before comparison — a metric fix, not a corpus-generator fix, so the
committed corpus manifest's per-document hashes (the "57/58 regenerate
byte-identically" guarantee) are untouched. Checked first that no other
`must_contain` string in either generator relies on preserved multi-space
runs (`grep` over both `generate.py` files) — none do; this is the only
affected string.

**Measured effect**, full fresh re-run, GPU CLEAR:

| document | before | after |
|---|---|---|
| `ord_invoice_png_vi` | 0.7143 | **0.8571** |
| `cmb_scan_stamp_table_vi` | 0.7500 | **0.8750** |
| corpus mean | 0.9491 | **0.9537** |
| fully recovered | 52/58 | 52/58 (unchanged — both documents carry a second, independent defect each: `ord_invoice_png_vi`'s word-order scramble on `"Dịch vụ lắp đặt"`, exp016/017; `cmb_scan_stamp_table_vi`'s table-detection failure, exp018/019) |

14-document hardcase corpus: **98% mean, 13/14 full recovery, 0 regressions**
— unaffected, as expected (no double-space ground truth exists there).
`pytest -q`: **304 passed, 10 skipped, 0 failed**, unchanged.

**INTERPRETATION:** this closes exactly the false-failure exp016 diagnosed
(2/9 misses were metric artifacts, not pipeline defects) and makes every
future recall number on this corpus honest by that margin. It does not and
should not move `fully_recovered`, because both affected documents have a
real, separately-tracked second defect exp016-018 already found.

## 2. Table-quality-gate wiring — does not transfer as scoped

Milestones 017 and 019 both named the same next step: wire
`table_quality.assess_table` (currently only called from
`pymupdf_table_backend.py`, the native-PDF path) to the Table-Transformer/
OCR path, to catch stamp text landing inside a legitimately-detected cell
(exp019's `r1c1`/`r2c1` contamination on the OCR-grid → Table-Transformer
combined trial). Before writing that wiring, this milestone checked the two
things neither prior report verified: what evidence is actually available
on that path, and whether the contaminated code is live.

**Checked directly (not assumed):**

* `assess_table`'s three signals, read from `src/doc_extraction/ingest/table_quality.py`:
  * Signal 1 (a text run straddling cell boundaries) needs only `bbox`.
  * Signals 2 and 3 (style outlier, mixed-style cell) need `span["size"]`
    and `span["color"]` — PyMuPDF span fields.
* `OCRToken` (`pipelines/base.py:67`) — the only evidence the
  Table-Transformer/OCR path produces per token — is `text`, `bbox`,
  `confidence`. **No size, no color, no style field of any kind.** Docling's
  own `recognize()` additionally sets `confidence=None` unconditionally
  (`docling_backend.py:345,396`) — even the one numeric field OCRToken has
  is absent from the default OCR backend on this path.
* `grep` for `assess_table` and `spans_by_table` across `src/`: `assess_table`
  is called from exactly one place, `pymupdf_table_backend.py`.
  `TableResult.spans_by_table` (the carrier `assess_table` reads) is
  populated only there; its own docstring already says "Empty for backends
  that work from pixels" — the Table-Transformer path has always passed an
  empty dict, by design, not by omission.
* Whether signal 1 (the one signal that is geometry-only and could in
  principle run on `OCRToken`) would find anything new on this path: **no**.
  `_fill_table_cell_text`'s tier 1/2 (exp017) already leave an ambiguous,
  cell-boundary-straddling token unassigned by construction
  (`test_token_in_gap_between_cells_ambiguously_is_not_assigned`,
  `tests/test_table_cell_geometry.py`) — exactly the condition signal 1
  flags. A token that reaches a filled cell on this path has already passed
  a stricter geometric test than signal 1 applies. Wiring signal 1 here
  would relabel work already done, not add coverage.
* Where the actual contamination case lives: exp019's `r1c1`/`r2c1` case is
  from the **combined strategy** (OCR-grid candidate bbox fed into Table
  Transformer's own structure model) — a one-off manual trial script,
  explicitly **REJECTED for production** in exp019's own Promotion Decision
  and never wired into `pipelines/base.py`, `stages/table.py`, or any
  config. The currently-shipped Table-Transformer path (ordinary
  whole-page/region detection, no OCR-grid rescue) has no example of this
  contamination in either real corpus — it was never observed on a document
  that reaches production code, only on the one manual trial.

**INTERPRETATION:** the recommendation ("wire the existing gate") does not
survive contact with the two backends' actual evidence shapes. This is not
a tuning gap or a missed call site — it is a genuine schema mismatch: the
gate's two content-bearing signals require font metadata that OCR tokens
structurally do not carry, and its one geometry-only signal is already
subsumed by logic exp017 built for a different reason. Forcing a "wiring"
here would mean either (a) shipping a gate that can never fire (an ignored
gate, which the module's own docstring already names as worse than none),
or (b) inventing a new signal (OCR-confidence outlier, or duplicate-text-
against-page-header — both plausible, neither measured) under the name of
"wiring an existing gate," which is a different, larger task this
milestone's evidence does not justify starting on an n=1 case that isn't
even in production.

**Corrected finding, replacing exp017/019's recommendation:** there is
currently **no live production contamination risk** for this fix to close
— the vulnerable code path is unshipped. If the combined strategy is ever
promoted (which exp019 explicitly declined to do), the right precondition
work is designing and measuring a *new* content signal appropriate to
featureless OCR tokens — not reusing `assess_table`. That is future,
evidence-gated research, not a wiring task, and should not be started
speculatively against a code path with zero production exposure.

**No code changed for item 2.** Per the project's own discipline (do not
build ahead of evidence, do not wire a gate that cannot fire), the correct
action here was to correct the roadmap, not to write code that looks like
progress without being any.

## Production Impact

| | before | after |
|---|---|---|
| 58-doc corpus mean recall | 0.9491 | **0.9537** |
| 58-doc fully recovered | 52/58 | 52/58 |
| 14-doc hardcase mean recall | 98% | 98% (unchanged) |
| `pytest -q` | 304 passed / 10 skipped | 304 passed / 10 skipped |

Zero regressions on either corpus or the test suite. `table_quality.py`,
`pymupdf_table_backend.py`, and the Table-Transformer path are all
byte-unchanged.

## What We Learned

1. A recommendation written with full confidence in a prior milestone
   ("this is the actual fix, not a smarter detector") can still fail to
   survive a feasibility check against the actual data shapes involved —
   the fix was reasoned correctly about *what* was missing (a content
   check) but not verified against *what evidence exists to build it from*.
   Checking that before writing code is cheaper than writing code that
   cannot do anything.
2. "Unwired" and "unbuildable-as-stated" are different findings, and
   conflating them would have produced a gate that never fires — exactly
   the failure mode `table_quality.py`'s own docstring warns against
   ("an ignored gate is worse than none").
3. A capability gap tied to code that was itself rejected for production
   (exp019's combined strategy) carries no current production urgency,
   regardless of how well-diagnosed the gap is. Diagnosis quality and
   production priority are independent axes.

## Next 3 Actions

1. **If the combined strategy (OCR-grid → Table Transformer structure
   model) is ever reconsidered for production**, design and measure a
   content signal appropriate to featureless `OCRToken` evidence first —
   OCR-confidence outlier (only usable with a backend that populates
   `confidence`, which Docling's default `recognize()` does not) or
   duplicate-text-against-page-header are the two candidates surfaced here,
   neither measured.
2. **`cmb_scan_tiny_vi`** (0.0 recall, correlated backend failure) remains
   the corpus's most severe unresolved case across four consecutive
   milestones (014/015/018/019) — still the single highest-value real gap.
3. **Unify `scan_recovery.RecoveryRecord` and
   `order_recovery.OrderRecoveryRecord`** into the shared diagnostic shape
   named in milestone 018 — the convergent-design signal is now three
   milestones old.

## Promotion Decision

| | decision |
|---|---|
| **Ground-truth whitespace fix** | **PROMOTE** — shipped in both benchmark scripts, measured, zero regression |
| **Table-quality-gate wiring** | **WITHDRAWN** — the prior recommendation is corrected, not implemented; no code exists to promote |

## Reproduce

```bash
python research/production_corpus/run_benchmark.py --strategy adaptive --device cuda
python research/hardcases/run_benchmark.py --strategy adaptive --device cuda
pytest -q
```
