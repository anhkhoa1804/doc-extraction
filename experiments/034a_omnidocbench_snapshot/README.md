# 034a — Full OmniDocBench External Benchmark Snapshot

External validation layer, not a replacement for the production-shaped
023–033 research track. See `FINAL_REPORT.md` for the full report.

## Question

How does the current system perform on the full independent OmniDocBench
benchmark, and do the 023–033 production-shaped failure modes generalize
to it?

## Headline results

- **A real, previously-latent production bug was found and fixed**:
  `process_file()` never resolved `config.device == "auto"` before
  constructing backends — every historical caller had avoided triggering
  it by luck (always using a literal `cpu`/`cuda`, or resolving it
  themselves first). Fixed with a 2-line guard, a new regression test
  (`tests/test_cli_device_resolution.py`), zero regressions (345 passed
  vs baseline 341, +4 new tests), and confirmed semantically no-op
  (100% byte-identical output, old workaround vs the fix).
- **Live GPU-sharing test, not hypothetical**: partway through this
  milestone, another project's training job (`Research-No.1`) began
  actively using the shared L4. The in-progress GPU run was stopped
  cleanly within seconds (zero interference, verified), switched to
  CPU-only, then switched back to GPU once that job finished — a real
  exercise of `select_device()`'s CLEAR/LIMITED/PROTECTED policy.
- **Concurrency measured, not assumed**: C2 gives 1.71x throughput, C4
  gives 2.60x — both real, zero-failure, zero-determinism-mismatch — but
  both push VRAM to within 1–4% of the L4's 23 GB capacity on a 77-page
  sample. Neither was selected for the full run; C1 (serial) was, on
  safety grounds explicitly reasoned through in `selected_benchmark_
  config.json`.
- **A dramatic, real accuracy finding**: on the 77-page representative
  subset, mean text-similarity is 0.50 for English pages vs 0.03 for
  Simplified Chinese (16.7x gap) — every one of the 10 worst-scoring
  pages is Chinese, every one of the 10 best is English. This is the
  system's documented, deliberate EN/VI-only OCR scope (already
  established by experiment 007), not a new defect, and was **not**
  "fixed" by adding Chinese OCR per this milestone's own explicit rule.
- **A genuine bug in the official evaluator itself**: its TEDS
  computation hit an internal multiprocessing race
  (`AssertionError: can only join a started process`) on 26 of 37 table
  samples — the reported table TEDS number is computed from the 11 that
  didn't fail, not a clean signal.

## Status at close

The full 1651-page benchmark completed (1651/1651 pages, 0 failures) and
has been scored by the official evaluator (665 table samples, all 1651
pages matched, 0 timeouts). All accuracy numbers in `FINAL_REPORT.md` are
now drawn from the complete, real, official-evaluator-scored **full
1651-page corpus** (`results/full_baseline/metrics.json`), with the
original 77-page subset kept as an explicit comparison column — see
`FINAL_REPORT.md` §1, §1a, §11, §12 for the full recovery/completion
account (including a VM reboot that occurred between prediction
generation and scoring, verified not to have affected either).

Headline update from full-corpus scoring: the English/Chinese language
gap reproduces almost exactly (16.7x subset → 14.2x full), while table
TEDS more than tripled (0.10 → 0.32) once the subset's own `table_hard`
oversampling is accounted for — the subset's table number was a
legitimate hard-case measurement, not a representative one.
