# Samples

## Where the documents are

The real sample documents live at the **repo root**, not in this directory,
and are treated as immutable input data: never moved, renamed, overwritten,
or modified by anything in this repo.

Keeping them at the root (rather than copying them here) means nothing in the
pipeline — or in a careless refactor later — can mistake them for writable
working files. `configs/*.yaml` set `input_dir: "."` for exactly this reason.

## They are not committed to git

The sample documents are **excluded by `.gitignore`**. They are real internal
enterprise documents, and at least one of them
(`FROGSLEAP_BUSINESS LICENSE.pdf`) contains personal data — national ID
numbers, dates of birth, and home addresses of named individuals. Others
contain commercial pricing.

Committing them would mean any push, especially to a public remote, discloses
that data irreversibly. Nothing in the repository depends on them being
tracked: the pipeline reads them from the working directory.

**If you clone this repository elsewhere, `outputs/` will be empty and
`run` will find no inputs until you supply your own documents** (any
directory works — `doc_extraction run --input /path/to/docs`).

If your copy of this repository is private and its policy explicitly permits
storing these documents in git, delete the sample block at the top of
`.gitignore` and `git add` them deliberately.

## MANIFEST.json

`MANIFEST.json` **is** committed. It is generated, read-only-derived data —
filename, size, SHA-256, and detected file type for each document at the repo
root. That documents and makes the corpus verifiable (you can confirm you
have the same bytes) without distributing any content.

Regenerate it after changing which documents are present:

```bash
.venv/Scripts/python.exe scripts/build_sample_manifest.py
```

The generator only ever opens the sample files for reading.

If `MANIFEST.json` and the actual root files disagree, trust the files and
regenerate — it is derived data, not the source of truth.

## What the corpus actually contains

Observed by running the pipeline over it (see the failure report and
`experiments/`):

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
