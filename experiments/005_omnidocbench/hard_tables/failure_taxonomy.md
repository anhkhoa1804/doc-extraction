# Hard-table failure taxonomy — the "both-fail" region

Population: every ground-truth table scoring exactly **0.0 TEDS** on the
deterministic 100-page subset (seed=0), from the `local_table_ensemble_100`
predictions. Manifest: [`both_fail_100.json`](both_fail_100.json). Raw
per-table classification: [`failure_taxonomy.json`](failure_taxonomy.json).

Each table was classified by **replaying the exact production table path**
(`layout → OCR → table backend → cell-text association → candidate
reconciliation → merge → markdown`) on its page and recording the stage at
which the table is lost — not by inspecting aggregate metrics.

---

## 0. Measurement correction that changes the population

**The previously-reported "14/30 (47%) both-fail" figure was substantially
a measurement artifact, not an extraction result.**

The upstream evaluator (`.external/OmniDocBench/src/metrics/cal_metric.py`,
`_evaluate_teds_pair_with_timeout`, unmodified at the pinned commit) scores
a TEDS computation that exceeds a **120-second wall-clock timeout** as
`0.0, 0.0` — indistinguishable in the per-table output from a genuine
extraction failure, and folded straight into the aggregate mean.

The original 100-page evaluation logged **9 `[TEDS-timeout]` events**.
Re-evaluating the **byte-identical predictions** with the timeout raised
(`OMNIDOCBENCH_TEDS_TIMEOUT_SEC=1800`) produced zero timeouts and:

| Metric | as originally reported | correct value | delta |
|---|---:|---:|---:|
| `table TEDS.all` | 0.2743 | **0.4080** | **+0.1337** |
| `table TEDS_structure_only.all` | 0.3504 | **0.5084** | **+0.1579** |
| both-fail tables | 14/30 (47%) | **8/30 (27%)** | −6 tables |
| `text_block` / `reading_order` / `display_formula` / `table Edit_dist` | — | *bit-identical* | 0.0000 |

Every non-TEDS metric is unchanged to four decimals, which confirms the
mechanism is specifically the TEDS timeout and nothing else (same
predictions, same ground truth, same evaluator commit). Two independent
timeout-free runs agree on all 30 tables to within 1e-9, so the corrected
numbers are reproducible.

Six tables previously counted as "both models failed" score **0.3704 to
0.9310** once actually evaluated — including one at 0.9310 with
`TEDS_structure_only = 1.0000` (a perfectly recovered structure that had
been recorded as a total failure).

Consequences for the prior research narrative:

- The claim "both-fail is *more* common at scale (47%) than the 20-page
  sample suggested (29%)" is **withdrawn**. The corrected rate is 27%,
  statistically indistinguishable from the 20-page sample's 2/7 = 29%.
  The small sample was right.
- Table TEDS on the 100-page subset is **0.4080**, not 0.2743.
- Any table metric measured on a loaded machine at the default 120s
  timeout is potentially depressed. **All table numbers below are measured
  with the timeout raised.**

This is an upstream evaluator behaviour, not a defect introduced here, and
the evaluator was not modified. The mitigation is operational: set
`OMNIDOCBENCH_TEDS_TIMEOUT_SEC` high enough that wall-clock never decides a
score, and treat any run whose log contains `[TEDS-timeout]` as invalid for
table metrics.

---

## 1. The population is a coherent, nameable family

Across all 30 ground-truth tables in the subset, sorted by ground-truth row
count, the separation is essentially perfect:

| GT row count | n | mean TEDS | tables scoring 0.0 |
|---|---:|---:|---:|
| **≤ 2 rows** | 7 | **0.0000** | **7 / 7 (100%)** |
| > 2 rows | 23 | 0.5322 | 1 / 23 (4%) |

**Every table with two or fewer rows fails completely. Exactly one table
with more than two rows does.** By document source the same family shows up
as: `exam_paper` **6/6 tables at 0.0**, versus at most one zero in any other
source (`research_report` 1/8, `academic_literature` 1/5, `book` 0/6,
`colorful_textbook` 0/2, `newspaper` 0/1, `PPT2PDF` 0/1, `note` 0/1).

Concretely these are short, wide banner-style tables occupying **1.5–5.2%
of page area**: exam answer keys (`题号/答案` — question-number/answer),
score boxes (`题号/得分`), and two-cell grammar fill-in boxes. The one
>2-row member (`page-d29fe4d2`, 4×4) is a full-page layout table at 63% of
page area and fails for a different reason (below).

So the hard-table distribution is coherent: **few-row, wide, small-area
tables**, overwhelmingly from Chinese exam papers.

---

## 2. "Both-fail" is three different things — and half of it is ours

The critical question (is this a shared *capability* gap, or something
else?) resolves as follows:

| Category | Tables | % of both-fail | Is it a model capability gap? |
|---|---:|---:|---|
| **Composition-layer loss** | 3 | 37.5% | **No** — a viable candidate existed and was discarded |
| Shared detection failure | 4 | 50.0% | **Yes** — no source detected a region at all |
| Orphaned table | 1 | 12.5% | **No** — a table was produced but never referenced |

