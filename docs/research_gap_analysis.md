# Small-table detection: bug, limitation, SOTA capability, or research gap?

Written to answer one question before spending more compute: the remaining
hard-table failures are concentrated in small, wide, often borderless
1–2 row tables — **is that our bug, our implementation limitation, a known
limitation of the specific models we chose, something existing SOTA already
solves, or a genuine research gap?**

Entry state: commit `982cc2f`. 100-page subset, timeout-free measurement,
`table TEDS.all` 0.4514, both-fail 5/30 (17%) after the candidate-recovery
fix. Evidence trail:
[`experiments/005_omnidocbench/hard_tables/failure_taxonomy.md`](../experiments/005_omnidocbench/hard_tables/failure_taxonomy.md),
[`observations.md`](../experiments/005_omnidocbench/observations.md)
sections 18–23.

**Answer up front: this is NOT a research gap — for 3 of the 5 remaining
cases decisively, and "not established" for the other 2.** It is a
combination of (a) two real defects in our own pipeline, (b) a
documented-upstream classification ambiguity plus a genuine structure
limit in the models we chose, and (c) a capability whose established
solution — coarse-to-fine crop-and-refine — is already the published SOTA
architecture, benchmarked roughly twice our score. The correct action is
**fix + integrate**, not research.

All five hard tables were diagnosed individually (§1a), not extrapolated
from one. Raw probe data:
`experiments/005_omnidocbench/hard_tables/detection_diagnostics.json`.

---

## 1. Observed failure

Five tables in the 100-page subset still score exactly 0.0 TEDS:

| Table | GT shape | GT size | % of page | Class from taxonomy |
|---|---|---|---:|---|
| `jiaocaineedrop_46.pdf_1` | 2×7 | 553×150 px | 2.15% | shared detection failure |
| `..._en_2901` [0] | 2×2 | — | 2.31% | shared detection failure |
| `..._en_2901` [1] | 2×2 | — | 1.46% | shared detection failure |
| `page-28657a85` | 1×3 | — | 4.19% | shared detection failure |
| `page-d29fe4d2` | 4×4 | — | 63.42% | orphaned table |

Across all 30 tables, **every table with ≤2 GT rows scored 0.0 (7/7)**
before the recovery fix; the 4 remaining ≤2-row cases are the ones above.

## 1a. Failure matrix — all 5 hard tables, individually diagnosed

Each table probed by replaying the production path, then four controlled
probes: layout-region overlap against the GT bbox, TT full-page detection
at 0.7 and 0.05, TT on a GT-bbox crop at 1×/2×/3×, and Docling TableFormer
on the 2× crop.

| Table | GT | Layout sees region? | TT full-page | TT on crop (1× / 2× / 3×) | Docling on 2× crop | Cause |
|---|---|---|---|---|---|---|
| `jiaocaineedrop_46.pdf_1` | 2×7, 2.15% | **yes — but labelled `picture`**, IoU 0.753, **98.3% of GT covered** | 0.0675 @0.05, nothing @0.7 | **0.943 → exact `2×7`** at 1×; 2×/3× no better | nothing | **PIPELINE BUG** (label filter) |
| `page-d29fe4d2` | 4×4, 63.4% | no — only fragmentary `text` (≤6.7%) | **0.9991, fires @0.7** | 0.9994 → `6×4` (GT 4×4) | nothing | **PIPELINE BUG** (orphaned: detected, never attached) |
| `page-28657a85` | 1×3, 4.19% | no — fragmentary `text` (≤22.9%) | 0.1527 @0.05 | 0.730 → `1×2`; **2× → `1×3` (= GT exactly)**; 3× → `1×3` | nothing | **PREPROCESSING / RESOLUTION** (upscale genuinely required) |
| `..._en_2901` [0] | 2×2, 2.31% | no — fragmentary `text` (≤2.5%) | 0.6234 @0.05 | 0.996 detect but **structure `None` at 1×, 2× AND 3×** | nothing | **MODEL LIMITATION** (structure) |
| `..._en_2901` [1] | 2×2, 1.46% | no — fragmentary `text` (≤12.6%) | 0.108 @0.05 | 0.968 → `2×1` (GT 2×2) at all scales | nothing | **MODEL LIMITATION** (partial) |

