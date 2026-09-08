# OmniDocBench report — baseline

Dataset: `experiments/034a_omnidocbench_snapshot/dataset/smoke`  
Backend: `baseline`  
Upstream evaluator commit: `193627ae9e97d89188468ed1ee3b7a856ff76044`  
Device: `cuda`  
Samples evaluated: 6 of 6 available  
Timestamp: 2026-09-08T16:51:52.750911+00:00  

## Runtime

- Total: 58.028 s (wall clock: 58.063 s)
- Pages: 6 succeeded, 0 failed, of 6 total
- Mean seconds/page: 9.6713
- Pages/second: 0.1034
- Routes taken: {'image': 6}

## End-to-end metrics

No aggregate "Overall" score is reported: OmniDocBench's own Overall formula `((1 - TextEditDist) * 100 + TableTEDS + FormulaCDM) / 3` requires the formula CDM metric, which needs a Linux-only toolchain (TeX Live + ImageMagick 7.x + Ghostscript — stated by the upstream project itself, not assumed here) and was not run. Reporting the per-metric numbers the evaluator actually computed, not a substitute composite.

| Category | Metric | Value |
|---|---|---|
| text_block | Edit_dist.ALL_page_avg | 0.5322 |
| text_block | Edit_dist.edit_whole | 0.4666 |
| text_block | Edit_dist.edit_sample_avg | 0.8365 |
| display_formula | Edit_dist.ALL_page_avg | 1.0000 |
| display_formula | Edit_dist.edit_whole | 1.0000 |
| display_formula | Edit_dist.edit_sample_avg | 1.0000 |
| table | TEDS.all | 0.6438 |
| table | TEDS_structure_only.all | 0.6667 |
| table | Edit_dist.ALL_page_avg | 0.6909 |
| table | Edit_dist.edit_whole | 0.7343 |
| table | Edit_dist.edit_sample_avg | 0.6451 |
| reading_order | Edit_dist.ALL_page_avg | 0.5083 |
| reading_order | Edit_dist.edit_whole | 0.2206 |
| reading_order | Edit_dist.edit_sample_avg | 0.5083 |

### Attribute breakdown

_Straight from the evaluator's own `group` output — official OmniDocBench attribute labels, not a category we invented._


## Error summary

Only evidence the pipeline/evaluator actually reported — no inferred causes.

- No prediction-generation failures.
