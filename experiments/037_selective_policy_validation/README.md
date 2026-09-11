# Experiment 037 — selective Mechanism-D policy validation

This directory contains an **independent synthetic-corpus validation
protocol**, downstream of frozen Experiments 035 and 036.  It is deliberately
separate from production code and from the 036 treatment/control identities.

The source corpus is `research/production_corpus/corpus`, generated
deterministically by `research/production_corpus/generate.py`.  Its source
documents are not OmniDocBench pages and none occurs in 035 or 036.

Raw renders, production baseline runs, and counterfactual predictions belong
under `results/` and are intentionally ignored.  Compact manifests and source
code are tracked here.
