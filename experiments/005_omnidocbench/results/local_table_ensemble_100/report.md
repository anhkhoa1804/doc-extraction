# OmniDocBench report — baseline

Dataset: `.external/OmniDocBench-data`  
Backend: `baseline`  
Upstream evaluator commit: `193627ae9e97d89188468ed1ee3b7a856ff76044`  
Device: `cpu`  
Samples evaluated: 100 of 1651 available  
Subset: 100 pages (seed=0) — **not the full benchmark**  
Timestamp: 2026-08-22T10:15:44.403741+00:00  

## Runtime

- Total: 6956.835 s (wall clock: 6959.212 s)
- Pages: 100 succeeded, 0 failed, of 100 total
- Mean seconds/page: 69.5683
- Pages/second: 0.0144
- Routes taken: {'image': 100}

## End-to-end metrics

No aggregate "Overall" score is reported: OmniDocBench's own Overall formula `((1 - TextEditDist) * 100 + TableTEDS + FormulaCDM) / 3` requires the formula CDM metric, which needs a Linux-only toolchain (TeX Live + ImageMagick 7.x + Ghostscript — stated by the upstream project itself, not assumed here) and was not run. Reporting the per-metric numbers the evaluator actually computed, not a substitute composite.

| Category | Metric | Value |
|---|---|---|
| text_block | Edit_dist.ALL_page_avg | 0.4869 |
| text_block | Edit_dist.edit_whole | 0.4228 |
| text_block | Edit_dist.edit_sample_avg | 0.4540 |
| display_formula | Edit_dist.ALL_page_avg | 0.9951 |
| display_formula | Edit_dist.edit_whole | 0.9976 |
| display_formula | Edit_dist.edit_sample_avg | 0.9944 |
| table | TEDS.all | 0.2743 |
| table | TEDS_structure_only.all | 0.3504 |
| table | Edit_dist.ALL_page_avg | 0.7177 |
| table | Edit_dist.edit_whole | 0.6389 |
| table | Edit_dist.edit_sample_avg | 0.7271 |
| reading_order | Edit_dist.ALL_page_avg | 0.4921 |
| reading_order | Edit_dist.edit_whole | 0.5927 |
| reading_order | Edit_dist.edit_sample_avg | 0.4921 |

### Attribute breakdown

_Straight from the evaluator's own `group` output — official OmniDocBench attribute labels, not a category we invented._


## Error summary

Only evidence the pipeline/evaluator actually reported — no inferred causes.

- No prediction-generation failures.
