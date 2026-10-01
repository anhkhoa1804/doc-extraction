# 043 — observation-ledger vertical slice

Question: does retaining acquired stage observations reveal a distinction that
the frozen canonical representation cannot express?

`replay_hard_case.py` performs A/B observational replay of frozen 035
development case `d2-00`. A is the exact persisted canonical document. B
uses that same document and captures the persisted layout, OCR, and table
stage artifacts into the private ledger. It does not rerun a model, alter a
role, invoke a table specialist, or use held-out material.

Novel textual evidence means normalized-exact text in a candidate projection
that is absent from A. Correctness is deliberately not claimed without an
external token/cell truth annotation. The evaluator separately reports text
that exists in canonical objects but disappears from current Markdown
serialization.

The accounting invariant is over captured observations only:
`captured = accepted disjoint-union unresolved disjoint-union excluded`.
It does not assert that captured observations equal source truth.
