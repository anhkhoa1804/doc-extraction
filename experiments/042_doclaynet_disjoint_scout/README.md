# Experiment 042 — independent `document_index` control discovery

042 is a development-only corpus-discovery and provenance experiment. Its
primary goal is to find naturally emitted `document_index` regions in source
document groups that are disjoint from every 038/039 identity, including the
039 held-out groups. It does not start TableTransformer treatment.

The local inventory found no suitable raw independent corpus. The frozen 039
DocLayNet annotation member does contain the complete validation metadata, so
042 uses only groups not present in 038 or 039 and acquires a deterministic
scout cohort from the official archive. The cohort contains 40 new source
groups and up to 10 deterministic pages per group. Page selection does not
inspect table annotations.

## Reproduction order

```bash
/home/magnusfrog_frogsleap/.venvs/doc-extraction-linux312/bin/python \
  experiments/042_doclaynet_disjoint_scout/build_scout_manifest.py

/home/magnusfrog_frogsleap/.venvs/doc-extraction-linux312/bin/python \
  -m pytest -q tests/test_042_design.py

/home/magnusfrog_frogsleap/.venvs/doc-extraction-linux312/bin/python \
  experiments/042_doclaynet_disjoint_scout/acquire_scout.py
```

The acquisition script downloads only the frozen scout pages by bounded HTTP
ranges and never retains the 30 GB source archive. A later baseline scout may
use `configs/cpu.yaml` and the validated additive telemetry, but treatment is
forbidden until natural controls, source independence, and all design gates
are frozen.

## Current checkpoint

`CONTROL_SUPPLY_INADEQUATE_BUT_INFORMATIVE`

All 279 source pages are acquired and pass the independent integrity audit.
The annotation-only scout found no exact source `document_index` category;
this does not observe the production role vocabulary. An unchanged baseline
replay is justified to observe natural roles and invocation provenance. No
039-held-out page is in the scout cohort, and no treatment or policy tuning is
permitted.
