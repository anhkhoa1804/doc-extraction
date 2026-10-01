# Diagnosis of stored 046 no-token-centre challenge cases

The v2 artifact contains five, not eight, challenge cases with no acquisition
OCR token whose **centre** falls inside the selected truth locator. All five
truth rectangles were checked against rendered image dimensions, raw OCR JSON,
and raw layout JSON. No routing or OCR setting was changed.

| Case | Explanation | Evidence | Confidence |
| --- | --- | --- | --- |
| ind-07 | evaluator geometry / annotation segmentation mismatch | One OCR `text` span and one layout region intersect truth, but the coarse span centre lies below it; text includes target plus adjacent content. | LIKELY |
| ind-10 | evaluator geometry / annotation segmentation mismatch | One OCR `section_header` span intersects title, but its centre lies below it because it also includes the date. | LIKELY |
| ind-12 | insufficient OCR coverage at truth region | Valid in-image Chinese paragraph; four OCR tokens total, with no OCR or layout intersection. | LIKELY |
| ind-15 | truth-locator coordinate/clipping mismatch | Truth box extends 1.56 pixels beyond rendered image right edge; one OCR token total and no intersection. | LIKELY |
| ind-16 | insufficient OCR coverage at truth region | Valid in-image Chinese byline; ten OCR tokens, but no OCR or layout intersection. | LIKELY |

The backend invoked OCR in every case: all have non-empty OCR result files.
For `ind-07` and `ind-10`, centre containment incorrectly labels overlapping
evidence absent. For the other three, coverage is only a likely explanation:
the artifact cannot distinguish language/model coverage, cropping, or
truth-model mismatch. No evidence shows role-dependent routing suppressed OCR.

Thus “no candidate” cannot be equated to “acquisition loss” without independent
coordinate and segmentation validation.
