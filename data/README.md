# data/

Local, internal sample documents used as pipeline input for development and
the experiment suite. **Not part of the public repository** — see below.

## Local and private, intentionally excluded from Git

Everything in this directory except this file and `manifest.json` is
ignored by `.gitignore` (`data/*` with `!data/README.md` and
`!data/manifest.json` as the only exceptions). These are real internal
enterprise documents — at least one
(`FROGSLEAP_BUSINESS LICENSE.pdf`) contains personal data (national ID
numbers, dates of birth, home addresses of named individuals); others
contain commercial pricing. They must never reach a public remote or a
Kaggle notebook.

If you clone this repository elsewhere, `data/` will be empty except for
this README and the manifest — that's expected. Put your own local
documents here, or point `--input` at any other directory; nothing in the
pipeline requires this exact location.

## `manifest.json` describes the corpus without containing it

`manifest.json` **is** tracked. It is generated, derived data — filename,
size, SHA-256, and detected type for each file — so the local corpus is
documented and verifiable (you can confirm you have the same bytes) without
distributing any content. It never contains extracted text or other
document content.

Regenerate it after adding/removing local documents:

```bash
.venv/Scripts/python.exe scripts/build_sample_manifest.py
```

The generator only ever opens files here for reading. If `manifest.json`
and the actual files disagree, trust the files and regenerate — the
manifest is derived data, not the source of truth.

## The pipeline scans this directory by default

`configs/cpu.yaml` / `configs/default.yaml` set `input_dir: "data"`, so:

```bash
.venv/Scripts/python.exe -m doc_extraction run --input data --config configs/cpu.yaml
```

is equivalent to the plain `run --config configs/cpu.yaml` most docs show.

## What the current local corpus contains

Observed by running the pipeline over it (see `experiments/000_smoke/` and
the failure report):

- **12 files, 10 unique documents.** Two pairs are byte-identical duplicates
  under different names (`FROGSLEAP COMPANY PROFILE EN UP 26.pptx.pdf` ==
  `FROGSLEAP_COMPANY PROFILE.pdf`, and `FROGSLEAP PARTNERSHIP PROPOSAL.pdf`
  == `frogsleap_partnership_proposal_v2_20260307095034.pdf`). They are
  processed separately — `document_id` includes a content hash, so their
  outputs are directly comparable and should be identical.
- **10 PDFs, 2 XLSX, 1 DOCX** (one PDF is a PPTX export). No PPTX and no
  standalone image, which is why `tests/fixtures.py` synthesizes those.
- **Mixed Vietnamese and English**, which is why OCR is configured for
  `["en", "vi"]` and why the text-quality check treats Latin script
  (including Vietnamese precomposed diacritics) as expected.
- **One document with a corrupt text layer** — see
  `experiments/001_pdf_text_quality/`.
- **9 of 10 unique documents are born-digital** and extract by the cheapest
  path; only the corrupt one needs OCR.

## Not to be confused with `experiments/005_omnidocbench/`

`data/` is private, local, enterprise input. `experiments/005_omnidocbench/`
is a public benchmark against a public dataset (OmniDocBench). The two are
kept structurally separate on purpose — nothing under `data/` is ever
attached to a Kaggle notebook or passed to the benchmark runner. See
`docs/kaggle.md`.
