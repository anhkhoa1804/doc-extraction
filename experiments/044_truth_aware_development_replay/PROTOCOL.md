# 044 — truth-aware development replay, protocol v1

## Question

In frozen real difficult cases, do preserved OCR observations contain correct
text that the baseline canonical representation does not already expose?

## Population and split

The development-only population is `d2-00` through `d2-07`, the first eight
entries of 036's already-frozen strict-D2 treatment manifest. They are not
re-ranked by outcome. Each has persisted canonical, layout, OCR, table, and
OmniDocBench GT HTML/geometry artifacts. No held-out data is read.

## Truth and matching

Truth is the OmniDocBench GT table HTML associated by `(image, anno_id)`, with
the annotation's rectangle as its page locator. HTML cell strings and
candidate OCR strings use `normalize_text`: trim, collapse all whitespace to
one ASCII space, then Unicode case-fold. A candidate is **correct** only if
its normalized text exactly equals a nonempty GT `td`/`th` cell string. This
is intentionally stricter than substring, fuzzy, semantic, or visual-plausibility matching.

Baseline duplication is the same normalized-exact string already present in a
baseline canonical element or cell whose center lies in the same GT table
rectangle. A candidate is **novel** only when correct, text-bearing,
ownership-valid, provenance-complete, and not baseline-duplicate.

## Other definitions

- **Ownership-valid:** exactly one ledger ownership claim, or an accepted
  recovered orphan reference; multiple claims are unresolved.
- **Structural-valid:** a nonempty canonical table cell with a derivation
  chain. OCR-only candidates are structurally unclaimed, not structurally
  valid.
- **Structural-only:** a derived table cell exists but has no text-bearing,
  correct, novel candidate. It is not a quality gain.
- **Truth-unresolved:** candidate cannot be compared to a GT cell under the
  exact rule. It is never counted correct.
- **C condition:** only run if at least one B candidate is novel and correct.
  It would copy only that frozen observation into an explicitly derived cell;
  no selector, role map, detector, or threshold may change.

## Decision

If B contains one or more novel correct items and a bounded C uses them
without control damage, the direction is supported for the next stage.
Otherwise, meaningful ledger distinctions without a quality gain yield
`OBSERVABILITY SUPPORTED; QUALITY BENEFIT UNPROVEN`; inadequate truth yields
`INCONCLUSIVE`.
