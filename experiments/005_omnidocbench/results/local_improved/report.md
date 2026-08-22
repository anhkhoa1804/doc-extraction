# OmniDocBench report — baseline

Dataset: `.external/OmniDocBench-data`  
Backend: `baseline`  
Upstream evaluator commit: `193627ae9e97d89188468ed1ee3b7a856ff76044`  
Device: `cpu`  
Samples evaluated: 20 of 1651 available  
Subset: 20 pages (seed=0) — **not the full benchmark**  
Timestamp: 2026-08-22T06:14:19.929596+00:00  

## Runtime

- Total: 1021.614 s (wall clock: 1021.788 s)
- Pages: 20 succeeded, 0 failed, of 20 total
- Mean seconds/page: 51.0807
- Pages/second: 0.0196
- Routes taken: {'image': 20}

## End-to-end metrics

No aggregate "Overall" score is reported: OmniDocBench's own Overall formula `((1 - TextEditDist) * 100 + TableTEDS + FormulaCDM) / 3` requires the formula CDM metric, which needs a Linux-only toolchain (TeX Live + ImageMagick 7.x + Ghostscript — stated by the upstream project itself, not assumed here) and was not run. Reporting the per-metric numbers the evaluator actually computed, not a substitute composite.

| Category | Metric | Value |
|---|---|---|
| text_block | Edit_dist.ALL_page_avg | 0.6332 |
| text_block | Edit_dist.edit_whole | 0.5638 |
| text_block | Edit_dist.edit_sample_avg | 0.4602 |
| display_formula | Edit_dist.ALL_page_avg | 0.9959 |
| display_formula | Edit_dist.edit_whole | 0.9957 |
| display_formula | Edit_dist.edit_sample_avg | 0.9966 |
| table | TEDS.all | 0.2584 |
| table | TEDS_structure_only.all | 0.3631 |
| table | Edit_dist.ALL_page_avg | 0.7438 |
| table | Edit_dist.edit_whole | 0.6697 |
| table | Edit_dist.edit_sample_avg | 0.7438 |
| reading_order | Edit_dist.ALL_page_avg | 0.5301 |
| reading_order | Edit_dist.edit_whole | 0.5974 |
| reading_order | Edit_dist.edit_sample_avg | 0.5301 |

### Attribute breakdown

_Straight from the evaluator's own `group` output — official OmniDocBench attribute labels, not a category we invented._


## Error summary

Only evidence the pipeline/evaluator actually reported — no inferred causes.

- No prediction-generation failures.
