# OmniDocBench report — baseline

Dataset: `.external/OmniDocBench-data`  
Backend: `baseline`  
Upstream evaluator commit: `193627ae9e97d89188468ed1ee3b7a856ff76044`  
Device: `cpu`  
Samples evaluated: 100 of 1651 available  
Subset: 100 pages (seed=0) — **not the full benchmark**  
Timestamp: 2026-08-24T02:19:30.142544+00:00  

## Runtime

- Total: 33798.375 s (wall clock: 33802.022 s)
- Pages: 100 succeeded, 0 failed, of 100 total
- Mean seconds/page: 337.9838
- Pages/second: 0.003
- Routes taken: {'image': 100}

## End-to-end metrics

No aggregate "Overall" score is reported: OmniDocBench's own Overall formula `((1 - TextEditDist) * 100 + TableTEDS + FormulaCDM) / 3` requires the formula CDM metric, which needs a Linux-only toolchain (TeX Live + ImageMagick 7.x + Ghostscript — stated by the upstream project itself, not assumed here) and was not run. Reporting the per-metric numbers the evaluator actually computed, not a substitute composite.

| Category | Metric | Value |
|---|---|---|
| text_block | Edit_dist.ALL_page_avg | 0.4870 |
| text_block | Edit_dist.edit_whole | 0.4228 |
| text_block | Edit_dist.edit_sample_avg | 0.4542 |
| display_formula | Edit_dist.ALL_page_avg | 0.9951 |
| display_formula | Edit_dist.edit_whole | 0.9976 |
| display_formula | Edit_dist.edit_sample_avg | 0.9944 |
| table | TEDS.all | 0.4514 |
| table | TEDS_structure_only.all | 0.5734 |
| table | Edit_dist.ALL_page_avg | 0.6792 |
| table | Edit_dist.edit_whole | 0.6348 |
| table | Edit_dist.edit_sample_avg | 0.6899 |
| reading_order | Edit_dist.ALL_page_avg | 0.4912 |
| reading_order | Edit_dist.edit_whole | 0.5911 |
| reading_order | Edit_dist.edit_sample_avg | 0.4912 |

### Attribute breakdown

_Straight from the evaluator's own `group` output — official OmniDocBench attribute labels, not a category we invented._


## Error summary

Only evidence the pipeline/evaluator actually reported — no inferred causes.

- No prediction-generation failures.
