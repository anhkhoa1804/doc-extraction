# OmniDocBench report — docling

Dataset: `experiments/005_omnidocbench/dataset/demo`  
Backend: `docling`  
Upstream evaluator commit: `193627ae9e97d89188468ed1ee3b7a856ff76044`  
Device: `cpu`  
Samples evaluated: 18 of 18 available  
Timestamp: 2026-08-20T10:34:03.980044+00:00  

## Runtime

- Total: 829.351 s (wall clock: 829.886 s)
- Pages: 18 succeeded, 0 failed, of 18 total
- Mean seconds/page: 46.075
- Pages/second: 0.0217
- Routes taken: {'image': 18}

## End-to-end metrics

No aggregate "Overall" score is reported: OmniDocBench's own Overall formula `((1 - TextEditDist) * 100 + TableTEDS + FormulaCDM) / 3` requires the formula CDM metric, which needs a Linux-only toolchain (TeX Live + ImageMagick 7.x + Ghostscript — stated by the upstream project itself, not assumed here) and was not run. Reporting the per-metric numbers the evaluator actually computed, not a substitute composite.

| Category | Metric | Value |
|---|---|---|
| text_block | Edit_dist.ALL_page_avg | 0.7510 |
| text_block | Edit_dist.edit_whole | 0.7687 |
| text_block | Edit_dist.edit_sample_avg | 0.7777 |
| display_formula | Edit_dist.ALL_page_avg | 0.9960 |
| display_formula | Edit_dist.edit_whole | 0.9964 |
| display_formula | Edit_dist.edit_sample_avg | 0.9953 |
| table | TEDS.all | 0.4562 |
| table | TEDS_structure_only.all | 0.6112 |
| table | Edit_dist.ALL_page_avg | 0.6831 |
| table | Edit_dist.edit_whole | 0.6437 |
| table | Edit_dist.edit_sample_avg | 0.6758 |
| reading_order | Edit_dist.ALL_page_avg | 0.6512 |
| reading_order | Edit_dist.edit_whole | 0.7402 |
| reading_order | Edit_dist.edit_sample_avg | 0.6512 |

### Attribute breakdown

_Straight from the evaluator's own `group` output — official OmniDocBench attribute labels, not a category we invented._

#### text_block — by attribute

| attribute | Edit_dist | n |
|---|---|---|
| text_background: multi_colored | 0.9256 | 16 |
| text_background: single_colored | 0.7009 | 8 |
| text_background: white | 0.7596 | 216 |
| text_language: text_en_ch_mixed | 0.8793 | 10 |
| text_language: text_english | 0.4043 | 80 |
| text_language: text_simplified_chinese | 0.9595 | 149 |
| text_rotate: horizontal | 1.0000 | 1 |
| text_rotate: normal | 0.7694 | 238 |

#### display_formula — by attribute

| attribute | Edit_dist | n |
|---|---|---|
| formula_type: print | 0.9953 | 23 |

#### table — by attribute

| attribute | Edit_dist | TEDS | TEDS_structure_only | n |
|---|---|---|---|---|
| include_background: False | 0.6124 | 0.4977 | 0.7764 | 5 |
| include_background: True | 0.7392 | 0.4147 | 0.4461 | 5 |
| include_equation: False | 0.6892 | 0.4176 | 0.5366 | 8 |
| include_equation: True | 0.6219 | 0.6108 | 0.9097 | 2 |
| include_photo: False | 0.6758 | 0.4562 | 0.6112 | 10 |
| language: table_en | 0.6509 | 0.4253 | 0.6905 | 3 |
| language: table_simplified_chinese | 0.6865 | 0.4694 | 0.5772 | 7 |
| line: fewer_line | 0.6622 | 0.5064 | 0.6560 | 5 |
| line: full_line | 0.7124 | 0.3629 | 0.5040 | 4 |
| line: less_line | 0.5972 | 0.5784 | 0.8163 | 1 |
| table_layout: horizontal | 0.6758 | 0.4562 | 0.6112 | 10 |
| with_span: False | 0.7102 | 0.3670 | 0.5032 | 5 |
| with_span: True | 0.6414 | 0.5454 | 0.7192 | 5 |
| with_structured_text: False | 0.6758 | 0.4562 | 0.6112 | 10 |


## Error summary

Only evidence the pipeline/evaluator actually reported — no inferred causes.

- No prediction-generation failures.
