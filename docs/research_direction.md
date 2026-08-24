# Research direction: specialist composition, not specialist replacement

This is a narrative around one measured result, not a roadmap of
hypotheses — see [research-roadmap.md](research-roadmap.md) for those.
Full evidence trail: [experiments/005_omnidocbench/observations.md](../experiments/005_omnidocbench/observations.md)
("Bottleneck Analysis"), numbers in
[experiments/005_omnidocbench/results/comparison.md](../experiments/005_omnidocbench/results/comparison.md).

## The question this answers

After fixing a real architectural bug (table cells were 100% empty because
Docling's own per-cell text was being discarded — see the observations log,
"table cell text association"), the aggregate benchmark gain was modest
(+0.013 TEDS on OmniDocBench). The natural next question — asked directly,
not assumed — was whether that meant the canonical IR itself was coupling
text/table/reading-order concerns in a way that caps any single fix's
payoff.

It doesn't. Traced completely: `Element.text` and `Table.cells[i].text`
are separate fields linked by reference, not merged; `compute_reading_order`
reads only geometry and never inspects text; the apparent metric coupling
(fixing table text also moved the reading-order score) turned out to be a
property of *how OmniDocBench scores matched elements*, not of our
representation — the evaluator only scores reading-order for GT/prediction
pairs that already matched on text similarity, so a table that couldn't
match before (empty cells) simply wasn't part of the ordering sequence
being scored at all.

So the IR was not the bottleneck. The next question became concrete: given
a clean, decoupled representation, where does headroom actually live?

## What the evidence says

Seven real ground-truth tables, individually inspected with targeted
counterfactuals (not aggregate statistics alone):

- Two tables: neither of two independent table-detection mechanisms found
  a region at all. One remained undetectable even given the correct crop
  directly (a structure-model capability limit on an atypical table shape).
- Three tables: `TableTransformerBackend`'s structure model detected the
  wrong row/column grid. On one of these, **Docling's own independent
  TableFormer model, run on the identical page, found the exact correct
  structure with every cell populated correctly** — direct, page-level
  proof that a second existing model already contains the missing
  capability for at least some of these failures. On another of the three,
  Docling's own model did *worse* — proof the two specialists fail on
  *different* inputs, not that one is strictly better.
- Two tables: structure was essentially correct; the remaining loss was
  Docling's own OCR producing no text for that specific region — a
  capability gap in the underlying OCR engine, not in how this project
  wires components together.

## The principle, stated generally

**Two independently-trained models that solve the same sub-problem
(table structure recognition) disagree on which inputs they handle well,
in a way that is cheap to detect after the fact and does not require
predicting failure in advance.** A single, per-table, deterministic signal
— cell fill-rate, "did this extraction actually produce content" — picks
the better of the two on every case where they disagreed in this sample,
without any model retraining, fine-tuning, or new dependency.

Implemented as `select_better_populated_table()` in
`src/doc_extraction/pipelines/base.py`: given two candidate `Table` objects
for the same region, keep whichever has more non-empty cells, preserving
the original candidate's identity so nothing downstream needs to know a
swap happened. `DoclingBackend.native_tables()` exposes the second
candidate from the *same cached model conversion* `recognize()` already
triggers — no extra inference cost when Docling is already the configured
OCR backend, which it is by default.

Measured effect on the same 20-page subset used throughout this
investigation: `table TEDS.all` **+0.073** (~28% relative), `TEDS_structure_only`
+0.016, with `text_block`, `reading_order`, and `display_formula` unchanged
to the fourth decimal place — the change is table-local, as designed. One
table's score dropped as a direct, named, pre-identified side effect: an
all-empty prediction had been *accidentally* scoring well against a
naturally sparse ground truth (a checkbox-matrix table), and replacing
empty cells with a real-but-wrong attempt removed that lucky match. That
trade-off is reported, not hidden, in `observations.md`.

## Why this is a direction, not just a fix

The mechanism generalizes past tables. Nothing about
`select_better_populated_table`'s logic is table-specific beyond its
"count non-empty cells" quality signal — the same shape of composition
(two independently-produced candidates for the same region, a cheap
deterministic quality proxy, pick the better one, preserve identity for
downstream linking) applies anywhere this project already runs more than
one component capable of producing the same kind of output: layout
regions, OCR text spans, or a future second OCR/layout backend. The
specific instance implemented here is deliberately the smallest one with
direct evidence behind it — not a general "ensemble everything" rewrite.

## What this does not claim

- It does not claim Table Transformer should be replaced or fine-tuned.
  One of the seven tables shows *both* independent structure models
  failing together — a single better model is not guaranteed to exist by
  this evidence, whereas composition already captures real, measured gain
  today.
- It does not claim the table-detection gap (two tables with no region
  found by either mechanism) is solved. That remains open — see
  `observations.md` for the specific pages and why the oracle-region
  ablation shows it is at least partly a genuine model-capability
  question, not an orchestration bug.
- It does not claim n=7 tables generalizes without the larger-subset
  validation `observations.md` records the result of.

## Opus audit addendum

