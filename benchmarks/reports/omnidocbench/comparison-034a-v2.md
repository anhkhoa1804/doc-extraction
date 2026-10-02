# Historical 034a vs Representative-v2

## Comparison boundary

The stored historical 034a full run covered 1,651 pages. Comparing those aggregate values directly to representative-v2's 180 pages would mix populations, so no full-vs-subset delta is reported.

For a same-population descriptive comparison, the 1,651 stored 034a Markdown predictions were subset to the exact frozen representative-v2 sample IDs and evaluated again against the exact v2 ground-truth subset. Both v2 runs use OmniDocBench evaluator commit `193627ae9e97d89188468ed1ee3b7a856ff76044`, `quick_match`, one page-match worker, one TEDS worker, and identical page denominators. Both had 180/180 exact matches, zero match fallbacks/timeouts, and zero TEDS evaluator errors/timeouts over 64 table instances.

The selected manifest identity is `899191e7471ae5c826a6a07ff7edf3c7c8facec72764196ef9f3f49a8265a93b`; annotation identity is the same snapshot SHA recorded in `historical-034a.json` and `representative-v2.json`. There are no missing/unexpected historical predictions in the paired subset.

## Paired v2 results

Delta is `current-v2 minus historical-034a predictions on v2`; for normalized edit distance lower is better, while TEDS higher is better.

| Metric | Historical 034a on v2 | Current representative-v2 | N | Delta | Direction |
| --- | ---: | ---: | ---: | ---: | --- |
| Text block Edit distance | 0.5737038750 | 0.5739880899 | 168 pages | +0.0002842149 | lower |
| Table Edit distance | 0.7134206960 | 0.7125178639 | 50 pages | -0.0009028321 | lower |
| Table TEDS page average | 0.4121830233 | 0.4138769497 | 50 pages | +0.0016939264 | higher |
| Table structure-only TEDS page average | 0.6691942641 | 0.6731710442 | 50 pages | +0.0039767801 | higher |
| Reading-order Edit distance | 0.5859472934 | 0.5849918953 | 178 pages | -0.0009553980 | lower |
| Display-formula Edit distance | 0.9846542994 | 0.9853894477 | 35 pages | +0.0007351483 | lower |

These small deltas are numerical comparisons of predictions on the same samples under the same evaluator, not evidence of a controlled improvement or regression. The historical extraction Git revision and config-file hash are absent. Historical model/backend versions mostly match, but Torch differs (`2.11.0+cu128` historical versus `2.14.0+cu130` current), and device/runtime environments differ. TEDS per-table files in both paired runs contain three scores below zero; the same pinned implementation produced those values, which remain a metric interpretation caveat.

## Full historical reference (separate population)

| Metric | 034a full value | N | Aggregation | Caveat |
| --- | ---: | ---: | --- | --- |
| Text block Edit distance | 0.5836654200 | 1,557 pages | `ALL_page_avg` | extraction revision/config hash unknown |
| Table Edit distance | 0.7017997645 | 458 pages | `ALL_page_avg` | extraction revision/config hash unknown |
| Table TEDS page average | 0.3526450950 | 458 pages | page average | 94/665 table instances errored and were scored zero |
| Table structure-only TEDS page average | 0.5647383253 | 458 pages | page average | 94/665 table instances errored and were scored zero |
| Reading-order Edit distance | 0.5966756386 | 1,638 pages | `ALL_page_avg` | extraction revision/config hash unknown |
| Display-formula Edit distance | 0.9755954914 | 313 pages | `ALL_page_avg` | extraction revision/config hash unknown |

These full-population numbers are reproducible as historical recorded metrics, but they are **NOT DIRECTLY COMPARABLE** to current representative-v2 because the population, failures, and extraction identity differ. No deltas are computed against them.

## Interpretation

The paired subset shows very small metric differences between the archived 034a predictions and current predictions. The current system is not shown to have broadly improved or regressed by this comparison. A same-manifest current rerun is the appropriate engineering regression reference going forward; the historical full run remains a separate archive reference.
