# Production contract

What this system promises, for whom, and how it behaves when it cannot keep
the promise. Written to be falsifiable: every capability below is either
measured, or explicitly marked as not yet measured.

Target population: **English and Vietnamese enterprise documents** — business
licences, contracts, invoices, financial reports, certificates, forms.

## Inputs

| Format | Route | Status |
|---|---|---|
| PDF (born-digital) | native text + native tables | validated |
| PDF (scanned / image-only) | render → layout → OCR → table | validated |
| DOCX | native object model | validated |
| XLSX | native, one page per sheet | validated |
| PPTX | native, one page per slide | validated |
| PNG / JPEG / TIFF / BMP | render passthrough → visual route | validated |

Legacy OLE (`.doc`, `.xls`, `.ppt`) is detected and **refused with a clear
reason**, not silently mis-parsed.

## Languages

Primary: **English, Vietnamese.** OCR is configured `["en", "vi"]`, which is
a deliberate choice for this corpus — EasyOCR serves `vi` from its Latin
model, and experiment 007 measured that swapping to a Chinese model to chase a
public benchmark costs 43.6% on English and collapses English table structure
from 0.715 to 0.000.

Other languages are an architectural possibility, not a current promise. The
language set is a config value and its model pack must be prefetched to match;
mismatches fail loudly rather than producing empty output.

## Outputs

The **canonical IR is authoritative** (`schemas/document.py`, currently schema
`1.2.0`). Markdown and HTML are derived views and are explicitly lossy.

Every run also emits:

* `metadata.json` — route and its evidence, config snapshot, model versions,
  device and *why that device* (`device_decision`)
* per-stage intermediates under `outputs/<document_id>/<stage>/`
* `logs/pipeline.jsonl` — one timed, device-stamped record per stage

Coordinates: origin top-left, +y down, units declared per page
(`pt` | `px` @ dpi | `emu` | `none`). Backends normalize on the way in.

## Capabilities

Measured against `research/hardcases/` (14 EN/VI cases). "Recovered" means the
case's known strings survived extraction.

| Capability | Status | Evidence |
|---|---|---|
| Text (born-digital) | **strong** | 100% on clean EN and VI incl. diacritics |
| Corrupt encoding detection | **strong** | routed to OCR and fully recovered; the alternative is confident garbage |
| Tables (ruled) | **good** | detected and populated |
| Tables (borderless) | **partial** | text recovered, grid not — native finder keys on ruling lines |
| Tables (merged cells) | **partial** | 67% — merged header cell text lost |
| Reading order | **baseline** | geometric, column-aware; not semantic |
| Multi-column | **good** | 100% text; ordering is the open question |
| Small text (to ~4pt) | **good** | recovered natively; visually at 200 DPI too |
| Watermarks | **good** | body text recovered, watermark preserved as content |
| Rotated regions | **partial** | text recovered, reading order degrades |
| Low contrast | **good** | native path unaffected |
| Stamps / seals over text | **partial** | native recovers occluded text; visual cannot |
| Stamps over tables | **weak** | no current strategy recovers it |
| Cross-page structures | **partial** | repeated headers/footers detected as pages, not yet linked |
| Images / figures | **recorded** | referenced with geometry, not interpreted |
| Forms, checkboxes, key-value | **not implemented** | element types exist in the IR; no extraction logic |
| Formulas | **not implemented** | measured at 0.996 edit distance on OmniDocBench — effectively absent |
| Charts | **not implemented** | recorded as images |
| Handwriting | **not measured** | no case in the corpus yet |

## Non-functional requirements

**Reliability.** Failures are visible. A stage that fails records the failure
and re-raises; a document that fails is reported per-file and the run
continues. The system must never turn a failure into empty output that looks
like success — the corrupt-CMap case exists precisely to lock that.

**Observability.** Every stage is timed and persisted. `scripts/profile_pipeline.py`
reconstructs a cold/warm profile from logs alone, with no re-run and no
special mode.

**Resource awareness.** `device: auto` inspects the GPU's current state —
free VRAM, *median* utilization over several samples, other compute
processes — and declines a GPU another project is actively using. Explicit
`cpu`/`cuda` are honoured verbatim and never probed.

**Resumability.** `document_id` embeds a content hash, so re-running the same
input lands in the same output directory and is comparable rather than
accumulating. True mid-document resume is **not** implemented.

**Reproducibility.** Runs record git-independent provenance: model versions,
config snapshot, dataset identity (byte hash *and* a platform-independent
content hash), and device rationale. Native and office routes are verified
deterministic; the visual route is observed deterministic but not asserted,
because model kernels are outside this project's control.

**Latency.** Deliberately unspecified. Measured so far, on this hardware:
native route ~0.03 s/document; visual route dominated by docling layout at
98.6% of CPU time. A target belongs here once the production corpus exists —
inventing one now would be a number with no evidence behind it.

## What this system does not promise

* Semantic understanding. The output is a technical document representation;
  interpreting it is the consumer's problem.
* Formula, chart, or handwriting recognition.
* Recovery of text that is genuinely destroyed — an opaque seal over a scan
  removes the pixels, and no amount of processing invents them. The system
  should say so rather than guess.
* Any language outside EN/VI without a matching OCR model pack.

## Failure policy

Preferred ordering, cheapest first:

```
accept  →  cheap repair  →  targeted re-render  →  specialist  →  VLM  →  fusion
```

A later rung is entered only when an earlier one is judged untrustworthy by a
quality gate. Currently implemented: the text-quality gate and per-page visual
fallback. Rungs beyond that are researched, not shipped.

When nothing recovers a region, the correct output is a recorded failure with
provenance — **`unknown` is always preferable to `invented`**.
