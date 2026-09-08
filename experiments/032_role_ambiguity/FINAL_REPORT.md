# Milestone 032 — Role Ambiguity & Evidence-Based Routing — Final Report

Baseline: `10ad80b` (031, EXPERIMENTAL). CPU-only, read-only over 023–031's
historical IR plus one small set of explicitly-synthetic adversarial
controls. `src/` untouched throughout. GPU checked at Phase 0
(`baseline.json`), never used.

Labels: **FACT** (directly measured), **INFERENCE** (a conclusion from
facts with a stated logical step), **HYPOTHESIS** (untested to
falsification), **RECOMMENDATION** (an action, not a claim about the
world).

---

## 1. Why role ambiguity was investigated

**FACT** (029/030/031 FINAL_REPORT.md, all read in full this milestone):
the research chain since 025 has repeatedly found that a hard,
mutually-exclusive detector label collapses information a more careful
analysis can recover — 029 called table-label correctness "formally
undecidable from the final IR alone" (029 §13); 031 found a real, if
narrow, mechanism for recovering some of it (2/4 documents, factual-oracle
confirmed) but also found the recovery method itself has real false-
positive risk. 032's premise: is there a GENERAL, reusable notion of
"role ambiguity" underneath the specific table/picture case, and does
representing it explicitly change anything?

---

## 2. Current role semantics (Phase 1)

**FACT** (`role_contract.json`, verified against current source, not
quoted from 031): the IR expresses exactly two of six requested concepts
as real, persisted fields:

| concept | exists? | carrier |
| --- | --- | --- |
| observed_role | ephemeral only | `Region.label` (pipelines/base.py:52-56, a dataclass never copied onto the persisted `Element`) |
| candidate_roles | **NO** | no field anywhere holds more than one role per region |
| evidence | PARTIAL | `Element.confidence` is fully wired end-to-end but the one layout backend in use (Docling) hardcodes it to `None` (docling_backend.py:322, re-verified this milestone) |
| routing_decision | implicit only | pure control flow (base.py:747, base.py:613) — outcome never written to data |
| final_role | YES | `Element.type`, a 9-value `ElementType` enum |
| provenance | YES | `source_backend`, `source_id`, `order_index`, `extra` (dict, free-form) |

**FACT, new this milestone (Phase 2, `role_contract.json` `phase_2_route_
mapping_consistency`):** two independently-maintained label→role mapping
tables exist — `pipelines/base.py`'s `_LABEL_TO_ELEMENT_TYPE` (scanned-page
route) and `docling_backend.py`'s `_LABEL_MAP` (whole-document route).
**18 of 28** label keys disagree between them. Most significant: Docling's
actual output format is `checkbox_selected`/`checkbox_unselected`
(underscore) — confirmed by a full corpus scan (2,210 layout files,
`role_contract.json` `observed_label_frequencies`: 19 + 38 = **57 real
historical instances**). `_LABEL_MAP` (whole-document route) correctly maps
these to `ElementType.CHECKBOX`; `_LABEL_TO_ELEMENT_TYPE` (scanned-page
route — the one every historical experiment actually exercises) only has
hyphenated keys (`checkbox-selected`), so **every one of those 57 real
checkbox regions silently becomes `ElementType.OTHER`** in this
repository's actual historical output. This is a genuine, verified,
previously-undocumented bug — orthogonal to the role-ambiguity question,
not fixed here (`src/` untouched), flagged as a separate low-risk fix
candidate.

**FACT:** `ElementType.SIGNATURE` is declared (schemas/element.py:29) but
structurally unreachable — no key in either mapping table produces it, and
it appears nowhere else in `src/` except a color entry in a visualization
helper.

---

## 3. Evidence model (Phase 4)

**FACT** (`role_evidence_schema.json`): 14 dimensions retained (available,
interpretable, reproducible, at least a stated routing-relevance
rationale), 4 rejected with reasons recorded (stamp overlap, image
texture — no pixel-level analysis exists anywhere in this repository;
grid_consistency — computed only post-reconstruction by 028's
`structural_integrity`, never as a pre-filter).

**FACT, verified by direct source inspection this milestone, not
asserted:** `col_regularity_cv` is computed by 031's `table_shape_probe.py`
for every candidate but **never used** in `table_shape_score`'s point
rule — a real, previously-unstated gap in 031's own probe.
`row_regularity_cv` IS used.

---

## 4. Role population (Phase 3)

