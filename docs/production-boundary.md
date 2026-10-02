# Production boundary

## Runtime and public surface

Production code is `src/doc_extraction/`. The supported invocation is the
`doc-extraction` CLI or `doc_extraction.cli.process_file` (see
[public-api.md](public-api.md)). Lower-level parser/backend functions are
internal building blocks, not safe entry points for unvalidated uploads.
They depend on the public entry point's private snapshot and preflight.
`tests/`
contains production regression, integration, contract, and determinism tests.

`experiments/` and `research/` are historical evidence archives. They are not
imported by the normal extraction route and are not a dependency of packaging
or deployment. Their compact protocols, manifests, and reports are retained;
large raw stage output remains outside Git under the managed research work
disk, as documented in `.gitignore`.

## Optional diagnostic components

`evaluation/evidence_integrity.py` is retained as optional diagnostic tooling:
it is not invoked by the CLI or canonical extraction pipeline. Its ledger is
opt-in at the scanned-page pipeline seam and must not change canonical output.
The closed research claim is not part of the production contract.

`ingest/evidence_fusion.py`, `targeted_recovery.py`, `scan_recovery.py`, and
`order_recovery.py` are retained for historical reproducibility and focused
unit tests. They are not selected by the production CLI route. New production
features must not import or enable them without an explicit product decision,
public configuration, and regression coverage.

## Contract authority

The repository's production output today is the internal canonical
`Document` schema (currently v1.4.0). No separate authoritative
`DocumentExtractionContract 1.0.0` or `ExtractionPackage v1` contract was
found. Internal schema validation is not a substitute for that external
authority. A future integration must provide the authoritative schema and use
a narrow adapter at the public boundary; it must not expose private diagnostic
or historical classes downstream.
