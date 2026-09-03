# 019 — OCR-Grid Table Detection Under Occlusion: a decisive negative result

## Baseline

`git rev-parse HEAD` at start: `31fc820`. `pytest -q`: 303 passed, 10
skipped, 1 pre-existing flaky failure (confirmed unrelated across three
consecutive milestones now — noted, not chased). GPU preflight **CLEAR**
before every one of the 5 GPU-using commands this milestone ran.

Reproduced `cmb_scan_stamp_table_vi`'s failure fresh (not reused from
memory): Docling's layout labels the whole table area `picture` (no
`table`-labeled region at all), Table Transformer's own standalone
whole-page detector's best candidate for the real table area scores
**0.267–0.272** against the configured 0.7 threshold — genuinely present,
genuinely low-confidence, not absent.

**No production code was changed this milestone.** The finding below is
decisive enough that nothing was promoted to `src/`.

## OCR Structural Signals

Built `table_candidate.py` (`experiments/019_ocr_grid_table_detection/`,
deliberately kept out of `src/` — see Promotion Decision): row clustering
by mutual y-overlap (same primitive as `order_recovery`'s line
clustering), then column clustering by x-overlap *across rows* — a
"column" is an x-range that recurs in at least 2 different rows, which
correctly excludes a single wide paragraph token (one row only) from
being counted as a column.

## Candidate Detector

Score = `min(1, (rows-1)/4) × min(1, cols/3) × row_height_regularity ×
max(coverage, 0.3)` — requires structural repetition (≥3 rows, ≥2
recurring columns) **and** regularity/coverage together, not either
alone. Thresholds were read off real measured distributions (below), not
picked first and tested after.

## Positive / Negative Results

Real documents, actual OCR tokens (not synthetic):

| document | rows | cols | regularity | coverage | **score** | ground truth |
|---|---|---|---|---|---|---|
| `cmb_scan_stamp_table_vi` (target, occluded) | 4 | 4 | 0.876 | 0.813 | **0.534** | real table |
| `ord_invoice_png_vi` (TT already succeeds) | 4 | 5 | 0.899 | 0.850 | **0.573** | real table |
| `hc_scan_vi` (plain letter) | 6 | 0 | — | — | **0.0** | not a table |
| `hc_scan_en` (plain letter) | 4 | 0 | — | — | **0.0** | not a table |
| `cmb_scan_multicol_en` (2-column policy prose) | 3 | 2 | 0.486 | 1.0 | **0.162** | not a table |

**OBSERVED**: on this real sample, the two real tables (0.53–0.57) sit
well clear of the hardest real negative (0.16, 3.5× lower) and the two
plain-letter negatives (0.0 — Docling's own paragraph merging left too
few, too-coarse tokens for any column pattern to even form).

**INTERPRETATION at this point** (revised below): a threshold around
0.3 looked like it would cleanly separate tables from prose on real
corpus data.

## Adversarial Cases

This is where the design was tested to destruction, per instructions —
and it failed:

| synthetic case | rows | cols | regularity | coverage | **score** |
|---|---|---|---|---|---|
| aligned bullet list (marker + variable-length text) | 6 | 2 | 1.0 | 1.0 | **0.667** |
| well-aligned key:value form fields | 5 | 2 | 1.0 | 1.0 | **0.667** |
| regular 3-column prose (evenly wrapped) | 8 | 3 | 0.801 | 1.0 | **0.801** |
| tab-separated field rows | 5 | 3 | 1.0 | 1.0 | **1.0** |

**OBSERVED**: every adversarial case scores **at or above** the real
target table's 0.534 — the bullet list and form both score 0.667, the
regular 3-column prose scores 0.801 (higher than either real table), and
tab-separated rows saturate at 1.0.

**Root cause, confirmed not a tuning artifact**: inspected the bullet
list's own column bands directly — `[(50,65), (80,205)]`. The bullet
marker (x=50–65) and the item text (x starting at 80, width 130–205)
cluster into a real "column" because a *consistent left edge* is
sufficient evidence under x-overlap clustering, and that is exactly what
any left-aligned list, indented paragraph, or form label also has. This
is a structural ambiguity in the signal itself — cranking a threshold
cannot fix it, because the real target table (0.534) sits *below* three
of the four adversarial scores, not above them. Any threshold that
admits the real table also admits the bullet list and the 3-column
prose.

**INTERPRETATION**: the real-corpus negative sample (§ above) was not
representative. Real prose in this corpus scores near-zero specifically
because Docling merges it into 2–3 huge paragraph blocks (an artifact of
*that* text being ordinary, unfragmented prose) — not because tables
have a distinctive geometric signature prose lacks. The moment text is
genuinely column-regular for a non-table reason (a list, a form, evenly
wrapped multi-column text), the signal cannot tell the difference.

**LIMITATION**: adversarial cases are synthetic (no scanned image
rendered); this is a geometry-only test of the scoring function, not an
end-to-end pipeline test of whether Docling would ever actually emit
this exact token shape for a real bulleted list. It is enough to
disprove the scoring function's safety, which is what it was built to
test.

