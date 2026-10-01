# Module A control-population audit

## Frozen rule

A candidate is a same-role development control only when all of these are
true:

1. the 039 manifest record has `split == "development"`;
2. the frozen 039 baseline layout region has raw role `document_index`;
3. `(image_id, region_index)` is not one of the frozen 039 strict-D2 region
   identities;
4. selection does not inspect 040 treatment output or use GT geometry to rank
   candidates.

The exclusion in item 3 is an identity exclusion required by the frozen
control definition, not a post-treatment outcome filter.

## Audit result

The development baseline has 136 pages, 17 source-document groups, and six
categories. It contains 15 `document_index` regions. Every one is a frozen D2
region identity:

| image | region | source group | category | page | status |
| ---: | ---: | --- | --- | ---: | --- |
| 453 | 2 | `ann_reports_00_04_fancy::NYSE_ACN_2001.pdf` | financial_reports | 18 | excluded, D2 identity |
| 474 | 2 | `ann_reports_00_04_fancy::OTC_STKAF_2002.pdf` | financial_reports | 42 | excluded, D2 identity |
| 717 | 5 | `ann_reports_00_04_fancy::NYSE_ACN_2001.pdf` | financial_reports | 3 | excluded, D2 identity |
| 1772 | 0 | `arxiv_doublespaced::1201.4397.pdf` | scientific_articles | 8 | excluded, D2 identity |
| 1782 | 0 | `arxiv_doublespaced::1201.4397.pdf` | scientific_articles | 7 | excluded, D2 identity |
| 1890 | 1 | `arxiv_doublespaced::1201.4397.pdf` | scientific_articles | 9 | excluded, D2 identity |
| 2036 | 1 | `arxiv_doublespaced::1201.4397.pdf` | scientific_articles | 10 | excluded, D2 identity |
| 3196 | 5 | `eu_tenders::EN-Lot1 Vol2 d4 particularconditions en.pdf` | government_tenders | 0 | excluded, D2 identity |
| 3197 | 1 | `eu_tenders::EN-Lot1 Vol2 d4 particularconditions en.pdf` | government_tenders | 1 | excluded, D2 identity |
| 3664 | 0 | `faa_regulations::amt_general_handbook.pdf` | laws_and_regulations | 10 | excluded, D2 identity |
| 3741 | 1 | `faa_regulations::amt_general_handbook.pdf` | laws_and_regulations | 8 | excluded, D2 identity |
| 3741 | 2 | `faa_regulations::amt_general_handbook.pdf` | laws_and_regulations | 8 | excluded, D2 identity |
| 4872 | 0 | `manuals::perl-all-en-5.8.5.pdf` | manuals | 1673 | excluded, D2 identity |
| 5771 | 0 | `manuals::perl-all-en-5.8.5.pdf` | manuals | 1704 | excluded, D2 identity |
| 6436 | 17 | `patents_superacid_pags::20130303482_AdobeOCR.pdf` | patents | 0 | excluded, D2 identity |

Therefore:

```text
candidate document_index regions = 15
excluded frozen D2 identities = 15
eligible same-role controls = 0
target controls = >= 30 naturally occurring, if available
```

The 040 control population also contains zero `document_index` regions. No
held-out record was used to fill the gap. No treatment was run.

## Scientific implication

`2/15` recovery in 040 remains a descriptive D2-arm result. The same-role
false-positive estimand is not identifiable from the current development
corpus. The correct result is a blocked refinement, not a zero-FP claim.
