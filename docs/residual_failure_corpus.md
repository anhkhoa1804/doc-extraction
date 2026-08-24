# Residual failure corpus — current pipeline vs. SOTA evidence

> **SUPERSEDED IN PART — read `docs/sota_comparison.md` first.**
> This document's central limitation (no SOTA system had been run on these
> exact images) has since been removed: MinerU2.5 was installed and run
> locally on all five cases. It achieves `TEDS_structure_only = 1.0000` on
> **all five**, including both cases this document classified
> `[F] unresolved`. Those two are now **`[B] missing integration`**, and
> **zero cases remain in `[F]` or `[E]`**. The verdict below ("no confirmed
> research gap") is unchanged and now rests on direct measurement rather
> than inference. Everything else here — the per-case mechanisms, the
> category A–F analysis, the classification method — still stands.

Population: the 5 tables still scoring 0.0 TEDS after the candidate-recovery
fix (commit `982cc2f`), individually traced (commit `9a9843c`,
`docs/research_gap_analysis.md`). This document adds the SOTA side of the
comparison and reaches a verdict on whether a genuine research gap exists.

**Methodology limitation as originally written (now resolved — kept for
the record):** at the time this document was first written, no independent
inference had been run on these exact images through a SOTA system. A
public MinerU demo was located (huggingface.co/spaces/opendatalab/MinerU →
a Gradio app on ModelScope) and reached, but the in-app Browser tool has no
file-upload primitive; a base64-relay workaround was attempted and
abandoned after the first 90KB chunk alone cost ~85,000 tokens of
transcript. The SOTA side below was therefore **convergent evidence from
primary sources** rather than direct measurement, and every claim was
labeled accordingly.

**That limitation no longer applies.** MinerU2.5 was subsequently
installed locally (isolated `.venv-mineru`, `mineru-vl-utils[transformers]`
on CPU) and run directly on all five images — see
`docs/sota_comparison.md`. The inference-based SOTA reasoning below is
therefore superseded by measurement wherever the two touch the same
question; where it isn't contradicted, it stood up.

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
| 4 | `..._en_2901` [0] | structure (2×2 borderless) | TT detects at 0.996 on crop; **structure returns `None` at 1×, 2×, and 3×**. Docling TableFormer also returns nothing on the same crop. | No direct evidence either way. Official `special_issue: ['colorful_backgroud']` tag (our own GT) — a different axis (visual complexity) than the geometric one (borderless, 2×2) that appears to be the actual blocker. **RESOLVED: MinerU2.5 → structure-only TEDS 1.0000** (`docs/sota_comparison.md`). | ~~[F] unresolved~~ → **[B] missing integration** |
| 5 | `..._en_2901` [1] | structure (2×2 borderless, partial) | TT: `2×1` vs GT `2×2` at every scale. Same page as #4. | **RESOLVED: MinerU2.5 → structure-only TEDS 1.0000, content TEDS 0.9881.** | ~~[F] unresolved~~ → **[B] missing integration** |

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
| [B] missing integration | ~~2~~ **4** | `jiaocaineedrop_46`, `page-28657a85`, **+ both `..._en_2901` tables** |
| [C] known SOTA limitation | 0 | — |
| [D] model capability limitation | 0 | not distinguished from [F] below without a real second/third structure model's output on these exact cases |
| [E] possible research gap | **0** | see verdict |
| [F] unresolved | ~~2~~ **0** | ~~`..._en_2901` ×2~~ — both resolved by MinerU2.5, see `docs/sota_comparison.md` |

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

**Now measured, not inferred** (`docs/sota_comparison.md`):

| Case | Docling | Table Transformer | **MinerU2.5 (measured)** |
|---|---|---|---|
| 1, 3 | fails at page scale, nothing on crop | fails at page scale; **succeeds on crop** | **succeeds — structure-only 1.0000 on both, full page, no GT crop** |
| 2 | nothing on crop | **succeeds at page scale (0.9991)** | **succeeds — structure-only 1.0000** |
| 4, 5 | **fails on crop** | **fails on crop, all scales** | **succeeds — structure-only 1.0000 on both** |

The "ALL MODELS WRONG" category the task calls out as most interesting
(§7) turned out to be **empty**: the third column is now filled in, and
there is no case where all three model families fail. Cases 4–5, the only
candidates for it, are solved outright by MinerU2.5.

## Verdict

**No confirmed research gap** — and, unlike when this document was first
written, that verdict now rests on direct measurement for every case.
Restating the task's own permitted valid outcome: *"there is no clear
research gap yet; the remaining problems are mostly model integration /
known SOTA limitations."*

- 3/5 cases (`jiaocaineedrop_46`, `page-d29fe4d2`, `page-28657a85`) are
  **[A] pipeline bug / [B] missing integration** — recoverable with models
  already loaded, no new capability needed, matches `docs/
  research_gap_analysis.md`'s prior finding exactly.
- 2/5 cases (`..._en_2901` both tables) were **[F] unresolved**; they are
  now **[B] missing integration**. Both existing structure models fail on
  that 2×2 borderless grid at every scale, but **MinerU2.5 returns the
  exactly-correct structure on both** (structure-only TEDS 1.0000). A
  third model family succeeding is precisely the evidence that rules out
  a shared capability gap.
- **Zero cases remain in `[E]` or `[F]`.**

## Recommended experiment — DONE, and what it showed

This section recommended integrating one real SOTA system as a genuine
third candidate source. **That has now been done** (`docs/sota_comparison.md`):
MinerU2.5 runs locally via a thin `MinerUVLTableBackend` exposing the same
`native_tables(page)` hook the existing N-way composition already consumes,
with no change to the composition algorithm or canonical IR.

Outcome against the three things this section wanted from it:

1. **The missing SOTA column is filled.** Cases 4–5 are `[D]-then-[B]`:
   both existing models incapable, third model succeeds — an integration
   win, not a shared limit. There is no `[E]` evidence.
2. **Adapter-loss data exists now.** MinerU emits `<table>` HTML with
   `colspan`/`rowspan`; `parse_html_table()` converts it into the canonical
   `Table` via an occupancy grid. Verified round-trip on real output: the
   2×7 and 1×3 tables parse to exactly their GT shapes with every cell
   populated. **No adapter loss observed on these cases** — so the residual
   content gap (TEDS 0.76–0.99) is the model's, not the adapter's.
3. **Measurable on the existing protocol** — though at a real cost: ~180–220 s
   per page CPU-only, ~2.6–3× the current pipeline. The composition A/B is
   therefore scoped as the next step, not run here.

Production-compatible per the task's constraint: MinerU2.5 is open-weight
and runs on-device with no external SaaS API. **One caveat found in the
audit and not present for the other backends: the weights are AGPL-3.0**
(the code is Apache-2.0-based), which needs licensing review before
redistribution or hosted deployment.

## What NOT to pursue

- **Do not build a novel cross-region-reasoning or evidence-fusion
  architecture** (task §6/§10 candidates) — zero cases in this corpus
  demonstrate a need for cross-region reasoning, global document context,
  or semantic understanding. Building one would address a phenomenon this
  corpus does not contain.
- **Do not conclude the 2×2-borderless cases are a confirmed model
  limitation of the *field***, only of the two specific models tested.
  *(Settled: MinerU2.5 extracts both perfectly — it was never a limitation
  of the field, exactly as this warning cautioned.)*
- **Do not treat the aggregate SOTA numbers (~90+ TEDS) as proof our
  specific 5 cases are solved elsewhere.** They are strong, converging,
  but indirect evidence — stated as such throughout this document, not
  rounded up to a stronger claim than the evidence supports.
