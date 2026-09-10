# Milestone 035 — Mechanism D: Table-Gating Forensic Study

Status snapshot reconciled after cold-start takeover on 2026-09-10.
This document is the primary
human-readable entry point for 035 — read it before any phase script.

## Authoritative current state

- Phase 13 is **COMPLETE and frozen: 150/150** validation-gated identities
  (33 immutable original + 117 recovery), zero duplicate identities and zero
  unresolved incomplete identities. Batch1–5 were structurally revalidated
  from disk after the VM restart; batch4's initially invisible harness-owned
  worker ultimately emitted a genuine 20/20 completion record and PASS
  validation. Memory released to about 29 GiB available after each completed
  worker; no swap or usable NVIDIA driver exists.
- Chunk1 is **COMPLETE: 229/229** (199 original + 30 recovered), with both
  recovery batches validated and audited.
- Chunk0 is **COMPLETE: 229/229** validated page-runs (32 original + 20
  recovery batch0 + 20 recovery batch1 + 20 recovery batch2 + 20 recovery
  batch3 + 20 recovery batch4 + 20 recovery batch5 + 20 recovery batch6 +
  20 recovery batch7 + 20 recovery batch8 + 17 recovery batch9). Batch6 was
  structurally revalidated from disk after the VM restart. The final audit
  confirms 197 recovered + 32 immutable original runs, zero duplicate
  identities, zero unresolved incomplete runs, zero schema errors, and all
  ten recovery-batch validations PASS.
- The first batch7 attempt was interrupted by the tool-session transition
  after layout/OCR on its first page and before table/final/metadata output.
  It has **zero valid page-runs** and remains preserved at the canonical
  `batch7/` root. The retry writes to `batch7_retry0/` with
  `HF_HUB_OFFLINE=1` and `TRANSFORMERS_OFFLINE=1`; this uses the same
  locally cached, already-recorded model snapshots and prevents futile
  network metadata retries in the restricted VM.
- Recovery-root discovery is now validation-gated. A PASS validation can
  record a noncanonical retry root, so downstream phases use exactly one
  verified attempt per batch and cannot accidentally ingest preserved
  interrupted artifacts.
- `recovery_run_telemetry.json` records batch2's genuine exit, runtime,
  validation, and available-memory samples. Exact batch2 worker RSS was not
  observable from the outer PTY namespace and is intentionally recorded as
  unavailable rather than invented.
- The checked-in analysis artifacts are still the **old preliminary 122/665
  GT-table analysis**. No Phase 3–17 full rerun has been started. The run-root
  discovery bug that would have excluded recovery trees is fixed in source,
  but the scientific outputs must be regenerated only after chunk0 reaches
  229/229.
- **Source-audit caveat, methodology decision still open:** the exact region
  gate is `region.label.lower() == "table"`, but the current
  `TableTransformerBackend` also performs whole-page detection when no
  table-labelled boxes are supplied. Therefore D2 is currently a
  *region-scoped crop-gating* classification, not proof that the specialist
  was absent from the page. `merge_regions_into_page()` only assigns table
  objects to `ElementType.TABLE` regions, so a globally detected table may
  also be present but unowned in the final IR. Do not revise D2 denominators
  or the routing hypothesis until this is explicitly decided and measured.
- Phase 13's original direct 150-page worker was intentionally interrupted
  after preserving **33 valid complete page-runs** and one incomplete run:
  that direct process violated the established process-recycling execution
  policy. Continuation batch0 was later interrupted without a kernel OOM;
  its **18 complete runs** passed salvage validation and its two empty,
  no-metadata directories are preserved outside the admitted root. The frozen
  sample is unchanged. `phase13_identity_ledger.json` records every frozen
  identity exactly once: 33 `VALID_ORIGINAL`, 117 `VALID_RECOVERY`, and no
  `INCOMPLETE`/`NOT_STARTED` identity. One historical render-only original
  directory remains isolated as incident evidence; its identity was recovered.
  Its annotation-mismatch accounting bug is fixed in source. Final Phase 13
  analysis finds five table-labelled regions on no-GT-table pages: three
  harmless over-detections, two ambiguous, and zero annotation mismatches.

