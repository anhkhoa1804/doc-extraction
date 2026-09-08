# 030 — Resolve H1 and H2 — Final Report

A causal falsification study, not a validation exercise. The goal at the
outset was to determine whether H1/H2 are SUPPORTED, REJECTED, PARTIALLY
SUPPORTED, or UNRESOLVED — not to confirm them.

Baseline: `d8f38f7f8980d899f34be5b0833afbbe9679011f` (029 frozen, pushed).
CPU-only, read-only throughout. GPU was PROTECTED (Research-No.1 PID 61016)
for the entire milestone and was never touched — nothing here needed new
extraction.

Labels: **FACT** (directly measured), **INFERENCE** (a conclusion drawn from
facts with a stated logical step), **HYPOTHESIS** (untested to
falsification), **PROJECTION** (a forward-looking claim explicitly not
backed by an experiment).

---

## 1. Scope

Resolve H1 and H2 exactly as stated in the frozen 029 report, to a formal
verdict, using direct source/IR/paired-artifact evidence. H3 is explicitly
out of scope per the user's instruction and is recorded only for lineage
continuity (`hypotheses.json`). No production code, no historical scorer,
no historical artifact was modified.

---

## 2. Exact H1/H2 definitions

**FACT**, extracted verbatim by `hypotheses.py` from
`experiments/029_deep_forensic_replay/FINAL_REPORT.md` §15 — not
reconstructed from memory. Full text in `hypotheses.json`.

**H1:** *stamp/occlusion artifacts near a table's true boundary increase the
likelihood that Table Transformer's detected `table.bbox` undershoots the
table's real extent, which increases both (a) how often tier-3 synthesis
fires and (b) how often a synthesized cell's raw token edge crosses that
same undershot boundary.*

**H2:** *because synthesized-row tokens must first pass
`_center_in(token, table.bbox)`, the maximum possible escape of any single
cell edge is bounded by that token's own bbox height/width — synthesis can
never attribute a token whose entire extent lies in a different table or a
different page region.*

---

## 3. Falsification design

**FACT.** `falsification_matrix.json` contains 8 rows (5 for H1, 3 for H2),
each a specific prediction with its evidence source, whether it is
observable from existing artifacts, the measured result, and whether it
supports or falsifies the hypothesis. Built AFTER resolution (§7–8), so
every row cites an actual measured number, never a plan.

