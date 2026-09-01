# enterprise-hardcases

An internal benchmark for the document population this project actually
serves: **English and Vietnamese enterprise documents**.

## Why this exists rather than only using OmniDocBench

OmniDocBench is a good public benchmark and a poor proxy for this project.
Two measured reasons:

1. **It contains no Vietnamese.** Its language coverage is English, simplified
   Chinese, and English-Chinese mixed. Vietnamese is half of this project's
   stated production target and the benchmark cannot measure it at all.
2. **Its aggregate is dominated by a language this project does not target.**
   149 of 239 text blocks in the demo set are simplified Chinese. Experiment
   007 showed the pipeline's headline score was mostly reporting whether a
   Chinese OCR model was loaded.

So OmniDocBench remains useful for *generalization* testing and for comparing
against published systems, and it is not a measurement of production quality
here. This corpus is the complement, not the replacement.

## Design

Every case is **synthetic and self-labelling**. The generator draws the text,
so the ground truth is exactly the strings it drew — no annotation, no
annotator disagreement, and the corpus is freely distributable because it
contains no real enterprise data.

Each case declares:

| field | purpose |
|---|---|
| `must_contain` | short distinctive strings that must survive extraction |
| `must_not_contain` | strings whose presence indicates hallucination or corruption |
| `expected_tables` | how many tables should be detected |
| `failure_mode` | taxonomy code — a *mechanism*, not a document category |
| `expected_behavior` | what a correct system should do, including "should fail loudly" |

Recall over `must_contain` is a blunt metric on purpose. It is unambiguous and
it answers the production question directly: *did the company registration
number survive?* An edit distance of 0.55 does not.

## What synthetic cases can and cannot tell you

They are a **regression floor and a diagnostic instrument**, not a substitute
for real documents. A system that passes here can still fail on a genuine
phone-camera photo of a creased invoice under fluorescent light.

The cases that earn their place are the ones reproducing a *mechanism*
faithfully. `broken_cmap_vi` is the model: it corrupts the font's `ToUnicode`
map rather than writing pre-garbled characters, so it reproduces the true
failure and not a costume of it.

## Taxonomy

Codes are grouped by mechanism. The corpus currently exercises 12 of them;
the rest are declared because they are known-real and unbuilt.

| Code | Mechanism | Built |
|---|---|---|
| `T-CLEAN` | control: clean born-digital text | yes (×2) |
| `T-TINY` | text below what the render DPI resolves | yes |
| `T-LOWCON` | low ink/background contrast | yes |
| `T-ROT` | rotated content | yes |
| `T-CMAP` | text layer present but wrongly decoded | yes |
| `O-STAMP` | opaque seal over text | yes |
| `O-WATERMARK` | translucent watermark across the page | yes |
| `L-MULTICOL` | multi-column with a real gutter | yes |
| `L-HEADFOOT` | repeated header/footer across pages | yes |
| `B-BORDERLESS` | table with no ruling lines | yes |
| `B-MERGED` | table with merged cells | yes |
| `X-COMBO` | two mechanisms interacting | yes (×2) |
| `T-SKEW` | scanner/camera skew | not yet |
| `T-NOISE` | scan speckle | not yet |
| `T-DIACRITIC` | Vietnamese diacritics specifically at risk | not yet |
| `O-HANDWRITE` | handwriting over print | not yet |
| `B-TINYCELL` | small text inside table cells | folded into `X-COMBO` |

`X-COMBO` exists because real enterprise documents combine failure modes —
a stamp *over a table*, tiny text *inside cells*. Testing mechanisms in
isolation overstates how well a system does.

## Usage

```bash
python research/hardcases/generate.py                       # build the corpus
python research/hardcases/run_benchmark.py \
    --strategy native adaptive visual --device cpu          # compare strategies
```

The three strategies differ **only** in how the router is constrained, so any
difference is attributable to routing rather than to a different backend:

* `native` — never leave the text layer
* `visual` — force render + layout + OCR for every page
* `adaptive` — the shipped router

## Adding a case

Add a builder to `generate.py` returning a `HardCase`. Prefer reproducing a
mechanism you have actually observed failing over inventing a plausible-looking
one. If a case cannot state `must_contain` strings that unambiguously indicate
success, it is not ready to be a benchmark case.