## Objective

> Among all OmniDocBench ground-truth tables, what fraction are actually
> lost because the production region-label gate prevents table processing
> (`region.label.lower() == "table"`, `pipelines/base.py:747`), what
> fraction fail earlier or later in the pipeline, and what is the
> smallest intervention that would recover genuine gated tables without
> creating an unacceptable new failure mode?

This resolves whether Mechanism D (031's central finding — table-shaped
content silently mislabeled as `picture`/`text`/etc.) is a dominant,
secondary, or minor production bottleneck, using the full 665-GT-table,
458-page OmniDocBench population as independent evidence — not a
synthetic stamp-case argument.

## Frozen methodology

Cannot change without explicitly overturning the experimental record:

- IoU/containment thresholds in `matching_lib.classify_match` (round
  numbers, not tuned — see its docstring).
- The D0–D7 failure-stage taxonomy in `phase4_9_14_funnel.classify_stage`.
- 033's table-shape rule (`row_bands>=3 AND col_bands>=2 AND
  children_per_row_band>=1.5`), reused verbatim via
  `experiments/019_ocr_grid_table_detection/table_candidate.py` — not
  reimplemented, not retuned.
- `configs/cpu.yaml` (device=cpu) as the extraction config — CPU-only,
  never GPU, for the duration of this milestone (see Incident below).
- The GT-table population definition: every OmniDocBench page with ≥1
  `layout_dets` entry `category_type == "table"` (665 tables / 458 pages
  — cross-checked exactly against the official evaluator's own
  `table.metric_debug.TEDS.sample_count`).

Nothing in `src/`, `configs/`, or `tests/` has been touched by this
milestone (verified: `git status --porcelain` on those paths is empty).

## Current evidence

**All numbers below are PRELIMINARY — partial-coverage samples, not the
final population.** Coverage fractions are stated explicitly; do not cite
these as final Mechanism-D findings.

- Phase 1 (GT contract): **FINAL** — 665 GT tables / 458 pages, all clean
  axis-aligned rectangles, no `ignore` flags. Not sample-dependent.
- Phase 2 (coordinate proof): **FINAL** — identity pixel-space transform
  confirmed (100/100 dimension matches across 8 page sizes, geometric IoU
  0.98 on available cases). Not sample-dependent.
- Phase 3–9/14 (matcher + funnel): **FINAL full-population rerun** — 665/665
  GT tables matched over 458 pages: D0=561, D1=41, D2=34, D4=25, D6=3,
  D7=1, D3=0. Strict Mechanism D is 34/665 (5.11%). D2 is a region-scoped
  crop-gating loss, not proof that Table Transformer was absent at page level.
- Phase 10 (occlusion): full rerun: D2=0/37 on the documented proxy-occluded
  subgroup versus 34/628 (5.41%) clean; this is a null result for these
  proxies, not a general proof that occlusion is irrelevant.
- Phase 11 (historical cross-reference): **FINAL** — 023–033's corpus is
  synthetic (EN/VI only, zero real data) and OmniDocBench is real/scraped
  with zero Vietnamese content; the two are disjoint by construction, so
  no same-page natural experiments are possible. Not sample-dependent.
- Phase 12 (table-shape-on-GT): full rerun: 033's frozen rule recognizes
  11/34 D2 cases (32.35%), while firing on 55/105 eligible non-table regions.
- Phase 13 (false positives): **NOT STARTED** — dataset built and
  validated (150 pages, 0 duplicates, 0 overlap with GT population, 0
  false "no-table" claims), extraction deliberately not run yet
  (queued to avoid competing with the primary/recovery extraction for
  CPU/RAM).
- Phase 15 (external metric reconciliation): mechanics verified correct
  (665 GT count cross-checks; evaluator's 571/665 TEDS coverage kept
  strictly separate from this milestone's own funnel counts) — numbers
  themselves are preliminary pending full coverage.
- Phase 17 (counterfactual): mechanics verified, numbers preliminary
  (n=2 D2 cases).

## Hypotheses

| Hypothesis | Status |
|---|---|
| D3 (correct label, rejected anyway) is architecturally near-impossible in this codebase | **SUPPORTED** — source-verified (single gate, no secondary filter, `stages/table.py:run_table`), and measured D3=0 in all data collected so far |
| Mechanism D (D2) is a dominant failure mode | **UNRESOLVED** — 18% coverage, D2=2 so far; nowhere near enough data |
| Concurrency amplifies peak extraction-process RAM beyond what a single worker would reach | **PARTIALLY SUPPORTED** — chunk1 alone has stayed bounded (7.9–11.4GB) across 60+ pages without incident, while the original 2-worker run died at 12.1GB; not yet proven that a single worker can NEVER reach that zone over a long enough run |
| A single worker's memory is unbounded / a leak | **REJECTED for the tested range** — calibration test (4 pages, isolated) showed spike-and-release per page, not cumulative growth; chunk0 recovery batches 0–1 and chunk1 recovery batches 0–1 show the same pattern |

## Pipeline status

| Phase | Status |
|---|---|
| 0 Baseline | READY (done) |
| 1 GT contract | DONE (final) |
| 2 Coordinate proof | DONE (final) |
| 3 Region matching | DONE — fresh 665/665 full-population rerun |
| 4 Failure funnel | DONE — fresh full-population rerun |
| 5 Mechanism-D population | READY for full rerun |
| 6 Confusion matrix | READY for full rerun |
| 7 Gating impact | READY for full rerun; MULTIPLE_MATCH denominator fix present |
| 8 Final IR outcomes | READY for full rerun (folded into gating_impact.json) |
| 9 Geometry stratification | READY for full rerun |
| 10 Stamp/occlusion | DONE — fresh full-population rerun |
| 11 Historical cross-reference | DONE (final) |
| 12 Table-shape-on-GT | DONE — fresh full-population rerun |
| 13 False positives | **DONE (final sample)** — frozen 150/150 validated; 5 table-labelled regions, 3 harmless over-detections, 2 ambiguous, 0 annotation mismatches |
| 14 Specialist invocation map | DONE — fresh full-population rerun |
| 15 External metric reconciliation | DONE — fresh full-population rerun |
| 16 Root-cause distribution | Not yet written — pure synthesis over Phase 4 data, no blocker |
| 17 Counterfactual | DONE — 11/34 D2 eligible upper bound, with substantial false-positive exposure |
| 18–20 (production options / reassessment / decision) | Not started — correctly deferred until full-population data exists |

## Incident

### Current recovery state

The first Linux OOM remains **PROVEN** and the second termination remains a
**high-confidence, not directly verifiable harness-level classification**;
the evidence and uncertainty are preserved below. Recovery is now serial,
single-worker, and process-recycled. Chunk0 batches 0–7 completed 20/20 with
zero schema errors or collisions. The current chunk0 recovery count is
197/197, leaving no recovery pages. Chunk1's recovery is complete and
independently audited at 229/229.

The two incomplete directories left by the interrupted original chunk1 run
remain immutable historical artifacts; the page-identity audit confirms all
30 assigned missing identities were recovered, so they are excluded by the
phase loader rather than silently treated as valid runs.

**Original first interruption (2026-09-09 02:51:28 UTC)**: chunk0 (PID 20454, one of two original
concurrent CPU extraction workers) was killed by the Linux OOM killer at
12.1GB anon-RSS (kernel-confirmed, `journalctl -k`). 32/229 of its pages
were already valid and complete; 1 was in-flight (incomplete, not
corrupted); 196 had not started.

Root cause: **PROVEN** — kernel OOM, global, zero swap configured.
**PROBABLE** — two concurrent processes' per-process memory floors (model
weights cached for process lifetime, by design —
`_get_component_backends`, `cli.py`) combined to exceed 31GB system RAM.
**UNRESOLVED** — whether a single long-lived worker can independently
reach the same zone given enough pages (not yet observed either way).

At the time of that interruption, recovery was authorized in Mode 2 (single worker, process
recycling every 20 pages), writing to an isolated
`results/gt_tables_chunk0_recovery/batch<N>/` tree — the original 32
valid page-runs under `results/gt_tables_chunk0/` are immutable, untouched.
10 batches were planned (9×20 + 1×17 = 197 pages). The historical batch-0
snapshot below predates the completed batch1 recovery.

Full detail: `oom_incident_record.json`, `oom_calibration_results.json`,
`recovery_manifest.json`, `recovery_batches_manifest.json`,
`recovery_run_telemetry.json` (populated after each batch),
`chunk1_live_evidence_timeline.json`.

Three low-available-memory alerts (min 2476MB) fired during batch0 on a
conservative 3GB threshold; all investigated and confirmed **not**
recurrences of the OOM (no kernel OOM event, both processes remained
alive and returned to their normal RSS bands within seconds — consistent
with transient buffer/cache reclaim, not memory exhaustion).

Batch0 completed cleanly: 20/20 valid, 0 incomplete, 0 schema errors, 0
collisions, peak RSS 10.07GB, genuine exit code 0, RSS confirmed released
on exit. Batch1 subsequently completed 20/20 and passed structural
validation. Batch2 completed 20/20 and passed structural validation; its
first launch used the repository `.venv` and produced 0/20 because Docling
was unavailable, so it was not counted and did not overwrite valid output.
The retry used the validated CPU runtime `doc-extraction-linux312`.
Combined chunk0 total is now **32 original + 197 recovered = 229/229**;
`chunk0_recovery_final_audit.json` is COMPLETE with all ten batches PASS.

**Incident status: RECOVERY COMPLETE** — all remaining pages completed
serially without a recurrent OOM. The aggregate-pressure explanation remains
PROBABLE rather than a claim that every possible single-worker workload is
memory-safe indefinitely.

### MEMORY INCIDENT DECISION

```text
Concurrent heavy extraction is no longer used.

