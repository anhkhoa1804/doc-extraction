# OmniDocBench report — baseline

Dataset: `dataset/full`  
Backend: `baseline`  
Upstream evaluator commit: `193627ae9e97d89188468ed1ee3b7a856ff76044`  
Device: `cuda`  
Samples evaluated: 1651 of 1651 available  
Timestamp: 2026-09-08T21:37:18.742116+00:00  

## Runtime

- Total: 13665.459 s (wall clock: 13687.102 s)
- Pages: 1651 succeeded, 0 failed, of 1651 total
- Mean seconds/page: 8.2771
- Pages/second: 0.1208
- Routes taken: {'image': 1651}

## End-to-end metrics

No aggregate "Overall" score is reported: OmniDocBench's own Overall formula `((1 - TextEditDist) * 100 + TableTEDS + FormulaCDM) / 3` requires the formula CDM metric, which needs a Linux-only toolchain (TeX Live + ImageMagick 7.x + Ghostscript — stated by the upstream project itself, not assumed here) and was not run. Reporting the per-metric numbers the evaluator actually computed, not a substitute composite.

| Category | Metric | Value |
|---|---|---|
| text_block | Edit_dist.ALL_page_avg | 0.5837 |
| text_block | Edit_dist.edit_whole | 0.4410 |
| text_block | Edit_dist.edit_sample_avg | 0.6222 |
| display_formula | Edit_dist.ALL_page_avg | 0.9756 |
| display_formula | Edit_dist.edit_whole | 0.9893 |
| display_formula | Edit_dist.edit_sample_avg | 0.9733 |
| table | TEDS.all | 0.3224 |
| table | TEDS_structure_only.all | 0.5247 |
| table | Edit_dist.ALL_page_avg | 0.7018 |
| table | Edit_dist.edit_whole | 0.7196 |
| table | Edit_dist.edit_sample_avg | 0.7172 |
| reading_order | Edit_dist.ALL_page_avg | 0.5967 |
| reading_order | Edit_dist.edit_whole | 0.7192 |
| reading_order | Edit_dist.edit_sample_avg | 0.5967 |

### Attribute breakdown

_Straight from the evaluator's own `group` output — official OmniDocBench attribute labels, not a category we invented._


## Error summary

Only evidence the pipeline/evaluator actually reported — no inferred causes.

- No prediction-generation failures.