## Table Transformer Comparison

Not run as a formal A/B/C (Table Transformer alone vs. OCR-grid alone vs.
combined) across a corpus — the adversarial result above already
disqualifies "OCR-grid alone" from being a safe standalone detector, so
comparing its corpus-wide precision/recall against Table Transformer's
would answer a question already settled in the negative. What *was*
tested is a single real end-to-end trial of the combined idea (next
section).

## Combined Strategy

Tested directly on the one real case available: fed the OCR-grid
candidate bbox (constructed only from the `picture`-labeled layout
region + real OCR tokens) into Table Transformer's **own, unmodified**
structure-recognition model (`_recognize_structure` — the same function
Table Transformer already runs everywhere else; no new model, no
duplicated logic) instead of its own low-confidence whole-page detection
box.

**OBSERVED**: this genuinely works better geometrically — the structure
model, given a good crop, found a 2-row/4-column grid (undercounting
rows again, `_fill_table_cell_text`'s tier-3 synthesis from milestone
017 then recovered a 3rd row unchanged, no new code). But:

```
r0c0 'Sản phẩm A-100'    r0c1 ''             r0c2 '2'    r0c3 '18.000.000'
r1c0 'Bộ lọc khí Mã 22B' r1c1 'CÔNG TY TNHH' r1c2 ''     r1c3 '6.400.000'
r2c0 'Dịch vụ lắp đặt'   r2c1 'ĐÃ DUYỆT'      r2c3 '3.500.000'
```

**`r1c1` and `r2c1` contain stamp text** ("CÔNG TY TNHH", "ĐÃ DUYỆT") —
not orphaned tokens milestone 017's corroboration-gated tier 3 would
catch, but text sitting inside a cell the structure model *itself*
placed a real boundary around, filled via ordinary tier-1 center
containment. Geometric containment has no way to know that boundary
happens to sit over a stamp rather than real unit-column data.