**Half the both-fail region (4/8) is not a model failure.** It is this
pipeline discarding or failing to serialize table structure it had already
successfully produced.

Mapping onto the Case A / B / C framing:

- **Case A** (both detect, both produce similar wrong structure): **0 of 8.**
  Not observed at all in this population.
- **Case B** (different failures, composition could help): **3 of 8** — and
  composition *already had* the winning candidate; it just could not use it.
- **Case C** (candidates reasonable, interface/serialization rejects them):
  **4 of 8** (3 composition losses + 1 orphan), plus the entire
  timeout artifact in §0 on top.

### 2a. Composition-layer loss (3 tables) — the actionable finding

Verified per page by replaying the production path:

| Page | GT | Docling's own candidate | Table Transformer | Emitted? |
|---|---|---|---|---|
| `..._en_2540` | 2×13 | **2×12, 18/18 cells filled, bbox matching GT within ~2px** | none (no row/col grid) | **nothing** |
| `..._en_922` | 2×13 | 2×6, 7 cells filled | none | **nothing** |
| `..._en_1349` | 2×9 | 1×6, 6 cells filled | none | **nothing** |

On all three, Docling's layout stage **correctly located the table region**
and Docling's own TableFormer **produced a real table for it** — on
`en_2540`, essentially the exact ground-truth structure. Table
Transformer's structure model returned no row/column grid for the same
crop, so `TableTransformerBackend.extract` emitted no `Table` object at all.

`_apply_native_table_fallback` then iterated over the primary backend's
tables to compare each against the alternatives — and with zero primary
tables, **the loop body never executed**. The good candidate was silently
dropped, the table element got `table_id=None`, and
`page_to_prediction_markdown` emitted nothing for it.

The composition layer could only ever *replace* a table the primary backend
had already found. It could never *add* one the primary had missed. That
asymmetry — not a model capability gap — is why these tables scored 0.0.

Why this family specifically: Table Transformer's structure model is being
handed a very short, very wide crop (a 2-row banner strip). That aspect
ratio is where its row/column detection returns nothing, while TableFormer
handles it. The two specialists have genuinely complementary behaviour
here; the pipeline just could not exploit it.

### 2b. Shared detection failure (4 tables) — the real capability gap

`jiaocaineedrop_46` (2×7), `..._en_2901` ×2 (2×2 each), `page-28657a85`
(1×3): **no source found a table region.** Docling's layout emitted zero
`table` regions, Docling's TableFormer produced zero tables, and Table
Transformer's standalone detector found nothing. The content is present in
the prediction, flattened into ordinary text.

These are the smallest members of the family (1.5–4.2% of page area, 1–2
rows, often borderless). This is a genuine detection-recall gap shared by
both backends and is **not** addressed by any composition change.

### 2c. Orphaned table (1 table)

`page-d29fe4d2` (4×4, 63% of page): Docling's layout emitted **no** table
region, so Table Transformer fell back to its own standalone detection and
**did** produce a table — but `merge_regions_into_page` only attaches
tables to elements created from layout regions labelled `table`. With no
such region, the detected table is never referenced by any element and is
never serialized. A third, separate content-loss path; not fixed here,
because emitting it would duplicate text already emitted by the other
layout regions covering that area, which risks the text metrics.

---

## 3. Candidate diversity

Restricted to the both-fail population (the disagreement structure across
*all* 30 tables is in `observations.md`):

| Class | Count | Meaning |
|---|---:|---|
| agree + both wrong | 4 | shared detection blind spot (§2b) |
| **disagree + one usable** | **3** | **Docling correct, TT empty — composition should have won** |
| disagree + both wrong | 0 | — |
| agree + both correct | 0 | (by construction: these are the 0.0 tables) |

The headline: **there is no "agree + both produce similar wrong structure"
case at all** in this population. Where both models engage with the table,
they do not share a blind spot — one of them gets it substantially right.
The shared blind spot is purely at **detection**, not structure.

---

## 4. What this implies

1. **A third structure model is not justified by this evidence.** In every
   case where the region was detected, an existing model already produced a
   usable structure. Adding a third structure specialist would address
   0 of 8 tables.
2. **The immediately actionable gap is the composition-layer asymmetry**
   (3/8), which is a code fix requiring no new model and no new inference.
3. **The remaining genuine gap is detection recall on small, borderless,
   few-row tables** (4/8) — shared by both backends. That is where a
   structurally different capability (e.g. a detector tuned for small
   banner-style regions, or a document VLM with stronger layout reasoning)
   could matter. It is a *detection* problem, not a structure problem —
   which is a materially different conclusion from "both table structure
   models fail together."
4. **Table metrics on this benchmark must be measured with the TEDS timeout
   raised**, or wall-clock load silently manufactures failures.

## 5. Experiment run from this diagnosis

Hypothesis, change, and measured result: see
[`../observations.md`](../observations.md) "Hard-table capability analysis"
and [`../results/comparison.md`](../results/comparison.md).