H1's original discriminating experiment (IoU against 025-instrumented OCR
tokens) was restricted to SCAN-49. **ADAPTATION, declared explicitly:**
undershoot(table.bbox, union of the table's own cell bboxes) measures the
same underlying quantity (does the detector's bbox contain the evidence
attributed to it) and is computable on all 1,867 `table_transformer`
instances across 023–025, not only SCAN-49's fraction. H2's experiment was
run exactly as 029 specified — no adaptation needed.

---

## 4. Existing evidence (positive)

**FACT**, reproduced exactly against 029:

- Stamp/occlusion invalid rate: 29.31% (17/58) vs non-stamp 4.70% (85/1809)
  — `h1_resolution.json`, exact match to `backend_stratification.json`'s
  original numbers, confirming the re-derivation is faithful.
- 265 escaping cells re-derived from raw IR, exactly matching 029's
  `causal_attribution.json` total of 265 — `h2_resolution.json`.
- 0/1,867 tables show undershoot without a synthesized (confidence==0.5)
  cell present — `h1_resolution.json` §2.2, ruling out an
  independent-of-synthesis alternative mechanism.

---

## 5. Paired analyses

**FACT**, `paired_comparisons.json`, three natural pairings, no synthetic
data:

1. **Same document, same route, different OCR recognizer** (023/adaptive,
   6 recognizer arms). `hc_encoding_vi`: undershoot = 0.0px under EasyOCR,
   14.4–15.4px under fusion/fusion_recovery/selection/tesseract/union.
   Confounder: none — Table Transformer is confirmed backend-independent by
   its own module docstring (`table_backend.py:1-14`), so recognizer
   differences can only act through which text corroborates tier-3
   synthesis. This is the cleanest, most discriminating natural experiment
   in the whole study.
2. **Same document, adaptive vs. visual routing** (table_transformer subset
   only, 6 pairs). 100% sign-concordant. Confounder: routing determines
   *whether* table_transformer runs at all; restricted to cases where both
   modes happened to invoke it.
3. **Same document, across milestones** (023→024→025, adaptive route).
   `hc_encoding_vi`, `hc_scan_en`, `hc_scan_vi` show stable behavior across
   milestones — not milestone-specific noise.

---

## 6. Negative evidence

**Not buried.** `negative_evidence.json`, 20 items, presented at full weight
alongside positive evidence:

- **41/58 (71%) stamp/occlusion instances show ZERO undershoot** — H1's
  implicit sufficiency reading is directly falsified by more than two
  thirds of its own predicted-positive population.
- **38/1809 (2.1%) non-stamp instances show undershoot >10px**, tracing to
  7 distinct documents with no stamp/occlusion label — the mechanism
  clearly operates independent of the labeled condition, at magnitudes
  including the single largest in the corpus (15.40px, `hc_encoding_vi`
  under `union`).
- **The single strongest negative item:** stamp/occlusion nonzero
  magnitudes (`{1.10, 1.47}px`) are smaller, not larger, than non-stamp
  nonzero magnitudes (up to `15.40px`) — the opposite of H1's severity
  prediction.
- **2 of 025's 3 named picture-gated documents never reach
  table_transformer in any replayed arm** — H1's test population and 025's
  gated-table population are almost disjoint by construction, meaning H1 as
  tested cannot speak to the corpus's most severe stamp/occlusion cases.
- **H2:** 100% of escaping-cell pages have zero other tables — the
  contamination test's precondition never co-occurs with the defect in this
  corpus (though the precondition exists elsewhere, §9).

---

## 7. H1 resolution

**Verdict: PARTIALLY_SUPPORTED, confidence MEDIUM.** Full detail in
`h1_resolution.json` and `verdicts.json`.

### 7.1 Document-level recurrence
**FACT.** 36 distinct documents ever produce a `table_transformer` table;
26/36 are deterministic (always or never show undershoot), 9 vary by arm
(driven by recognizer, §5.1). The stamp/occlusion population is **4
distinct documents** (58 arm-instances); the non-stamp-with-undershoot
population is **7 distinct documents**. **Both are too small for a strong
population-level statistical claim** — every number in this section should
be read as "true of these specific documents," not generalized further.

### 7.2 Component attribution
**FACT.** Mean undershoot with synthesis present: 2.076px. Without: 0.0px
(0 exceptions across 1,867 tables). Synthesis is **NECESSARY** for
undershoot to manifest, on this corpus.

### 7.3 Counterfactual
**FACT**, read-only. 1,765/1,867 (94.5%) tables already show zero
undershoot with no intervention needed. §13 (counterfactuals) explores what
would repair the remaining 102.

### 7.4 Mechanism test
**INFERENCE**, classified precisely: synthesis is **NECESSARY but not
SUFFICIENT**; stamp/occlusion is a **CORRELATED condition that elevates
rate**, not a deterministic trigger, and not (on this evidence) the
dominant one — OCR-recognizer choice (§5.1) is an equally well-demonstrated
trigger not named in H1's original statement.

### 7.5 Boundary test
**FACT**, two directions, both recorded:
- H1 predicted defect, didn't occur: 41/58 stamp/occlusion instances,
  0px undershoot.
- H1 predicted no defect (or weaker), it occurred at larger magnitude: 38
  non-stamp instances, up to 15.40px.

---

## 8. H2 resolution

**Verdict: SUPPORTED, confidence HIGH.** Full detail in `h2_resolution.json`.

**FACT.** All 265 escaping cells (re-derived directly from source IR, exact
match to 029's count) tested against every other table on their page:
**0 intersect.** 100% of the 102 affected pages have zero other tables —
the precondition for contamination literally does not co-occur with the
defect anywhere in this corpus.

**FACT.** This is not a vacuous result: 25 same-page multi-table instances
exist elsewhere in the corpus (1 document, `ord_technical_report_en`,
replicated across arms) — the precondition for H2's adversarial scenario is
real and present in the data, just never co-located with an escaping cell.

**FACT.** The evaluator itself was validated (§14, control H2-2): a
deliberately constructed synthetic case with a real cross-table
contamination was correctly flagged, proving the null empirical result is
not a broken-checker artifact.

**INFERENCE.** The primary evidentiary basis for H2 is the geometric
argument in its own statement — center-containment at admission
mathematically bounds edge escape by the admitted token's own dimension —
corroborated, not independently proven, by the empirical zero-contamination
result.

---

## 9. H1/H2 dependency

**FACT/INFERENCE**, `orthogonality.json`. H1 and H2 are **NESTED, not
orthogonal**: H2's precondition (an escaping cell exists) is definitionally
the same event as "H1's mechanism fired." The classical 2×2 independence
test breaks down — the quadrant "H1 false, H2 true/false" is **undefined**,
not merely unobserved, since H2 has no truth value where no cell ever
escaped. H1 asks *when/how much* the mechanism activates; H2 asks *given
activation, how far can it reach*. **Recommendation followed:** not merged
— they have different evidence, different falsification conditions, and
different production implications — but their shared root
(`base.py:505-576`) is recorded explicitly rather than treated as
coincidence.

---

## 10. Exact source provenance

**FACT**, `provenance.json`, 7 claims, each with file/function/line
range/condition, two independently re-verified by direct grep this
milestone (not merely cited from 029):

- `_center_in`, `base.py:161-164` — center-only containment predicate.
- Token admission to synthesis, `base.py:516-518` — same predicate applied
  against `table.bbox`.
- `MIN_CORROBORATING_COLUMNS = 2`, `base.py:394`.
- Synthesized cell bbox from raw token min/max edges, `base.py:559-567`.
- Synthesis marker `confidence=0.5`, **`base.py:567`** (corrected from
  029's report, which cited line 568 in one place — re-verified by direct
  grep this milestone: exactly one hit, line 567).
- `table.bbox` never reassigned in the synthesis function body — **re-
  verified this milestone** by grepping lines 505-580 for `table.bbox =`:
  zero hits, confirmed directly rather than trusted from 029's citation.
- `_renumber_rows_by_position`, `base.py:460-478` — fixes row/col values,
  does not touch cell bbox (confirmed by reading the function body: no
  bbox mutation).

---

## 11. Mechanism vs. symptom

**FACT/INFERENCE**, `severity_impact.json`. Five-level classification, per
the milestone's explicit discipline against overclaiming "root cause":

| level | classification | confidence |
| --- | --- | --- |
| Symptom | `cells_within_table_bbox` fails; invisible to Layer 1 | FACT |
| Immediate mechanism | tier-3 synthesis builds cell geometry from raw token edges after center-only admission | FACT, code-traced |
| Upstream mechanism | Table Transformer's own detected bbox undershoots the table's true extent | FACT that undershoot correlates with synthesis; INFERENCE that detector bbox specifically (vs. some other property) is why |
| Trigger | OCR-recognizer choice (proven); stamp/occlusion labeling (partially supported, rate only) | INFERENCE, PARTIALLY SUPPORTED |
| Root cause | **NOT CLAIMED** — would require inspecting Table Transformer's own model internals (confidence/attention), not done this milestone or in 029 | — |

---

## 12. Counterfactual analysis

**FACT/INFERENCE**, read-only, `counterfactuals.json`. Three intervention
candidates, none implemented:

- **A — expand `table.bbox` to the union of its own cells.** Simulated:
  102/1,867 tables' bbox would change; 0 new failures created on any other
  check. Risk LOW (no identified consumer depends on detector-original
  extent — same grep-based consumer search 026 performed). Preserves all
  evidence, consistent with L5's design precedent.
- **B — require full-bbox (not center-only) containment for admission.**
  **NOT safely simulable to completion** — the original OCR tokens are not
  retained in the IR, so the counterfactual cannot be fully computed from
  stored artifacts. Flagged as MEDIUM-HIGH risk: would discard the 265
  cells' text entirely, contradicting L5's "recover, never discard"
  principle this whole lineage protects.
- **C — keep detector bbox as-is; exclude `confidence==0.5` cells from the
  `cells_within_table_bbox` check specifically.** An evaluation-layer
  change only (parallel to 027's Layer-1/Layer-2 split), zero production
  risk, fully simulable: would raise structural validity from 94.5% to
  100.0% on this population without touching `src/` at all.

---

## 13. Severity/impact

**Distinguished FACT / INFERENCE / PROJECTION** per the milestone's
explicit requirement — no RAG/GraphRAG numbers invented.

- **Frequency (FACT):** 102 table instances, 9 distinct documents, 5.46%
  of 1,867 `table_transformer` instances.
- **Severity (FACT):** bounded, 1.1–14.4px at 200 DPI; 0/265 cross-table.
- **Effect on text (FACT):** none — 026 already proved text multiset is
  identical regardless of geometry.
- **Effect on structure (FACT):** none on row/col values (correct on
  1867/1867 via `_renumber_rows_by_position`); only `Cell.bbox` vs.
  `Table.bbox` containment is affected.
- **Effect on provenance (INFERENCE):** a consumer trusting `Table.bbox`
  for cropping/highlighting/citation display would draw a box excluding
  1–2 real rows of that table's own content.
- **Effect on RAG retrieval (PROJECTION, no experiment run):** only
  relevant if a system chunks by `Table.bbox` region rather than cell text;
  cell-text-based retrieval is unaffected.
- **Effect on GraphRAG (PROJECTION, no experiment run):** no GraphRAG
  extraction experiment exists in this repository to project onto; a
  first-order guess (LOW impact, since row/col/text are unaffected) is
  explicitly **not** evidence-backed and should not be treated as a
  finding.
- **Production observability (FACT):** currently zero outside 028's
  research-only `structural_integrity` view.

---

## 14. Measurement limitations

**FACT**, `adversarial_controls.json`, 10 new synthetic cases (5 H1, 5 H2),
each testing a prediction rather than code coverage — **10/10 passed**.

The single most important control is **H2-2**: a deliberately constructed
case placing an escaping cell so it *does* land inside an adjacent table.
This is not a test of H2 — it is a test of whether `resolve_h2.py`'s
checker would have caught H2 being false if it were. It passed, which is
what makes §8's "0/265 contaminated" result trustworthy rather than
suspicious.

Other limitations, stated plainly:
- Both H1's stamp/occlusion sample (4 documents) and its notable-non-stamp
  sample (7 documents) are too small for population-level statistical
  claims.
- H1's adapted discriminating test (undershoot vs. own-cell-union) is a
  reasonable proxy for the original SCAN-49-only IoU proposal but is not
  identical to it — declared explicitly in §3, not silently substituted.
- No pixel-level inspection of Table Transformer's own confidence/attention
  was performed — the "detector uncertainty" clause of H1 is untested at
  the model-internals level.
- Combined with 029's own limitations (unchanged, not re-litigated here):
  no cross-table contamination scenario currently exists in the corpus at
  all to test H2 against a real positive case.

---

## 15. Priority reassessment

**FACT/INFERENCE**, `verdicts.json`. 029's recommendation — table-label
gating under stamp/occlusion (025's Class D) is the highest-value next
research target — was re-evaluated against every criterion 029 used
(frequency, severity, causal confidence, fixability, regression risk,
production impact) in light of H1/H2's resolution.

**Verdict: SAME PRIORITY, reasoning partially revised.** H2 SUPPORTED
removes the one scenario (contamination found) that would have elevated
row-synthesis above gating. H1 PARTIALLY_SUPPORTED weakens the specific
stamp/occlusion→row-synthesis causal story but does not touch gating
itself, which is a structurally separate code path (`base.py:747`, a
label-equality test) from tier-3 synthesis (`base.py:505-576`). One
concrete revision: if tier-3 synthesis is ever fixed independently of the
gating question, it should not be motivated primarily by "this mainly
affects stamp/occlusion documents" — that framing is now only partially
supported; OCR-recognizer choice is an equally demonstrated trigger.

---

## 16. Final verdicts

### H1 — PARTIALLY_SUPPORTED (confidence MEDIUM)
Rate-elevation on stamp/occlusion confirmed exactly (29.31% vs 4.70%,
matching 029). Severity-direction prediction contradicted (stamp/occlusion
magnitudes smaller, not larger). Strongest evidence:
`h1_resolution.json:h1_core_test` + `2_2_component_attribution`. Strongest
counterevidence: `h1_resolution.json:critical_caveat_pseudo_replication` +
`paired_comparisons.json` pairing 1. What would change the verdict:
pixel-level Table Transformer confidence data, or a larger stamp/occlusion
sample than this corpus's 4 documents provide.

### H2 — SUPPORTED (confidence HIGH)
Zero cross-table contamination across all 265 re-derived escaping cells;
evaluator independently proven capable of detecting it if present.
Strongest evidence: `h2_resolution.json:H2_CORE_RESULT` +
`adversarial_controls.json` case H2-2. Strongest counterevidence:
`h2_resolution.json:same_page_multi_table_precondition_check` (the specific
adversarial co-occurrence was never naturally testable in this corpus).
What would change the verdict: a corpus example with a stamp/occlusion
table immediately adjacent to a second table — none currently exists here.

---

## 17. Surviving open questions

- Why does OCR-recognizer choice gate tier-3 synthesis firing on
  `hc_encoding_vi` specifically — is it about which recognizer reads the
  header/footer text near the missed row, or something else about how
  EasyOCR vs. Tesseract-family recognizers segment that region? Not
  investigated this milestone.
- Does Table Transformer's own confidence score correlate with bbox
  undershoot magnitude? Would directly test the "detector's own
  uncertainty" clause of H1. Requires inspecting model output this
  milestone did not access.
- H3 (reading_order blindness co-occurring with table-label gating)
  remains unresolved, explicitly out of scope here.
- Does the row-synthesis mechanism (now well-characterized) interact at
  all with table-label gating (025's separate mechanism) on any single
  document? Not checked — the two were treated as structurally
  independent code paths based on their source locations, but this was
  not empirically cross-tabulated.

---

## 18. Recommended Milestone 031

**RECOMMENDATION.** Two candidates, not both:

1. Resolve H3 (does the reading_order blind spot co-occur with table-label
   gating failure specifically, or is it independent) — read-only,
   low-risk, directly continues 029's unfinished hypothesis set, and its
   outcome bears on whether a single gating fix would address two observed
   defects at once, as §15's priority reassessment still projects.
2. If a production fix is eventually desired for the row-synthesis defect
   despite its LOW severity (§13), Intervention C from §12
   (exclude synthesized cells from `cells_within_table_bbox` at the
   evaluation layer) is the only zero-risk, fully-simulated candidate ready
   for implementation as a *separate, controlled* milestone — not proposed
   for immediate action here.

**Recommended: (1).** It is the more direct continuation of the falsified/
partially-falsified hypothesis chain this milestone and 029 built, and,
per §15, table-label gating remains the priority target this repository's
research lineage has consistently pointed toward since 025.
