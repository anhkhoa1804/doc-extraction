# 042 baseline provenance

This artifact records the first deterministic observational baseline replay.
It is not treatment, role normalization, selector development, or a D2
analysis. The production pipeline was run unchanged with additive telemetry;
raw telemetry and final outputs are kept under the ignored results tree.

## Frozen initial sample

The initial sample was exactly one page per each of 40 selected 042 source
groups, selected by the preregistered
`042-provenance-page-v1::<image_id>` hash. It completed 40/40 with zero
operational failures after applying the pre-existing CPU VM user-space
`libGL.so.1` workaround via `LD_LIBRARY_PATH`. No package was installed and
no `.deb` was added to the experiment.

| page-level mode | pages |
| --- | ---: |
| `PAGE_WIDE` | 34 |
| `LABELLED_CROP` | 6 |
| `BOTH` | 0 |
| `NONE` | 0 |

The sample generated 14 table objects and 443 table cells. It contained no
natural `document_index` region: 0 regions / 0 pages / 0 source groups. This
does not establish absence in the remaining 239 frozen pages; the sample is
one page per group and was designed to test provenance first.

The compact machine-readable result is `BASELINE_PROVENANCE_SAMPLE.json`.
The full-cohort replay remains separately gated and is not represented by
zero-filled fields here. `heldout_accessed = false` and
`treatment_executed = false`.
