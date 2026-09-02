# research/experiments

One-off probes that answer a specific question and then stop. Each script is
self-contained, writes its numbers to a `_<name>/results.json` working
directory, and is tracked here so the result can be regenerated.

**Only `results.json` is committed.** The working directories also hold probe
PDFs, rendered pages and crops; those are regenerable by re-running the script
and are excluded in `.gitignore`. The numbers are the evidence, the pixels are
not.

| Script | Working dir | Question |
|---|---|---|
| `dpi_recovery.py` | `_dpi/` | What render DPI does small text need, and what does it cost? |
| `recovery_hidpi.py` | `_recovery/` | Does a targeted high-DPI pass recover what a global one does, for less? |
| `screen_vlm.py` | — | Does a document VLM earn a place in this pipeline? (see `experiments/009_vlm_screening/`) |

## E11 — DPI sweep (`_dpi/results.json`)

Sweeps 4 font sizes × 5 DPIs (150/200/300/400/600), recording per-glyph pixel
height, pixels rendered, render time, and what the same region would cost as a
crop. Legibility thresholds are declared in the file: `min_glyph_px_reliable`
20, `min_glyph_px_marginal` 12.

At the shipped default of **200 DPI**:

| Font | Glyph height | Verdict |
|---|---|---|
| 12 pt | 33.3 px | reliable |
| 8 pt | 22.2 px | reliable |
| 6 pt | 16.7 px | marginal |
| 4 pt | 11.1 px | **below floor** |

Recorded `conclusion`: rendering globally at 600 DPI costs **9.0×** the pixels,
while the targeted crop costs **1.091×** — the targeted pass is **8.25×**
cheaper for the same region.

This probe measures **geometry only**. It deliberately does not measure OCR
accuracy — the script says so and gives the reason: that half is model-heavy
and belongs on a machine whose GPU is not shared. The geometry is
device-independent, which is why no device is recorded.

## E12 — targeted vs global high-DPI recovery (`_recovery/results.json`)

The accuracy half that E11 left open. Input is
`research/hardcases/corpus/tiny_cells_table.pdf` (tracked), rasterized to a
simulated scan, then read back three ways. Recall is over four target strings:
`SKU-1001`, `SKU-1005`, `Mô tả`, `Sản phẩm 1`.

| Arm | Recall | Seconds | Megapixels | Missing |
|---|---|---|---|---|
| `baseline_200` | **1.0** | 32.54 | 3.866 | — |
| `global_600` | **0.5** | 26.70 | 34.797 | `SKU-1001`, `Mô tả` |
| `targeted_600` | **1.0** | 38.34 | 8.192 | — |

**Rendering the whole page at 600 DPI made recall worse** — 1.0 down to 0.5 —
at 9× the pixels. Only the targeted crop held 1.0. This is a negative result
about the obvious remedy: resolution is not a global knob, and the finding
supports *targeted* high-DPI recovery rather than raising `render_dpi` for
every page.

Note that `baseline_200` already scores 1.0 here, so this run does not
demonstrate targeted recovery *rescuing* a failing baseline — it demonstrates
that the global alternative regresses while the targeted one does not.

## Provenance

Recorded in the results files: input document, configuration (DPIs, font
sizes, thresholds, target strings, region coordinates), per-arm runtime,
pixel cost, and results. Paths are repository-relative and portable.

Recoverable from the tracked source rather than the JSON:

* **Device.** `recovery_hidpi.py` constructs
  `DoclingBackend(device="cpu", ocr_languages=["en", "vi"])`, so E12 is a CPU
  measurement at the production language setting. E11 runs no model.

**Not recorded, and not reconstructed here:** the git commit at run time, the
run date, and the machine's contention state. Both probes predate the
convention used in `experiments/0NN/results.json`, which carries all three.
Timings from E12 should therefore be read as indicative — this VM is shared,
and a runtime without a recorded contention class is not a benchmark. The
recall and pixel figures do not depend on that caveat.
