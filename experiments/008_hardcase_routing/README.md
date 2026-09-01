# 008 — Adaptive routing on EN/VI enterprise hard cases

## Question

The repository routes adaptively: cheap native extraction by default, with a
quality gate that reroutes to render+OCR when the text layer is untrustworthy.
That design has never been measured against its alternatives on the document
population it actually serves.

Is adaptive routing worth its cost, compared with always-native and
always-visual?

## Why a new corpus was needed

The project's only benchmark, OmniDocBench, is a poor proxy for its target:

* it contains **no Vietnamese** (English, simplified Chinese, EN-CH mixed only),
  and Vietnamese is half the production target;
* its aggregate is dominated by simplified Chinese, which the project does not
  target — experiment 007 showed the headline score mostly reported whether a
  Chinese OCR model was loaded.

So this experiment runs on `research/hardcases/` — 14 synthetic EN/VI
enterprise documents (licenses, invoices, contracts, financial reports) each
isolating one failure mechanism, with ground truth free because the generator
draws the text.

## Method

Three strategies over the same 14 documents, same backends, same config, same
device. They differ **only** in how the router is constrained:

| Strategy | Constraint |
|---|---|
| `native` | never leave the text layer (fallback off, gate disabled) |
| `visual` | force render + layout + OCR for every page |
| `adaptive` | the shipped configuration, unchanged |

Metric: recall over each case's `must_contain` strings (NFC-normalized, so
Vietnamese composed/decomposed forms compare equal), plus a
`must_not_contain` check that catches confident garbage.

**Resource state: LIMITED.** One unrelated GPU job was resident throughout and
CPU loadavg ranged 1.4–3.1. All three strategies ran under the same conditions,
so the comparison is internally valid; the absolute timings are not a clean
benchmark and are not reported as one.

## Results

See `results.json` for full numbers and `observations.md` for interpretation.

Headline: adaptive **95%** mean recall with zero total failures and zero
hallucinations, against native **88%** (one silent-garbage failure) and visual
**66%** at ~390× native's runtime.

The experiment also uncovered and fixed a coordinate-space defect that was
costing the visual route two total failures; both before and after numbers are
recorded.

## Limitations

* 14 synthetic cases. They reproduce mechanisms faithfully but are not real
  scans — no sensor noise, JPEG artifacts, or genuine camera skew.
* One run per strategy; no variance estimate.
* Recall over a handful of strings is coarse by design. It answers "did the
  registration number survive" and deliberately says nothing about formatting
  fidelity.
* No VLM arm: the GPU was PROTECTED by another project's job for the whole
  session, so that comparison is outstanding.

## Reproduce

```bash
python research/hardcases/generate.py
python research/hardcases/run_benchmark.py --strategy native adaptive visual --device cpu
```
