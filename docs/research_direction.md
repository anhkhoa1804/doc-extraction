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
