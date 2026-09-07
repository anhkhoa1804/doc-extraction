# 023 — Evidence-centric extraction: does heterogeneous OCR evidence help?

## Baseline

`git rev-parse HEAD` at the start of this milestone: `723d4cf3efc30f05ee0bcdefaf2a244be73d0286`
("feat: add Tesseract as a genuinely independent OCR backend").
`pytest -q`: 329 passed, 10 skipped, 0 failed
(interpreter `~/.venvs/doc-extraction-gpu312/bin/python`, Python 3.12.14).
All 10 skips are absent private-corpus fixtures under `data/`; none touch OCR,
Tesseract, or token ordering.

GPU state is recorded inside every result file rather than asserted here.
Both A/B runs executed under **`LIMITED_OR_PROTECTED`** — an unrelated
training job (`Research-No.1`) held 7.4–12.1 GB of the L4 throughout — so
every condition ran `--device cpu`. Timings are upper bounds; quality
metrics are unaffected by contention.

Corpus: 49 PDFs / 112 pages from `research/production_corpus`, 200 DPI,
`vie+eng`, 226 `must_contain` strings.

## The question

022 established that Tesseract is a genuinely independent recognizer and
that it doubles Vietnamese recall. That raises the architectural question
this milestone exists to answer:

> Now that two independent OCR sources exist, is combining their evidence
> worth what it costs — and if so, which combination?

Six conditions, all through the *same* production `process_file`, so tables,
reading order, assembled IR and hallucination come from the real pipeline
and not a text-only side channel:

| | condition | what it is |
|---|---|---|
| A | `easyocr` | single source, the previously shipped path |
| B | `tesseract` | single source, genuinely independent (021/022) |
| C | `selection` | both, pick one page-wide by mean confidence |
| U | `union` | both, naive concatenation — the crude control |
| D | `fusion` | both, geometry- and conflict-aware `evidence_fusion` |
| E | `fusion_recovery` | D + `order_recovery`'s decision rule per region |

Two strategies. `visual` forces render+OCR on every page and isolates the
recognizer. `adaptive` is the shipped router; most corpus PDFs have a
usable text layer and never reach OCR, so it measures the *production*
delta. Reporting only `visual` would overstate the production win;
reporting only `adaptive` would hide the recognizer effect entirely.

## Artifact provenance — read this before quoting any number

Four distinct classes of artifact exist in this directory. They must not be
mixed, and two of them are superseded.

| class | file | status |
|---|---|---|
| **pre-fix benchmark** | `ab_visual_pre_reading_order_fix.json` | **SUPERSEDED.** Measured before the reading-order and `eng`-last changes. Retained as the before-side of the delta. Never quote as current. |
| **fresh post-fix benchmark** | `ab_visual.json` | **AUTHORITATIVE** for `visual`. 6/6 conditions, 49/49 documents each, 0 errors. |
| **adaptive benchmark** | `ab_adaptive.json` | **AUTHORITATIVE** for production shape. 6/6 conditions, 49/49 documents each, 0 errors. |
| **offline re-score** | `agreement_analysis.json`, `routing_experiment_visual.json`, `routing_experiment_adaptive.json`, `cell_evidence_audit.json`, `regression_analysis.json` | Derived from artifacts already on disk. Invoke no OCR engine, no GPU. |

A fourth, discarded artifact is named here so it is never mistaken for
evidence: an earlier post-fix attempt was killed by the OOM killer when two
~10 GB processes ran concurrently. Its `easyocr 0.6570` and
`tesseract 0.9311` reproduce the final run exactly and serve as an
independent determinism check; its `selection 0.5510` (where exact recall
and char recall are equal to four decimals, followed by all-zero documents)
is memory-starved corruption. **No number from that run appears below.**

`_runs/` (192 MB, 11,718 files) is deliberately untracked, per this repo's
convention of committing the measurement rather than the working files. It
is regenerable: the scripts are tracked and the corpus is regenerable from
its seeded generator, whose manifest carries a per-document sha256.

## OBSERVED — `visual` (recognizer-isolating)

Source: `ab_visual.json`. Post-fix.