**Quantified split — these categories are deliberately not merged:**

```
pipeline-induced (fixable by us, with models already loaded):  3 / 5  (60%)
    - 2 pipeline bugs (label filter; orphaned table)
    - 1 preprocessing/resolution (2x crop upscale recovers exact GT structure)
model-induced (structure model genuinely cannot parse the table):  2 / 5  (40%)
    - both are the same page's 2x2 borderless grammar boxes
```

Three findings that matter more than the split itself:

1. **Detection is recoverable on a crop in every single case** — TT crop
   confidence ranges 0.730–0.9994 across all 5, versus 0.0675–0.1527 at
   page scale (except `page-d29fe4d2`, which already fires at 0.9991 on
   the full page). Not one of these is an unsolvable detection problem.
2. **Cropping matters more than pixels, but not always.** On
   `jiaocaineedrop_46` 1× already gives the exact structure and upscaling
   adds nothing. On `page-28657a85` upscaling is decisive: 1× yields a
   wrong `1×2`, 2× yields the exactly-correct `1×3`. So both mechanisms
   are real and neither alone explains the family.
3. **`page-d29fe4d2` needs no new capability at all** — TT already detects
   it at **0.9991 above the default 0.7 threshold** on the unmodified full
   page. It is lost purely because `merge_regions_into_page` attaches
   tables only to layout regions labelled `table`, and layout emitted none
   there. Pure orchestration loss.
4. **Docling's TableFormer found nothing on any of the five 2× crops** —
   so on this family the two backends are not interchangeable, and the
   composition layer cannot help here. TT-on-crop is the capability that
   works.

## 2. Pipeline contribution

**Two concrete pipeline causes were found, and neither is a model
limitation.**

### 2a. A hard label filter discards table regions the layout model found

`src/doc_extraction/pipelines/base.py:559`:

```python
table_regions = [r for r in layout_result.regions if r.label.lower() == "table"]
```

Only regions the layout model labels **exactly** `table` are ever passed
to the table backend. Any other label — `picture`, `text`, `form` — is
filtered out and never probed for table structure. `table_backend.extract`
then finds `table_boxes` empty and falls back to full-page detection at
`_DETECTION_THRESHOLD = 0.7`.

Measured consequence on `jiaocaineedrop_46.pdf_1`, the one page examined
in full detail (diagnostic replaying the exact production path):

| Probe | Result |
|---|---|
| Layout regions overlapping the GT table | **1 region, labelled `picture`, IoU 0.753, covering 98.3% of the GT table** |
| Table Transformer full-page detection @ 0.7 | nothing near GT |
| Table Transformer full-page detection @ 0.05 | 2 weak boxes near GT, **top score 0.0675** |
| **Table Transformer on a crop of that region, 1× (no upscale)** | **detection score 0.9434, structure recognition returns the exactly-correct `2×7` grid** |
| Same crop at 2× / 3× upscale | 0.9377 / 0.9390 — **no better than 1×** |
| Docling TableFormer on the 2× crop | found nothing |

The layout model **did localize the region** — it simply classified it as
a picture. So for this table the failure is **not detection recall and not
resolution**: it is (i) region *classification*, and (ii) our filter
turning that misclassification into total content loss.

### 2b. Resolution is not a lever on this benchmark route, and not the cause

`configs/*.yaml` set `render_dpi: 200`, but OmniDocBench pages take the
**image** route (`routes: {'image': 100}`), and
`pipelines/image.py` calls `render_image_passthrough` — the source image is
used at **native resolution** and `dpi` is metadata only. "Try 300/400
dpi" is therefore not an available ablation for this corpus; the only
resolution lever is upscaling a crop.

On `jiaocaineedrop_46`, upscaling is **not** what recovers the table: the
1× crop already scores 0.9434 and yields the exact structure, with 2× and
3× no better. What matters there is **cropping (removing page context),
not pixel count** — the classic DETR-style scale/context effect.