Independently re-verified (new owner, fresh eyes, not a rubber stamp — see
`experiments/005_omnidocbench/observations.md`, "Opus audit and oracle
analysis"). Every number above checked directly against `metrics.json`
files, not the markdown reports; all matched. The mechanism and the
measured effect are real.

What the audit added is a quantified answer to the question this document
did not ask: **how much of the theoretically available gain does the
fill-rate heuristic actually capture?** Built an oracle (the candidate
with the higher ground-truth TEDS, per table — not a production method,
an upper-bound measurement) from the same real tables, using a coherent
single-process reconstruction (comparing Table Transformer and Docling
candidates generated in *separate* processes turned out to be unreliable —
Table Transformer's structure output is not perfectly reproducible run to
run on CPU, a previously-undocumented finding in its own right).

Result: the fill-rate selector matches the oracle on 5 of 7 real tables
(71%); mean oracle TEDS 0.4476 vs. the selector's actual 0.3325 — a real
headroom of ~0.115. Both misses trace to the *same* mechanism, not two
independent bugs: OmniDocBench's TEDS scores an all-empty table generously
against a naturally sparse ground truth, and cell fill-rate cannot tell
"correctly recognized nothing is here" apart from "failed to recognize
something that is here." Checked directly whether any fill-rate threshold
closes this without breaking a currently-correct decision elsewhere — none
does, on this data (see observations.md section 13 for the specific
counter-example). Also checked, per the task's explicit "measure before
implementing" requirement, whether either model's own fill-rate could
gate a compute-saving selective-escalation policy (run the expensive model
only when the cheap one looks uncertain) — it cannot: Docling's own
fill-rate is a binary "found something" signal with no graded confidence
information, and Table Transformer's fill-rate is graded but not
predictive in the useful direction (see observations.md section 15).

Refactored the composition layer to be genuinely model-agnostic
(`TableCandidate` / `compute_table_quality_features` /
`select_best_table_candidate` in `pipelines/base.py`) — the previous
`select_better_populated_table` was a fixed two-argument function; the new
primitive takes any number of candidates and does not know or care which
backend produced any of them, satisfying the "does this conceptually
support a third/fourth specialist" requirement without touching selection
logic. `select_better_populated_table` and `_apply_native_table_fallback`
are now thin, behavior-preserving wrappers over it (all 10 pre-existing
tests pass unchanged; 9 new tests cover the general primitive directly).

**Superseded in part — see the "Hard-table capability analysis" addendum
at the end of this document.** A later session found that the 100-page
both-fail statistic quoted below was contaminated by evaluator timeouts,
and that half the remaining both-fail region was this pipeline discarding
candidates it had already produced, not a model capability gap.

**Revised verdict:** this is a validated, real engineering improvement
with a well-understood, appropriately-bounded ceiling — not (yet) a
generalizable "confidence-aware ranking" research result. The available
cheap signals (each candidate's own fill-rate) explain most, not all, of
the achievable gain, and the specific gap that remains is disproportionately
a benchmark-scoring-function artifact rather than a genuinely closable
extraction-quality gap. A more sophisticated multi-signal or learned
ranker is not justified by the amount of data available (n=7, and the
larger-subset check below) and is not pursued on this evidence. See
`docs/research_proposal.md` for the full writeup, and the "100-page
validation" addition in `observations.md` for whether this ceiling holds
at scale.

## Hard-table capability analysis addendum

Full evidence: `experiments/005_omnidocbench/hard_tables/failure_taxonomy.md`
and `observations.md` sections 18-23.

Asking *why* both specialists fail on the same tables produced two
findings that revise the picture above.

**1. A measurement artifact, not a capability statistic.** The upstream
evaluator scores a TEDS comparison exceeding a 120-second wall-clock
timeout as `0.0` — indistinguishable from genuine failure. Re-evaluating
byte-identical 100-page predictions on an unloaded machine changed
`table TEDS.all` from 0.2743 to **0.4080** and the both-fail count from
14/30 to **8/30**, with every non-TEDS metric bit-identical. The claim
that both-fail was worse at scale (47%) than in the small sample (29%) is
**withdrawn**: the corrected 27% matches the small sample. Table metrics
on this benchmark are only valid when the evaluator log contains no
`[TEDS-timeout]` lines.

**2. Half the real both-fail region was never a model failure.** Of the 8
genuine cases, 3 are the composition layer discarding a candidate it
already had (Docling's TableFormer produced the correct structure — on one
page a 2x12 answer-key table with all 18 cells populated and a bbox within
~2px of ground truth — while Table Transformer produced nothing for the
same crop, and the reconciliation loop only ever *replaced* primary tables,
never *added* a missing one), and 1 is a table produced but never
referenced by any element. Only 4/8 are a genuine shared gap, and that gap
is at **detection**, not structure: the failing family is small, wide,
1-2 row banner tables (every table with <= 2 GT rows scored exactly 0.0,
7/7; `exam_paper` 6/6) that neither backend detects as a table at all.

Notably, **"both models detect the table and both produce similar wrong
structure" occurs 0 times out of 8.** Where both engage, one succeeds. So
the composition thesis is *more* right than the earlier writeup credited —
the ceiling it appeared to hit was substantially an artifact plus an
implementation asymmetry, not a shared capability limit.

This also settles the "is a third candidate model justified" question for
now: **no.** A third structure specialist would address 0 of the 8 cases.
The open direction is small-region *detection* recall.

**Revised by the next phase** (`docs/residual_failure_corpus.md`,
`observations.md` §24–26): after the deeper per-table diagnosis, the
picture is 3/5 pipeline-fixable (label filter, orphan-attach, crop
upscale — no new model needed) and 2/5 genuinely undetermined without a
third model's actual output on those exact tables (both existing
structure models fail on the same 2×2 borderless grid at every scale
tested). **A pipeline-integrity audit also found and fixed a real,
previously-undocumented gap**: the TEDS-timeout mitigation this whole
investigation depended on was never durable — an env var nobody's tooling
set — and silently contaminated results twice before being caught. Now
written directly into the evaluator config with a post-run check;
see `docs/pipeline_integrity.md`.

**Current verdict: no confirmed research gap.** The recommended next
experiment is integrating one real SOTA system (MinerU2.5 or
PaddleOCR-VL — both open-weight, on-device, no external API) as a third
candidate source into the already-model-agnostic composition layer, which
would resolve the 2 unresolved cases with real evidence rather than
inference from aggregate benchmark numbers.
