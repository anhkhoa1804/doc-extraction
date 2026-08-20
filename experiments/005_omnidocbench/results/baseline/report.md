# OmniDocBench report — baseline

Dataset: `experiments/005_omnidocbench/dataset/demo`  
Backend: `baseline`  
Upstream evaluator commit: `193627ae9e97d89188468ed1ee3b7a856ff76044`  
Device: `cpu`  
Samples evaluated: 18 of 18 available  
Timestamp: 2026-08-20T10:19:37.993024+00:00  

## Runtime

- Total: 1049.171 s (wall clock: 1049.273 s)
- Pages: 18 succeeded, 0 failed, of 18 total
- Mean seconds/page: 58.2873
- Pages/second: 0.0172
- Routes taken: {'image': 18}

## End-to-end metrics

No aggregate "Overall" score is reported: OmniDocBench's own Overall formula `((1 - TextEditDist) * 100 + TableTEDS + FormulaCDM) / 3` requires the formula CDM metric, which needs a Linux-only toolchain (TeX Live + ImageMagick 7.x + Ghostscript — stated by the upstream project itself, not assumed here) and was not run. Reporting the per-metric numbers the evaluator actually computed, not a substitute composite.

| Category | Metric | Value |
|---|---|---|
| text_block | Edit_dist.ALL_page_avg | 0.7448 |
| text_block | Edit_dist.edit_whole | 0.7614 |
| text_block | Edit_dist.edit_sample_avg | 0.7729 |
| display_formula | Edit_dist.ALL_page_avg | 0.9960 |
| display_formula | Edit_dist.edit_whole | 0.9964 |
| display_formula | Edit_dist.edit_sample_avg | 0.9953 |
| table | TEDS.all | 0.1526 |
| table | TEDS_structure_only.all | 0.6095 |
| table | Edit_dist.ALL_page_avg | 0.7024 |
| table | Edit_dist.edit_whole | 0.6831 |
| table | Edit_dist.edit_sample_avg | 0.6958 |
| reading_order | Edit_dist.ALL_page_avg | 0.6463 |
| reading_order | Edit_dist.edit_whole | 0.7722 |
| reading_order | Edit_dist.edit_sample_avg | 0.6463 |

### Attribute breakdown

_Straight from the evaluator's own `group` output — official OmniDocBench attribute labels, not a category we invented._

#### text_block — by attribute

| attribute | Edit_dist | n |
|---|---|---|
| text_background: multi_colored | 0.9256 | 16 |
| text_background: single_colored | 0.7003 | 8 |
| text_background: white | 0.7544 | 216 |
| text_language: text_en_ch_mixed | 0.8780 | 10 |
| text_language: text_english | 0.3893 | 80 |
| text_language: text_simplified_chinese | 0.9601 | 149 |
| text_rotate: horizontal | 1.0000 | 1 |
| text_rotate: normal | 0.7646 | 238 |

#### display_formula — by attribute

| attribute | Edit_dist | n |
|---|---|---|
| formula_type: print | 0.9953 | 23 |

#### table — by attribute

| attribute | Edit_dist | TEDS | TEDS_structure_only | n |
|---|---|---|---|---|
| include_background: False | 0.7233 | 0.1218 | 0.5987 | 5 |
| include_background: True | 0.6683 | 0.1834 | 0.6202 | 5 |
| include_equation: False | 0.7014 | 0.1614 | 0.5681 | 8 |
| include_equation: True | 0.6733 | 0.1175 | 0.7748 | 2 |
| include_photo: False | 0.6958 | 0.1526 | 0.6095 | 10 |
| language: table_en | 0.7892 | 0.2708 | 0.5007 | 3 |
| language: table_simplified_chinese | 0.6558 | 0.1019 | 0.6561 | 7 |
| line: fewer_line | 0.6628 | 0.1390 | 0.7221 | 5 |
| line: full_line | 0.7470 | 0.1975 | 0.4475 | 4 |
| line: less_line | 0.6561 | 0.0408 | 0.6939 | 1 |
| table_layout: horizontal | 0.6958 | 0.1526 | 0.6095 | 10 |
| with_span: False | 0.7275 | 0.2201 | 0.5336 | 5 |
| with_span: True | 0.6641 | 0.0851 | 0.6854 | 5 |
| with_structured_text: False | 0.6958 | 0.1526 | 0.6095 | 10 |


## Error summary

Only evidence the pipeline/evaluator actually reported — no inferred causes.

- No prediction-generation failures.
