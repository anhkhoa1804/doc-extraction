# Milestone 031 — Table-label gating and recovery

**Status:** research-only, offline, CPU-only. `src/` untouched. Frozen scorer
untouched. Decision: **EXPERIMENTAL**.

Every claim below is tagged FACT / INFERENCE / HYPOTHESIS / RECOMMENDATION
and cites an artifact path and field. Artifacts referenced are all in
`experiments/031_table_label_gating/` unless stated otherwise.

---

## 1. Actual gating mechanism

**FACT** (`gating_contract.json`, `gating_contract.py`): the entire table
gate is one line, `src/doc_extraction/pipelines/base.py:747` —
`table_regions = [r for r in layout_result.regions if r.label.lower() ==
"table"]`. It is a hard, exact-string-equality, label-based filter. It is
**not** geometric, **not** confidence-based, **not** semantic beyond
trusting Docling's own layout classification verbatim.

**FACT**: Docling's stable API exposes no confidence field for these
region items — `docling_core.types.doc.TextItem.model_fields` and
`ProvenanceItem.model_fields` were inspected directly this milestone (via
prior work; re-confirmed unchanged). `confidence=None`
(`docling_backend.py:322`) is not a discarded signal; it is the honest
absence of one.

**FACT**: `traverse_pictures=True` (`docling_backend.py`) means Docling's
own iteration descends into picture-labelled blocks and emits their child
text items as separate top-level `Region` objects at the same page —
this is why a picture-labelled region can carry rich nested text evidence
even though the label itself says "picture." This is Docling's behavior,
not custom code in this repository.

---

## 2. Complete candidate population

**FACT** (`gated_table_population.json`): exactly **7 distinct documents**
in the entire replayed 023–025 corpus ever produce a picture/chart-labelled
region with ≥1 nested text child: `cmb_scan_stamp_table_vi`,
`cmb_stamp_boundary_vi`, `cmb_stamp_table_vi`, `hc_stamp_table_vi`
(CONFIRMED, ≥6 children) and `cmb_lowcontrast_stamp_vi`, `hc_stamp_text_vi`,
`hc_transparent_seal_vi` (AMBIGUOUS, 1–2 children). This is more than the
3 documents named in Milestone 025.

