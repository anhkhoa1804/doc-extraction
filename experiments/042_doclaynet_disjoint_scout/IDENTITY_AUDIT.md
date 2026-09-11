# 042 identity and leakage audit

## Prior identity sets

| source | identity material available locally | use in 042 |
| --- | --- | --- |
| 035 | 150 OmniDocBench image names in the identity ledger; historical source images absent | distinct dataset namespace; compare names/hashes when 042 pages are acquired |
| 036 | 34 treatment cases and 145 controls derived from 035; source image/document hashes in its manifest | distinct dataset namespace; no 042 page is selected from it |
| 037 | 15 synthetic source-document groups and source PDF/rendered hashes | distinct synthetic namespace; excluded from real-corpus selection |
| 038 | 20 DocLayNet source groups, 149 image identities, annotation hash `eacd2ba...0bcef6` | all groups and image IDs excluded |
| 039 | 33 DocLayNet source groups, 269 image identities; all 039 split values, including 133 held-out records, are identity exclusions only | all groups and image IDs excluded |
| 040 | 794 region units over the 039 pages | subset excluded transitively by 039 group/image exclusion |
| 041 | 15 039 `document_index` candidates, all frozen D2 identities | subset excluded transitively by 039 group/image exclusion |

## Candidate-space audit

The local full DocLayNet validation metadata contains 160 source groups and
6,489 precedence-zero page records. The union of 038 and 039 source groups
contains 53 groups. After excluding that union, 107 groups and 1,409 pages
remain. The 042 scout chooses 40 groups and 279 pages from that remaining
space using stable hashes; no table annotations are consulted for selection.

Because all 039 groups are excluded, the 042 scout has zero source-group
overlap with the complete 039 population and therefore zero overlap with the
039 held-out partition. 040 and 041 cannot add a new overlap because their
source identities are subsets of 039.

The downloaded-page audit must additionally compare content SHA-256 values
against all available prior image-hash sets. Any exact hash collision or
unresolved source-document similarity is a hard stop and the page is not
admitted.

## Held-out boundary

The 039 held-out identity set is used only as an exclusion set via its source
group/image identity. No held-out layout, OCR, D2 outcome, treatment output,
or provenance is read for discovery or selection. The 042 pipeline must keep
`heldout_accessed = false`.