| condition | exact recall | char recall | perfect | zero | order ok | tables ok | en | vi | wall_s |
|---|---|---|---|---|---|---|---|---|---|
| easyocr | 0.6570 | 0.9577 | 14/49 | 6 | 45/49 | 47/49 | 0.9214 | **0.4747** | 3295.4 |
| **tesseract** | **0.9311** | 0.9715 | **40/49** | 1 | **46/49** | 47/49 | 0.9690 | **0.9050** | **167.6** |
| selection | 0.9282 | 0.9716 | 38/49 | 1 | 45/49 | 47/49 | 0.9619 | 0.9050 | 2234.0 |
| union | 0.8519 | **0.9859** | 26/49 | 0 | 45/49 | 47/49 | 0.9690 | 0.7711 | 2258.1 |
| fusion | 0.9026 | 0.9850 | 35/49 | 0 | 45/49 | 47/49 | 0.9690 | 0.8567 | 1858.4 |
| fusion_recovery | 0.9026 | 0.9850 | 35/49 | 0 | 45/49 | 47/49 | 0.9690 | 0.8567 | 1751.4 |

`wall_s` is **not comparable across arms**: `easyocr` ran first and paid all
111 layout cache misses (561 hits / 111 misses over 672 page-passes), so
roughly 950 s of its 3295.4 s is layout the other five arms received free.
Cost claims below therefore use the instrumented per-engine timers, not
`wall_s`.

## OBSERVED — `adaptive` (production routing)

Source: `ab_adaptive.json`. **Only 7 of 112 pages (6.3%) ever reach OCR.**

| condition | exact recall | char recall | perfect | zero | en | vi | wall_s | OCR invocations |
|---|---|---|---|---|---|---|---|---|
| easyocr | 0.9456 | 0.9909 | 44/49 | 1 | 0.9667 | 0.9310 | 237.8 | — |
| **tesseract** | **0.9838** | 0.9941 | **46/49** | 0 | 0.9833 | **0.9842** | **15.3** | — |
| selection | 0.9838 | 0.9941 | 46/49 | 0 | 0.9833 | 0.9842 | 150.7 | 14 |
| union | 0.9787 | **0.9962** | 45/49 | 0 | 0.9833 | 0.9756 | 153.0 | 14 |
| fusion | 0.9838 | 0.9953 | 46/49 | 0 | 0.9833 | 0.9842 | 152.1 | 14 |
| fusion_recovery | 0.9838 | 0.9953 | 46/49 | 0 | 0.9833 | 0.9842 | 151.7 | 14 |

## Cost — the decisive measurement

Instrumented per-engine, same pages, same DPI, CPU:

| | Tesseract | EasyOCR | ratio |
|---|---|---|---|
| 112 pages (`visual`, composite arms) | 77.2–82.4 s | 1607.7–2087.0 s | **20.8–25.3×** |
| per page | 0.69–0.74 s | 14.4–18.6 s | |
| 7 pages (`adaptive`) | 5.7 s | 135.2 s | 23.7× |

Tesseract is simultaneously the **more accurate** and the **~20× cheaper**
engine, and it is CPU-only. That inversion is what changes the
architecture. Heterogeneous evidence was worth paying for when the cheap
engine was the weak one; it no longer is. Every both-engine arm is now
strictly dominated, and the L4 leaves the OCR path entirely.

## Complementarity

Over 226 required strings (`agreement_analysis.json`, recomputed on
post-fix tokens):

| outcome | strings | share |
|---|---|---|
| both right | 149 | 65.9% |
| **tesseract only** | **62** | **27.4%** |
| **easyocr only** | **8** | **3.5%** |
| both wrong | 7 | 3.1% |
| *(disagreements)* | *70* | *31.0%* |

Real, but **7.75:1 asymmetric**. Per document: Tesseract wins 29, EasyOCR
wins 4, 16 tie. The four EasyOCR wins are all geometric or scale failures,
and they reproduce `regression_analysis.json`'s four `is_regression` rows
exactly:

| document | easy | tess | fusion | failure type |
|---|---|---|---|---|
| `hc_rotation_vi` | 0.3333 | 0.0000 | 0.3333 | 90° rotation |
| `cmb_lowcontrast_stamp_vi` | 0.8000 | 0.6000 | **1.0000** | low contrast + stamp occlusion |
| `hc_tiny_cells_vi` | 0.5714 | 0.4286 | 0.5714 | tiny text in table cells |
| `cmb_tiny_table_en` | 0.8571 | 0.7143 | 0.8571 | tiny text in table cells |

## Agreement as a verification signal

The milestone's central question. Now that the pair is genuinely
independent, agreement predicts **the better source**, not **correctness**:

- agreement vs **best**-of-pair recall: **r = +0.8425**
- agreement vs **min**-of-pair recall: r = +0.5434
- geometric overlap vs min recall: r = +0.2295 (near-useless)
- Tesseract confidence vs its own recall: r = +0.7773
- EasyOCR confidence vs its own recall: r = +0.3923

Calibration is monotone: band `[0.0,0.3)` n=2 → best-recall 0.500;
`[0.9,1.01)` n=21 → best-recall 1.000. But the shipped threshold of 0.5
**flags only 3 of 49 documents**, and is blind to the `[0.7,0.9)` band
(n=21) where min-recall is 0.4600 against best-recall 0.9881. Agreement is
a good **arbiter** and a weak **alarm** — and it costs both engines to
compute, so it can never save an invocation.

## Routing policies — `visual` only

`routing_experiment_visual.json`. Quality is the arm's real full-pipeline
score; cost is the arm's real engine-invocation count. A policy cannot
invent a quality it did not actually produce.

| policy | recall | char | invocations/doc | recall per invocation |
|---|---|---|---|---|
| P0 easyocr always | 0.6570 | 0.9577 | 1.00 | 0.6570 |
| P1 tesseract always | 0.9311 | 0.9715 | 1.00 | 0.9311 |
| P2 tesseract if low easyocr conf | 0.7223 | 0.9647 | 1.00 | 0.7223 |
| P3 tesseract if Vietnamese | 0.9117 | 0.9699 | 1.00 | 0.9117 |
| P4 fusion if disagree | 0.6747 | 0.9624 | 1.06 | 0.6358 |
| P5 composite risk | 0.9172 | 0.9787 | 1.16 | 0.7884 |
| P6 tesseract-first → fusion | 0.9438 | 0.9776 | 1.06 | 0.8893 |
| **P7 tesseract-first → easyocr** | **0.9438** | 0.9761 | **1.00** | **0.9438** |
| ORACLE best arm per document | 0.9560 | 0.9859 | 1.12 | 0.8517 |

P7: run Tesseract; where its own mean page confidence is below 0.90, run
EasyOCR *instead*. 46 documents Tesseract, 3 EasyOCR, **1.00 invocations
per document** — 98.7% of the oracle at single-engine cost. Stable across
thresholds 0.88–0.90; degrades above 0.92 as good Tesseract pages are
handed to the weaker engine.

**Scope discipline.** P7 is *the best measured `visual` routing policy*.
It is not the production number. Under `adaptive`, where only 6.3% of pages
reach OCR at all, P1/P6/P7 and the oracle all collapse to the same 0.9838
and the sweep cannot discriminate between them.
`routing_experiment_adaptive.json` is indicative only: it takes quality
from adaptive arms but signals from `agreement_analysis.json`, which is
computed on `visual` tokens that production would not have.

## Where the residual failures actually are

`cell_evidence_audit.py` asks, for each of the 81 strings a single-engine
arm failed to find, whether the text was ever recognized — comparing raw
OCR tokens against the assembled document, from artifacts already on disk.

| verdict | definition | n | share |
|---|---|---|---|
| **acquisition** | char recall in raw tokens < 0.90 — never read | 31 | 38.3% |
| **fidelity** (`ambiguous`) | ≥ 0.90 in raw *and* preserved into the final document, but not exact | 47 | 58.0% |
| **assembly** | ≥ 0.90 in raw, ≥ 0.15 worse in the final document — read and lost | **3** | **3.7%** |

