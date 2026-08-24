# Pipeline integrity baseline

Establishes, before any new research claim, whether the current pipeline
has known avoidable losses left over from prior phases. Checked directly
against the code at commit `9a9843c` — not from memory of what was fixed.
One new fix was made *during* this audit (TEDS timeout hygiene): it is a
pure measurement-tooling change with no accuracy tradeoff, so it did not
need the evidence-gating the other, still-open items do.

| Mechanism | Status | Evidence |
|---|---|---|
| Table candidate preservation (compare + add) | **Fixed** (commit `982cc2f`) | [`pipelines/base.py:_apply_native_table_fallback`](../src/doc_extraction/pipelines/base.py) now adds an unmatched extra candidate, not only replaces a matched one. Verified: 185→190 tests include 3 that fail against the pre-fix code. |
| Model-agnostic N-way candidate selection | **Fixed** (commit `df1f0a1`) | `TableCandidate` / `select_best_table_candidate` in `pipelines/base.py` — not hardcoded to exactly two backends. |
| Non-`table`-labelled regions containing a real table | **Open — diagnosed, not fixed** | `pipelines/base.py:559`: `table_regions = [r for r in layout_result.regions if r.label.lower() == "table"]`. A region layout correctly localized (IoU 0.753, 98.3% GT coverage) but labelled `picture` is never probed. Deliberately not fixed yet — needs a false-positive study first (`docs/research_gap_analysis.md` §8, "what NOT to do"). |
| Orphan table handling (detected, never attached) | **Open — diagnosed, not fixed** | `merge_regions_into_page` attaches a `Table` to an `Element` only when layout emitted a `table`-labelled region. `page-d29fe4d2`: Table Transformer detects at 0.9991 **on the unmodified full page**, at the default 0.7 threshold — layout emits no `table` region for it, so the table is computed and silently never serialized. Same reason as above for not fixing yet: attaching without checking for overlapping `text` regions risks duplicating content into `text_block`. |
| Crop/refine for small/borderless tables | **Not implemented** (by design — analysis phase only) | `docs/research_gap_analysis.md` measured detection recoverable in 5/5 hard cases via cropping (0.068–0.62 at page scale → 0.730–0.9994 on crop), with resolution decisive in 1/5. No source path performs this; `grep -rn "upscale\|LANCZOS" src/` is empty. |
| Native Docling table fallback (`native_tables`) | **Working as designed** | `DoclingBackend.native_tables()` reuses the same cached conversion `recognize()`/`analyze()` already produced — zero extra inference cost when Docling is the configured OCR/layout backend, confirmed by direct code read. |
| Evaluator subset/ground-truth alignment | **Fixed** (commit `9db9215`, still correct) | `write_subset_ground_truth` + `run.py`'s automatic `--ground-truth` override, re-verified present at `evaluate.py:46` and `run.py:264` this session. Regression tests: `tests/test_omnidocbench.py`. |
| **TEDS timeout methodology** | **Fixed this session** | Previously an env var (`OMNIDOCBENCH_TEDS_TIMEOUT_SEC`) nobody was required to set — silently contaminated two separate 100-page runs (14/30→8/30 both-fail, table TEDS 0.2743→0.4080, purely from re-evaluating the same predictions with the timeout raised; see `observations.md` §18, §22). Now: `write_evaluator_config` writes `timeout_sec` directly into the evaluator's own `table` metric config (default 900s, `DEFAULT_TEDS_TIMEOUT_SECONDS`), and `evaluate.py` scans evaluator stdout for `[TEDS-timeout]` lines, writing a `TEDS_TIMEOUTS.txt` marker and a loud stderr warning into the result directory whenever any occur — so a contaminated run can never again look identical to a clean one. `run.py` inherits this automatically (calls `evaluate_step.main()` without overriding the flag). 5 new tests in `tests/test_omnidocbench.py`. |
| Deterministic subset selection | **Working as designed, re-verified** | `select_subset`'s `step = len(samples)/limit`, floor-indexed, same `seed` → same pages every time. Explains the exact page-level reproducibility found across the 20- and 100-page subsets (`observations.md` §17). |
| **Table Transformer structure-recognition determinism** | **Open — known, unaddressed** | `TableTransformerBackend`'s structure output is **not** bit-identical across separate `prepare.py` process invocations on CPU, same image, same code, same config (`book_zh_DLT10902008` scored 0.232 in one run, 0.368 in another — `observations.md` §12). No `torch.manual_seed`/determinism flag anywhere in `table_backend.py` or `docling_backend.py` (checked directly, empty grep). Does not affect any *reported* result (the large deltas already published are far bigger than this noise, and the coherent-single-run methodology used since sidesteps it), but any *future* cross-run comparison of raw TT scores should not trust single-run numbers at the 1-2-decimal-place level without accounting for this. |

## What this table means for the next phase

Three items are genuinely still open, and none of them is silently
assumed fixed going into the SOTA comparison below:

1. **Label-filter and orphan-table gaps** (3 of the 5 currently-known hard
   cases) remain unfixed by design — evidence-gating first, per the
   previous phase's explicit scope. They are **not** re-litigated here;
   the SOTA comparison below is run against the pipeline *as it exists*,
   label-filter bug and all, because that is genuinely what determines
   today's residual failures.
2. **TT nondeterminism** means any single-run per-table TT score in this
   or a future phase carries unquantified noise at the sub-0.1 level.
   Large, cross-metric-consistent deltas (like the composition fix's
   +0.073/+0.043 TEDS results) are unaffected; anything smaller reported
   from a single run should say so.
3. **TEDS timeout** is now closed at the tooling level. Every evaluation
   run from this point in the project onward automatically gets the
   raised timeout and the post-run check — this is the one item on this
   list that required no evidence-gating to fix, because it only changes
   how correctly we *measure*, never what the pipeline *produces*.