**But that does not generalize across the family, and the full matrix
(§1a) corrects the impression the single-page result gave.** On
`page-28657a85`, upscaling *is* decisive: the 1× crop produces a wrong
`1×2` grid while the 2× crop produces the exactly-correct `1×3`. So both
mechanisms are genuinely present:

- **crop / context** (`jiaocaineedrop_46`): 0.0675 → 0.9434 from cropping alone
- **crop + upscale** (`page-28657a85`): correct structure only at ≥2×

Resolution is therefore a real contributing factor for part of the family
— just not one reachable through `render_dpi` on this route, since the
source images are consumed at native resolution. It is reachable through
crop upscaling, which is exactly what the SOTA Stage-II designs in §4 do.

## 3. Model contribution

The layout model's TABLE-vs-PICTURE ambiguity on borderless tables on
sparse pages is a **real, upstream-acknowledged issue in the model we
chose** — not something we introduced, and not a fundamental incapacity.

Primary source: [docling-project/docling issue #3495](https://github.com/docling-project/docling/issues/3495)
(open, maintainer-labelled `layout`, addressed by PR #3701). It reports
that the RT-DETR layout model scores a borderless/raster-style table above
the 0.5 threshold for **both TABLE and PICTURE simultaneously**, and
states explicitly that **sparse pages are more susceptible — the same
table converts correctly when contextual content is added around it.**
The root cause identified there is unreachable dead code in
`_handle_cross_type_overlaps`, i.e. a postprocessing dedup failure on top
of genuine model uncertainty.

Our observation is the adjacent variant: on our page only the `picture`
cluster survived, so instead of a duplicate we got a silent drop. Same
underlying ambiguity, different postprocessing outcome.

An independent third-party empirical review reports the same
sparse-page/Picture-misclassification behaviour, and is explicit that it
is *"measured, not previously documented"* — so it corroborates our
measurement but is **not** citable as official documentation, and is not
treated as such here.

### 3a. But the structure model has a real limitation too

The single-page result suggested "the structure model is fine, only
classification fails." **The full matrix disproves that**, and it is the
one place where this family genuinely exceeds our models' capability:

| Table | TT detection on crop | TT structure on crop | Verdict |
|---|---|---|---|
| `jiaocaineedrop_46` | 0.943 | **exact `2×7`** | structure fine |
| `page-d29fe4d2` | 0.999 | `6×4` vs GT 4×4 | structure plausible, imperfect |
| `page-28657a85` | 0.730–0.806 | `1×2` at 1×, **exact `1×3` at ≥2×** | structure fine *given upscale* |
| `..._en_2901` [0] | **0.996** | **`None` at 1×, 2× and 3×** | **structure model fails outright** |
| `..._en_2901` [1] | 0.968 | `2×1` vs GT 2×2 | structure partially wrong at all scales |

On `..._en_2901` the detector is *confident* (0.996) and still the
structure model returns no row/column grid at any of three scales — and
Docling's TableFormer returns nothing on the same crop. Two independent
structure models both fail on a 2×2 borderless grammar box. That is a
genuine capability limit of the structure models we have, not an
orchestration artifact.

So the model contribution is twofold: **region classification** (Docling
layout, upstream issue #3495) *and* **structure recognition on very small
borderless grids** (both TT and TableFormer, 2/5 of the remaining cases).

## 4. SOTA landscape

The mechanism our own ablation just demonstrated — layout proposal, then
crop and re-run at fine granularity — **is the established SOTA
architecture**, already published and benchmarked. This is the decisive
finding against a novelty claim.

| System | Architecture relevant to this problem | OmniDocBench table evidence |
|---|---|---|
| **MinerU2.5** ([paper](https://arxiv.org/html/2509.22186v1)) | Explicitly *"a decoupled architecture that separates global layout analysis from local content recognition via an efficient coarse-to-fine, two-stage inference mechanism."* Stage I: page resized to a **1036×1036 thumbnail** for global layout. Stage II: *"crop the native high-resolution image into local regions, which are then parsed at fine granularity"* (native res, ≤2048×28×28 px). | MinerU2.5-Pro reports **Table TEDS 93.42 / TEDS-S 95.92** (v1.6), overall 95.69 |
| **PaddleOCR-VL** ([paper](https://arxiv.org/html/2510.14528v1)) | RT-DETR-based layout (PP-DocLayoutV3) + **NaViT-style dynamic/native-resolution** visual encoder, *"avoiding tiling and preserving detail essential for dense or variable input layouts."* | **Table-TEDS 89.76 / TEDS-S 93.52** (v1.5 end-to-end); Table-block TEDS 0.9195 |
| **Table Transformer (ours)** | Single-scale DETR detection + separate structure DETR; no crop-refine stage, no multi-scale | our pipeline: **Table TEDS 45.14** (100-page subset) |
| **Docling / TableFormer (ours)** | RT-DETR layout + TableFormer structure; known TABLE/PICTURE ambiguity on sparse borderless tables (issue #3495) | — |
| Coarse-to-fine as a named technique | A dedicated paper exists on *"Boosting Document Parsing Efficiency and Performance with Coarse-to-Fine Visual Processing"* ([arXiv 2603.24326](https://arxiv.org/pdf/2603.24326)) | — |

On our specific failure family, the OmniDocBench authors' own comparison
reports that **MinerU's table parsing "drastically improves parsing for
challenging cases, including rotated tables, borderless/semi-structured
tables, and long/complex tables"** — i.e. borderless tables, our exact
family, are explicitly claimed as addressed by an existing pipeline
system.

**Two honest caveats on these numbers**, so they are not over-read:

1. Our 45.14 is a **100-page subset**, not the full 1651-page benchmark,
   and is not a like-for-like comparison with published full-benchmark
   figures. The gap (~45 vs ~90) is far too large to be explained by
   subset variance, but the exact delta is not a valid measurement.
2. The **OmniDocBench "Table-block" sub-benchmark crops tables from the
   page and feeds the crop to the model** — so PaddleOCR-VL's 0.9195
   Table-block TEDS *already bypasses detection* and does not by itself
   prove small-table detection is solved. The end-to-end v1.5 Table-TEDS
   (89.76) does include detection, and is the number that matters here.

## 5. Evidence for / against a research gap

**Against (decisive):**

- The recovery mechanism (crop-and-refine) is **already published SOTA**
  in at least two independent systems, with a dedicated paper on the
  technique. Proposing it would be reinventing benchmarked prior work.
- Existing systems report Table TEDS ~90–93 end-to-end on this very
  benchmark, roughly double ours — so the capability demonstrably exists
  outside our pipeline.
- Our failing family (borderless tables) is explicitly named as improved
  by an existing pipeline system in the benchmark authors' own analysis.
- On the case examined in full, the failure is a **classification** and
  **filtering** problem, fully recoverable with models we already have
  loaded (0.0675 → 0.9434 confidence, exact correct structure, from
  cropping alone).

**For (weak / not established):**

- No public evidence was found that specifically isolates *1–2 row,
  <5%-page-area, borderless exam-paper tables* as a solved sub-problem.
  Absence of that specific evidence is not evidence of a gap, and it is
  outweighed by the direct demonstration that our own models handle these
  tables correctly once cropped.

## 6. Controlled experiments run

| # | Experiment | Result |
|---|---|---|
| 1 | Layout-region overlap vs GT table bbox | Region found, mislabelled `picture`, 98.3% GT coverage → **classification problem, not detection recall** |
| 2 | TT full-page detection threshold 0.7 → 0.05 | 0.0675 top score near GT → threshold alone cannot fix this safely |
| 3 | **Crop + upscale 1× / 2× / 3×**, all 5 tables | Detection recoverable in **5/5** (0.730–0.9994 on crop). Structure: exact in 1, exact only at ≥2× in 1, imperfect in 1, **absent at every scale in 1**, partially wrong in 1 → cropping is necessary everywhere; upscaling is decisive on one case and irrelevant on another |
| 4 | Docling TableFormer on 2× crop, all 5 tables | **found nothing on any of the five** → the two backends are not interchangeable on this family; composition cannot help, TT-on-crop is the working capability |
| 5 | Route/DPI audit | image route uses native resolution; `render_dpi` inapplicable → DPI ablation not available on this corpus; crop upscaling is the only resolution lever |
| 6 | TT full-page detection @0.7 on `page-d29fe4d2` | **0.9991 — already fires with no change at all**; lost purely to the orphan-attach gap |

## 7. Recommended direction

**Fix and integrate. Do not research this.** Ranked:

| Rank | Action | Class | Expected reach | Rationale |
|---|---|---|---|---|
| 1 | **Crop-and-verify pass**: probe non-`table` layout regions (and low-confidence areas) with the already-loaded Table Transformer on a **2× upscaled crop**, accepting only crops that clear a confidence bar *and* yield a structure grid | **[C] SOTA-technique integration** (MinerU-style Stage II, scoped to ambiguous regions) | **2 of 5** (`jiaocaineedrop_46` exact; `page-28657a85` exact at 2×) | Recovers measured 0.0675→0.9434 and 0.153→0.806 cases with zero new models. **Must be gated**: a false-positive study on table-free pages is a prerequisite, not an afterthought |
| 2 | Attach orphaned detected tables to the page when layout emitted no `table` region | **[A] bug fix** | **1 of 5** (`page-d29fe4d2`, already detected at 0.9991) | Content produced then silently dropped. **Caveat measured**: layout emitted overlapping `text` regions there, so attaching without suppressing them risks duplicating content into `text_block` — needs a 100-page check, not a blind fix |
| 3 | Benchmark MinerU2.5 / PaddleOCR-VL as a third candidate source on the hard-table set | **[C] SOTA integration** | potentially **2 of 5** (the structure-limited cases) | The only route to the 2 cases where *both* our structure models fail. Establishes a real ceiling instead of guessing; the composition layer is already N-way capable |
| 4 | Adaptive routing (crop-verify only when layout confidence is ambiguous) | **[B] engineering improvement** | — | Compute control; only worth it after 1 works and is measured |
| 5 | Novel multi-scale detector-selection research | **[D] — NOT justified** | — | Already published SOTA; see §4 |

**Reach ceiling, stated honestly:** items 1+2 together address **3 of the
5** remaining hard tables (60%), all with models already loaded. The other
2 (`..._en_2901` ×2) are **not reachable by any orchestration change** —
both TT and TableFormer fail on them at every scale tested. Those need
item 3, a genuinely different model. Nothing in this analysis suggests a
novel method is required for any of the five.

## 8. What NOT to do

- **Do not claim small-table detection as a research contribution.**
  Coarse-to-fine crop-refine is established, published, benchmarked SOTA.
- **Do not add a VLM as a *novel method* for this.** For 3 of the 5 cases
  the failure is our own filtering/orchestration plus crop scale, and
  models already loaded recover them (0.73–0.999 confidence on a crop). A
  VLM would be large compute for a problem existing specialists solve.
  *However* — for the 2 structure-limited cases where both TT and
  TableFormer fail at every scale, a stronger existing model is the only
  demonstrated route, which is item 3: integrate and **measure** a
  published system, not invent one.
- **Do not chase `render_dpi`.** Inert on this route (native-resolution
  images). Crop upscaling is the real lever — and it matters on
  `page-28657a85` (1×2 → correct 1×3 at 2×) while being irrelevant on
  `jiaocaineedrop_46`. Do not generalize either case to the family.
- **Do not blanket-lower detection thresholds.** Near-GT page-scale scores
  were 0.0675–0.6234; a threshold low enough to catch them all would
  flood the pipeline. The fix is *where* the model looks (crops), not
  *how permissive* it is.
- **Do not implement item 1 or 2 without a false-positive / duplication
  study first.** Both have a measured, named risk (hallucinated tables in
  real figures; duplicated content into `text_block`). This analysis
  deliberately stops before spending that compute.
- **Do not run the full 1651-page benchmark locally** to chase this.

---

## Summary table

| Issue | Pipeline bug | Known model limitation | SOTA already solves | Research gap |
|---|---:|---:|---:|---:|
| `label == "table"` filter discards mislabelled table regions (1/5) | **YES** | no | n/a | no |
| Orphaned detected table never attached to any element (1/5) | **YES** | no | n/a | no |
| Layout model labels borderless sparse-page table as `picture` | no | **YES** (upstream issue #3495, open) | **YES** (MinerU2.5, PaddleOCR-VL) | no |
| TT single-scale page-level detection misses small tables (0.068–0.62 at page scale, 0.73–0.999 on crop) | partial (no crop-refine stage) | **YES** (single-scale DETR) | **YES** (coarse-to-fine is published SOTA) | no |
| Structure needs ≥2× crop upscale to be correct (1/5) | partial (no upscale stage) | **YES** | **YES** (native-res Stage II) | no |
| **Both TT and TableFormer fail on 2×2 borderless grids at every scale (2/5)** | no | **YES — hard limit of both our structure models** | **likely** (MinerU claims borderless; not verified by us on these exact tables) | **NOT ESTABLISHED** |
| Docling TableFormer finds nothing on any of the 5 crops | no | **YES** | — | no |
| "Small/borderless table extraction" as a general capability | no | — | **YES** (~90 TEDS end-to-end vs our 45) | **NO** |

## Verdict

```
Pipeline bug?             PARTIAL — YES for two specific, fixable defects
                          covering 2 of the 5 remaining hard tables
                          (label filter; orphaned table). Not the whole story.

Known SOTA limitation?    YES for the models we chose, in TWO distinct places:
                            - Docling layout TABLE/PICTURE ambiguity on sparse
                              borderless tables (upstream issue #3495, open)
                            - single-scale DETR detection (0.068-0.62 at page
                              scale vs 0.73-0.999 on a crop)
                            - AND a hard structure limit: both TT and
                              TableFormer fail on 2x2 borderless grids at 1x,
                              2x and 3x (2 of 5 cases)
                          NO as a limitation of the field.

Implementation gap?       YES — the dominant category (3 of 5 cases). We lack
                          the crop-and-refine verification stage that both
                          MinerU2.5 and PaddleOCR-VL implement as their core
                          architecture.

Research gap?             NO for 3 of 5 cases — decisively not, the recovery
                          mechanism is published, benchmarked SOTA.
                          NOT ESTABLISHED for the remaining 2 (2x2 borderless
                          grids that defeat both our structure models). No
                          public evidence was found isolating that exact
                          sub-family as solved, but our own models failing is
                          not evidence the field has not solved it, and
                          MinerU explicitly claims borderless-table gains we
                          have not independently verified. The honest status
                          is: unresolved, and cheap to resolve by measuring an
                          existing system (§7 item 3) rather than by research.
```

**So: fix and integrate. Do not research.** Concretely, the next compute
should go to (1) a false-positive study gating a crop-and-verify pass,
(2) that pass itself, reaching 2 of 5, (3) the orphan-attach fix with a
duplication check, reaching 1 more, and (4) benchmarking MinerU2.5 or
PaddleOCR-VL on the hard-table set to settle the last 2 — **not** to a
novel method. This analysis deliberately stops before spending that
budget, which was its purpose.

## Addendum: item 4 attempted, formal verdict recorded

`docs/residual_failure_corpus.md` is the direct follow-up: item 4 above
(benchmark a real SOTA system on these exact tables) was attempted via a
public MinerU demo and blocked on browser-automation tooling (no
file-upload primitive; a base64-relay workaround cost ~85,000 tokens for
one 90KB image chunk, abandoned as disproportionate to corroborating
evidence). The comparison instead uses convergent primary-source evidence
(architecture papers, official OmniDocBench numbers, and this project's
own ground-truth attribute tags — two of the four unique failing pages
carry OmniDocBench's own `table_hard` label, a third carries the official
`table_full_line`/`table_horizontal` tag). That document also runs the
formal task categories (A–F shared-mechanism, [A]–[F] classification) this
one didn't yet, and reaches the same practical verdict with more rigor:
3/5 cases are pipeline-fixable, 2/5 are `[F] unresolved` (not `[E]` — a
single page's geometric pattern, not multiple independent examples), and
**there is no confirmed research gap.**