In the fidelity bucket, 45 of 47 have final char recall *identical* to raw,
median raw char recall 0.957, and **0 of 47 are exactly present even in the
raw tokens**. Assembly preserved what the recognizer produced; the
recognizer got the last few characters wrong.

**This falsifies the working hypothesis that tiny table-cell text is lost
during assembly.** Across the six table-bearing documents, 18 missing
strings: 11 fidelity, 7 acquisition, **0 assembly**. Inspected directly,
`hc_tiny_cells_vi`'s cells under Tesseract contain `'Cai'`, `'iz'`,
`'Gái'`, `'T'`, `'+'` — the cells *are* populated, with garbage. That is a
recognition failure, not an ownership failure. Experiment 017 already
hardened `_fill_table_cell_text` and appears to have closed the ownership
gap it targeted.

All three genuine assembly losses are region-ordering under multi-column
scans, not cell assignment:

| arm | document | raw | final | labels |
|---|---|---|---|---|
| easyocr | `cmb_scan_multicol_en` | 0.966 | 0.655 | scan_quality, multi_column, reading_order |
| tesseract | `cmb_scan_multicol_en` | 1.000 | 0.655 | scan_quality, multi_column, reading_order |
| tesseract | `cmb_scan_tiny_vi` | 0.957 | 0.478 | scan_quality, tiny_text |

## Remaining failure boundary

Seven documents where **no arm** reaches 1.0:

| document | best any arm | labels |
|---|---|---|
| `hc_rotation_vi` | 0.3333 | rotation, reading_order |
| `hc_tiny_cells_vi` | 0.5714 | tiny_text, table_structure |
| `cmb_scan_multicol_en` | 0.6667 | scan_quality, multi_column, reading_order |
| `cmb_scan_tiny_vi` | 0.6667 | scan_quality, tiny_text |
| `cmb_tiny_table_en` | 0.8571 | tiny_text, table_structure |
| `cmb_scan_stamp_table_vi` | 0.8750 | scan_quality, stamp, occlusion, table_structure |
| `cmb_stamp_table_vi` | 0.8750 | stamp, occlusion, merged_cells, table_structure |

Plus: 3 documents fail `order_ok` in *every* arm (`hc_borderless_en`,
`cmb_borderless_lowcontrast_en`, `cmb_stamp_boundary_vi`) — untouched by
the line-band fix, which orders *within* a region and cannot order regions.
2 documents fail `tables_ok` (`hc_stamp_table_vi`,
`cmb_scan_stamp_table_vi`).

The oracle gap of 0.0122 (P7 0.9438 → oracle 0.9560) is entirely
`cmb_lowcontrast_stamp_vi`, where Tesseract is *confidently wrong*
(confidence 0.94, above every escalation threshold) while agreement drops
to 0.3906. No single-engine signal detects it.

---

# RESEARCH FREEZE — 2026-09-07

## Proven

Established by the authoritative artifacts above, on this corpus, at this
configuration.

- **Tesseract is a genuinely independent OCR source.** 70 of 226 strings
  are decided by one engine and not the other; the two disagree on 31.0% of
  strings. It shares no model lineage with EasyOCR (021/022).
- **Tesseract substantially improves Vietnamese extraction on this
  corpus.** `visual` Vietnamese recall 0.4747 → 0.9050 (+0.4303);
  `adaptive` 0.9310 → 0.9842. English is a wash (0.9214 → 0.9690).
- **Tesseract is dramatically cheaper than EasyOCR.** 20.8–25.3× on
  identical pages, CPU-only, measured with per-engine timers.
- **Always-both strategies are not justified by measured quality.** Every
  arm that pays for two engines is beaten on exact recall and perfect-document
  count by one engine alone: selection 0.9282, fusion 0.9026, union 0.8519
  against Tesseract's 0.9311, at 11–13× the wall time.
- **Page-wide confidence selection is not a valid production arbiter.**
  `selection` scores 0.9282 against 0.9311 for its own better source —
  −2 perfect documents for 13.3× the cost. Strictly dominated.
