# 044 — truth-aware development replay, protocol v2

This supersedes protocol v1 **before outcome evaluation**. Its rules are
unchanged; it adds two frozen exact-match table controls, required to test
whether the evaluator calls ordinary already-represented table evidence
novel. The executable protocol is otherwise identical to `PROTOCOL.md`.

Population: `d2-00` through `d2-07` (eight strict-D2 difficult cases) plus
`ctl-00` and `ctl-01` (two table-gated exact-match controls). All ten records
are development-only persisted 035 artifacts with OmniDocBench HTML table
truth. No item was selected from recovery/treatment outcome.

Primary endpoint, truth source, normalized-exact rule, ownership rule,
provenance rule, structural-only definition, and C trigger are exactly those
in protocol v1. A control is expected to produce zero novel-correct evidence;
a nonzero control result is evaluator false-positive evidence.
