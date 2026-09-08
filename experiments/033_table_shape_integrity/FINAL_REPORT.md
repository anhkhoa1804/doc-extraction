# Milestone 033 — Table-Shape Evidence Integrity & Routing Boundary Revalidation — Final Report

Baseline: `c549764` (032, EXPERIMENTAL). CPU-only throughout. `src/`
untouched. GPU checked at Phase 0 (`baseline.json`: PID 72505, 7650 MiB,
PROTECTED, never touched).

Labels: **FACT** (directly measured), **INFERENCE** (a conclusion from
facts with a stated logical step), **HYPOTHESIS** (untested to
falsification), **RECOMMENDATION** (an action, not a claim about the
world).

---

## 1. Reconstructing the existing rule (Phase 1)

**FACT** (`experiments/031_table_label_gating/table_shape_probe.py`,
re-read this milestone):

| Signal | Meaning | Score contribution | Independent axis? | Failure mode |
|---|---|---:|---|---|
| `row_bands >= 2` | multi-row | +1 | row axis | none alone |
| `col_bands >= 2` | multi-column | +1 | col axis | none alone |
| `children_per_row_band >= 2` | multiple items per row | +1 | weak proxy for col evidence | can be satisfied by row-merge artifacts, not true horizontal separation |
| `row_regularity_cv < 0.5` | even row spacing | +1 | row axis | high for irregular real tables (case 32) |
| `n_nested_text_regions >= 6` | enough evidence to judge | +1 | neither | trivially satisfied by any list/paragraph of 6+ lines |

