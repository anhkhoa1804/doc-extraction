# Observations — 010

## 1. A new failure mode: overlay text is interleaved into table cells

This is the most important thing the corpus found, it is not in any previous
record, and it is a **silent data-corruption bug**.

On `hc_stamp_table_vi` the native route produces a table that looks perfectly
healthy — 4×5, every cell populated, recall 0.875, no hallucination flag:

```
[ 3] r0 c3  'Số lượn'
[ 4] r0 c4  'gThành tiền'
[11] r2 c1  'Bộ lọc khí Mã 22B CÔNG TY T'
[12] r2 c2  'NBHộH'                       <-- garbage
[16] r3 c1  'Dịch vụ lắp đặt ĐÃ DUY'
[17] r3 c2  'ỆGTói'                       <-- garbage
```

The seal's text (`CÔNG TY TNHH`, `ĐÃ DUYỆT`) is drawn inside the table's
bounding box. Cell text is assigned by coordinate with no notion of which
*text run* a glyph came from, so the overlay and the cell contents are
merged in coordinate order and interleave character by character. `NBHộH` is
`NHH` (from `TNHH`) woven through `Bộ`. `ỆGTói` is `ỆT` woven through `Gói`.

**Controlled**: three stamped tables, three unstamped controls, same
generator, same route.

| Document | Stamp | Contaminated cells |
|---|---|---|
| `hc_stamp_table_vi` | yes | 2 |
| `cmb_stamp_table_vi` | yes | 2 |
| `cmb_stamp_boundary_vi` | yes | 1 |
| `ord_invoice_vi` | no | **0** |
| `ord_purchase_order_en` | no | **0** |
| `hc_merged_en` | no | **0** |

Why this is worse than it scores: recall barely moves, because the *body*
text is fine and only cells are corrupted. Nothing flags it. A downstream
consumer reading `Đơn vị = NBHộH` has no way to know that is not a real unit
of measure. This is the same class of danger as the broken-CMap case — output
that looks like success — except the CMap case is caught by
`must_not_contain` and this one is not caught by anything.

It also reframes the §8 fusion target. The mission's hypothesis was that
native text plus visual geometry would recover `stamp_over_table`. That may
still be true, but it is not the first problem: **the native table path
corrupts cells whenever anything overlaps them**, and fusing a corrupted
input with a second source would propagate the corruption, not fix it.

A separate, smaller observation from the same dump: `'Số lượn'` / `'gThành
tiền'` splits a word across a cell boundary. That one is partly a corpus
artifact — the generator draws a header wider than its column — but the
*behaviour* (splitting mid-word by x-coordinate rather than by text run) is
the same root cause and would occur on any real document whose cell text
overflows its ruling.

## 2. Scanning is the top production failure class, and it dominates cost too

`scan_quality` is first by frequency (6 documents), contains the only total
failure, and consumed **88.9 s of 136.1 s — 65% of all runtime** in the first
run. It is simultaneously the most common failure and the most expensive
thing the system does.

Every scanned document lost text:

| Document | Recall | Missing |
|---|---|---|
| `cmb_scan_tiny_vi` | **0.00** | everything |
| `hc_scan_vi` | 0.25 | title, VI header, addressee |
| `cmb_scan_stamp_table_vi` | 0.25 | 6 of 8 strings |
| `ord_invoice_png_vi` | 0.57 | title, invoice number |
| `cmb_scan_multicol_en` | 0.67 | one section heading |
| `hc_scan_en` | 0.67 | the title |

Note what is missing: **titles and headers**, repeatedly. These are larger
text than the body, so this is not a resolution floor — it is more likely
layout regions being dropped or mis-ordered before OCR. That is a lead worth
following, and it is not the lead I would have guessed.

## 3. The single total failure is a compound case, and only a compound case

`cmb_scan_tiny_vi` — scanned *and* 4.5 pt — scored **0.0**, returning 93
characters of nothing useful. Neither mechanism alone does this:

| | recall |
|---|---|
| `hc_tiny_text_vi` (tiny only, born-digital) | **1.00** |
| `hc_scan_vi` (scan only) | 0.25 |
| `cmb_scan_tiny_vi` (both) | **0.00** |

This is the argument for the combination cases stated as a measurement.
A corpus of isolated mechanisms would have reported tiny text as *solved*
(native reads 4.5 pt from the text layer perfectly) and scanning as
*degraded*. Their conjunction is a total failure, and it is invisible to any
benchmark that tests one mechanism at a time.

It is also precisely the case that `research/experiments/_recovery`
targeted high-DPI recovery was built for — a difficult region on a page with
no text layer to fall back on.

## 4. The tail is three orders of magnitude wide

| p50 | p90 | p95 | p99 |
|---|---|---|---|
| 0.051 s | 14.196 s | 22.588 s | 33.035 s |

**p99 is 648× p50.** The median document costs nothing because it is
born-digital and the native route reads it directly; the tail is entirely
the visual route.

Two consequences. First, a mean (2.833 s) describes no document in the
corpus — nothing takes 2.8 s. Second, this is the strongest possible
argument for the adaptive architecture: 48 of 58 documents cost 0.05 s, so
the money is available to spend on the ten that need it. It also says any
future latency target must be a percentile, never a mean.

## 5. Ordinary documents are genuinely solved, across five formats

29 of 29 ordinary documents scored 1.00, including all seven office files
(DOCX/XLSX/PPTX) and both Vietnamese-diacritic-heavy types, at 0.01–0.05 s
each. The 60-page document took **0.84 s** on the native route.

This deserves to be stated plainly because it bounds the problem: the
system's weakness is not general. It is specifically *pixels* — documents
where the text layer is absent or occluded. Every one of the ten failures
involves either no text layer (6) or something drawn over the text (4).

That is a much narrower target than "improve extraction quality", and it is
the kind of narrowing that only a corpus with easy documents in it can
produce.

## 6. Zero hallucinations and zero crashes

Across 58 documents and 125 pages: no crash, no confident garbage that
`must_not_contain` could catch, and the broken-CMap document correctly
rerouted and scored 1.00. The failure *policy* is working even where the
failure *rate* is not zero — documents fail visibly, which is the property
the architecture was built for.

The one exception is §1's cell contamination, which is exactly a silent
failure and is not caught because no gate looks inside table cells. That is
the gap.

## 7. An honest defect in my own instrumentation

The runner classified CPU state as `CLEAN` at loadavg 3.79 on an 8-core box
while a neighbouring project was demonstrably running four jobs at ~451% CPU.
The threshold (`load > cores × 0.5`) is too lenient and the classification
was wrong.

It did not affect any conclusion — recall is contention-independent and every
runtime here is already labelled an upper bound — but a resource classifier
that reports CLEAN during known contention is worth fixing before anyone
relies on it, and it is recorded rather than quietly corrected.

## 8. What this experiment does NOT establish

* **Nothing about production.** This corpus is synthetic. It is designed to
  be representative and it is not evidence about real documents. The
  frequencies above are *my* frequencies — I chose the mixture — so the
  ranking is only as good as that choice. Real frequency data requires the
  real corpus.
* **No timing claim.** Every runtime was measured beside another project's
  jobs.
* **No comparison between strategies.** Only `adaptive` was run. The
  native/visual comparison from experiment 008 has not been repeated here.
* **Nothing about the GPU.** It was PROTECTED throughout and was not used.
