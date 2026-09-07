# Proposal — 024: Table-cell evidence recovery

**Status: PROPOSED. Not started. No code written, no experiment run.**

## The hypothesis this proposal was asked to pursue, and why it changed

The milestone was expected to open as *"tiny text inside table cells is
recognized by OCR and lost during cell assignment; the intervention is
IR-side."*

`cell_evidence_audit.py` tested that offline against saved artifacts before
any new work was scoped, and **it does not hold**. Across the six
table-bearing documents, 18 strings were missed and **zero** were assembly
losses: 11 were recognized at ≥0.90 char recall and preserved intact into
the final document while still not matching exactly, and 7 were never read
at ≥0.90 at all. Inspected directly, `hc_tiny_cells_vi`'s table cells under
Tesseract are populated — with `'Cai'`, `'iz'`, `'Gái'`, `'T'`, `'+'`.
The cells own their tokens. The tokens are wrong.

Corpus-wide the same shape holds: of 81 missed strings, **3.7% assembly,
38.3% acquisition, 58.0% fidelity**. All three assembly losses are
region-ordering under multi-column scans (`cmb_scan_multicol_en`,
`cmb_scan_tiny_vi`), not cell assignment. Experiment 017 already hardened
`_fill_table_cell_text`, and this is consistent with 017 having closed the
ownership gap it targeted.

**So the §11 question — acquisition or ownership — is already answered from
completed artifacts: acquisition and fidelity, not ownership. The next
intervention is OCR-side, not IR-side.** This proposal is re-pointed
accordingly. The ownership investigation is retained, demoted, and scoped
to the three confirmed region-ordering cases.

## Objective

Recover the text that both recognizers currently get *nearly* right —
median 0.957 character recall, exact match failing — and the tiny-cell text
neither reads at all, using deterministic, CPU-cheap, OCR-side
interventions. Establish whether the residual is reachable without a new
model class.

## Investigation order

Re-ordered by measured share of the residual. The originally requested
sequence is preserved in the right-hand column so the change is auditable.

| # | line of investigation | evidence share | was |
|---|---|---|---|
| 1 | **Character fidelity**: what are the last 4.3% of characters? Diacritics, digit/letter confusion, punctuation, whitespace, or normalization? | 58.0% | (6) |
| 2 | **OCR token fragmentation**: does a cell's text arrive split across tokens whose join inserts or drops a separator? | part of 1 | (4) |
| 3 | **Acquisition on tiny glyphs**: segmentation mode (PSM), per-region re-OCR at native cell scale, orientation | 38.3% | (8) |
| 4 | **Ordering inside cells** and **geometry margins** — cheap to test, now known to be low-yield | ~0 measured | (5), (2) |
| 5 | **Token-to-cell assignment** and **row/column reconstruction** | 0 of 18 in table docs | (1), (3) |
| 6 | **Confidence-aware ownership** and **conflict detection** | untested | (6), (7) |
| 7 | **Region-level re-OCR**, only if 1–6 leave deterministic evidence insufficient | — | (8) |

VLM is explicitly out of scope for 024.

## Falsifiable experiment

**Question.** Are the residual table-cell and tiny-text failures reachable
by deterministic OCR-side intervention, or do they require a different
model class?

The prior question ("acquisition or ownership") is treated as answered;
this experiment re-verifies it as a control rather than re-litigating it.

**Baseline.** `ab_visual.json`, condition `tesseract`: exact recall 0.9311,
char recall 0.9715, 40/49 perfect, over 49 PDFs / 112 pages at 200 DPI, CPU,
`vie+eng`. Measured on the failure corpus below: **exact recall 0.6038,
char recall 0.8430**. Measured on the 42-document control: **exact recall
0.9857**.

**Exact failure corpus.** Frozen, 7 documents, named — no document is added
after results are seen:

| document | best any arm | primary class |
|---|---|---|
| `hc_rotation_vi` | 0.3333 | acquisition (orientation) |
| `hc_tiny_cells_vi` | 0.5714 | acquisition (tiny glyphs) |
| `cmb_scan_multicol_en` | 0.6667 | **assembly** (region order) |
| `cmb_scan_tiny_vi` | 0.6667 | **assembly** + acquisition |
| `cmb_tiny_table_en` | 0.8571 | fidelity |
| `cmb_scan_stamp_table_vi` | 0.8750 | fidelity |
| `cmb_stamp_table_vi` | 0.8750 | fidelity |

Held-out control: the remaining 42 documents, to detect regression.

**Primary metric.** Mean exact recall on the 7-document failure corpus,
full pipeline, same scorer as 023.

**Secondary metrics.** Char recall; perfect-document count; `order_ok`;
`tables_ok`; per-engine wall time and OCR invocation count; exact recall on
the 42-document control; and the acquisition/fidelity/assembly split from
`cell_evidence_audit.py` re-run after each intervention — an intervention
that moves char recall without moving the split has not addressed the
mechanism.

**Expected failure modes.**
- Per-region re-OCR at higher effective scale improves tiny cells and
  regresses normal text through over-segmentation.
- PSM changes help one document and hurt another — already observed:
  `psm=1` lifts `hc_rotation_vi` 0.0000 → 0.6667 while `psm_fixes_it` is
  `false` for all three tiny-cell documents (`regression_analysis.json`).
- Fidelity gains are real at char level and invisible at exact level,
  because exact match is all-or-nothing on 226 fixed strings.
- Whitespace/normalization changes move the metric without improving
  extraction — 0 of 47 fidelity strings are exactly present even in raw
  tokens, so some of the gap may be scorer-side and must be separated.
- Prior milestones report DPI escalation is not the answer; this is
  **inherited, not re-verified here**, and is worth one cheap re-check
  before any scale-based intervention is designed.

**Acceptance threshold.** Failure-corpus mean exact recall **≥ 0.75**
(from 0.6038, i.e. ≥ +0.146) with **no regression** on the 42-document
control (≥ 0.9807, i.e. Δ ≥ −0.005) and **no increase** in OCR invocations
per document above 1.10. Promote the intervention.

**Rejection threshold.** Failure-corpus mean exact recall **< 0.68**
(≤ +0.076) after lines 1–3 are exhausted, **or** any control regression
worse than −0.01 (< 0.9757). Record the boundary, stop, and escalate the
question to a different model class as a separate milestone.

Between 0.68 and 0.75: partial — promote only the per-document
interventions that are individually non-regressive, and re-freeze.

**Compute budget.** CPU only. No GPU: every intervention in lines 1–6 is
Tesseract-side or IR-side, and Tesseract runs at 0.69–0.74 s/page.
Estimated ≤ 45 min per full 49-document `visual` sweep (baseline 167.6 s for
Tesseract plus layout, which is cached), and ≤ 5 min per failure-corpus-only
iteration. Ceiling: **4 full sweeps and 30 failure-corpus iterations**. If
line 7 (region-level re-OCR) is reached, re-scope and re-budget before
running it. GPU policy: CLEAR not required, since nothing proposed uses the
GPU; if that changes, re-check before the run.

## Out of scope

VLMs. A third OCR engine. Production architecture changes. Anything
touching the `adaptive` router. All deferred until 024 returns a verdict.