Reason:
The original OOM and subsequent live evidence indicate aggregate
memory pressure is the dominant operational hazard -- chunk1 alone
subsequently reached ~12.9GB (exceeding chunk0's exact 12.1GB kill
value) without any OOM, while batch0+chunk1 running concurrently
produced 3 low-memory alerts that chunk1-alone conditions have not
reproduced. This confirms the failure mode is aggregate system
pressure under concurrency, not a fixed per-process RSS ceiling.

Recovery schedule:
Chunk1 is now complete and audited. Continue chunk0 recovery batches 3-9
with one process at a time, conservative process recycling (20 pages/batch,
unchanged -- not increased based on the clean early batches).

Scientific impact:
None. This changes execution scheduling only -- no threshold, gate,
routing rule, OCR setting, matching policy, or table-shape rule changed.
```

**Important nuance, stated explicitly**: a single worker has **not** been
proven memory-safe indefinitely. It has only been shown to behave
substantially more safely than two concurrent workers in the population
observed so far (chunk1 original plus 30 recovered pages; chunk0 recovery
batches 0–1: 40 pages). Do not treat
either the 12.1GB or the 12.9GB reading as a safe/unsafe per-process
threshold — the operating signal is system-wide available memory and
observed behavior, not either historical number.

## Technical debt

- **P0**: none currently open.
- **P1**: Phase 13 needs three remaining process-recycled continuation batches.
  The original 33 plus batch0–2's validated 58 are immutable; every remaining
  batch must exit, validate, and be admitted only through its PASS-selected root.
- **P2**: `phase4_9_14_funnel.py` is doing the work of 7 phases (4–9, 14)
  in one file for shared-classifier-consistency reasons (documented in
  its own module docstring) — readable but dense; a future pass could
  split it into `funnel.py` + a thin per-phase runner without changing
  any logic, if it becomes a maintenance burden. Not worth doing now.
- **P2**: no `.gitignore` coverage existed for
  `experiments/035_mechanism_d_gating/{dataset,results/**/_doc_extraction_runs,results/**/predictions}`
  until this cleanup pass — **fixed** (see `.gitignore`).
- **P2 fixed**: Phase 3–12/14 previously hard-coded only the original chunk
  roots. Discovery now includes only PASS-validated recovery roots and can
  select a separately preserved retry root without changing matching or
  routing methodology.
- **P2**: Phase 13 previously dropped annotation-mismatch records; source now
  preserves them and reports separate total/no-overlap/mismatch counts.
- **P1 research/architecture boundary**: whole-page Table Transformer fallback
  plus table-object ownership is not represented as a separate 035 funnel
  stage. This is a confirmed source fact, not yet a methodology change; add a
  measured page-level fallback/ownership split before using D2 as a production
  causal estimate.

## Pending decisions

- Preserve the completed recovery outputs as immutable evidence; no
  recomputation is authorized or needed.
- Phase 13 remains a 150-page frozen stratified sample. Its sequential
  scheduling is an execution policy, not a scientific threshold.

## Next execution gate

Immediate: run the fresh Phase 3–17 analysis from the complete, validation-
gated population. The primary 458-page GT-table corpus is complete and both
chunks independently audit to 229/229; Phase 13's frozen non-table sample is
also complete at 150/150. This execution recovery was an ENGINEERING CHANGE,
not a scientific-methodology change.

Full Phase 3–17 analysis at final numbers requires, in order:
1. Phase 3 rerun using original plus recovery run roots (458 complete pages /
   665 GT tables), then Phases 4–17 rerun in sequence.

Only after (2) should Phases 16 (root-cause distribution), 18 (production
options), 19 (031–034 reassessment), and 20 (final decision) be written.

## SECOND EXECUTION INTERRUPTION (2026-09-09 ~06:07Z)

The original 035 chunk1 worker was terminated after reaching **199/229
pages**. 199 completed page-runs were preserved and verified intact
(valid JSON, correct schema, correct page identity); 1 page was in-flight
and incomplete; 29 were never started. By assigned-image-name the split
is **199 valid + 30 to-recover = 229** (the in-flight page is
indistinguishable by name from a never-started one, because its
`metadata.json` was never written — so it is simply one of the 30
recovery targets).

**No kernel OOM event was found.** Across the entire session uptime there
is exactly one kernel OOM kill ever recorded — the *first* incident
(chunk0, 02:51:28) — confirmed via `journalctl -k` since boot and raw
`dmesg -T`. Cgroup counters (`user-1002.slice`, `session-3.scope`) show
`oom_kill=1`, fully accounted for by that first incident; a cgroup-limit
kill would have produced its own `CONSTRAINT_MEMCG` dmesg entry and none
exists. `systemd-oomd` is not installed. Container-runtime journals are
empty for the window.

The leading classification is therefore an **agent/harness-level memory
guard** (the termination notice originates from the tool platform's own
background-task supervisor, not any OS log) — **high confidence that it
was NOT kernel/cgroup/systemd OOM** (direct negative evidence), and
high-but-not-independently-verifiable that it was the harness (its
internals aren't inspectable from this session). Unlike the first
incident, no genuine process exit code was captured, because the wrapper
shell itself was terminated before its capture line could run. That
uncertainty is recorded, not papered over.

Only the missing population is being reprocessed — the 199 valid runs are
immutable and are never recomputed. No scientific methodology change is
introduced; this remains an execution-level recovery.

Note also: Research-No.1's evaluator **completed successfully and
naturally** at ~06:05 (`result.json` + 383MB `pair_logits.pt` written) —
it was not killed, and was never interfered with by this project.

## CHUNK1 COMPLETE — 229/229 (2026-09-09 ~08:10Z)

`chunk1_recovery_final_audit.json`: **199 original valid + 30 recovered =
229/229**, zero duplicate identities, zero unresolved incomplete runs,
zero schema errors, both recovery batches PASS. Independently
cross-checked on disk (counting run dirs containing a valid
`final/document.json`), not only via the validation JSONs.

| batch | pages | exit | peak RSS | min avail | validation |
|---|---|---|---|---|---|
| c1 recovery batch0 | 20/20 | 0 (genuine) | 9.82 GB | 19.9 GB | PASS |
| c1 recovery batch1 | 10/10 | 0 (genuine) | 7.18 GB | 22.6 GB | PASS |
| c0 recovery batch2 | 20/20 | 0 (genuine) | unavailable | 24.9 GB sampled | PASS |

Zero kernel OOM events during either batch. Every batch transition
followed the required handoff: worker completes → genuine exit verified →
RSS released → validation PASS → telemetry recorded → next worker starts.
The original 199 runs were never recomputed or touched.

**Scheduling decision for chunk0**: resumed immediately after this audit.
Machine state at handoff was recorded: zero 035 extraction workers, 25GB
available, GPU idle. Research-No.1 independently started a new CPU-only
job (`representation_decoder_ladder.py`, ~3.7GB) at 08:09 — noted, not
interfered with; at ~3.7GB alongside one ~10GB recovery worker this is
far from the two-heavy-extraction-worker condition that caused the
original OOM.

## GPU opportunity audit (2026-09-09 ~04:30Z)

Authorized to consider opportunistic GPU use given chunk1's long remaining
runtime. Read-only source audit of Research-No.1's active evaluator
(`tools/readout_v2_evaluate.py`, PID 19811 + 2 DataLoader worker children,
PID 19847/19848) — **not touched, not modified, not restarted**.

**Finding: the premise that it might be CPU-bound due to a missing CUDA
path is refuted by source.** Line 124 of that script hard-codes
`"--device", "cuda"` into its own training-harness invocation, with no
CLI flag to override it — CUDA is already correctly selected and active
(confirmed independently: it is the sole process holding ~4.75GB VRAM,
and `nvidia-smi` utilization fluctuated 0-100%, read 58% at last check —
consistent with real, ongoing GPU compute, not an idle context). Its
long wall-clock time (`--eval_batches 0` = full VG150 validation split,
not a subset) plus its visible CPU load (`--num_workers 4` DataLoader
workers doing CPU-side CLIP preprocessing, and per-batch CPU
synchronization in its own monkey-patched hooks for statistics
accumulation and pair-logit dumping) is normal, expected behavior for a
thorough full-split SGG evaluation — not a fixable bottleneck, and not
something a "cleaner" GPU-enabled relaunch would meaningfully improve,
because there is nothing to fix.

**Conclusion**: no valid, additive GPU workload exists to launch against
Candidate 2. Launching a duplicate/equivalent evaluator would compete for
the same GPU/VRAM/CPU the active one needs — interference, not
opportunistic use of idle capacity.

**Candidate 1 (a future 035 GPU-enabled extraction workload)**: VRAM is
genuinely abundant right now (~18.3GB free of 23GB), but this does not
address 035's actual proven bottleneck, which is **system RAM**, not
VRAM — switching `device: cuda` would not repair the OOM mechanism
(model-weight loading and Python-side per-page object accumulation both
happen in host RAM regardless of which device runs the matrix
multiplies). It would also deviate from 035's frozen CPU-only
methodology (`configs/cpu.yaml`) mid-experiment, which Phase H of this
milestone's own rules requires measuring and reporting as a
reproducibility finding, not adopting casually for speed. Not pursued.

**GPU opportunity decision: RED** (no candidate today clears the bar of
"safe AND additive AND decision-relevant") — correctly deferred, not a
missed opportunity. No probe was run.

## Deferred / not worth chasing yet

- GPU optimization or probing — GPU has read PROTECTED (Research-No.1
  active) at every check this session; not blocking anything, revisit
  opportunistically, never proactively.
- Further memory-mechanism forensics (e.g. instrumenting Docling/torch
  internals to find the exact allocator behavior behind the spike-and-
  release pattern) — the operational question (is single-worker safe
  enough to resume) has enough evidence to act on; the underlying
  mechanism is intellectually interesting but not decision-relevant.
- Splitting `phase4_9_14_funnel.py` into separate files — cosmetic,
  no correctness or velocity benefit right now.
- Any new hypothesis or probe that doesn't change what Phase 16/18/19/20
  will conclude — full-population data, not more targeted probes, is
  what's actually blocking those.
- Re-litigating the D2/D3 architectural finding — already source-verified
  twice (initial audit + this cleanup pass), stable.
