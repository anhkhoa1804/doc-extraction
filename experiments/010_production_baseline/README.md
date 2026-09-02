# 010 — Production baseline and failure taxonomy

## Question

The system has never been measured against a corpus shaped like its target
population. `research/hardcases/` is fourteen documents, every one of them
hard by construction, which makes it a good regression lock and a useless
basis for deciding what to build next.

**Where does the shipped pipeline actually fail on a realistic EN/VI
enterprise mixture, how often, and how badly?**

The point is to replace intuition with a ranked failure table (mission §5,
§6). "Which AI problem is interesting" and "which failure costs the most"
are different questions, and only the second one should direct work.

## Method

Corpus: `research/production_corpus/` — 58 synthetic documents, 125 pages,
five formats, EN and VI, `manifest.json` sha256
`d73ee35488d8284e...`. Composition is deliberately realistic: 29 ordinary
documents, 18 single-mechanism hard cases, 10 that *combine* 2–4
difficulties, 1 long document of 60 pages.

Strategy: `adaptive` — the shipped configuration, unmodified. Scoring is
identical to `research/hardcases/run_benchmark.py`: recall over
`must_contain`, NFC-normalized, with `must_not_contain` catching confident
garbage.

Every document that came out wrong contributes rows of
`(document, failure_type, severity, strategy, recovered, runtime)`.

## Reproduce

```bash
python research/production_corpus/generate.py
python research/production_corpus/run_benchmark.py --strategy adaptive
```

## Resource state

| | |
|---|---|
| Device | CPU |
| GPU | **PROTECTED** — a co-tenant held 4,208 MiB at 100% median utilization |
| CPU | loadavg 2.6 → 6.23 of 8 during the run; **CONTENDED** |

The GPU was not used and no other project's process was touched. Per §18 a
PROTECTED GPU means yield, not compete.

**Runtime figures here are upper bounds, not benchmarks.** Recall is not:
experiment 006 showed CPU and GPU outputs identical to 0.000 px, and the
quality numbers reproduced exactly across two runs whose runtimes differed by
21% (p99 23.5 s vs 33.0 s).

## Headline

| | |
|---|---|
| Mean text recall | **0.9269** |
| Fully recovered | **48 / 58** |
| Total failures (recall 0.0) | **1** |
| Hallucinations | **0** |
| Errors / crashes | **0** |
| Tables OK | 55 / 58 |
| Runtime p50 / p90 / p99 | **0.051 s / 14.196 s / 33.035 s** |

## Ranked failure classes

| Rank | Class | n | critical | high | medium |
|---|---|---|---|---|---|
| 1 | `scan_quality` | 6 | 1 | 2 | 3 |
| 2 | `stamp` / `occlusion` | 4 | 0 | 1 | 3 |
| 3 | `borderless_table` / `table_detection` | 2 | 0 | 2 | 0 |
| 4 | `table_structure` | 2 | 0 | 1 | 1 |
| 5 | `merged_cells`, `tiny_text`, `multi_column`, `reading_order` | 1 each | — | — | — |

See `observations.md` for what these mean and for the one finding that was
not in any prior record.