**FACT** (`role_ambiguity_population.json`): 23 real items assembled from
historical IR (19 CONFIRMED, 1 PLAUSIBLE, 3 UNKNOWN/not-individually-
verified) plus 6 categories explicitly reported as **absent from this
corpus, not invented**: form, chart, signature, logo, stamp (as a distinct
detector label — confirmed absent from the full 2,210-file label-frequency
scan), decorative. **FACT, important nuance:** "stamp" is not a role this
corpus's detector or IR represents anywhere — it is a human document-
naming convention applied during corpus generation. Every stamp/seal
document in 031's 7-document population is labelled `picture` by Docling;
the domain concept "stamp" is invisible at the detector-label layer.

---

## 5. Label/evidence conflicts (Phase 5)

**FACT** (carried forward and re-verified from 031's `role_ambiguity_
analysis.json`, not recomputed): 5/11 evaluated picture-labelled regions
in 031's population produce a label/evidence conflict; 3 were confirmed
real tables, 2 confirmed not tables. **FACT, new this milestone (§2):** a
SECOND, structurally different kind of label/evidence conflict exists —
the route-dependent label-mapping disagreement — affecting checkboxes and
(in principle) charts/forms, independent of any structural-evidence
question.

---

## 6. Route flip analysis (Phase 6)

**FACT** (`role_transition_matrix.json`, reshaped from 031's already-
verified `paired_gating_cases.json`, not re-derived): `cmb_stamp_table_vi`
and `hc_stamp_table_vi` are `UNSTABLE_CLEAN_FLIP`; `cmb_stamp_boundary_vi`
is `UNSTABLE_COEXISTENCE` (never a clean flip — consistent with 031's own
finding that this document does not behave like the other two).

**FACT — route-family outcome matrix:** adaptive (native) → table_only=3,
picture_only=0, coexist=0. scan_cohort/coverage (rasterized) →
table_only=1, picture_only=2, coexist=0. visual (forced-OCR, not
rasterized) → table_only=0, picture_only=1, coexist=2. **INFERENCE,**
unchanged from 031: the earliest observable divergence is at the
**routing** stage (whether the page is rasterized before Docling sees it),
not the OCR-recognizer stage.

**FACT, new observation:** no case exists anywhere in the replayed corpus
of a genuinely table-labelled region becoming picture-labelled with no
trace — the only observed direction is picture-only ↔ {coexist,
table-only}. Consistent with `traverse_pictures=True` always being the
SOURCE of the duplicate, not a symmetric confusion.

---

## 7. Stability analysis (Phase 7) — the central positive finding

**FACT** (`role_stability.json`): for **3 of 7** documents, the evidence
vector is *strictly* more stable than the observed role across every
recorded arm — concretely, `table_shape_score` is **exactly 4** in
literally every one of 19 arms for both `cmb_stamp_table_vi` and
`hc_stamp_table_vi`, while the observed role flips (2 distinct states)
across those same arms. **0/7 documents show the reverse** (evidence less
stable than role).

**LIMITATION, stated plainly:** n=7, one small document family — this is
an exact measurement over this population, not a general claim.

---

## 8. Ambiguity score (Phase 8)

**RECOMMENDATION, not newly implemented:** the score already exists and
is already correctly named — `table_shape_evidence_score`
(`role_evidence_schema.json`, `role_ambiguity_population.json`) — never
called "confidence." Its components (`score_reasons`) are individually
interpretable. §9's adversarial testing is a test OF this score, not a
replacement for it.

---

## 9. Routing policy comparison (Phase 9)

**FACT** (`routing_policy_results.json`, built on 031's already-executed
arms, not re-run): Policy 0 (current hard gate) recovers 0 tables.
Policy 1 (evidence override, tested only via 031's AGGRESSIVE arm as an
explicitly-labeled, lower-risk PROXY — a true override was never
implemented, rejected at design time by 031) recovers 66 true-table
instances but creates 39/39 false tables on the known negative population.
Policy 2 (ambiguity-aware defer) recovers the same 66 true-table instances
with **0** false tables on the same negatives. **FACT, important:** Policy
3 (candidate-role routing) is **not a distinct tested mechanism** in this
repository — 031's conservative-mode implementation already keeps the
original label AND adds a provenance-marked candidate, which IS Policy 3's
definition. 032 set out to evaluate this as a new idea and found it was
already implicitly built.

---

## 10. Factual paired evaluation (Phase 10)

Covered by §9 — the same 118-row population, same arms, same documents as
031's factual-oracle-backed evaluation (`recovery_verdicts.json`,
`factual_oracle_comparison.json`). No new paired evaluation was run; §9's
numbers ARE the paired evaluation, reused rather than duplicated.

---

## 11. Hard negatives (Phase 11)

**FACT** (`negative_controls.json`, this milestone's own): 031's
"exhaustive" search pattern (`experiments/*/_runs/**/layout`) itself
missed a real pocket — `experiments/024_ocr_fidelity_recovery/_l5prod/
_runs/` (49 layout directories, verified this milestone by using the
fully unconstrained `experiments/**/layout` glob and diffing against
031's pattern). Re-scanning it found 7 candidate instances, **0 belonging
to a genuinely new document** — all already known from 031's population.
**CONCLUSION, restated:** the negative-control limitation stands exactly
as 031 described it; this milestone's contribution is confirming 031's
population count via a MORE completely verified search, not discovering a
new gap in the population itself. 031's Chapter9 false positive remains
the only confirmed real-world false positive in this repository's
artifacts.

---

## 12. Adversarial controls (Phase 12) — the second key finding

**FACT** (`adversarial_controls.json`, 20 synthetic cases, real
`table_shape_score`/`compute_signals` code, not reimplemented): 6/17
decidable misfires (2 cases marked `AMBIGUOUS_BY_DESIGN` — form vs. table,
and repeated-template pseudo-table vs. table — genuinely undecidable from
geometry alone, not forced to a verdict).

**FACT, the most important single result of this milestone:** case 8
("aligned paragraph" — ordinary justified prose, single column, evenly
spaced lines) and case 18 ("dense bullet list") both **pass the
conservative gate** (score = 3), using ONLY row-based criteria
(`multi-row`, `regular row spacing`, `high nested-text-region count`) —
**zero column evidence is required**, because `table_shape_score` awards
points from 5 independently-scored criteria without requiring row AND
column evidence jointly. This is a more severe and more easily-triggered
false-positive mode than 031's Chapter9 case (which did require genuine
multi-row **and** multi-column structure). Case 15 reproduces 031's real
confirmed Chapter9 false positive exactly (same geometry), confirming the
synthetic-vs-real correspondence is faithful.

**RECOMMENDATION:** require `row_bands >= 2 AND col_bands >= 2` jointly
before any other criterion is even evaluated — a small, fully-simulable
fix against this exact 20-case set, not implemented in `src/` this
milestone.

---

## 13. Predictiveness of ambiguity (Phase 13)

**FACT, from §7 + §12 combined:** ambiguity (via the evidence vector) IS
predictive of role instability where a direct comparison exists (3/7
documents, 0 reverse cases) — supporting the idea that ambiguity is a
meaningful latent variable, not cosmetic. **FACT, the important
qualifier:** predictiveness of INSTABILITY is not the same claim as
RELIABILITY of the underlying score — §12 shows the same score can be
high for content that is not ambiguous at all, just wrongly scored (prose
is not "ambiguously a table"; it is confidently not a table, and the
current rule still misfires on it).

---

## 14. Downstream implications (Phase 14)

**FACT:** no RAG/GraphRAG pipeline exists in this repository to test
against (consistent with 030 §13's own finding, unchanged). **INFERENCE:**
preserving role uncertainty (via `provenance_design.json`'s additive
shape) would let a future downstream consumer choose whether to trust a
picture-labelled region's flattened text as prose versus flag it for
secondary handling when `candidate_roles` shows an active conflict — this
is a **PROJECTION**, not backed by an experiment, exactly as 030
distinguished for the same kind of downstream claim.

**FACT, re-derived and reconfirmed this milestone (§9, reused from 031):**
the tested dual-candidate policy shows **zero** change to Layer-1 recall
on the negative/other document populations — no evidence of general-
document-semantics harm was found, though this was never tested against
real running prose (only synthetic prose, §12), which is the actual gap
Case 4 of Phase 19 would need to close.

---

## 15. Provenance design (Phase 15)

**RECOMMENDATION** (`provenance_design.json`): reuse `Element.extra`
(already a viable, already-used carrier per 031's own precedent —
`extra['031_table_candidate_added']`) rather than a schema migration.
Proposed shape carries `observed_role`, `candidate_roles` (each with its
`table_shape_evidence_score`, never called confidence), `routing_decision`
+ `routing_reason`, `specialist_results`, and `final_role` — with
`final_role` explicitly NOT auto-promoted, preserving 031's own
established design discipline.

---

## 16. Cost (Phase 16)

**FACT** (`production_assessment.json`): zero new model calls, zero GPU
use, linear worst-case scaling in nested-child count — unchanged from
031's own cost finding, reconfirmed rather than assumed.

---

## 17. Minimal architecture change (Phase 17)

**RECOMMENDATION:** Option B (role candidates + routing reason, carried in
`Element.extra`) is the smallest change that captures the actual evidence,
**contingent on first fixing `table_shape_score`'s row-AND-column gap
(§12)** — a correctness fix, not an architecture change, and cheaper than
either. Option D (a dedicated routing layer) is explicitly REJECTED as
premature: building infrastructure around a signal with a demonstrated,
easily-triggered false-positive mode is not justified yet. Option E
(table-gate-only fix) is too narrow given §2's broader label-mapping
inconsistency finding.

---

## 18. Production assessment (Phase 18)

**Decision: EXPERIMENTAL** (`production_assessment.json`). Correctness is
not yet there (6/20 adversarial misfires, one severe); every other axis
(observability, explainability, provenance, backward compatibility,
latency, memory, failure isolation, determinism, rollback, operational
complexity) is favorable IF and only if the underlying evidence signal is
first made reliable.

---

## 19. Strongest counterargument

The strongest case against this report's own EXPERIMENTAL verdict: the
6 adversarial misfires are entirely SYNTHETIC, hand-constructed by this
milestone's own author to be adversarial — it is possible real-world
prose rarely achieves case 8's idealized perfectly-even line spacing
(`row_regularity_cv = 0.0` exactly), and the true real-world false-positive
rate could be much lower than the synthetic test suggests. Counter-
response: 031's OWN real (not synthetic) Chapter9 discovery already
falsified an earlier "100% precision" claim once; the responsible prior,
repeated from 031, is that more failure modes exist and have not all been
found — a synthetic case reproducing a plausible, ordinary document
pattern (justified paragraph text) is exactly the kind of evidence that
should lower confidence, not be dismissed for being constructed rather
than discovered.

---

## 20. Final recommendation

**EXPERIMENTAL.** Fix `table_shape_score`'s row-AND-column conjunction gap
(§12, trivial, fully-simulable) as a prerequisite, THEN re-run 031's full
population plus this milestone's 20 adversarial cases to confirm the fix
does not regress recall on the 3 confirmed true-recovery documents while
eliminating the prose-misfire mode — only then would Option B
(`provenance_design.json`) be ready for a real (still non-production,
still research) prototype. Do not ship Option B or any evidence-based
routing change to `src/` until that re-validation exists.

---

## 21. Limitations

- The role-stability finding (§7) is exact over n=7 documents, one small
  corpus family — not a general claim.
- The adversarial controls (§12) are synthetic; no real-world prose
  sample from this corpus was scored against `table_shape_score` to
  confirm the misfire mode occurs on ACTUAL text, not just idealized
  constructed geometry (a concrete, cheap next step: score every 'text'/
  'section_header' region in the historical corpus against
  `table_shape_score` and count how many exceed threshold 3).
- The label-mapping inconsistency (§2) is a verified CODE-level finding;
  the whole-document route was never exercised in any historical
  experiment, so its real-world manifestation (beyond the checkbox count)
  is not empirically observed.
- Downstream RAG/GraphRAG value (§14) remains PROJECTION, not measured,
  consistent with every prior milestone in this chain.
- Policy 1 (§9) was tested only via a proxy (031's aggressive arm); a
  true label-override policy was never implemented or measured.

---

## 22. Exact next research question

> Does scoring every `text`/`section_header`-labelled region in the
> ALREADY-REPLAYED historical corpus (not just picture-labelled ones)
> against `table_shape_score` reveal real (not synthetic) instances of
> ordinary prose crossing the conservative threshold — and, after fixing
> the row-AND-column conjunction gap this milestone found, does that same
> real-corpus sweep drop to zero false positives while `cmb_stamp_table_vi`
> and `hc_stamp_table_vi` still recover cleanly?

---

## Reproducibility (Phase 21)

See the commit for the exact verification performed: all scripts rerun
twice with byte-identical output, full test suite at `341 passed, 10
skipped`, `git diff --check` clean, 029/030/031 artifacts and `src/`
untouched, `uv.lock` still untracked.
