# Experiment 039 preregistration

**Status:** frozen before 039 baseline extraction and before any 039 D2
activation outcome is observed.

## Aim

Determine whether a larger independent real-document population has adequate
natural strict-D2 activation and diversity for a selective-policy study.

The result can be blocked.  039 does not assume that a selective policy will
work and does not optimize the population for positive activation.

## Frozen corpus

The selected source is DocLayNet validation 1.0.0, acquired from the official
core archive using the algorithm in `acquire_doclaynet.py`.  The corpus is
limited to source-document groups and page identities not present in 038; the
cross-experiment audit also records comparisons to 035, 036, and 037.  The
manifest, annotation-member hash, page hashes, group keys, and split are
immutable inputs to the baseline.

## Frozen D2 and analysis boundary

The D2 outcome is the 035-compatible strict definition in
`CORPUS_PROTOCOL.md`.  Baseline extraction does not read GT boxes or D2
labels.  Matching, activation counts, and adequacy assessment occur only
after the unchanged baseline has completed.

The following are prohibited as extraction or future selector inputs:

- GT geometry or table identity;
- forced-crop detector or structure outcome;
- post-treatment ownership or conflict outcome;
- any held-out outcome;
- synthetic relabelling or annotation manipulation.

## Frozen adequacy criterion

Development must have at least 12 strict-D2 table cases from at least 6
source-document groups, at least 3 raw region labels, at least 4 document
categories, and no group may supply more than 50% of development D2 cases.
The rationale and terminal statuses are fixed in `CORPUS_PROTOCOL.md`.

Only if all conditions pass may a later preregistration define a simple
development-only policy comparison.  A learned policy is not presumed valid.
The held-out groups remain untouched until a policy, feature contract,
ownership resolver, cost summary, and one-shot evaluation plan are separately
frozen.
