# Research proposal: table candidate composition — scope and ceiling

Owner: Opus, taking over from Sonnet (commit `746808f`). This document is
the structured writeup the task's own template asks for; the full evidence
trail lives in `experiments/005_omnidocbench/observations.md` ("Bottleneck
Analysis" and "Opus audit and oracle analysis") and
`experiments/005_omnidocbench/results/comparison.md`. `docs/research_direction.md`
is the shorter narrative version.

## Problem

Table structure recognition was identified (Sonnet's audit, independently
re-verified here) as the largest addressable component of OmniDocBench
table-metric loss — not OCR, not reading order, not serialization. Two
independently-trained structure models already exist in this pipeline
(`TableTransformerBackend`, Docling's own TableFormer via
`DoclingBackend.native_tables`) and disagree on which tables they handle
well. A cheap per-table selection rule (cell fill-rate) between the two
produced a real, measured gain (`table TEDS.all` +0.073, ~28% relative, on
the 20-page subset). The open questions this proposal answers: how much of
the *theoretically available* gain does that heuristic actually capture,
whether a more sophisticated selector is justified by the evidence, and
whether the same composition idea can safely reduce compute (run the
expensive model only when needed) rather than always running both.

## Observation

Re-verified against primary sources, not the prior report alone:

- Every reported number checked against raw `metrics.json` files and
  `run_metadata.json` (ground-truth hash, evaluator commit, config,
  seed) across all four existing runs (`local_baseline`, `local_improved`,
  `local_table_ensemble`, `local_table_ensemble_100`) — all matched.
- The implementation (`select_better_populated_table`,
  `_apply_native_table_fallback`, `DoclingBackend.native_tables`) does
  exactly what its docstrings claim.
- Cross-run comparison of `TableTransformerBackend`'s output is **not**
  fully reliable: the same image, same code, same config produced
  different structure output (`book_zh_DLT10902008` TEDS 0.232 in one
  `prepare.py` invocation vs. 0.368 in a separate one) — a
  previously-undocumented reproducibility gap, most likely multi-threaded
  CPU inference nondeterminism in the detection/structure transformer
  (`native_tables()` was directly checked and found bit-identical across
  repeated calls, ruling out Docling as the source). This does not affect
  any of the large, already-reported deltas (which are far larger than
  this noise), but it does mean any *new* TT-vs-X comparison must be run
  in one coherent process, not stitched together from separate runs — the
  methodology this proposal's own oracle analysis uses throughout.

## Hypothesis

> Cell fill-rate is a cheap, general "did this extraction produce
> anything" signal, not a "is this extraction correct" signal. It should
> capture most, but not all, of the gap between always-picking-one-model
> and an oracle that always picks the ground-truth-better candidate — and
> the cases it misses should be attributable to a specific, nameable
> mechanism (not random noise), since the underlying model behaviors are
> deterministic given a fixed input.

## Architecture

`Candidate generation → quality representation → selection → canonical
document`, instantiated at the table level (the task's proposed general
shape, applied to the first controlled case where this project already
has two independent producers of the same structure):

```
TableTransformerBackend.extract()  ──┐
                                       ├─→ TableCandidate (table + quality features) ──→ select_best_table_candidate ──→ Table (merged into Page)
DoclingBackend.native_tables()     ──┘
```

Refactored `src/doc_extraction/pipelines/base.py` so this is genuinely
N-candidate and backend-agnostic, not hardcoded to exactly these two
backends:

- `TableCandidate(table, source, quality)` — the common interface; nothing
  downstream branches on `source`.
- `compute_table_quality_features(table)` — `fill_rate`, `n_cells`,
  `avg_text_len`, `empty_cell_ratio`. Deliberately does **not** invent
  `ocr_confidence` (neither backend populates `Cell.confidence` — checked
  directly in `schemas/table.py`) or cross-model bbox agreement as an
  independent signal (checked directly: Table Transformer receives its
  table bbox from Docling's own layout stage by default, so TT-vs-Docling
  IoU is ~1.0 by construction on every table tested — not genuine
  cross-model consensus).
- `select_best_table_candidate(candidates, key="fill_rate")` — N-way,
  deterministic tie-break by input order.
- `select_better_populated_table` / `_apply_native_table_fallback` — kept
  as thin, behavior-preserving 2-candidate wrappers (all 10 pre-existing
  tests pass unmodified) so the production pipeline's actual behavior is
  unchanged by this refactor.
- `_gather_extra_table_candidates` — a list of recognized candidate-source
  method names (currently just `native_tables`); adding a third backend
  that exposes its own `*_tables(page)` method is a one-line addition
  here, not a change to selection logic.

## Selector

Default and only currently-justified selector: **fill-rate**, unchanged
from Sonnet's implementation. Considered and rejected on evidence, not by
default:

- **A weighted multi-signal score** (fill-rate + avg_text_len + n_cells
  + ...): no evidence a specific combination outperforms fill-rate alone
  on the available sample size (n=7 real tables at 20 pages); the task's
  own instruction is not to invent weights without data support.
- **A pairwise/learned ranker**: explicitly not attempted — nowhere near
  enough labeled examples (7-30 real tables) to fit or validate one
  without simply memorizing this specific sample.
- **Confidence-aware selective escalation** (run Table Transformer only
  when Docling's own result looks uncertain, to save compute): tested
  directly using each candidate's own quality features as the trigger.
  Docling's own fill-rate is binary (1.0 whenever it detects anything,
  0.0 otherwise) — no graded confidence information to threshold on.
  Table Transformer's fill-rate is graded but not predictive in the
  useful direction: the pages where escalating to Docling gives a real,
  large win (`eastmoney` +0.746, `yanbaor2` +0.226, `docstructbench`
  +0.498) have *moderate* TT fill-rate (0.333–0.636, not near zero), while
  TT fill-rate of exactly 0.0 appears in **both** a case where escalating
  is right (`docstructbench`) and two cases where it actively hurts
  (see Ablations). No threshold on either signal separates these
  correctly. **This is a genuine negative finding, reached by measurement
  before implementation, per the task's explicit instruction** — it is
  reported as such, not smoothed over.

## Ablations (20-page subset, n=7 real GT tables)

| Selector | mean table TEDS | matches oracle |
|---|---:|---:|
| Always Table Transformer | 0.2376 | 0/7 |
| Always Docling | 0.3325 | 5/7 (coincidentally, on this sample) |
| Fill-rate (production) | 0.3325 | 5/7 (71%) |
| **Oracle** (upper bound — picks whichever candidate has the higher *ground-truth* TEDS; not a production method) | **0.4476** | 7/7 by definition |

Headroom (oracle − fill-rate): **+0.115 mean TEDS**. Both misses share one
root cause: OmniDocBench's TEDS scores an all-empty prediction generously
against a naturally-sparse ground-truth table, and fill-rate cannot
distinguish "correctly recognized nothing is here" from "failed to
recognize something that is here." Checked directly whether any
fill-rate-based rule closes this without breaking a currently-correct
decision elsewhere — none does: `docstructbench` (a real, large,
currently-correct win) has the *identical* TT-fill-rate-is-zero signature
as both misses, so a rule keying on that signal alone cannot separate them.
Part of this headroom is therefore attributable to the benchmark's scoring
function on sparse tables, not to a genuinely closable extraction-quality
gap — this is stated explicitly rather than reported as pure recoverable
headroom.

Disagreement coverage (20-page subset): of 7 real GT tables, 2 are
unrecoverable by any composition (both models fail — a detection/structure
capability ceiling, out of scope here), 5 show disagreement (composition
opportunity), and fill-rate correctly resolves 3 of those 5.

**F. Selective fallback (primary + escalate only on low confidence):**
tested via simulation over the same candidate data (no new inference
needed) — not implemented in the pipeline, because section "Selector"
above found no reliable trigger signal. Simulating "escalate whenever
either model's fill-rate is below some threshold" was checked across the
achievable threshold range and never both (a) avoids the two artifact
losses and (b) still captures the two large real wins — those requirements
are in direct tension on this data, as detailed above.

## Results

**20-page subset (n=7 real GT tables):** see Ablations above and
`observations.md` sections 12–15 for the full per-table breakdown and
methodology (including why a first cross-run reconstruction attempt was
discarded as unreliable, and the coherent single-run fix).

**100-page subset (30 real GT tables) — directly measured, no
reconstruction:** the actual production fill-rate selector's per-table
output (already generated by `local_table_ensemble_100`) shows 14/30
tables (47%) score exactly 0.0 TEDS — the "both models fail together"
component is *more* common at this scale than the 7-table sample
suggested (29%), not less. This is the single most important number the
larger sample adds: it narrows the claimed opportunity for composition
rather than inflating it, which is the direction a good validation should
move an optimistic small-n estimate.

**100-page oracle-ceiling breakdown: not completed.** Attempted with the
same coherent single-run methodology; 11 of the subset's 29 table-bearing
pages are independently flagged by the official evaluator as
pathologically slow for TEDS matching alone (`[TEDS-timeout]` in
`logs/local_table_ensemble_100_evaluate.log`, near the 120s cap). Even
after excluding those 11 up front (a cost-based, not outcome-based,
exclusion) and restricting to the remaining 18, generating fresh
candidates for the first untested page ran past 850 CPU-seconds without
completing. Stopped rather than left running for an open-ended time —
see `observations.md` section 17 for the full accounting. The n=7
oracle-headroom result (+0.115 mean TEDS) is reported as a small-sample,
mechanistically-explained directional finding, not re-confirmed at n=30
for the specific size of the residual gap.

## Limitations

- n=7 (20-page) and the ~18-table 100-page check are both small relative
  to the full 1651-page dataset; the qualitative pattern (fill-rate
  captures most but not all of the oracle ceiling, via one specific
  identified mechanism) is mechanistically explained, not just observed,
  which is the strongest evidence available at this sample size — but it
  is not a population-level statistical claim.
- The oracle itself is not a clean "true quality" upper bound: part of the
  gap it measures is a property of OmniDocBench's TEDS scoring on sparse
  tables (rewarding emptiness), not of extraction quality a downstream
  consumer would actually prefer. Reported explicitly rather than treated
  as pure recoverable headroom.
- The "both models fail together" rate (2/7 at n=7; the 100-page subset's
  actual production run shows 14/30 = 47% of all real GT tables scoring
  exactly 0.0 TEDS with the current fill-rate selector already applied)
  remains outside what any composition-layer change can address — it is a
  detection/structure model-capability question.
- Cross-model geometric agreement is not currently a usable independent
  signal in this architecture, because Table Transformer's table bbox
  comes from Docling's own layout stage by default — a real architectural
  constraint on what "cross-specialist agreement" (task section 9) can
  mean here without also decoupling layout detection between the two.

## Addendum: hard-table capability analysis (supersedes parts of the above)

A follow-up session asked *why* both specialists fail on the same tables.
Two findings revise this proposal materially. Full evidence:
`experiments/005_omnidocbench/hard_tables/failure_taxonomy.md`,
`observations.md` sections 18-23.

**1. The both-fail statistic quoted above was contaminated.** The upstream
evaluator scores any TEDS comparison exceeding a 120-second wall-clock
timeout as `0.0`, indistinguishable from real failure. Re-evaluating
byte-identical predictions with no timeouts gives `table TEDS.all`
**0.4080** (not 0.2743) and **8/30** both-fail (not 14/30), with every
non-TEDS metric bit-identical and two independent runs agreeing to 1e-9.
The "47% at scale, worse than the small sample's 29%" claim in Results and
Limitations above is **withdrawn** — the corrected 27% matches the small
sample.

**2. The both-fail region is not primarily a capability gap.** Classified
by replaying the production path per page:

| Category | Tables | Model capability gap? |
|---|---:|---|
| Composition-layer loss | 3 (37.5%) | No — viable candidate discarded |
| Shared detection failure | 4 (50.0%) | Yes — at *detection*, not structure |
| Orphaned table | 1 (12.5%) | No — produced, never referenced |

"Both detect, both produce similar wrong structure" occurs **0 of 8
times**. The failing family is highly coherent: every ground-truth table
with <= 2 rows scored exactly 0.0 (7/7), `exam_paper` 6/6 — short, wide
banner tables (answer keys, score boxes) at 1.5-5.2% of page area.

This **strengthens** the composition thesis rather than weakening it: the
apparent ceiling was an artifact plus an implementation asymmetry
(`_apply_native_table_fallback` could only replace a primary table, never
add a missing one), not a shared model limit.

**Answers the "third candidate" question posed above: no.** A third
structure specialist would address 0 of 8 cases. The open direction is
small-region *detection* recall.

### The fix, implemented and validated

`_apply_native_table_fallback` now *adds* an extra-source candidate that
matched no primary table (previously it only ever compared/replaced
candidates that did match), guarded to require at least one non-empty
cell. `merge_regions_into_page` falls back to region OCR text for a table
region matching no detected `Table`, instead of emitting neither table nor
text — a second, independent content-loss path found in the same trace.

100-page result (evaluated with `OMNIDOCBENCH_TEDS_TIMEOUT_SEC=1800`, and
re-confirmed on an idle machine after an initial run showed unrelated
timeout contamination — see `observations.md` section 22):

| Metric | before | after | delta |
| --- | ---: | ---: | ---: |
| table TEDS.all | 0.4080 | **0.4514** | **+0.0434** |
| table TEDS_structure_only.all | 0.5084 | **0.5734** | **+0.0650** |
| table Edit_dist | 0.7177 | **0.6792** | **-0.0384** (improvement) |
| text_block / reading_order / display_formula | — | — | <= 0.0008 (noise) |

**Exactly the 3 hypothesized tables moved** (0.0000 -> 0.6429, 0.4464,
0.2114) and **all other 27 tables are bit-identical** — the cleanest,
most fully-predicted result this investigation produced. Both-fail:
8/30 (27%) -> 5/30 (17%), the remaining 5 being exactly the tables this
fix does not target. `pytest -q`: 185 passed, 3 of the 7 new tests
confirmed to fail against pre-fix code.

## Next experiment

**Superseded by the hard-table diagnosis above — the recommendation below
is stale and kept only for the record; see the addendum for the current
one.** ~~Given the evidence, the highest-value next step is not a more
sophisticated selector (not justified by available data) and not
selective escalation (evidence says the available signals don't support
it). It is closing the "both models fail together" component identified
above and in observations.md sections 3 and 14 — a detection/structure
capability question. That is a different, larger investigation (candidate
directions: a third structure model/backend as a genuine third candidate
source now that the composition layer is N-way-capable; or targeted
table-detection-recall work) and is out of scope for this proposal.~~

The diagnosis showed "both models fail together" was half measurement
artifact and half a fixable implementation asymmetry, not a structure
capability gap — and that fix is now implemented and validated above. The
current next step, given the remaining 5/30 (17%) both-fail tables are all
small (<=2 GT rows, 1.5-5.2% of page area) and *undetected* by either
backend's table-region localization: **table detection recall on small,
borderless regions specifically** — not a new structure model (the
structure step is never reached), and not a document VLM without first
checking whether a cheaper detection-side fix (e.g. a lower confidence
threshold or a size-aware detection pass for regions this small) closes
some of the remaining 5 before reaching for a heavier component.
