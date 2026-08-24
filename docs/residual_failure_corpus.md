# Residual failure corpus — current pipeline vs. SOTA evidence

Population: the 5 tables still scoring 0.0 TEDS after the candidate-recovery
fix (commit `982cc2f`), individually traced (commit `9a9843c`,
`docs/research_gap_analysis.md`). This document adds the SOTA side of the
comparison and reaches a verdict on whether a genuine research gap exists.

**Methodology limitation, stated up front, not discovered partway through:**
no independent inference was run on these exact images through a SOTA
system this session. A public MinerU demo was located
(huggingface.co/spaces/opendatalab/MinerU → a Gradio app on ModelScope) and
reached, but the in-app Browser tool has no file-upload primitive; a
workaround (relay the image as base64 through repeated `javascript_tool`
calls) was attempted and abandoned after the first 90KB chunk alone cost
~85,000 tokens of transcript — prohibitively expensive for what would be
corroborating, not load-bearing, evidence. The SOTA side below is therefore
**convergent evidence from primary sources** (architecture papers, official
benchmark numbers, this project's own ground-truth attribute tags) — not
directly measured per-case results. Every claim below is labeled with
which kind of evidence it is. Actually running a SOTA system as a genuine
third candidate source is the concrete next experiment this document
recommends, not something already done here.

## Common representation and adapter-loss note

Our own pipeline's outputs are already in the canonical IR
(`document → page → elements/tables → cells`) — no adapter loss to record
on our side; every number below comes directly from that representation's
own markdown serialization and the official evaluator. No SOTA output was
produced this session to normalize, so there is nothing to classify as
PIPELINE/ADAPTER LOSS yet — that classification applies once a real SOTA
run exists (see "Recommended experiment").

## The 5 cases

| # | Table | Category (task §3) | Pipeline-side evidence | SOTA-side evidence | Classification (§8) |
|---|---|---|---|---|---|
| 1 | `jiaocaineedrop_46` | table detection (label misclassification) | Layout localizes the region (IoU 0.753, 98.3% GT coverage) but labels it `picture`; our `label == "table"` filter then discards it. TT-on-crop: 0.9434, exact `2×7`. | Official OmniDocBench `special_issue: ['table_full_line', 'table_horizontal']` tag on this exact page (verified in our own GT — not third-party). Architecturally: MinerU2.5/PaddleOCR-VL both run layout on the *whole page* first, same as Docling, so the same TABLE-vs-PICTURE ambiguity is architecturally *possible* in them too — not ruled out by anything found. | **[B] missing integration** (crop-and-verify pass) |
| 2 | `page-d29fe4d2` | table detection (orphan attach) | TT already detects at **0.9991 on the unmodified full page** (default 0.7 threshold). Lost purely because layout emits no `table`-labelled region to attach it to. | Official `subset: table_hard` tag (verified in our own GT). No SOTA-specific evidence needed — this is a pure orchestration loss with no detection difficulty at all. | **[A] pipeline bug** |
| 3 | `page-28657a85` | table detection + structure (resolution) | 1× crop → wrong `1×2`; 2× crop → exact `1×3` (= GT). Official `subset: table_hard` tag (our own GT). | MinerU2.5's Stage II explicitly crops to native resolution before structure recognition (primary source, arXiv 2509.22186: *"crop the native high-resolution image into local regions, which are then parsed at fine granularity"*) — the same mechanism our own ablation showed decisive here. | **[B] missing integration** (crop upscale) |
| 4 | `..._en_2901` [0] | structure (2×2 borderless) | TT detects at 0.996 on crop; **structure returns `None` at 1×, 2×, and 3×**. Docling TableFormer also returns nothing on the same crop. | No direct evidence either way. Official `special_issue: ['colorful_backgroud']` tag (our own GT) — a different axis (visual complexity) than the geometric one (borderless, 2×2) that appears to be the actual blocker. | **[F] unresolved** |
| 5 | `..._en_2901` [1] | structure (2×2 borderless, partial) | TT: `2×1` vs GT `2×2` at every scale. Same page as #4. | Same as #4. | **[F] unresolved** |

## SOTA aggregate evidence (primary sources, cited exactly)

| Claim | Source | Value |
|---|---|---|
| MinerU2.5-Pro, OmniDocBench v1.6 overall | [arXiv 2604.04771](https://arxiv.org/html/2604.04771v1) | Table TEDS **93.42**, TEDS-S **95.92** |
| MinerU2.5-Pro, OmniDocBench v1.6 **official Hard subset** (samples independently selected as difficult: complex nested tables, dense formulas, unconventional layouts — table size/borderlessness not cited as a defining criterion, checked directly against the paper's own text) | same, §10.2 | Table TEDS **92.46**, TEDS-S **94.67** |
| PaddleOCR-VL, OmniDocBench v1.6 Hard subset | same | TEDS 88.28, TEDS-S 91.80 |
| PaddleOCR-VL, OmniDocBench v1.5 end-to-end | [arXiv 2510.14528](https://arxiv.org/html/2510.14528v1) | Table-TEDS **89.76**, TEDS-S 93.52 |
| MinerU2.5 architecture is decoupled coarse-to-fine (Stage I: 1036×1036 thumbnail layout; Stage II: native-resolution crops) | [arXiv 2509.22186](https://arxiv.org/html/2509.22186v1), quoted directly | — |
| OmniDocBench project's own comparative claim that MinerU's table parsing addresses "rotated tables, borderless/semi-structured tables, and long/complex tables" | WebSearch synthesis of OmniDocBench-related sources — **not independently re-fetched from a single primary document this session; treated as suggestive, not decisive, for that reason** | — |
| Docling layout TABLE/PICTURE ambiguity on sparse borderless tables | [docling-project/docling issue #3495](https://github.com/docling-project/docling/issues/3495) (open, maintainer-labelled `layout`) | — |

Our own pipeline, same benchmark, same 100-page subset (timeout-corrected):
**Table TEDS 45.14.**

**What this aggregate evidence does and does not prove.** It proves SOTA
systems are far more capable at table extraction in general, on this exact
benchmark, including on a subset independently curated to be hard for
*other* reasons (nested tables, dense formulas). It does **not** prove
they succeed on our specific geometric family (1–2 row, <5%-page-area,
borderless banner tables) — that family isn't how "Hard" was defined, and
no published attribute-level breakdown for OmniDocBench's own
`table_full_line`/`table_horizontal`/`table_hard` tags specifically was
found (searched; the evaluator's own `group` breakdown is also empty for
the `table` metric category — checked directly against our own
`metrics.json`, this is an upstream evaluator limitation, not something
this project can fix).

## Shared failure mechanism (task §5, categories A–F)

Applying the six candidate categories to what's actually missing:

- **A (geometry insufficient)** — not supported. `page-28657a85`'s
  correct structure IS recoverable from geometry alone, at 2× scale.
- **B (semantics required)** — not supported by any evidence gathered.
  Nothing in the 5 cases needed header/relationship understanding beyond
  what a structure model already attempts.
- **C (global document context required)** — not supported. Each case
  was resolved (or not) from the local crop alone; none needed
  surrounding-page context.
- **D (cross-region reasoning required)** — not supported. No case
  involved a relationship between two separate regions.
- **E (fine-grained text/layout interaction)** — **the closest fit**, but
  only for cases 4–5: two independent structure models return no usable
  grid on the same tiny borderless table at every scale tested. Whether
  this is "independent models cannot solve it" (category E) or "the two
  *specific* structure models we have cannot solve it, and a third one
  would" is exactly what's undetermined (see verdict).
- **F (evaluation/serialization artifact)** — **confirmed present, but
  already fixed**, not a residual case: the 120s TEDS timeout (`docs/
  pipeline_integrity.md`) was exactly this category, for a different set
  of tables, and is now closed at the tooling level.

**Measured, not assumed: no category dominates the 5-case corpus.** 3/5
are B-class orchestration/preprocessing gaps (categories A–D all ruled
out for them); 2/5 are genuinely unclassified pending more evidence.

## Classification tally (task §8)

| Class | Count | Cases |
|---|---:|---|
| [A] pipeline bug | 1 | `page-d29fe4d2` |
| [B] missing integration | 2 | `jiaocaineedrop_46`, `page-28657a85` |
| [C] known SOTA limitation | 0 | — |
| [D] model capability limitation | 0 | not distinguished from [F] below without a real second/third structure model's output on these exact cases |
| [E] possible research gap | **0** | see verdict |
| [F] unresolved | 2 | `..._en_2901` ×2 |

**Per the task's own rule ("only category [E] can support a research
direction... require at least multiple independent examples"): zero cases
qualify for [E].** The 2 unresolved cases are a single page, both
instances of the identical geometric pattern (2×2 borderless grid) — not
"multiple independent examples" of a generalizable phenomenon, and not yet
confirmed to defeat a third, differently-built model.

## Cross-model oracle (task §7), honestly scoped

The task asks to extend the prior Docling-vs-Table-Transformer oracle to
include a SOTA system and classify each case as "one model correct /
multiple partially correct / all models wrong." That requires the SOTA
system's actual output on these cases, which — per the limitation stated
at the top — was not obtained this session. What **is** available:

| Case | Docling | Table Transformer | SOTA (evidenced, not measured) |
|---|---|---|---|
| 1, 3 | fails at page scale, untested on crop | fails at page scale; **succeeds on crop** | architecturally does the same crop step by default (MinerU2.5 Stage II) — plausibly succeeds, not confirmed |
| 2 | untested (no crop-refine needed; TT already succeeds at page scale) | **succeeds at page scale (0.9991)** | not needed — this case has nothing to do with model capability |
| 4, 5 | **fails on crop** | **fails on crop, all scales** | **genuinely unknown** — the one place a real oracle entry is missing |

The "ALL MODELS WRONG" category the task calls out as most interesting
(§7) is real for cases 4–5, but only two of three columns are filled in.
That is precisely the gap the next experiment should close.

## Verdict

**No confirmed research gap.** Restating the task's own permitted valid
outcome: *"there is no clear research gap yet; the remaining problems are
mostly model integration / known SOTA limitations."* That is this
document's answer, for 3 of 5 cases decisively and for the other 2
because the evidence needed to call them anything else does not exist yet.

- 3/5 cases (`jiaocaineedrop_46`, `page-d29fe4d2`, `page-28657a85`) are
  **[A] pipeline bug / [B] missing integration** — recoverable with models
  already loaded, no new capability needed, matches `docs/
  research_gap_analysis.md`'s prior finding exactly.
- 2/5 cases (`..._en_2901` both tables) are **[F] unresolved** — not [E].
  Both existing structure models fail on the same narrow geometric
  pattern (2×2 borderless grid), which is a real, specific, but
  single-page, non-generalized finding. Calling this a research gap would
  violate the task's own "require multiple independent examples" bar.

## Recommended experiment

Not a novel method. The evidence gap above has one honest fix: **integrate
one real SOTA system (MinerU2.5 or PaddleOCR-VL) as a genuine third
candidate source**, exactly as `docs/research_gap_analysis.md` §7 already
ranked as item 3, and let the existing N-way composition layer
(`select_best_table_candidate`, already model-agnostic per commit
`df1f0a1`) consume it. This simultaneously:

1. Fills the oracle table's missing SOTA column for cases 4–5 with real
   data, resolving whether they are [D] (both existing models incapable,
   third model succeeds — an integration win) or a genuine shared limit
   across three independent architectures (the closest this project could
   get to actual [E] evidence).
2. Provides real per-case adapter-loss data (task §3) once there's an
   actual SOTA output to normalize into the canonical IR.
3. Is directly measurable on the existing 20-/100-page protocol, with no
   new architecture and no training.

Production-compatible per the task's constraint: both MinerU2.5 and
PaddleOCR-VL are open-weight, run on-device (CPU or GPU), and require no
external SaaS API — the same deployment shape as the existing Docling/
Table Transformer backends.

## What NOT to pursue

- **Do not build a novel cross-region-reasoning or evidence-fusion
  architecture** (task §6/§10 candidates) — zero cases in this corpus
  demonstrate a need for cross-region reasoning, global document context,
  or semantic understanding. Building one would address a phenomenon this
  corpus does not contain.
- **Do not conclude the 2×2-borderless cases are a confirmed model
  limitation of the *field***, only of the two specific models tested.
  That distinction is exactly what's unresolved.
- **Do not treat the aggregate SOTA numbers (~90+ TEDS) as proof our
  specific 5 cases are solved elsewhere.** They are strong, converging,
  but indirect evidence — stated as such throughout this document, not
  rounded up to a stronger claim than the evidence supports.
