# 007 — Is the OmniDocBench score measuring the pipeline, or the OCR language config?

## Question

The first official OmniDocBench evaluation of this pipeline (18-page demo,
`baseline` backend) returned a text-block edit distance of **0.7476** — bad
enough that, taken at face value, it would suggest the extraction pipeline is
broadly broken.

But the per-group breakdown does not look like a broken pipeline. It looks
like two different systems:

| Subset | Text edit distance (lower is better) | n |
|---|---|---|
| `text_english` | **0.386** | 80 |
| `text_en_ch_mixed` | 0.931 | 10 |
| `text_simplified_chinese` | **0.961** | 149 |

and the same split appears in tables:

| Subset | TEDS-structure (higher is better) | n |
|---|---|---|
| `table_en` | **0.715** | 3 |
| `table_simplified_chinese` | **0.095** | 7 |

An edit distance of 0.96 is not "poor recognition" — it is close to producing
nothing correct at all. A pipeline that genuinely could not segment or read
documents would not score 0.386 on the English subset with the same code,
same models and same run.

## Hypothesis

The aggregate score is dominated by a **configuration/dataset mismatch, not a
pipeline defect**.

`configs/cpu.yaml` sets `ocr_languages: ["en", "vi"]`. That is correct for
this repository's private corpus, which is mixed Vietnamese/English — it is
the reason EasyOCR was chosen over Docling's default RapidOCR in the first
place (see `docs/backends.md`). But OmniDocBench's demo set is **majority
simplified Chinese** (149 of 239 text blocks). With no Chinese recognition
model loaded, Chinese text is unreadable *by construction*.

**Prediction:** configuring `ocr_languages: ["ch_sim", "en"]` should improve
the Chinese subset substantially, while leaving English roughly unchanged. If
instead English also changes materially, the language model choice is not a
free switch and the trade-off must be reported.

## Method

Two runs of the identical pipeline over the identical 18-page demo set, at
the same commit, in the same environment. The configs differ in **exactly one
line** — verified by diff:

```
< ocr_languages: ["en", "vi"]        (config_baseline.yaml — repository default)
> ocr_languages: ["ch_sim", "en"]    (config_candidate.yaml)
```

EasyOCR cannot serve `ch_sim` and `vi` from one reader — `vi` belongs to the
`latin_g2` model group and `ch_sim` to `zh_sim_g2` — so this is `ch_sim`+`en`
rather than adding Chinese to the existing pair. That constraint is itself
part of the finding: the language sets are mutually exclusive here.

Scoring: the official OmniDocBench evaluator, unmodified, at pinned upstream
commit `193627ae9e97d89188468ed1ee3b7a856ff76044`, `quick_match`.

### Resource conditions

Both runs are **accuracy** measurements, and accuracy is device-independent
here — GPU and CPU outputs were previously shown byte-identical (0.000 px
bbox delta, experiment 006). So contention does not invalidate them.

The candidate run was executed on **CPU under contention** (another project's
job on the same VM; `device: auto` classified the GPU as PROTECTED and
selected CPU automatically). Its *timing* is therefore not a benchmark and is
not reported as one. The baseline run's timing was clean; see experiment 006.

## An operational finding, discovered by the run failing

The first attempt failed on all 18 pages:

```
FileNotFoundError: Missing .../.cache/docling/EasyOcr/zh_sim_g2.pth
and downloads disabled
```

Changing `ocr_languages` is **not** purely a config change: it requires a
matching model prefetch, because the project sets `DOCLING_ARTIFACTS_PATH`,
which disables Docling's auto-download. This is worth stating plainly because
the failure is easy to misread as a code bug.

It is also the *right* behaviour — a hard, loud failure rather than silently
producing empty output for every page, which is precisely the "confident,
plentiful, wrong" failure mode this repository was built to avoid. The remedy
is one command (`make models`, with the language flags).

## Results

See `results.json` for the full metric sets and `observations.md` for the
interpretation, including the English-subset regression, which is the part
that makes this a trade-off rather than a straightforward improvement.

## Limitations

* One dataset (18 pages), one run per configuration. No variance estimate.
* The demo set is small: `table_en` has n=3, so table conclusions on the
  English side are indicative only.
* This experiment says nothing about whether `["en","vi"]` is right for the
  *private* corpus — it almost certainly still is. The finding is about not
  inheriting a corpus-tuned config into a benchmark, not about changing the
  project default.