**FACT** (`negative_controls.json`, exhaustive filesystem search over
**1,004** layout directories across every `experiments/*/_runs/**/layout`
in the repository, not just 029's own inventory): these are the *only* 7
documents with any nested-child picture region anywhere in the previously
scanned corpus. One additional pocket of unscanned artifacts was found —
`experiments/024_ocr_fidelity_recovery/_runs/realscan_probe/` (7 genuinely
diverse real-world documents, never included in 029's `cohort_inventory.json`
and therefore never scanned by 031 Phases 2–6) — which added 2 more
documents with nested-child picture regions (§8).

---

## 3. Same-document route flips

**FACT** (`paired_gating_cases.json`): `cmb_stamp_table_vi` and
`hc_stamp_table_vi` each have arms where they are picture-gated
(`arms_ONLY_gated_never_tabled`) and arms where a real table reaches
`table_transformer` (`arms_ONLY_tabled_never_gated`), for the identical
source document.

**INFERENCE**, refined this milestone beyond Phase 3/7's own framing: the
flip is not binary "adaptive vs everything else." Three distinct regimes
were found by cross-referencing `paired_gating_cases.json` against actual
element contents in `final/document.json`:

- **adaptive route** (native, non-rasterized PDF extraction): a genuine
  table is always produced, cleanly, no picture duplicate.
- **scan_cohort / coverage route** (forced rasterization to an image
  before Docling analysis): the table is *never* produced — picture-only,
  a clean gating failure (`arms_ONLY_gated_never_tabled`).
- **visual route** (forced OCR, but per `causal_models.py`'s own route
  classifier, *not* rasterized): **both** persist simultaneously — a real,
  narrower `table` element **and** a larger picture-labelled duplicate
  covering the same content, confirmed directly by inspecting
  `023/visual/easyocr`'s `final/document.json` for `cmb_stamp_table_vi`
  (`p0-e2` type `table`, bbox `{x0:164, y0:464, x1:1200, y1:689}`; `p0-e3`
  type `image`, bbox `{x0:164, y0:464, x1:1201, y1:798}` — the picture is
  a strict superset).

**FACT** (`causal_models.json`): 2/3 paired stamp/occlusion documents
(`cmb_stamp_table_vi`, `hc_stamp_table_vi`) show a clean route-driven
flip; `cmb_stamp_boundary_vi` does **not** (`arms_ONLY_gated_never_tabled:
[]` — every gated arm is also a tabled arm, i.e. permanent coexistence,
never a clean flip).

---

## 4. Causal interpretation

**FACT** (`causal_models.json`): Model A ("stamp directly causes picture
label," deterministic) is **REJECTED** — the same stamp content, present
in every arm, produces different gate outcomes depending on route alone.

**FACT**: Model C ("route/backend interaction is the proximate cause,
stamp merely correlates") is **SUPPORTED** by the same flip evidence.
Model B (indirect, mediated by evidence degradation) is **PARTIALLY
SUPPORTED** and not cleanly separable from C without inspecting Docling's
internal layout model at matched resolution (not done). Model D
(incidental) is **REJECTED as sole explanation**.

**INFERENCE** (§3, this milestone): the mechanism is more specifically
**rasterization**, not merely "route" in the abstract — full rasterization
(scan_cohort/coverage) causes total table loss; forced-OCR-without-
rasterization (visual) causes duplication rather than loss; native
extraction (adaptive) is clean. This is consistent with, and sharpens,
Model C/B's own acknowledged ambiguity in `causal_models.json`
("rasterization could BOTH change the route AND degrade the visual
evidence Docling's layout model sees").

---

## 5. Intervention behavior (Phase 10)

**FACT** (`intervention_results.json`, `controlled_intervention.py`):
three arms run over the same 118 document-arm-mode rows (the full
`gated_table_population.json` candidate population, positives and
negatives together):

| mode | tables reconstructed | structurally valid | false tables on negatives | true recovery on confirmed docs |
|---|---|---|---|---|
| control | 0 | 0 | 0 | 0 |
| conservative (probe ≥3) | 79 | 6 | 0 | 66 |
| aggressive (any ≥1 child) | 118 | 45 | 39 | 66 |

**FACT** (discovered and fixed this milestone, `controlled_intervention.py`
`attach_text_from_elements`): the first Phase 10 run produced **79/79
conservative reconstructions with 100% empty cell text**, because
`apply_intervention` sourced child geometry from `layout/*.json`, whose
`Region` schema is `{bbox, label, confidence, source_id}` — no `text`
field exists there at all. The real OCR text for the identical nested-
child geometry is already present in the SAME `document.json`'s
`pages[].elements` (Docling emits the same child geometry into both
places). Fixed via IoU-bbox matching against `pg["elements"]`
(`bbox_iou > 0.5`); after the fix, conservative-mode reconstructions carry
real text in 1,162/1,246 cells (93.3%). **This was a bug in the Phase 10
research script, not a production finding** — flagged explicitly so it is
not later mistaken for evidence about production behavior.

**FACT**: mean Layer-1 `text_recall` on the 66 rows belonging to the 3
CONFIRMED documents rose 0.7538 → 0.7708 (+0.017) under conservative mode;
`char_recall` rose 0.9771 → 0.9810 (+0.0039); **zero** change on the 39
negative-document rows or the 13 `cmb_stamp_boundary_vi` rows, in either
mode; **zero** `docs_hallucinated` in all 3 arms × 118 rows.

**INFERENCE**: the Layer-1 gain is small because the underlying OCR text
was mostly *already* present in the flattened document text via Docling's
duplicate nested-text-element emission (Milestone 025's finding) — the
intervention's real value is structural (organizing already-present flat
text into row/col cells), which Layer-1's flat-text metric is largely
blind to.

---

## 6. TRUE_RECOVERY / PLAUSIBLE_RECOVERY / PSEUDO_TABLE / INVALID (Phase 11)

**FACT** (`recovery_verdicts.json`, 79 conservative-mode instances
classified using `structural_integrity` (028) + `factual_oracle_comparison`
(§7) + Phase 4–6 negative-population membership — never shape alone):

| document | verdict | n | why |
|---|---|---|---|
| `cmb_stamp_table_vi` | TRUE_RECOVERY | 19/19 | oracle exists, same_physical_region YES/PROBABLE, row count matches (4) |
| `hc_stamp_table_vi` | TRUE_RECOVERY | 19/19 | oracle exists (cross-arm), token recall 0.73, row count matches (4) |
| `cmb_scan_stamp_table_vi` | PLAUSIBLE_RECOVERY | 28/28 | rows coherent, no factual oracle exists anywhere in the corpus |
| `cmb_stamp_boundary_vi` | PSEUDO_TABLE | 13/13 | `rows_vertically_coherent=False` — the real table occupies only ~20% of the picture region's own area (§7); the region mixes genuine table content with substantial non-table content the reconstruction cannot separate |

**FACT**: 0/79 INVALID — no reconstruction violates a hard geometric
invariant (`coords_in_declared_range`, duplicate coordinates, non-
contiguous rows/cols, invalid bbox, cells escaping the table bbox). The
*only* observed failure modes are `cols_horizontally_coherent` (73/79 —
an artifact of the reconstruction's deliberately naive rank-based column
assignment, not a hard-invariant violation) and `rows_vertically_coherent`
(13/79, all `cmb_stamp_boundary_vi`).

**INFERENCE**: `cols_horizontally_coherent` failing alone does not mean
"not a table" — it means the reconstruction's column-INDEX labeling is
approximate. `rows_vertically_coherent` failing is a stronger, different
signal (row bands themselves don't cohere) and is treated as such in the
classification logic.

---

## 7. Factual oracle comparisons (Phase 12)

**FACT** (`factual_oracle_comparison.json`): `cmb_stamp_table_vi` — same-
arm pairing (`023/visual/easyocr` etc.) gives bbox IoU 0.6746, table
99.97% contained in the picture bbox → **same physical region: YES**.
Cross-arm (`025/coverage` vs `023/adaptive/easyocr`) token recall 0.7692 →
PROBABLE. Factual oracle shape 4×5, 20 cells, 19 populated
(`counterfactual_replay.json`).

**FACT**: `hc_stamp_table_vi` — no same-arm pair exists (gated and tabled
arms are fully disjoint); cross-arm token recall 0.7317 → **same physical
region: PROBABLE**. Factual oracle shape 4×5, 20 cells, 20 populated.

**FACT**: `cmb_stamp_boundary_vi` — same-arm IoU only 0.1958, but the
factual table is **100%** contained within the picture bbox
(`table_contained_in_picture_frac: 1.0`) → **same physical region:
PROBABLE**, but the picture region is roughly 5× the area of the real
table — most of its content is not the table.

**FACT**: `cmb_scan_stamp_table_vi` — **no factual table exists anywhere**
in the replayed corpus (`factual_oracle_exists: false`) — any
reconstruction for this document is a geometric simulation, consistent
with `counterfactual_replay.json`'s own `SIMULATED_COUNTERFACTUAL` label.
**Same physical region: UNKNOWN** by construction — not claimed otherwise.

---

## 8. Negative controls and their limitations (Phase 13)

**FACT** (`negative_controls.json`): the existing 39-negative population
(`table_shape_probe.json`) is exactly 3 documents, all zero-nested-child
picture regions from the same small stamp-vi family as the 4 positives.
Its reported 0-false-positive / 100%-precision result at threshold=3 is a
property of that narrow population, not of the probe.

**FACT**: exhaustive search found `experiments/024_ocr_fidelity_recovery/
_runs/realscan_probe/` — 7 genuinely diverse real-world documents
(scientific papers, textbook chapters, a newspaper page, a slide deck),
never scanned by 031 Phases 2–6 because the arm is absent from 029's
`cohort_inventory.json`.

**FACT — confirmed false positive**: `jiaocaineedrop_Chapter9.pdf_46`,
page-1 region 0, scores **4/5** on `table_shape_evidence_score` (above the
conservative threshold of 3). Its recovered nested-child text is
`['macmillanmh.com', 'Practice', '3', 'Cumulative, Chapters 1-9']` — a
textbook worksheet page **header/banner** (publisher watermark + unit
title + practice-set label), manually verified, not a table.

**CONCLUSION**: the corpus available to this research chain cannot
support a validated false-positive-rate claim for the probe as specified.
`table_shape_probe.json`'s "100% precision" claim does not generalize.

---

## 9. Decision-boundary analysis (Phase 14)

**FACT** (`table_shape_probe.json` `all_positive_rows` signals): all 4
CONFIRMED true positives have `row_bands` 3–4 and `aspect_ratio` 3.08–3.21.
The Chapter9 false positive has `row_bands=2` and `aspect_ratio=4.88` — a
wide, short banner, not a grid.

**HYPOTHESIS**, validated only against this single counter-example (n=1,
**not** a validated rule): raising the probe's `row_bands` floor from ≥2
to ≥3 would exclude Chapter9 while retaining all 4 known positives. It
would **not** exclude `cmb_stamp_boundary_vi` (`row_bands=3`), whose
failure is of a different kind — `rows_vertically_coherent` fails at
*reconstruction* time even though the *probe*'s looser band-clustering
counts 3 bands. This shows the probe (pre-reconstruction shape test) and
`structural_integrity` (post-reconstruction coherence test) catch
different failure modes; neither alone is sufficient.

**RECOMMENDATION**: a safe design needs both a stricter pre-filter
(row_bands, aspect_ratio) **and** a mandatory post-reconstruction
`rows_vertically_coherent` check that discards, not merely flags,
non-coherent candidates before they are ever exposed (`recommendation.json`
§ phase_18).

---

## 10. Route/recognizer causal decomposition (Phase 15)

See §3–4. **FACT**: the earliest observable divergence between a table-
producing arm and a picture-gated arm, for the same document, is at the
**rendering/route** stage — whether the page reaches Docling as native
vector content (adaptive) or as a rasterized image (scan_cohort/coverage)
— not at the OCR-recognizer stage (Docling's own layout classification
runs independent of which text recognizer is later used to fill in text).

**Classification**: **routing-driven**, with a **layout-driven** mediating
step (rasterization changes what Docling's layout model sees), not
**OCR-driven** — text-recognizer identity (tesseract/easyocr/fusion/etc.)
does not change picture-vs-table classification within the same route
family in any paired case examined.

---

## 11. Role ambiguity analysis (Phase 16)

**FACT** (`role_ambiguity_analysis.json`): 5 of 11 evaluated picture-
labelled regions produce a label/evidence conflict (label says "picture,"
`table_shape_evidence_score ≥ 3`). Of these, 3 were independently
confirmed as genuine missed tables and 2 were independently confirmed
**not** tables (`cmb_stamp_boundary_vi`, `jiaocaineedrop_Chapter9.pdf_46`
region 0).

**INFERENCE**: the hard single-label gate does discard a real,
recoverable uncertainty signal — but the currently available structural
evidence is not yet sufficient to safely auto-resolve that ambiguity. No
synthetic picture-confidence was fabricated to pair against
`table_shape_evidence_score`; Docling provides none, and inventing one
would violate the same discipline this analysis argues for.

**RECOMMENDATION**: keep role uncertainty visible (a candidate-alongside-
original design, per intervention option B/D) rather than collapsing it
to one label (today) or auto-resolving it to a second hard label without
a stronger signal (not yet justified). A full `region → role_candidates`
IR schema redesign is a larger change than this milestone's evidence
justifies shipping.

---

## 12. Intervention safety (Phase 17)

Full detail in `recommendation.json` → `phase_17_intervention_safety`.
Summary: benefit is real but concentrated (2/4 documents, 38 TRUE_RECOVERY
instances); regression includes one confirmed false positive outside the
validation corpus and one confirmed PSEUDO_TABLE misfire *inside* the
validated candidate set; zero hard-invariant violations, zero page/table-
order corruption, zero fabricated confidence, in every case checked.
Duplicate-ownership at the token level was **not** independently measured
this milestone — an explicit limitation, not a clean result.

---

## 13. Production design (Phase 18)

**RECOMMENDATION** (`recommendation.json` → `phase_18_production_design`):
Option A (label relaxation) rejected — the Chapter9 finding makes this
concretely dangerous. Option C (real TableTransformer fallback) not
executed, and not automatically safer against unseen content than a
geometric heuristic. Option D as implemented is what was tested and has
known failure modes. **Option B, refined** (stricter pre-filter +
mandatory post-reconstruction coherence gate, evidence-based routing that
preserves the original label) is the recommended direction, contingent on
revalidation against a larger negative corpus (§14) — not ready to ship
as currently specified.

---

## 14. Research-target reassessment (Phase 19)

**RECOMMENDATION**: 029's original target (table-label gating recovery)
is not wrong but is no longer the single highest-value next step. This
milestone's own negative-control search surfaced a higher-leverage
prerequisite: **the corpus this entire research chain validates against
does not contain enough picture-region diversity to certify any gating
intervention safe.** Ranked: (1) negative-corpus breadth — closing this
is a data-collection task, not new research, and `realscan_probe`'s
5 unscored documents are a concrete, already-on-disk starting point; (2)
table-label gating recovery itself, contingent on (1); (3) the
architectural `role_candidates` redesign — real, but larger than current
evidence justifies.

---

## 15. Final decision (Phase 20)

# **EXPERIMENTAL**

Not SHIP: a confirmed false positive exists outside the validation corpus,
and a confirmed structural misfire exists inside the milestone's own
validated candidate set — false-positive risk is not low.

Not REJECT: the mechanism is independently confirmed for 2 of 4 documents
via factual historical oracle agreement, with zero hard-invariant
violations and zero Layer-1 regression across every evaluated arm.

Not HOLD: a specific, testable refinement (two-stage gate) and a
specific, actionable prerequisite (negative-corpus expansion via
already-discovered `realscan_probe` artifacts) were both identified —
there is a concrete next step, not an open-ended pause.

**The mechanism being real and the intervention being safe are separate
claims. This report affirms the first and declines the second as
currently specified.**

---

## 16. Strongest counterargument

The strongest case *against* this milestone's own EXPERIMENTAL verdict:
both known failure modes (Chapter9, `cmb_stamp_boundary_vi`) were found
via n=1 counter-examples each, discovered through manual/targeted search
rather than a systematic adversarial sweep. It is possible a properly
tuned two-stage gate (§9, §13) would in fact be safe in production, and
this report is being more conservative than the evidence strictly
requires. The counter-response: given that the ONLY validation this
mechanism has ever received (`table_shape_probe.json`'s "100% precision")
was already falsified once by a few hours of additional search, the
responsible prior is that more failure modes exist and have not yet been
found — not that none do.

---

## 17. Limitations

- Duplicate-ownership at the token/evidence level was not re-measured
  against 031's reconstructed tables (025's own instrumentation was not
  re-run).
- The `row_bands ≥ 3` refinement (§9) and the post-reconstruction
  coherence gate (§13) are both HYPOTHESES validated against n=1
  counter-example each, not validated rules.
- `realscan_probe` has 5 documents beyond the 2 with nested-child picture
  regions that were not individually re-examined for OTHER picture
  regions with zero children that might still be worth manual review.
- Option C (real TableTransformer fallback) remains unexecuted; its
  false-positive behavior against Chapter9-style content is unknown.
- Coordinate-system incomparability between adaptive (native PDF points)
  and scan_cohort (rasterized pixels) routes means several
  same-physical-region determinations rely on text-token recall rather
  than direct geometric IoU (`factual_oracle_comparison.json`, CROSS_ARM
  pairs) — a weaker, though explicitly labeled, form of evidence.

---

## 18. Exact next research question

> Does a two-stage gate — probe `row_bands ≥ 3` AND `aspect_ratio` within
> the observed true-positive band (≈3.0–3.3), followed by a mandatory
> post-reconstruction `rows_vertically_coherent` check that discards
> (never merely flags) incoherent candidates — eliminate both known
> failure modes (`jiaocaineedrop_Chapter9.pdf_46`,
> `cmb_stamp_boundary_vi`) without losing recall on `cmb_stamp_table_vi`
> / `hc_stamp_table_vi`, when validated against the remaining unscored
> `realscan_probe` documents and any further real-world picture-region
> population that can be assembled?

---

## Artifacts produced this session (Phase 10 onward)

- `controlled_intervention.py` / `intervention_results.json` (Phase 10;
  fixed a text-attachment bug found this session)
- `factual_oracle_comparison.py` / `factual_oracle_comparison.json` (Phase 12)
- `recovery_verdicts.py` / `recovery_verdicts.json` (Phase 11)
- `negative_controls.py` / `negative_controls.json` (Phase 13)
- `role_ambiguity_analysis.py` / `role_ambiguity_analysis.json` (Phase 16)
- `recommendation.py` / `recommendation.json` (Phases 17–20)
- this file (Phase 21)
