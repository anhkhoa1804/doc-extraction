# 044 — truth-aware development replay results

## Status

`OBSERVABILITY SUPPORTED; QUALITY BENEFIT UNPROVEN`

This is a persisted-intermediate-artifact replay, not acquisition-time proof.
It establishes neither a production recovery nor extraction-quality gain.

## Frozen population

Protocol v2 (`247f3b5bfa61bcbdb75047913cef3fe50ee407d576673ce16e7c39196bbb2c5a`)
froze ten development-only cases (`population_sha256`
`0c5e44e0de3dc5315a907cbc08b775bc6f7de73d606518ccaf81d9eba7283582`):
eight strict-D2 difficult cases, `d2-00` … `d2-07`, and two table-gated
exact-match controls, `ctl-00`, `ctl-01`. There are eight source-page
identities: `d2-02`/`d2-03` share a page and the two controls share another.
All ten had persisted canonical/layout/OCR/table artifacts and OmniDocBench
GT HTML plus table-rectangle truth; none was excluded.

Truth requires normalized-exact equality to a nonempty GT `td`/`th` cell.
Duplicate matching requires the same normalized exact phrase at the same GT
table locator in canonical output. No fuzzy or semantic matching is used.

## Results

| case | captured / accepted / unresolved / excluded | candidates | structure | owner-valid | correct | novel | duplicate | incorrect | provenance |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---|
| d2-00 | 11 / 10 / 1 / 0 | 1 | 0 | 0 | 0 | 0 | 1 | 1 | complete |
| d2-01 | 34 / 20 / 14 / 0 | 14 | 2 | 0 | 6 | 0 | 14 | 8 | complete |
| d2-02 | 120 / 118 / 2 / 0 | 1 | 0 | 0 | 0 | 0 | 1 | 1 | complete |
| d2-03 | 120 / 118 / 2 / 0 | 1 | 0 | 0 | 0 | 0 | 1 | 1 | complete |
| d2-04 | 75 / 74 / 1 / 0 | 1 | 1 | 0 | 0 | 0 | 1 | 1 | complete |
| d2-05 | 314 / 163 / 151 / 0 | 55 | 36 | 1 | 18 | 0 | 55 | 37 | complete |
| d2-06 | 96 / 92 / 4 / 0 | 1 | 0 | 1 | 0 | 0 | 1 | 1 | complete |
| d2-07 | 120 / 88 / 32 / 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | complete |
| ctl-00 | 55 / 47 / 8 / 0 | 6 | 5 | 1 | 1 | 0 | 5 | 5 | complete |
| ctl-01 | 55 / 47 / 8 / 0 | 6 | 3 | 3 | 1 | 0 | 6 | 5 | complete |

Across 1,000 **per-case observation records**, 777 were accepted, 223
unresolved, and zero excluded. `d2-02` and `d2-03` are distinct GT table
locators on one page, so their page ledger is intentionally counted once per
case; these totals are accounting results, not an independent-observation
sample size. Of 86 OCR observations in the truth-table locators, 26 were
cell-exact correct (30.23%), **zero** were novel-correct (0.00%), 85 were
baseline duplicates (98.84%), 60 were incorrect (69.77%), and 80 had
ownership conflicts/unresolved status (93.02%). All ten case ledgers had a
complete observation provenance link. No C condition ran because B contained
no qualifying novel-correct candidate. Structural-only recovery is zero:
neither A nor B produced a new structure, and C was not invoked.

Both controls had zero novel-correct results, so the observed control
false-positive rate is 0/2. This is a very small control check, not a
precision estimate.

## Failure analysis

The central negative result is not absence of correct OCR: 26 candidates are
truth-exact. It is that those candidates were already represented in the
baseline at the same table locator, while most candidate observations also
had competing layout/cell claims. Thus the ledger explains duplicated and
ambiguous evidence but identifies no safe, genuinely new text to recover.

The immutable machine-readable result is
`runs/2026-10-01_protocol-v2_observational-v3.json`, generated at evaluator
commit `e8ec038fc585181bb368a9460c5ac7b05c8194be`.
