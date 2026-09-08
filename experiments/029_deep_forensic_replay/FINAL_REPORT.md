# 029 — Deep Forensic Replay & Causal Attribution — Final Report

Baseline: `b9b87d1be5edc4238140c2342661ef4121912378` (028 frozen). CPU-only,
read-only replay over existing frozen artifacts of 023–025. GPU was
PROTECTED throughout (Research-No.1 PID 61016, 100% util) and was never
touched — nothing in this milestone required new extraction.

Labels used throughout: **FACT** (directly measured from source/IR/data),
**INFERENCE** (a conclusion drawn from multiple facts with a stated logical
step), **HYPOTHESIS** (not yet tested to falsification), **RECOMMENDATION**
(an action, not a claim about the world).

---

## 1. Executive finding

**FACT.** 028's discoveries generalize completely, and a full causal chain
was found for the largest one. All **102 of 102** structurally-invalid table
instances across every replayed arm (023–025) — not a sample, the entire
population — are produced by one exact, previously undocumented interaction
between two independent pieces of production code: tier-3 row synthesis
(`pipelines/base.py:505-576`, part of 024's L5/table-recovery lineage) and
the center-point containment test `_center_in` it reuses. The defect is
small (1.1–14.4px escape at 200 DPI, always carrying the synthesis marker
`confidence == 0.5`) and currently invisible to every existing metric.

**FACT.** Layer 1's order metric has a third, previously uncharacterized
blind spot: it never reads `Page.reading_order`, only raw element-list
order. 19 document-arm pairs exist where this produces a false result —
list order coincidentally monotonic while the actual computed reading order
is not.

**INFERENCE.** These two findings, plus 025's table-label gating finding,
converge on stamp/occlusion documents specifically: **INFERENCE**, table
gating failure → scattered text elements → `compute_reading_order`'s
column-banding heuristic (designed for prose columns, not shattered table
grids) produces a genuinely wrong sequence for them → Layer 1 cannot see it
because it never reads that sequence. One root cause, three observable
symptoms, only the last of which any prior milestone measured.

---

## 2. Cohort inventory

**FACT**, from `cohort_inventory.json`, ground-truthed against each
generator script's own `CORPUS`/manifest constant (not inferred from
document-id overlap — verified that the 51-document SCAN-49 manifest is a
byte-subset of the 58-document production-corpus manifest, so ID membership
alone is ambiguous and was explicitly rejected as a signal).

| milestone | arms (excl. smoke) | documents (non-distinct) | pages |
| --- | ---: | ---: | ---: |
| 023 | 18 | 882 | 2,016 |
| 024 | 10 | 341 (+7 OmniDocBench, unscoreable) | 782 |
| 025 | 3 | 147 | 336 |
| **total** | **32** (31 scoreable) | **1,370 scoreable** | **3,134** |

024's `realscan_probe` (7 OmniDocBench pages) carries no `must_contain` in
either manifest and is explicitly marked `manifest: NONE` — mechanism-only,
as 024/025 already stated, and excluded from all Layer-1/Layer-2 scoring
below rather than silently coerced into one manifest.

---

## 3. Layer-2 prevalence (raw replay numbers)

