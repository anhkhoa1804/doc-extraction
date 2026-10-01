# Experiment 041 — role signal and specialist provenance

Experiment 041 is a development-only identification study. It was designed
to separate three questions left open by Experiment 040:

1. whether `document_index` has informative same-role negative controls;
2. whether the unchanged 039 production baseline invoked the TableTransformer
   page-wide path on D2 pages; and
3. whether a role-normalization counterfactual would change routing without
   claiming table recovery.

The design was frozen from the 039 and 040 artifacts before any 041 replay or
treatment. Population construction then found zero eligible same-role
`document_index` development controls: all 15 `document_index` regions in the
039 development baseline are among the frozen D2 region identities. The
pre-registered hard stop therefore applies. No 041 specialist treatment, page
replay, held-out access, or policy tuning was performed.

## Reproduction

From the repository root, using the project CPU environment:

```bash
/home/magnusfrog_frogsleap/.venvs/doc-extraction-linux312/bin/python \
  experiments/041_role_signal_provenance/build_population.py

/home/magnusfrog_frogsleap/.venvs/doc-extraction-linux312/bin/python \
  -m pytest -q tests/test_041_design.py
```

The population builder reads only development records and their frozen 039
baseline layout artifacts. It writes an atomic manifest and exits with a
blocked status when the same-role-control gate cannot be satisfied. It must
not be changed to include the 039 held-out split or any treatment output.

## Status

`BLOCKED_BEFORE_EXECUTION_NO_SAME_ROLE_CONTROLS`

The correct next action is a separately approved corpus expansion that
provides naturally occurring development `document_index` controls, not
another treatment run on the same confounded population.
