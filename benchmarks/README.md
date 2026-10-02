# Benchmark registry

This directory is internal evaluation infrastructure. Its manifests describe
where data may be obtained, what local copy was selected, and how a result is
recorded. They are not data files, production configuration, or an external
interchange contract.

## Principles

* Each benchmark measures one task layer; no aggregate score is produced.
* Dataset acquisition is explicit. `resolve_local_dataset` never downloads.
* Result files use internal `benchmark-result/1` bookkeeping only.
* Existing local OmniDocBench data is reused. Kleister, SWDE, and live-web
  datasets are prepared as manifests only until an operator obtains them under
  verified terms.
* The committed OmniDocBench manifest intentionally names only the 18-page
  demo copy it can validate as one dataset identity. A locally available
  1,651-page historical snapshot has a different ground-truth filename and
  hash; it needs its own versioned manifest before it can be selected for a
  new measurement.
* Raw datasets belong under `.benchmarks/` or existing ignored dataset roots;
  they must not be committed accidentally.

## Commands

```bash
uv run python -m benchmarks.scripts.runner list
uv run python -m benchmarks.scripts.runner inspect benchmarks/manifests/omnidocbench.yaml
```

The live-web manifest is opt-in metadata only. The runner refuses it unless
`--allow-live` is provided, and it never relaxes crawler policy, TLS, robots,
or SSRF controls.

## Adapters

`doc_extraction.evaluation.omnidocbench` remains the existing physical
document adapter to the official evaluator. Generic exact field metrics in
`registry.py` prepare input bookkeeping for semantic benchmarks; they are not
claims that the official Kleister or SWDE protocols have been executed.
