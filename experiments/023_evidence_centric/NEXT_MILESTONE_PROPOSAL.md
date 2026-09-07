# Proposal — 024: OCR fidelity / acquisition recovery

*(Renamed. This milestone was scoped as "table-cell evidence recovery"
until the audit below falsified the hypothesis that named it. The old title
described a problem the evidence says is not there.)*

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

## Research question

> Can OCR-side intervention recover residual failures without sacrificing
> the strong Tesseract quality/cost advantage?

The "without sacrificing" half is not decoration. Tesseract's value in 023
is that it is simultaneously more accurate and ~20x cheaper on this corpus;
an intervention that recovers the residual by making the cheap engine
expensive has not solved the problem this milestone exists to solve. Cost
is therefore an acceptance criterion below, not a footnote.

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
| 1 | **Character fidelity** — what are the last 4.3% of characters? Diacritics, digit/letter confusion, punctuation, whitespace, or normalization | 58.0% | (6) |
| 2 | **Token fragmentation** — does a cell's text arrive split across tokens whose join inserts or drops a separator | part of 1 | (4) |
| 3 | **Acquisition of tiny glyphs** — segmentation mode (PSM), per-region re-OCR at native cell scale | 38.3% | (8) |
| 4 | **Orientation** — OSD is already available and already diagnostic (`hc_rotation_vi`: `Rotate: 90`, `psm=1` lifts 0.0000 → 0.6667) | 1 document, worst absolute score | (8) |
| 5 | **Ordering** — inside cells, and region ordering under multi-column scans (the 3 confirmed assembly losses) | 3.7% | (5) |
| 6 | **Ownership / row-column reconstruction** — token-to-cell assignment, geometry margins, confidence-aware ownership, conflict detection. **Only if evidence from 1–5 warrants it**; 023 found 0 of 18 table-document failures here | 0 measured | (1), (2), (3), (7) |
| 7 | **Region-level re-OCR** — only if 1–6 leave deterministic evidence insufficient | — | (8) |
| 8 | **VLM** — only if deterministic OCR-side recovery reaches a *proven* capability boundary, i.e. the rejection threshold below is hit with 1–7 exhausted and documented | — | (new) |

Line 8 is a gate, not a plan: VLM is out of scope unless 1-7 are exhausted
and the rejection threshold is met. Reaching it is a finding in itself and
should be recorded before any VLM work is scoped.

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

A third OCR engine. Production architecture changes, including implementing
P7. Anything touching the `adaptive` router. VLM, except through the line-8
gate above. All deferred until 024 returns a verdict.

## Threshold integrity

The baseline and the acceptance/rejection thresholds above were computed
from `ab_visual.json` before any 024 work began, and are frozen. They must
not be adjusted after results are seen.