**FACT**, from `results/all_arms.json`, recomputed per-arm (not aggregated
away — every arm's own numbers are in `results/<milestone>__<arm>.json`).
Layer 1 was executed unchanged (`run_ab.score` over `run_benchmark.document_text`,
real pydantic objects) in every arm; three representative rows:

| arm | Layer1 exact | Layer1 order_ok | L2 tables | L2 valid | L2 canonical | L2 page_order_ok |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| 023 adaptive/tesseract | 0.9838 | 46/49 | 17 | 15 | 14 | 49/49 |
| 023 visual/tesseract | 0.9311 | 46/49 | 97 | 92 | 87 | 48/49 |
| 024 SCAN-49/l5 | 0.9060 | 45/49 | 94 | 90 | 83 | 48/49 |

Full table in `results/all_arms.json`.

---

## 4. Generalization

**FACT.** Structural invalidity is present in **every milestone replayed**
(023, 024, 025) and in both `adaptive` and `visual` routing modes — it is
not a SCAN-49 artifact. Table count varies by route (17 tables under
adaptive's mostly-native routing vs. 94–97 under forced-scan/visual routing,
because `pymupdf_tables` handles most adaptive-route digital PDFs), but the
**defect rate conditioned on backend is stable**: `table_transformer`
produces invalid tables at 5.46% across the whole corpus; `pymupdf_tables`
produces **zero**, 0/117, in every arm it appears in.

**FACT**, per-document (`causal_attribution.json`, `results/all_tables.json`):
9 distinct documents produce at least one invalid table somewhere in the
replay. Conditioned on `table_transformer` usage specifically, invalidity is
**deterministic per document in 27 of 36 documents that ever hit
table_transformer** (always-valid or always-invalid, never both) and
**non-deterministic in 9** — driven by which rows tier-3 synthesis adds,
which depends on which OCR backend recognized enough corroborating text
(§5).

---

## 5. Causal attribution — the defect classes

Per the milestone's required taxonomy (A–J), classified from direct
evidence, not from "final IR is wrong so it's a bug":

| class | definition | 029 finding |
| --- | --- | --- |
| A. acquisition failure | recognizer never saw the text | not investigated this milestone (024/025 territory) |
| B. OCR recognition failure | text recognized wrong | not investigated this milestone |
| C. layout-region coverage failure | evidence outside every region | 025's territory; not re-investigated |
| D. region-label failure | correct geometry, wrong label | **025's stamp/occlusion table-gating finding; correlates with row-synthesis rate (§8)** |
| E. table detection failure | detector itself wrong | **NOT what causes the 102 invalid tables — see F** |
| **F. table structure failure** | **structure right, post-processing wrong** | **THE finding: tier-3 row synthesis, 100% of 102 instances (§6)** |
| G. ownership/duplication failure | correct regions, wrong assignment | 028's 82-token finding; not re-investigated |
| H. reading-order failure | sequence wrong despite correct evidence | **`compute_reading_order` itself wrong on 1 confirmed document (§7); Layer 1 blind to 19 (§9)** |
| I. serialization/evaluation artifact | correct IR, evaluator misreads it | **56% of order_ok failures (60/107, §9)** |
| J. evaluator limitation | the metric can't express the property | **table-label correctness — formally undecidable from final IR alone (§14)** |

Class F is the dominant, newly-attributed class this milestone establishes.
It was previously invisible: 028 counted 4 invalid tables and stopped at
"structurally invalid"; this milestone traced all 102 to their construction.

---

## 6. The structurally-invalid-table mechanism (full causal chain)

**FACT**, verified by direct source inspection plus re-opening all 102
source `document.json` files (`causal_attribution.json`):

1. `_fill_table_cell_text` (base.py:505) collects tokens whose *center*
   falls inside `table.bbox` (`_center_in`, base.py:161-164 — a deliberate,
   documented center-point rule).
2. Unclaimed tokens within margin of exactly one cell are absorbed; the rest
   are clustered into row bands and — only when corroborated across
   `MIN_CORROBORATING_COLUMNS = 2` (base.py:394) — synthesized into a new
   row (base.py:549-571), specifically to recover rows Table Transformer's
   structure model missed.
3. The synthesized cell's bbox is built from `min`/`max` of the **raw token
   edges** (base.py:559-560): `y0 = min(t.bbox.y0 ...)`, `y1 = max(t.bbox.y1 ...)`.
4. **The gap:** step 1's admission test uses the token's *center*; step 3's
   geometry uses the token's *edges*. A token whose center sits just inside
   `table.bbox` but whose top or bottom edge extends past it produces a
   synthesized cell that formally escapes its own table.
5. `table.bbox` is never expanded to accommodate synthesized rows (grepped:
   no assignment to `table.bbox` anywhere in the synthesis path).
6. `_renumber_rows_by_position` (called at base.py:573) fixes `row`/`col`
   *values* — which is why 026 correctly found 94/94 tables have correct
   row/col metadata — but does nothing about the cell's own bbox.

**FACT, quantified:** 265 escaping cells across 102 table instances; **100%
carry `Cell.confidence == 0.5`**, the literal value set only at base.py:568
and nowhere else in the codebase (grep-verified, one hit). Escape magnitude:
min 1.1px, median 4.7px, mean 7.0px, **max 14.4px**, at 200 DPI — sub-
millimeter at physical page scale. **0 of 102 escape by more than 20px.**
Direction: 90/102 synthesize a row above the table's detected top edge
(a missed header/footer immediately outside the table), 12/102 below.

**Verdict: FACT, mechanism confirmed at rate 1.0.** Not "the 4 invalid
tables are unexplained" — the exact line of code, the exact test, and the
exact geometric relationship are known, and the same mechanism explains
every instance in the entire replayed corpus, not merely the SCAN-49 sample.

---

## 7. `hc_encoding_vi` — why the same document's table SHAPE varies by OCR backend

**FACT**, from direct multi-arm inspection (§ preliminary analysis, folded
into `causal_attribution.json`'s per-document breakdown). `hc_encoding_vi`
under `table_transformer` shows declared shape `[4,2]` (valid) in some 023
arms and `[5,2]`/`[6,2]` (invalid) in others, for the **same source
document** at the **same milestone**. Table Transformer itself operates on
pixels and is backend-independent (confirmed: `table_backend.py` takes no
OCR input). The variance is explained entirely by §6's mechanism: different
OCR backends (EasyOCR vs. Tesseract vs. fusion variants) recognize different
amounts of the header/footer text near the table edge, so the
`MIN_CORROBORATING_COLUMNS` threshold for tier-3 synthesis is met
differently — EasyOCR's arms show `[4,2]` (no synthesis fired), the
Tesseract/fusion/selection/union arms show `[5,2]`/`[6,2]` (synthesis
fired, and one of the synthesized rows escapes). This is not table-detector
nondeterminism; it is a downstream consequence of which recognizer ran.

---

## 8. Backend / configuration stratification

**FACT**, from `backend_stratification.json`, 1,984 table instances:

| stratum | n | invalid rate |
| --- | ---: | ---: |
| `pymupdf_tables` (native digital-PDF) | 117 | **0.00%** |
| `table_transformer` (vision-based) | 1,867 | **5.46%** |
| `table_transformer`, no stamp/occlusion label | 1,809 | 4.70% |
| `table_transformer`, **stamp/occlusion label** | 58 | **29.31%** |
| `table_transformer`, Vietnamese | 1,538 | 4.94% |
| `table_transformer`, English | 329 | 7.90% |

**FACT, paired analysis** (8 same-document pairs, adaptive vs. visual
routing, `table_transformer` both sides): **100% concordant** — 0 documents
flip valid↔invalid when only the routing mode changes. **INFERENCE:** the
source document (specifically, how close its true header/footer text sits
to the detected table edge) drives the outcome; routing mode determines only
*whether* `table_transformer` runs, not what it produces once it does.

**INFERENCE:** the 6.2× elevated rate on stamp/occlusion documents is
mechanistically plausible, not merely correlational — a stamp or occlusion
artifact near a table edge is exactly the kind of visual noise that would
cause Table Transformer to miss a row (triggering tier-3 synthesis) while
simultaneously placing OCR token edges irregularly relative to the missed
row's true boundary (increasing the odds a token's edge crosses
`table.bbox` while its center does not). Not independently verified at
pixel level this milestone — flagged as H1 in §13.

---

## 9. `cmb_stamp_boundary_vi` — formal Layer-1/Layer-2 counterexample

**FACT**, from `false_negative_case.json`, complete ordering chain
reconstructed. This document's page consists of 15 small text elements (a
shattered/undetected table — the same picture-label gating shape 025
documented in sibling documents, though this specific document was not in
025's named list).

**FACT:** `Page.reading_order` for this page is itself non-monotonic in y:
element `e7` ("Sản phẩm A-100", y0=596.5, a data cell) is placed **before**
`e6` ("Mô tả hàng hóa", y0=547.6, the header cell directly above it) —
`compute_reading_order`'s column-banding heuristic inverted them.

**FACT:** raw `page.elements` list order happens to place `e6` before `e7`
(matching geometry by coincidence of insertion order, not by design).

**FACT:** Layer 1's `document_text` iterates `page.elements` in raw list
order and **never reads `reading_order` or `order_index`** (confirmed by
027's Phase-1 audit and re-confirmed here). It therefore reports
`order_ok = True` — reading the coincidentally-correct list order — while
`page_order_ok` (which reads `reading_order`, production's own computed
answer to this exact question) correctly reports `False`.

**Formal counterexample:** *Layer 1 cannot distinguish "the element list
happens to have been appended in an order that looks right" from "the
computed reading order is right."* It never inspects the field production
computes specifically to answer that question. **This also means 025's
claim "`compute_reading_order` is exonerated" (0 order failures on SCAN-49
after canonical table serialization) was measured through the same blind
channel and did not detect this case** — `page_order_ok` is the first
metric in the entire 023–029 lineage to read `reading_order` directly.

**Classification: COMPOUND** — genuinely ambiguous ground truth is ruled
out (there is a clear correct order: header before data); this is one part
IR ordering defect (`compute_reading_order`'s heuristic), one part scorer
blind spot (Layer 1 ignoring the field), each independently verified.

---

## 10. Page-order vs. table-order decomposition

**FACT**, from `order_decomposition.json`, 1,378 document-arm pairs, three
independent structural checks per pair (not inferred from score deltas):

```
Layer-1 order failures = 107 (of 1,378 pairs, 32 arms)
  table_order_failure      60  (56%)  -- canonicalizing (row,col) alone fixes it
  append_boundary_failure  31  (29%)  -- elements-before-tables append structure at fault
  list_page_order_failure  16  (15%)  -- non-table elements themselves scrambled
  ---------------------------------------------------------------
  sum = 107, verified equal to total (no residual bucket)
```

Separately, **19 document-arm pairs** show `reading_order` revealing a
hidden failure list-order missed (§9's mechanism, generalized): 13 in 023's
`stamp_table_vi`-family documents, 6 in `cmb_stamp_boundary_vi` across
024/025.

**Correction to the milestone's own working assumption:** an earlier version
of this decomposition script classified 60 real table-order failures as
"unattributed" because of a backwards conditional (`not table_ok` instead of
`table_ok`) — caught by spot-checking a case already known from 027
(`cmb_borderless_lowcontrast_en`) and expecting `table_order_failure`,
getting `unattributed`, and tracing why. Documented in the script's own
comments rather than silently fixed.

**append_boundary_failure (29%, new this milestone)** is a distinct
mechanism from table-cell-order: `document_text` places **every** element
before **every** table on a page regardless of the table's true vertical
position (027 documented this structurally; 029 is the first to isolate how
much of the failure count it alone causes). Canonicalizing table cells does
not fix these — the table's *position relative to surrounding text* is
wrong in the flattened string, independent of what's inside the table.

---

## 11. Cross-milestone lineage

**FACT**, `lineage.json` — full hypothesis→experiment→observation→decision
chain for 023–029. Condensed:

```
023  best OCR strategy?           -> Tesseract adopted
024  L5 generalizes to scans?     -> SHIP (confirmed, low-sensitivity)
025  coverage is the bottleneck?  -> REJECTED (L5 already closes the gap)
026  cell canonicalization ships? -> FALSIFIED (defect is in eval, not prod)
027  document_text serializes     -> ADOPT 2-layer contract, no rebaseline
     tables wrong?
028  Layer 2 measures new things? -> ADOPT; found 4 invalid tables + 1 FN
029  are 028's findings general?  -> YES, with a complete causal mechanism;
                                      +1 new blind spot (reading_order)
```

Each milestone's decision was reached by testing its own hypothesis to
falsification against artifacts, not by assumption — 025 and 026 both
falsified their own starting hypotheses and said so.

---

## 12. Measurement controls

**FACT**, `expanded_controls.json`: 11 new synthetic cases targeting the
semantics 029 discovered (valid-structure/noncanonical-order independence,
canonical-order/invalid-geometry independence, page-order/table-order
independence in both directions, table-vs-non-table text retrieval, the
picture-labelled-region ambiguity, an **exact reproduction of the row-
synthesis escape mechanism**, and three `reading_order` semantics: explicit
reorder honored, empty falls back to list order matching
`Document.to_markdown`'s documented behavior, and — critically — an explicit
contradiction between `reading_order` and raw y-geometry where the view is
required to trust `reading_order` and *not* silently re-sort by position).

**11/11 passed.** Combined with 028's 12 controls + 7 anti-gaming attacks:
**30/30 evaluator-validation cases pass** across both milestones.

Four of the milestone's 15 suggested cases (7, 8, 11, 12 — duplicate-
ownership-without-text-duplication, text-duplication-without-overlap, and
the two relabeling attacks) were not re-implemented: they are exact
duplicates of checks 028's `overlap_diagnostic.py` and `anti_gaming.py`
already cover and pass. Re-running them here would not add evidence.

---

## 13. Measurement matrix

**FACT**, `measurement_matrix.json`, 12 properties, YES/PARTIAL/NO only —
no proxy silently called ground truth:

| property | L1 | L2 |
| --- | :---: | :---: |
| text fidelity (document) | YES | NO |
| text fidelity (per-cell) | NO | **NO (honest)** |
| evidence coverage | NO | PARTIAL (SCAN-49 only) |
| evidence duplication | NO | PARTIAL (SCAN-49 only) |
| page order | PARTIAL | **YES** |
| table cell order | PARTIAL | **YES** |
| table structure coherence | NO | YES |
| table bbox containment | NO | YES |
| cell geometry validity | NO | YES |
| **table-label correctness** | NO | **NO — formally undecidable** (§ below) |
| OCR correctness | PARTIAL | NO |
| extraction completeness | NO | PARTIAL (SCAN-49 only) |

**FACT, new this milestone:** table-label correctness (picture vs. table)
is not merely unmeasured — control case 09 demonstrates it is **formally
undecidable from the final IR alone**: a `picture`-labelled region and a
genuine `table` region can carry identical bbox geometry, and nothing
downstream of the layout stage retains a distinguishing signal. This is why
025's proposed fix must act on the *label*, at detection time, not on
geometry after the fact.

---

## 14. Highest-value bottleneck

**Scoring, using the stated criteria — prevalence, severity, causal
confidence, recoverability, production cost, regression risk, downstream
RAG/GraphRAG impact, evidence quality:**

| candidate | prevalence | severity | causal confidence | recoverability | RAG impact |
| --- | --- | --- | --- | --- | --- |
| Row-synthesis bbox escape (§6) | 102 instances, 9 docs | LOW (1-14px slop; text/row/col unaffected) | **1.0 (proven)** | trivial (test cell-bbox not center, or expand table.bbox) | low — bbox cropping/highlighting only |
| Table-label gating (025's D) | ~9 docs, concentrated in stamp/occlusion | **HIGH** (whole table lost) | HIGH (025 traced it to base.py:747) | moderate (needs a geometry-aware or confidence-aware gate, not yet attempted) | **HIGH — table content and structure vanish from retrieval** |
| `reading_order` blind spot (§9-10) | 19 doc-arm pairs (eval); ≥1 confirmed production defect | MEDIUM | HIGH for the eval gap; MEDIUM for the production `compute_reading_order` defect (n=1 confirmed) | eval fix is cheap (read the field); production fix needs `compute_reading_order` work on shattered-table pages | MEDIUM — citation order on affected pages |

**RECOMMENDATION.** The highest-value next research target is **table-label
gating under stamp/occlusion**, because it is the only candidate that is
simultaneously high-severity (a table's data structurally vanishes, not
merely mis-ordered by a few pixels) and already has a traced cause (025)
with a plausible, bounded fix. It is also — per §9's INFERENCE — the
apparent common root of the reading-order defect: fixing gating so
shattered tables stay tables would likely remove the `compute_reading_order`
failure mode as a side effect, since `compute_reading_order` would never see
those elements as loose text in the first place.

The row-synthesis bbox escape (§6) is **not** the highest-value target
despite being the most rigorously proven finding this milestone — its
severity is bounded and low (§6's magnitude data), and it should be treated
as a cheap, independent, low-risk fix rather than a research program.

---

## 15. Three falsifiable hypotheses

### H1 — Stamp/occlusion visual noise causally elevates row-synthesis escape rate through Table Transformer's own uncertainty

**Mechanistic statement:** stamp/occlusion artifacts near a table's true
boundary increase the likelihood that Table Transformer's detected
`table.bbox` undershoots the table's real extent, which increases both (a)
how often tier-3 synthesis fires (more real rows fall outside the
under-detected bbox) and (b) how often a synthesized cell's raw token edge
crosses that same undershot boundary.

**Why:** §8's stratification (29.31% vs 4.70% invalid rate, 6.2× elevated)
is consistent with this; the paired concordance result (§8) rules out
routing mode as the driver, leaving document content as the remaining
variable, and stamp/occlusion is the labeled document property most
directly implicated.

**Counterevidence:** the correlation was measured at the document-label
level, not verified at the pixel level — no per-page visual inspection of
whether the stamp actually overlaps the specific escaping row was performed
this milestone. It is also possible the correlation is confounded by
document *type* (stamped documents in this corpus tend to be Vietnamese
invoices with a specific dense-table layout) rather than the stamp itself.

**Minimal discriminating experiment:** for the 58 stamp/occlusion
`table_transformer` table instances, measure each detected `table.bbox`'s
IoU against the union of all OCR token bboxes plausibly belonging to that
table (from region/token geometry already in 025's `coverage_dataset.json`
shape); compare that IoU distribution against the 1,809 non-stamp instances.
If H1 is true, stamp/occlusion tables should show systematically lower
bbox-to-evidence IoU.

**Expected outcomes:** H true → materially lower IoU on stamp/occlusion
tables, explaining both symptoms as one geometric-undershoot cause. H false
→ IoU distributions overlap, meaning the elevated rate is confounded by
something else (document type, layout density) not yet isolated.

**Production relevance: MEDIUM.** Explains a mechanism but the practical
fix (§6, bound cell geometry to table geometry) is the same regardless of
whether H1 is confirmed.

**Risk: LOW.** Pure measurement, no code change implied by the experiment
itself.

---

### H2 — The row-synthesis bbox-escape defect is strictly bounded and never crosses into a neighboring table or region

**Mechanistic statement:** because synthesized-row tokens must first pass
`_center_in(token, table.bbox)` (their *center* is always inside), the
maximum possible escape of any single cell edge is bounded by that token's
own bbox height/width — synthesis can never attribute a token whose entire
extent lies in a different table or a different page region.

**Why:** §6's magnitude data already supports this at the sample level (max
14.4px, 0/102 instances exceed 20px, consistent with typical body-text
token heights at 200 DPI) — but the full population of 265 escaping cells'
neighboring-region overlap was not explicitly tested this milestone.

**Counterevidence:** 12/102 escapes are *below* the table (not above), and
a page with two tables stacked closely could in principle place an escaping
bottom-row cell inside the *next* table's bbox — a scenario not checked.

**Minimal discriminating experiment:** for every escaping cell in
`causal_attribution.json`, test whether its bbox intersects any OTHER
table's bbox on the same page (not just its own). If any escaping cell's
bbox overlaps a second table, H2 is falsified and the defect's severity
must be reclassified as HIGH (cross-table contamination), not LOW.

**Expected outcomes:** H true → confirms §14's LOW-severity classification
and the recommendation to treat this as a cheap, deprioritized fix rather
than urgent. H false → at least one instance of cross-table contamination
found, which would immediately elevate this above table-label gating as the
highest-value target, since silently-wrong table attribution is worse than
a lost table (a lost table is at least visibly absent; a contaminated one
looks correct and is not).

**Production relevance: LOW if confirmed, HIGH if falsified** (binary
severity swing).

**Risk: LOW.** Measurement only; the corpus and the exact escaping-cell list
already exist in `causal_attribution.json`.

---

### H3 — Layer 1's `reading_order`-blindness specifically and disproportionately hides defects on the same document class where table-label gating fails

**Mechanistic statement:** the 19 document-arm pairs where `reading_order`
reveals a hidden Layer-1-invisible order failure (§9-10) are concentrated in
documents that also exhibit table-label gating failures (025's Class D) —
i.e., the evaluation blind spot and the production defect are not
independent; they co-occur on the same shattered-table document class.

**Why:** of the 19 hidden-failure document-arm pairs listed in §10, the
underlying documents (`cmb_scan_stamp_table_vi`, `cmb_stamp_table_vi`,
`hc_stamp_table_vi`, `cmb_stamp_boundary_vi`) are exactly the stamp/table
family 025 named as gating failures — not a random sample of the corpus.

**Counterevidence:** the overlap could be coincidental — these are simply
the corpus's hardest documents by several unrelated measures (they also
carry the highest orphan rates, per 025), so co-occurrence with *any*
defect class might be expected regardless of a shared cause.

**Minimal discriminating experiment:** compute, for every document in the
corpus (not just the 19), whether it has (a) a table-label gating flag
(025's method, reproducible from the frozen IR) and (b) a `reading_order`-
vs-list-order divergence (this milestone's method). Cross-tabulate. If H3 is
true, divergence should be strongly conditional on gating failure and rare
otherwise; if false, divergence should be roughly uniform across documents
regardless of gating status.

**Expected outcomes:** H true → strengthens §14's recommendation that fixing
table-label gating is the single highest-leverage intervention (it would
silently repair the evaluation blind spot too). H false → the reading_order
gap must be treated as a separate, independent research target.

**Production relevance: HIGH if confirmed** (one fix, two problems solved).

**Risk: LOW.** Cross-tabulation over existing artifacts; no new extraction.

---

## 16. Production implications

**No production code was touched or is recommended for immediate change.**
Two concrete, low-risk future changes are now well-specified enough to scope
precisely, should the user choose to pursue them as a *separate, controlled*
milestone:

1. **Row-synthesis bbox containment (§6).** Either (a) test the synthesized
   cell's own bbox for containment before appending it, discarding/clamping
   escapes, or (b) expand `table.bbox` to the union of itself and every
   synthesized cell. Option (b) preserves more evidence (nothing is
   discarded) and is more consistent with L5's own "never discard real
   text" precedent (024). **Not implemented this milestone** — H2 should be
   resolved first, since the correct fix differs if cross-table
   contamination is found.
2. **`page_order_ok`-style evaluation of `reading_order`** could be adopted
   more broadly as a Layer-2 metric beyond SCAN-49 (§13 notes it is already
   general-purpose, not SCAN-49-specific) — a reporting change, not a
   production change.

Table-label gating (§14's recommended next target) is **not** newly
specified by 029 to implementation-readiness — 025 traced its cause but no
milestone has yet designed or tested a fix; H1 and H3 above are the
prerequisite measurements before one should be attempted.

---

## 17. Explicit non-findings

To be equally clear about what this milestone did **not** establish:

- **Did not** determine whether OCR recognition quality (Class A/B) differs
  by backend beyond what 023 already measured — out of scope.
- **Did not** pixel-inspect any stamp/occlusion image to visually confirm
  H1's mechanism — the correlation is document-label-level, not
  pixel-verified.
- **Did not** find any case of cross-table contamination from the row-
  synthesis escape (H2 is stated, not resolved) — absence of evidence in a
  sample is not proof of absence in the full population; H2's discriminating
  experiment was specified but not run this milestone.
- **Did not** extend evidence-coverage/orphan-rate/overlap-rate metrics
  beyond SCAN-49 — 025's token-level instrumentation was not re-run on
  023/024's other arms (would require new extraction with the same
  instrumented hooks, judged out of scope for a read-only replay milestone).
- **Did not** find any NEW instance of the class-C ownership-duplication
  defect (028's 82 tokens) outside SCAN-49 — not specifically searched for,
  since it requires the same token-level instrumentation as above.

---

## 18. Limitations

- Backend stratification (§8) has an 8-pair sample for the paired
  adaptive-vs-visual comparison — small enough that 100% concordance,
  while suggestive, is not a strong statistical claim; stated as FACT about
  the 8 pairs observed, not generalized beyond them.
- The English-vs-Vietnamese invalid-rate difference (7.90% vs 4.94%, §8) is
  reported but not investigated further — n=329 for English table instances
  is comparatively small and the difference was not tested for
  significance; treat as an observation, not a claim.
- `Cell.confidence == 0.5` as an exclusive synthesis marker was verified by
  grep (one source location) at this commit; a future code change could
  introduce a second use of the same literal without this document being
  updated — the marker is a property of the current code, not a permanent
  IR guarantee.
- This report's "100%" claims (mechanism confirmed rate, marker exclusivity)
  are exact over the **replayed population** (1,984 table instances, 102
  invalid) — not a claim about documents or configurations never replayed.

---

## Recommended Milestone 030

**RECOMMENDATION.** Resolve H1 and H2 first (both are pure read-only
measurement over already-frozen artifacts, no new extraction, low risk,
answerable in a single focused milestone), because their outcomes determine
which of two very differently-shaped fixes (§16) is correct for the
row-synthesis defect, and H1's outcome bears directly on whether table-label
gating (§14's recommended target) should be pursued next or whether the
row-synthesis mechanism deserves elevated priority instead. Do not proceed
directly to implementing a table-label-gating fix without H1/H3's evidence,
since 025 already showed that acting on an unverified geometric hypothesis
in this exact area (table detection) previously used a wrong assumption.
