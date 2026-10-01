# Experiment 040 — Mechanism-D development counterfactual

This is a CPU-only, development-only intervention study over the frozen 039
population. It must never write to `experiments/039_larger_real_corpus` and it
must never read or treat held-out records.

## Prepare and validate

```bash
cd /home/magnusfrog_frogsleap/projects/doc-extraction
PY=/home/magnusfrog_frogsleap/.venvs/doc-extraction-linux312/bin/python
$PY experiments/040_mechanism_d_counterfactual/build_population.py
$PY -m pytest -q tests/test_040_counterfactual.py
```

The population builder must report 28 D2 units and 766 controls. It records a
stable crop hash for every unit and fails on any source-image, baseline-artifact,
region-bbox, or split mismatch.

## Pilot

```bash
$PY experiments/040_mechanism_d_counterfactual/run_counterfactual.py --phase pilot
$PY experiments/040_mechanism_d_counterfactual/analyze_040.py --phase pilot --require-pilot
```

The pilot must pass integrity checks before the full run is started. Its
outcome must not be used to modify the frozen design.

## Full development run

```bash
$PY experiments/040_mechanism_d_counterfactual/run_counterfactual.py --phase full
$PY experiments/040_mechanism_d_counterfactual/analyze_040.py --phase full
```

The runner is resumable. Each unit writes a complete JSON record atomically;
the run index is also atomic. Operational failures remain in the denominator
and are not relabelled as scientific no-effect outcomes.

## Outputs

Tracked protocol and compact summaries:

```text
DESIGN.md
population_manifest.json
feature_manifest.json
protocol.json
results.json
failure_taxonomy.json
ANALYSIS.md
```

Raw per-unit treatment, telemetry, and run-index files under `results/` are
ignored by Git but are required for forensic replay. Held-out access is a
hard failure, not a skippable warning.
