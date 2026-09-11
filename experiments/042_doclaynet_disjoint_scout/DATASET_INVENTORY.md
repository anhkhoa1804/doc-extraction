# 042 local dataset inventory

Inventory performed before acquisition or model execution on 042. Paths and
counts below reflect the current VM, not historical availability.

| candidate | local path / format | local size and contents | provenance and overlap | natural `document_index` suitability | 042 disposition |
| --- | --- | --- | --- | --- | --- |
| DocLayNet 1.0.0 selected 039 | `experiments/039_larger_real_corpus/results/doclaynet/PNG`, PNG; full `val.json` also present | 269 PNG pages (~92 MB); annotation metadata has 6,489 pages/160 groups | Used by 039; 038/039 groups are prior identities; 039 held-out groups are forbidden | 039 development had 15 role regions, all D2; no same-role controls | Exclude prior identities; use only unselected source groups from the full annotation for a new scout |
| DocLayNet 038 | `experiments/038_independent_real_corpus/results/doclaynet/val.json`, JSON only | 57 MB annotation member; no local image files or baseline layout tree | Used by 038; 20 source groups/149 page records | No local baseline artifacts to scout; all groups excluded | Exclude |
| OmniDocBench historical 005/034a/035/036 | manifests/results under `experiments/005_omnidocbench`, `experiments/034a_omnidocbench_snapshot`, and 035/036 | Historical manifests/results; raw dataset directories are absent; 034a manifest records 1,651 pages historically | Used by 005, 034a, 035, and 036; different dataset namespace | No current raw pages for a scout; prior identity set must not be reused | Exclude |
| Synthetic production corpus / 037 | `research/production_corpus/corpus` | Only committed manifest is present; corpus definition is 58 synthetic documents/125 pages, 037 used 15 source documents | Synthetic, prior 037 source population; not real-document evidence | Any labels would be synthetic-corpus evidence and would not answer the independent real-corpus question | Exclude |
| Synthetic hardcases | `research/hardcases/corpus`, PDF | 14 generated hard-case PDFs plus manifest (~568 KB) | Synthetic, used by earlier research; one mechanism per document | No natural production layout-role population | Exclude |
| Private local input | `data` | Only README and manifest are present; manifest describes 12 files/10 unique documents, but source files are absent | Internal/private, no current raw content or baseline artifacts | Cannot scout on this VM; would require separate authorization and privacy handling | Exclude |
| Docling/Hugging Face caches | `.cache/docling`, `.cache/huggingface` | Model/package caches, not source corpora | No document identities | Not a corpus | Exclude |

## Candidate selected for 042

The only locally reproducible path is the full DocLayNet validation annotation
metadata plus bounded acquisition of new source groups not represented in
038/039. Before acquisition, there are 107 eligible source groups and 1,409
precedence-zero pages. The frozen scout uses 40 groups and 279 pages. The
selected cohort is development-only for 042 and identity-disjoint from the
entire 039 population, including its held-out groups.

No large production baseline or TableTransformer treatment was run during
inventory.
