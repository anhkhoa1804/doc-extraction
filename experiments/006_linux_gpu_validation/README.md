# 006 — Linux port and GPU validation

## Question

The repository was developed and validated on Windows, CPU-only. `README.md`
listed GPU as **"Not validated. `configs/gpu.yaml` documents intent only"**,
and `configs/gpu.yaml` described itself as *"WIRED, NOT YET MEASURED"* —
the device plumbing existed but no GPU had ever executed it.

Three questions, in order:

1. Does the pipeline run correctly on Linux at all?
2. Does `config.device: cuda` actually place models and tensors on the GPU —
   or does it merely fail to crash?
3. If it does, what is the *real* speedup, separating model load from
   inference?

## Hypothesis

Device propagation was believed correct by inspection (both `AcceleratorOptions`
and the Table Transformer `.to(device)` calls were added in commits
`a5c0420`/`cf81aca`), but "wired" and "works" are different claims. Expected:
propagation correct; speedup material for the visual route only, since the
native/digital route runs no model at all.

## Method

Machine: GCP `research-no-1`, Ubuntu 22.04.5, Linux 6.8.0-1066-gcp,
8× Xeon @2.20GHz, 31 GiB RAM, **NVIDIA L4 23034 MiB**, driver 580.173.02.

Two separate environments, both Python 3.12.14, identical source
(`4edd395` + the fixes below), identical model cache:

* CPU: `torch 2.13.0+cpu`
* GPU: `torch 2.11.0+cu128`

Keeping them separate (rather than upgrading one in place) means the
CPU numbers remain measurable after the GPU numbers are taken.

Every GPU workload was preceded by a preflight (`nvidia-smi` memory,
utilization and compute-apps) and followed by a postflight. The GPU was
STATE A (clear, 0 MiB, 0 %, no compute apps) before each.

Workloads:

* **A. Fixture** — `make_pdf_with_broken_cmap`, 2 pages, forced onto the
  visual route by the quality gate. Measured per stage, cold vs warm.
* **B. OmniDocBench demo** — the official 18-page demo set at pinned
  upstream commit `193627ae9e97d89188468ed1ee3b7a856ff76044`,
  `baseline` backend, all 18 pages routed `image`.

## Results

See `results.json`. Summary in `observations.md`.

## Limitations

* Workload A is synthetic. It reproduces the CMap failure *mechanism*
  faithfully (a deliberately wrong `/ToUnicode` map over real Latin glyphs),
  but it is not a real scanned document, and its layout is trivial.
* The private `data/` corpus was **not present on this machine**, so the
  Windows-validated corpus results could not be re-measured on Linux. Only
  the public benchmark and synthetic fixtures were used.
* One CPU 18-page run was contaminated by a concurrent Docker build on the
  same host and is reported separately, not used for the headline number.
* Single run per configuration. No variance estimate.