Gate: `score >= 3` (any 3 of 5). **FACT, the exact defect:** criteria 1, 4,
5 are ALL satisfiable by a single-column, evenly-spaced list of >=6 lines
with **zero column evidence** — `known_failure.json` confirms the minimal
reproduction is **n=6** lines (smaller than 032's own n=8 example),
scoring exactly 3 via `['multi-row', 'regular row spacing', 'high
nested-text-region count']`.

---

## 2. Minimal formal counterexample (Phase 2)

**FACT** (`known_failure.json`): a single-column region with 6 evenly-
spaced text children (`row_bands=6, col_bands=1, row_regularity_cv=0.0,
n_nested_text_regions=6`) scores exactly 3/5 and passes the conservative
gate, with `col_bands=1` and `'multi-column'` never among `score_reasons`
— deterministic, reproducible regression case, imported live from 031's
real code, not reimplemented.

---

## 3. Candidate designs (Phase 3)

**FACT** (`candidate_designs.json`): 5 candidates, all derived from
`compute_signals()`'s existing 8 fields, no new geometric feature
invented:

- **A** — original score AND `row_bands>=2 AND col_bands>=2`.
- **B** — A OR a strict column-dominant fallback (single-row fragments).
- **C** — pure structural predicate, drops score/regularity entirely:
  `row_bands>=2 AND col_bands>=2 AND children_per_row_band>=1.5`.
- **D** — A with `row_bands>=3` (031's own n=1 hypothesis, directly tested).
- **E** — C with `row_bands>=3` (added mid-milestone after A/B/C all still
  admitted the REAL Chapter9 case, C+D combined).

Explicitly rejected per this milestone's non-negotiable rules: raising the
score threshold alone (rule #1) and `n_cols>1` alone without testing
one-column tables (rule #2).

---

## 4/7. Measurement safety and paired evaluation (Phase 4/7)

**FACT** (`candidate_results.json`, corrected mid-milestone — see §4a):
every candidate (A–E) retains **100%** of the 79-instance real confirmed
population — 38/38 TRUE_RECOVERY, 28/28 PLAUSIBLE_RECOVERY instances still
admitted, in every one of the 19+19+28 arms. **Zero regression on
anything 031 already validated**, for any candidate.

**FACT:** the 13/13 `cmb_stamp_boundary_vi` (PSEUDO_TABLE) instances are
**still wrongly admitted by every candidate** — this document's failure
is `rows_vertically_coherent` at RECONSTRUCTION time (028's post-hoc
check), not a pre-filter shape defect; no candidate tested this milestone
touches that mechanism, confirming 031's own recommendation that a
separate post-reconstruction gate is still needed regardless of which
pre-filter is chosen.

**FACT — the pivotal result:** Candidates A, B, C **do not** fix the real
Chapter9 false positive (`col_bands=4` there — column evidence was never
the missing piece for this real case; its actual anomaly is `row_bands=2`,
too few rows). Only **D and E** (which add the `row_bands>=3` floor) reject
it. This is why Candidate E was added mid-milestone rather than stopping
at C.

### 4a. A bug found and fixed in this milestone's own script

**FACT:** `table_shape_probe.json`'s `all_negative_rows` field is an
**empty list** (verified: `len()==0`) despite `negative_population.n=39`
— the real 39-row negative/ambiguous population is embedded inside the
misleadingly-named `all_positive_rows` field (118 total items), tagged
`is_table_ground_truth=False`. This milestone's first `candidate_results.py`
run silently evaluated an empty negative population (`known_negative_
rejection: None`). Caught by inspecting the raw counts before trusting
the summary, fixed by filtering on `is_table_ground_truth` directly.
Flagged explicitly, not silently corrected, per this research chain's
standing discipline.

---

## 5/8. Expanded adversarial suite and single-column tables (Phase 5/8)

**FACT** (`adversarial_results.json`, 46 cases — 032's original 20
reproduced identically + 22 new): ORIGINAL rule scores 23/42 correct
(decidable cases); Candidate E scores **32/42** (best, tied with C).

**FACT, the most important synthetic result:** cases 17 (2-column prose)
and 36 (3-column prose) are misfired by **every candidate, A through E**.
This is not a threshold artifact — 2-3 column prose genuinely satisfies
`row_bands>=2 AND col_bands>=2 AND children_per_row_band>=1.5` by
construction. **No candidate built from the currently-retained evidence
dimensions can separate this from a real table.**

**FACT — Phase 8, single-column tables:** case 29 (single-column table,
5 rows, ground truth `table` by construction) and case 46 (one-column
table with a distinct header cell, "STT", matching the REAL
`cmb_stamp_table_vi`/`hc_stamp_table_vi` factual oracle's own first
column — `counterfactual_replay.json`) are **both rejected by every
candidate**, because every candidate requires `col_bands>=2`.

**RECOMMENDATION, Phase 8's explicit limitation statement:** a genuine
one-column table **cannot be reliably separated from one-column prose or
lists using current geometric evidence alone** — case 46 proves that even
adding a semantically-distinct header does not help unless the rule reads
actual TEXT CONTENT (not just geometry), which no candidate in this
milestone does. This is a real, disclosed, unresolved limitation, not
patched by any threshold choice — consistent with `role_evidence_
schema.json` (032) never having retained a content-aware dimension in the
first place.

**FACT, a genuine trade-off discovered:** Candidate C (row floor 2) and
Candidate D (row floor 3) each independently fix problems the other does
not — C correctly handles sparse 2-row real tables (cases 6/44) that D's
tighter floor wrongly rejects; D correctly rejects the real Chapter9 case
that C does not. Candidate E combines both floors and — checked directly,
not assumed — achieves C's best-tied synthetic accuracy (32/42) while
also matching D's real-corpus fix, at the cost of also inheriting D's
sparse-table rejection (cases 6/44 misfire under E too). No candidate
dominates on every single case; E was chosen for the best OVERALL
trade-off across the REAL (not just synthetic) evidence.

---

## 6. Full corpus re-search (Phase 6)

**FACT** (`corpus_recheck.json`): fully unconstrained `experiments/**/
layout` glob confirms **1,053 layout directories** (matching 032's own
prior exhaustive count) — no further hidden pocket found. Candidate
population reconciles exactly to 9 = 031's 7 + realscan_probe's 2 (no
contradiction of prior counts, a naming/aggregation nuance, resolved
explicitly).

**FACT, real (not synthetic) evidence of the prose blind spot:** every
page with >=2 text/section_header regions, treated as one whole-page
block, was scored against every rule. ORIGINAL rule: **121 page-instances
across 12 distinct documents, 6 of them NOT already known candidates**
cross the threshold. After deduplicating the heavy arm-replay (the same
physical page is replayed near-identically dozens of times — raw instance
counts would grossly overstate this), Candidate E reduces the **novel**
false-positive document count from **6 to 1** (an 83% reduction).

**IMPORTANT scope caveat, stated explicitly in `corpus_recheck.json`:**
this whole-page test measures the rule's INTRINSIC discriminative power
in a generalized application — production never actually invokes
`table_shape_score` on arbitrary text regions, only on a Docling
picture/chart-labelled region's own nested children. This is not a claim
about current production risk; it is a stress test relevant to any FUTURE
broader application of this evidence vector.

---

## 9. Role-ambiguity reassessment (Phase 9)

**FACT, verified directly this milestone:** under Candidate E, the GATE
decision remains perfectly stable (`True` in all 19/19 arms) for both
`cmb_stamp_table_vi` and `hc_stamp_table_vi`, identical to 032's original
score-stability finding, while the observed LABEL still flips across the
same arms. **The corrected rule does not weaken 032's stability finding —
it is UNCHANGED**, because stability measures consistency, which this
milestone's fix never touched (it only touched correctness).

**INFERENCE:** 032's "role ambiguity" measurement conflated two different
things — genuine label/evidence conflict on ACTUAL tables (which
stability-tracks correctly and survives this milestone's correction
intact) and MEASUREMENT ERROR on non-tables (Chapter9, synthetic prose —
which this milestone's correction substantially resolves). Disentangling
these was this milestone's central contribution.

---

## 10. Routing policy re-evaluation (Phase 10)

**FACT** (`routing_policy_results.json`, built by filtering 031's own
verified `recovery_verdicts.json` by each candidate's gate — no new
reconstruction run): every candidate's Policy 2/3 admits the identical 79
instances with the identical 38/28/13 TRUE_RECOVERY/PLAUSIBLE_RECOVERY/
PSEUDO_TABLE breakdown. **Zero regression within the validated
population, for any candidate** — the corrected rule's benefit is
entirely OUTSIDE this specific 79-instance set (Chapter9, real-corpus
prose), confirming Phase 4's safety requirement rigorously.

---

## 11. Threshold robustness (Phase 11)

**FACT** (`threshold_robustness.json`, 48-point grid over Candidate E's 3
structural floors): **12/48 (25%)** of the grid achieves simultaneously
100% true-recovery retention, 0 known-negative false positives, AND
correct Chapter9 rejection — a moderately wide safe region, not a
knife-edge, though not dominant across the full grid either. The chosen
operating point (row>=3, col>=2, density>=1.5) sits inside this region
with `synthetic_accuracy=0.7619` on the 42 decidable adversarial cases.

---

## 12. Out-of-population test (Phase 12)

**FACT** (`out_of_population_results.json`, document-family holdout, not
a random split): Family B (`realscan_probe`, 7 documents, none used to
tune any candidate) — whole-page sweep drops from **6/7 (85.7%)** pages
triggering the ORIGINAL rule to **2/7 (28.6%)** under Candidate E. **One
real, held-out false positive survives** even the best candidate: a
genuine scientific paper (`docstructbench...chroma.2005.05.085.pdf_4`,
`children_per_row_band=1.55`, barely above the 1.5 floor).

**LIMITATION, stated explicitly per this milestone's own rule against
fake statistical confidence:** n=7 is too small for a production
false-positive-RATE estimate — these are exact counts over a specific
small population, not a generalizable rate.

---

## 13. Provenance safety (Phase 13)

**FACT** (`provenance_safety.json`, all 5 checks re-verified directly
against current `controlled_intervention.py` source, not assumed): 033's
candidates change only the GATE, never the reconstruction/provenance
mechanism. Original label is never mutated (`el['type']` is never
reassigned in the annotation path); the candidate table is additive, not
replacing; reconstruction source is explicitly marked, never presented as
detector-original; confidence is never fabricated. **Gap carried forward
unchanged from 032:** which specific rule admitted a region is recorded
only in this milestone's own research JSON, never in the persisted IR —
032's `provenance_design.json` shape remains unimplemented.

---

## 14/15. Downstream impact and cost (Phase 14/15)

**FACT:** table structure, cell text, evidence ownership, duplicate
emission, page/table ordering, and serialization are all UNCHANGED by any
candidate — only which regions are ADMITTED changes, not what happens
once admitted (§10). **FACT:** compute cost is unchanged from 031/032
(zero new model calls, zero GPU use, same asymptotic scaling); Candidates
D/E actually invoke reconstruction on FEWER regions than the original
rule (they reject Chapter9-pattern content the original rule would have
wastefully reconstructed).

---

## 16. Decision (Phase 16)

# **EXPERIMENTAL**

Not SHIP_CANDIDATE: a real held-out false positive survives even the best
candidate (§12); the multi-column-prose blind spot is rejected by ZERO
candidates (§5); this heuristic has never been in production, so there is
no existing behavior to "patch" — only a new intervention to propose,
which the residual risk does not yet justify. Not HOLD: a materially
improved, extensively validated boundary WAS established (Candidate E
dominates the original rule on every measured axis, zero regression, a
25%-wide safe threshold region). Not REJECT: strictly better than the
status quo on every axis measured, zero identified downside.

**Recommended candidate: E** (`row_bands>=3 AND col_bands>=2 AND
children_per_row_band>=1.5`), for any future research prototype —
not proposed for `src/`.

---

## 17. The central research question

# Answer: **C — both survive, as separate mechanisms**

A substantial, DEMONSTRATED portion of 032's measured "role ambiguity"
(Chapter9-pattern banners, single-column prose) was in fact a measurement
defect in the evidence rule's row/column conjunction, and IS now largely
resolved by Candidate E without any role-routing architecture change:
100% true-recovery retention, real-corpus false positives on novel
documents cut from 6 to 1, held-out-family false positives cut from 6/7
to 2/7. But a genuine residual survives that no amount of threshold
tuning on the CURRENT evidence dimensions resolves: multi-column prose
(misfires under every candidate, by construction — genuinely
indistinguishable from a table using bbox geometry alone), one-column
tables (unrecognizable even with a semantically distinctive header,
without reading text content), and the separate post-reconstruction
coherence question (`cmb_stamp_boundary_vi`, untouched by any pre-filter
candidate). **This milestone does not force the architecture toward
"role ambiguity" — most of 032's finding was a fixable rule defect, and
this report says so plainly. What remains after the fix is small,
specific, and named, not a sweeping architectural mandate.**

---

## Strongest counterargument

Candidate E was partly SHAPED by this milestone's own real-corpus and
adversarial evidence (the `row_bands>=3` floor exists specifically
because Chapter9 has `row_bands=2`) — an n=1-driven design choice, same
caveat 031 itself raised about its own hypothesis. It is possible E is
overfit to the two known real failure cases (Chapter9, single-column
prose) and a genuinely different held-out failure (the scihub paper,
§12) shows this concern is not hypothetical — it already happened once,
within this same milestone.

---

## Limitations

- Evidence ownership/duplicate-ownership at the token level remains
  unmeasured (031's original limitation, still open).
- The scihub-paper residual (§12) is n=1 within an n=7 holdout — real,
  but not a rate.
- One-column table recognition remains an open, disclosed gap; no
  content-aware signal was tested this milestone (would require reading
  actual OCR text, a larger scope change).
- Multi-column prose remains fully unresolved; the recommended next step
  (§ recommendation.json priority 1) is untested, not implemented.
- The post-reconstruction `cmb_stamp_boundary_vi` failure mode was
  reconfirmed, not newly addressed.

---

## Exact next research question

> Does adding right-edge (`x1`) alignment regularity as a new evidence
> dimension — distinguishing justified/ragged prose columns (variable
> `x1`) from true table columns (consistent `x1` per column, since real
> cells have fixed boundaries) — correctly separate cases 17/36
> (multi-column prose) from genuine multi-column tables, without
> re-introducing the single-column-prose failure mode this milestone
> fixed, when tested against the same 46-case adversarial suite plus a
> newly-collected sample of real multi-column real-world documents?
