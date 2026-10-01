# Experiment 042 design

## Objective

Build an independent, development-only source-document population containing
natural `document_index` regions, then measure whether that role remains
associated with D2-like ownership failures and what unchanged production
specialist invocation occurred. Role normalization is a separate routing-only
counterfactual. No 042 treatment is authorized by this design.

The three questions are kept separate:

```text
A: does an independent natural same-role population exist?
B: does document_index remain enriched for D2-like failures?
C: what baseline specialist mode actually ran, and would offline role
   normalization change the gate?
```

## Frozen provenance

The design is frozen at parent commit
`3d92570793b01aaecf62fcbfc5d2352c5bbcd830`, branch
`fix/table-text-ownership`, origin
`git@github.com:anhkhoa1804/doc-extraction.git`.

Source metadata is the local DocLayNet validation annotation member at
`experiments/039_larger_real_corpus/results/doclaynet/val.json`. Its expected
SHA-256 is
`eacd2ba2a32e6c2ebe2dc5ea1545f405d8461c46bba53e0c35d9c54fba0bcef6`.
The 039 population manifest is
`55fe36b5f39e1e87437f81ed2cc2d120e5c7d747b1f3109318b06d530b50f8e5`.

## Corpus inventory result

The inventory is recorded in `DATASET_INVENTORY.md`. Local raw candidates are
not suitable independent sources: the 039 DocLayNet PNGs are already used;
038 has annotation metadata but no raw pages; OmniDocBench raw pages are
absent and its identities were used by 035/036; 037 and the production
corpus are synthetic; hardcases are synthetic; and the private `data/` source
files are absent from this VM. Therefore 042 uses new DocLayNet source
groups, not any prior page or document group.

## Scout population

The full local validation metadata has 6,489 precedence-zero page records in
160 source groups. All source groups represented in 038 or 039 are excluded,
including the complete 039 held-out partition. This leaves 107 source groups
and 1,409 pages. A frozen scout cohort is selected as follows:

1. construct the source group key `(doc_category, collection, doc_name)`;
2. exclude every `collection::doc_name` represented in 038 or 039;
3. rank remaining groups by `SHA256("042-group-v1::" + joined group key)`;
4. take the first 40 groups;
5. within each selected group rank all pages by
   `SHA256("042-page-v1::" + image_id)` and take at most 10.

This selects 279 pages across 40 source groups. It uses no table annotation,
GT bbox, D2 result, treatment result, or role result. All selected records are
`split == development` for 042; no 042 held-out partition is created or
accessed in this scout checkpoint.

## Identity and leakage rules

The primary identity is source group plus source image `image_id`,
`file_name`, and downloaded content SHA-256. Source group is
`collection::doc_name`, with category retained as an independent provenance
field. A filename-only match is never sufficient.

042 rejects any candidate with a source-group or image identity represented in
038/039. 040 and 041 are subsets of 039 and are therefore excluded by the
same rule. OmniDocBench/035/036 and synthetic 037 use distinct dataset
namespaces; downloaded 042 image hashes are still audited against available
prior hashes after acquisition. Unresolved identity similarity is exclusionary.

## Natural control definition

After baseline scouting, every naturally emitted `document_index` region is
retained as a candidate record before any treatment. The candidate record
stores baseline layout/OCR features and source identity. D2-like status is a
post-baseline analytical annotation only; it is never used to choose the page
or region for the scout cohort. A control is a candidate role region that is
not a frozen D2 identity, with this distinction recorded explicitly rather
than silently removing records.

The control target is at least 30 natural regions, preferably 50, from at least
five source groups and at least three categories where naturally available.
No synthetic relabeling, source-group page splitting, or treatment-outcome
selection is allowed. If fewer than 30 exist, status is
`BLOCKED_NO_ADEQUATE_DOCUMENT_INDEX_CONTROL_POPULATION`; if group/category
independence fails, status is `BLOCKED_INSUFFICIENT_INDEPENDENCE`.

## Baseline provenance

Only after scout acquisition and population freeze, replay the selected
development pages through the unchanged baseline with validated telemetry.
Record `PAGE_WIDE`, `LABELLED_CROP`, and `NOT_INVOKED` separately, including
specialist calls, detector/structure output, ownership, final table output,
warnings, and timings. A page-wide call is not correct ownership.

The 039 D2-page provenance sample is a separate deterministic development
stratum. No 039 held-out page is replayed.

## Role-normalization module

After provenance, run only an offline routing counterfactual. The frozen
hypothesis is `document_index -> table`; `text`, `picture`, `code`, and
`list_item` remain unchanged. No specialist or GT is accessible to this
module. Report routing changed/unchanged/errors separately from any future
table recovery.

## Treatment boundary

042 does not run 040's crop treatment. If the new corpus satisfies all gates,
the result is a treatment-ready checkpoint for a later experiment. Any future
treatment must use exact baseline region bboxes, the 040 structural and
ownership definitions, isolated outputs, explicit controls, and a separately
frozen protocol.