**INTERPRETATION**: this is a **different contamination mechanism** than
the one milestone 017 defended against. 017's corroboration requirement
protects against *inventing* a row from spatially-coincidental orphaned
tokens; it does nothing when the structure model *legitimately* detects
a cell whose interior happens to contain foreign ink. This is exactly
the class of defect `pymupdf_table_backend`'s `table_quality.assess_table`
gate already exists to catch (style/content-outlier signals) on the
native-PDF path — and confirms, a second time this milestone, that this
gate is not wired to the Table-Transformer/OCR path at all (first
observed in milestone 017's Verification section).

## Stamp Safety

**Not achieved.** The one real end-to-end trial produced stamp
contamination, caught only indirectly: `Table.confidence` was downgraded
to 0.5 (SUSPICIOUS) — but *because* a row was synthesized, not because
stamp text was detected in a cell. `verify_document()` correctly tells a
consumer not to fully trust this table, but for a reason that happens to
be true rather than the reason that is actually true. Recorded honestly
as a near-miss safety outcome, not a real one.

## Cell Ownership

`_fill_table_cell_text` (milestone 017) was reused **unmodified** — no
duplication, per instructions. It performed exactly as designed: tier 1
(plain containment) filled the stamp-contaminated cells because they are
genuinely, geometrically contained by cells the structure model itself
created; tier 3 (corroboration-gated synthesis) correctly recovered the
undetected 3rd row without any stamp leaking into *that* mechanism
specifically. The contamination in this trial is not a 017 regression —
it is upstream, in what geometry gets handed to `_fill_table_cell_text`
in the first place.

## Verification

`Table.confidence` / `verify_document()` (wired in milestone 017) did
fire — SUSPICIOUS, not silently TRUSTED — confirming that pipeline still
provides a partial safety net even when this milestone's own new
mechanism introduces contamination. The gap: the recorded reason
(`"synthesized 1 row(s)..."`) does not name the actual problem (stamp
content in an existing cell). Closing that gap would mean wiring
`table_quality.assess_table`-style content/style checking to this path —
already identified as the right next step in milestone 017, reconfirmed
here with a second concrete failure mode motivating it.

## Performance

Pure Python, no model: 0.50 ms/call on the real 18-token document
(2000-iteration microbenchmark), 20.0 ms/call under a 180-token stress
test (10× the real token count) — the row/column clustering is
single-linkage, O(n²) worst case, so cost grows faster than linearly
with token count. Cheap for this corpus's realistic case sizes;
worth flagging as a scaling caveat for any future, denser use.

## Production Corpus

**Not re-run.** No `src/` code changed this milestone (the standalone
detector was rejected before reaching production, and the combined-
strategy trial used existing code paths only for one manual, offline
test — never wired into `pipelines/base.py` or any config). The 58-
document corpus ranking from milestone 018 stands unchanged; re-running
it would measure nothing new.

## Updated Failure Ranking

Unchanged from milestone 018 (re-stated, not re-derived, since nothing
that would move it changed):

```
scan_quality        n=6 (now partially addressed: order_recovery, EXPERIMENTAL)
borderless_table     n=2
table_detection       n=2 (cmb_scan_stamp_table_vi remains unresolved --
                            this milestone's own target, still open)
tiny_text            n=1
table_structure       n=1
```

`cmb_scan_stamp_table_vi`'s table-detection failure is **still open**.
This milestone determined *why* the obvious cheap fix doesn't work
safely, which is real progress on the research question even though the
production failure itself is unchanged.

## VLM Decision

Per the instructions' own rule: "Can deterministic evidence recover the
stamp-over-table case? If YES: NO VLM." The answer here is genuinely
mixed, and the mixed answer itself resolves the question. Deterministic
evidence **can** geometrically locate the table (the OCR-grid candidate
bbox is good, and Table Transformer's own structure model can build a
grid from it). What deterministic evidence **cannot** yet do safely is
distinguish real cell content from overlay content sitting inside a
legitimately-detected cell — but the tool for that (`table_quality`'s
style/content-outlier gate) already exists in this codebase, just
unwired to this path. **This is an integration gap, not a capability
gap** — the missing piece is deterministic and already built, not visual
semantic reasoning a VLM would supply. **No VLM experiment is justified
by this milestone's evidence.**

## Promotion Decision

No hedging, per instructions:

| | decision |
|---|---|
| **OCR-GRID TABLE CANDIDATE DETECTOR (standalone)** | **REJECT** |
| **OCR-grid candidate → Table Transformer structure model (combined)** | **REJECT for production; kept as a documented, evidenced research direction** |

**REJECT**, not EXPERIMENTAL, for the standalone detector: this is not
"insufficient evidence yet" (milestone 014/018's EXPERIMENTAL bar) — it
is *demonstrated unsafe* on adversarial geometry that real documents
plausibly contain (bulleted lists and forms are common), with a decisive
negative result at the design-validation stage, not the deployment
stage. No amount of threshold tuning fixes it, per the direct
measurement above (every adversarial case scores at or above the real
target).

The combined strategy (OCR-grid bbox feeding Table Transformer's own
structure model) is more promising geometrically — it correctly located
and structured the real table where nothing existed before — but its
one real trial produced genuine stamp contamination that the existing
safety net catches only by accident (right verdict, wrong reason). Not
promotable without the `table_quality`-style content gate wired to this
path first; recorded as the concrete precondition for revisiting this,
not as "maybe someday."

## Research Implication

Directly answers this milestone's stated research question:

> Can heterogeneous weak structural signals recover document structure
> when a specialized detector becomes uncertain?

**Partially, and the partial answer is the interesting part.** Weak
geometric signals (row/column recurrence) *can* recover structural
*location* — the OCR-grid candidate bbox was good, better in fact than
Table Transformer's own best sub-threshold candidate (which missed the
price column entirely). But geometric signals alone cannot resolve
*ownership* — the question of whether content inside a structurally
correct cell actually belongs there — which is a content/style question,
not a position question. This is the same distinction milestone 017's
own commit message drew from `pymupdf_table_backend`'s history
("ownership removes interleaving; it cannot remove contamination... the
residual belongs to a gate") — now shown to hold on an entirely
different backend and failure mechanism, which is stronger evidence for
it being a general property of this problem, not a quirk of one code
path.

## What We Should NOT Build

* A generic table-candidate-detection framework — the standalone
  detector is rejected; building infrastructure around a rejected
  mechanism would be pure waste.
* A learned classifier to distinguish tables from lists/forms
  geometrically — the instructions' own constraint ("do not add a new
  model unless the evidence forces it") is not met: the actual missing
  piece is a content/style gate that already exists in this codebase.
* Any VLM work for this case — the gap is an integration gap, not a
  capability gap, per the VLM Decision section.

## Next 3 Actions

1. **Wire `table_quality.assess_table`'s style/content-outlier signals to
   the Table-Transformer/OCR path** — named as the right next step in
   milestone 017, now reconfirmed by a second, independent contamination
   mechanism found this milestone. This is the actual fix for stamp
   safety, not a smarter detector.
2. **If the content gate closes the contamination risk**, the combined
   strategy (OCR-grid bbox → Table Transformer structure model) becomes
   revisitable — re-run this exact trial with the gate in place and
   check whether `r1c1`/`r2c1` get correctly flagged or excluded.
3. **Do not revisit standalone OCR-grid detection** without a
   fundamentally different signal (visual ruling-line/border detection,
   or a genuinely content-aware feature) — this milestone's adversarial
   evidence is a closed question, not an open one to retry with
   different weights.

## Reproduce

```bash
python -c "
import sys; sys.path.insert(0, 'experiments/019_ocr_grid_table_detection')
from table_candidate import Tok, detect_table_candidate
# see README tables above for the exact token sets used
"
```

Raw captured data: `cmb_scan_stamp_table_vi_raw.json`,
`negative_positive_raw.json` (both real corpus documents' layout regions,
OCR tokens, and Table Transformer's own raw detection candidates).