- **P7 is the best measured `visual` routing policy.** 0.9438 at 1.00
  invocations per document, 98.7% of the 0.9560 oracle. This is a `visual`
  result and is not the production number.
- **Production `adaptive` routing reaches the strongest cost/quality point
  measured in this milestone:** 0.9838 exact recall, 0.9941 char recall,
  46/49 perfect, 0 zero-recall, 15.3 s. This is a separate measurement from
  the `visual` policy sweep and is the production-shaped one.
- **`fusion_recovery` adds nothing over `fusion`.** Identical to four
  decimals on every metric in both strategies.
- **Residual failures are dominated by recognition, not assembly.**
  58.0% fidelity, 38.3% acquisition, 3.7% assembly; and 0 of 18 missing
  strings in table-bearing documents are assembly losses.

## Strong evidence

Consistent across every measurement here, but resting on one corpus.

- Tesseract-first should be the production OCR direction.
- EasyOCR should remain available as a secondary backend. The four
  geometric cases justify retention *because* the P7 escalation path makes
  it nearly free — 3 escalations in 49 documents, no both-engine default.
  Those four cases would not justify an always-both architecture.
- Confidence-based escalation is useful. Tesseract's own confidence
  correlates with its own recall at r = +0.7773 and is available after one
  engine has run, unlike cross-engine agreement.

## Not proven

- **Hallucination safety at production scale.** `must_not_contain`
  supervision covers **1 of 49 documents (2.0%), 2 of 112 pages (1.8%),
  2 of 226 supervision strings (0.9%)** — `hc_encoding_vi`, forbidden
  strings `'ЅoҖѸ'` and `'Йoa'`, both Cyrillic-homoglyph mojibake. Every
  `halluc 0` in this milestone means only *"no arm emitted those two
  strings on that one document."* Union and fusion, which concatenate
  evidence, are exactly the arms that would hallucinate, and this corpus
  cannot see it. **UNDER-MEASURED, not zero.**
- **Generalization beyond this 49-document / 112-page corpus.** Per-document
  deltas of ±0.02 rest on one or two documents. The four EasyOCR wins are
  four documents.
- **Superiority across arbitrary document domains.** The corpus is
  synthetic, Vietnamese/English, business-document shaped, 200 DPI.
- **That fusion can never be useful.** Fusion produced the only
  above-both-sources result in the milestone (`cmb_lowcontrast_stamp_vi`
  → 1.0000) and holds the best char recall alongside union. It is
  dominated *as a default*, not refuted as a mechanism.
- **That VLMs have no future role.** Not tested in this milestone.

## Attribution caveat — Change A and Change B

`_tokens_in_reading_order` (line-band ordering) and `to_tesseract_langs`
(`eng`-last) landed in the same change and were **never measured apart end
to end**. The pre→post delta of Tesseract 0.2222 → 0.9311 belongs to both.
Neither should be credited with the whole of it. The `eng`-last figure
(Vietnamese 0.7488 vs 0.9050) comes from an isolated backend-level
measurement recorded in `tesseract_backend.py`, not from a full-pipeline
A/B in this milestone.

A second correction: an earlier docstring on `_tokens_in_reading_order`
claimed the change was a no-op for one-token-per-line backends. It is not.
EasyOCR moved **0.6380 → 0.6570**, reproduced in two independent runs.
The docstring has been corrected to state what the function actually
guarantees.

## Reproducibility

- Interpreter: `~/.venvs/doc-extraction-gpu312/bin/python` (Python 3.12.14)
- Benchmark: `python run_ab.py --strategy {visual,adaptive} --device cpu`
- Offline re-scores:
  `python agreement_analysis.py --strategy visual`;
  `python routing_experiment.py --ab ab_{visual,adaptive}.json --out routing_experiment_{visual,adaptive}.json`;
  `python cell_evidence_audit.py`
- Tests: `pytest -q` → 329 passed, 10 skipped, 0 failed (three consecutive
  identical runs; no flakiness observed)
- Resource policy: both A/B runs `LIMITED_OR_PROTECTED`, recorded in
  `gpu_state_start` / `gpu_state_end` inside each result file
