# 039 candidate corpus audit

This audit was written before the 039 baseline.  Dataset facts below are
source-reported or local preflight facts; no 039 production outcome was used
to select individual pages.

| Candidate | Version / license | Real/full-page/GT/grouping | Non-table context and scale | D2 relevance | Decision and limitation |
|---|---|---|---|---|---|
| **DocLayNet** | 1.0.0; CDLA-Permissive-1.0 for the dataset | Human-annotated real documents; full-page 1025x1025 PNGs and matching single-page PDFs; COCO table boxes; explicit `collection`, `doc_name`, `page_no` | Six document categories and 11 layout labels; official source reports 80,863 pages. Local validation preflight: 6,489 pages, 1,478 table pages, 2,269 precedence-zero table annotations, 53 groups with at least 3 table pages; 33 groups remain after 038 group exclusion | 038 empirically produced natural D2, but its development cases were concentrated in 2 groups and 1 raw label. 039 tests the disjoint, category-stratified remainder | **Selected.** Best joint fit for full-page context, independent table boxes, non-table regions, grouping, and family diversity. Limitation: it is identity-independent from 038 but comes from the same dataset release, so this is not a dataset-level replication. |
| **PubLayNet** | Public release; annotations CDLA-Permissive-1.0; images subject to PMC Open Access Subset terms | Real PubMed Central articles; page images/PDFs available; COCO-style layout annotations; source grouping is less explicit than DocLayNet and primarily scientific | Five layout classes including table, text, title, list, figure; source is one scientific article family and annotations are automatically generated from PDF/XML; official release is over 360k pages | Natural D2 not measured here; one-family and automated-label limitations make role/family adequacy uncertain | **Rejected for 039 headline corpus.** It lacks the document-family breadth needed to repair 038's concentration and has more complicated image-rights provenance. |
| **PubTables-1M** | Versioned public release; access through Microsoft Research Open Data/Hugging Face; exact redistribution terms require separate audit | Real PubMed source PDFs; 575,305 page images in the detection archive and PDF-level annotations; source-PDF grouping is possible | Detection population is pages containing tables, so a clean table-free control population is not supplied; one scientific source family. It has 947,642 fully annotated tables and rich structure labels | Strong table GT, but its page-selection design is table-positive and not naturally suited to selectivity/control estimation | **Rejected.** Excellent table structure resource, insufficient as the sole full-context/control corpus for this study. |
| **TableBank** | Official repository states Apache-2.0 but also research-only and no-redistribution restrictions | Real Word/LaTeX-source documents with markup-derived weak supervision; page/document identity and full-page control provenance are not sufficiently stable in the public benchmark packaging | 417,234 labeled tables and 278,582 detection images; table-focused distribution; weakly supervised rather than independent human layout annotation | D2-like label failure cannot be cleanly separated from markup-derived table labels and uncertain page/control identity | **Rejected.** License/use statements conflict operationally, and the released benchmark does not provide the required auditable corpus identity/control contract. |
| **FinTabNet / FinTabNet.c** | FinTabNet.c 2023; CDLA-Permissive-2.0 for the published fork | Real financial-report material with PDF/HTML alignment, but public task packaging is table/structure-focused rather than a stable full-page layout corpus | One financial family; table images/structure annotations are strong, but non-table full-page controls and broad layout labels are not provided as a comparable corpus | Could study financial-table structure, not broad region-role D2 selectivity | **Rejected.** Domain, context, and role diversity are too narrow for the 039 question. |

## Sources

- DocLayNet official repository: https://github.com/DS4SD/DocLayNet
- PubLayNet official repository: https://github.com/ibm-aur-nlp/PubLayNet
- Table Transformer / PubTables-1M official repository: https://github.com/microsoft/table-transformer
- TableBank official repository: https://github.com/doc-analysis/TableBank
- FinTabNet.c dataset card: https://huggingface.co/datasets/bsmock/FinTabNet.c

## Local preflight and selection rule

The local DocLayNet validation annotation member already retained by 038 was
used only to enumerate eligible source groups and page identities.  The
remaining 33 eligible groups cover all six DocLayNet categories.  The 039
manifest selects all remaining eligible groups, assigns development/held-out
within category by the preregistered hash, then chooses pages by stable image
ID hashes.  It does not inspect production layout labels or outcomes.
