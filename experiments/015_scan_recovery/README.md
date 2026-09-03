# 015 — Scan Recovery v1 against real scan documents

## Question

Experiments 013/014 measured `evidence_fusion`/`targeted_recovery` against
isolated OCR-stage output (raw backend text, not real `Page`/`Element`
objects). `scan_recovery.recover_page_elements` (the page-level
orchestration built on top of those two — trigger:
`verification.assess_ocr_agreement`, action: `evidence_fusion.fuse_page`)
had unit tests against synthetic stubs but had never been run through the
actual production route. This experiment asks: **does it help, on real
documents, when wired through the real pipeline** (`process_file`, strategy
`adaptive`, default config — `ocr_backend: docling`, so elements really do
carry Docling OCR text, `coordinate_unit="px"`, a real
`rendered_image_path` on disk — the exact preconditions the module assumes)?

## Method

Two scripts, both driving the real `process_file` entrypoint (not a
synthetic harness):

* `run_scan_recovery.py` — the 6 real `scan_quality` documents named in the
  corpus manifest (`hc_scan_vi`, `hc_scan_en`, `cmb_scan_multicol_en`,
  `cmb_scan_stamp_table_vi`, `cmb_scan_tiny_vi`, `ord_invoice_png_vi`).
  For each: run the production pipeline, record baseline recall, run
  `recover_page_elements` against the resulting `Page`, record every
  per-element trigger/decision, record final recall.
* `run_production_recovery.py` — same recovery pass applied to all 58
  corpus documents (125 pages), to check for regressions on documents
  recovery was never meant to touch (native PDF/office pages have no
  `rendered_image_path` and are skipped by construction — the loop is a
  no-op there, not a special case).

Device: `cuda` (GPU preflight **CLEAR** before both runs — 0 MiB used, 0%
util, no other processes; re-checked immediately before each run).
Recall metric: identical methodology to `run_benchmark.py`/experiment 013 —
exact substring match of each `must_contain` phrase against the assembled
document text (elements + table cells, NFC-normalized).

## 6 Case Outcomes

| document | baseline recall | triggered? | recovery action | accepted? | final recall | recovery runtime |
|---|---|---|---|---|---|---|
| `hc_scan_vi` | 0.250 | no (0/3 elements) | none | n/a | 0.250 | 3.54s |
| `hc_scan_en` | 0.667 | no (0/2 elements) | none | n/a | 0.667 | 0.89s |
| `cmb_scan_multicol_en` | 0.667 | no (0/2 elements) | none | n/a | 0.667 | 0.99s |
| `cmb_scan_stamp_table_vi` | 0.750 | no (0/19 elements) | none | n/a | 0.750 | 1.24s |
| `cmb_scan_tiny_vi` | 0.000 | **yes** (1/2 elements, agreement=0.23) | fuse_with_easyocr attempted | **rejected** — fusion resolved to `conflict`, not `keep_both_agree`/`keep_both_partial` | 0.000 | 1.02s |
| `ord_invoice_png_vi` | 0.714 | no (0/2 elements) | none | n/a | 0.714 | 1.22s |

The one trigger, in detail (`cmb_scan_tiny_vi`, element `p0-e1`):

```
old (Docling):  Điéu 2Tham Khoan chi trên 50.000.000 công quyén Phè dóng phải
fused attempt:  Điéu 2Tham Khoan chi trên 50.000.000 công quyén Phè dóng phải
                Quy che nay áp dung cho toan bộ nhan sư thupc công ty va cac
                chi nhanh Tham quyén phe d[...]
reasons: docling/easyocr word-agreement=0.23; below threshold 0.5;
         fusion status=conflict, not accepted as verified-better
decision: kept_old
```

This is the decision rule working exactly as designed (`scan_recovery.py`
docstring: "replace only if better") — low agreement correctly flagged a
real problem (tiny text, both backends struggling), but the fused result
is a `conflict` (similarity < 0.3, no real overlap), not a safe union, so
it was correctly declined rather than guessed at. **Net effect on this
6-case sample: zero elements replaced, zero recall change, in either
direction.**

## Production Corpus Impact

Full 58-document / 125-page corpus, `adaptive` strategy, GPU **CLEAR**,
`n_errors=0`:

| | before recovery | after recovery |
|---|---|---|
| mean text recall | 0.9491 | **0.9491** (unchanged) |
| documents changed | — | **0 / 58** |
| documents improved | — | 0 |
| documents regressed | — | 0 |

9 of 125 pages had a `rendered_image_path` (the scanned/image route —
`ord_certificate_png_en`, `ord_invoice_png_vi`, `hc_scan_vi`, `hc_scan_en`,
`hc_encoding_vi` ×2, `cmb_scan_tiny_vi`, `cmb_scan_stamp_table_vi`,
`cmb_scan_multicol_en`); every other page was correctly left untouched
(no image, no coordinate space to cross-check against — recovery is a
no-op there by construction, not a bug). Of those 9 pages, **1 triggered**
(`cmb_scan_tiny_vi`, the same case as above) and **0 were replaced**. The
0.9491 mean exactly matches experiment 011's post-picture-traversal-fix
baseline, an independent cross-check that this run reflects real current
production behavior rather than a harness artifact.

## Runtime

* 6-case run: `process_file` 1.1s–20.0s/doc (mostly Docling layout-model
  load on the first call), recovery pass 0.9s–3.5s/page (dominated by the
  extra full-page EasyOCR call `recover_page_elements` always makes,
  regardless of whether anything ends up triggered).
* Full corpus: 33.5s total `process_file` time, **+13.2s (+39%) total
  recovery time**, entirely spent on the 9 image-bearing pages (non-image
  pages cost 0.00s — the loop never touches them) — for zero documents
  changed. The cost is not "reasonable overhead for a safety net"; it is
  pure loss on this corpus, because the trigger essentially never fires
  and the one time it did, the action correctly declined.

## Root Causes

Answering the 5 questions this milestone was scoped around, from the data
above (not from assumption):

1. **Does low OCR agreement actually identify useful recovery targets?**
   Rarely, and when it does, "useful" and "actionable" turned out to be
   different things. It fired on 1/9 real scanned pages (11%), correctly
   flagging a genuinely bad region — but flagging is not the same as
   fixing: the fusion action available to it could not safely resolve that
   one case either.
2. **Which failures are fixed by direct OCR (this module's actual
   action)?** None, in this sample. `fuse_page`'s "keep_both_agree" /
   "keep_both_partial" paths never fired on real scan data here; the one
   place it engaged, it resolved to `conflict` and correctly refused.
3. **Which require segmentation?** Can't be answered by this module as
   built — `recover_page_elements` calls `evidence_fusion.fuse_page` only,
   never `targeted_recovery.recover_region` (the resegmentation-capable
   path from experiment 014). `cmb_scan_tiny_vi` — the one real trigger —
   is exactly the case 014 already flagged as its own unresolved case
   (tiny text, needs more than a plain crop+re-OCR); this milestone
   confirms scan_recovery v1 does not reach that path at all, not that
   segmentation itself would fail here.
4. **Which require higher resolution?** Plausibly `cmb_scan_tiny_vi` again
   (tiny text is the declared hard-case label; 0.23 cross-backend
   agreement is consistent with both readers genuinely struggling at
   render DPI 200) — but `recover_page_elements` v1 never calls
   `targeted_recovery`'s upscale attempt either, so this is inference from
   the failure shape, not a measurement this module produced.
5. **Which failures cannot be solved by the current deterministic stack?**
   The dominant category by far: **5 of 6 real scan documents have
   recall < 1.0 and never trigger recovery at all** — Docling and EasyOCR
   *agree* on the same incomplete or wrong reading (correlated error), so
   word-Jaccard agreement between them, the only trigger this module has,
   reports nothing suspicious. This is experiment 013's "correlated error"
   finding, now confirmed to be the dominant real-world failure mode, not
   a rare edge case: it accounts for 5/6 real cases and 4/5 non-triggering
   corpus scan documents with recall < 1.0. No cross-backend agreement
   signal — this one or any other built the same way — can catch a defect
   both backends share.

## What Recovery Solves

Nothing, on this corpus, as currently composed. The mechanism is
*safety-verified* (it never replaced anything with something worse — the
one trigger was correctly declined, and the 58-document run shows zero
regressions), which is exactly what the existing synthetic unit tests
(`tests/test_scan_recovery.py`) already lock in. But "never makes things
worse" and "makes things better" are different claims, and only the first
one is supported by real data.

## What It Cannot Solve

* **Correlated errors** (Docling and EasyOCR independently produce the
  same wrong/incomplete reading) — invisible to any two-backend agreement
  trigger by construction. This is the majority failure mode measured
  here (5/6 real cases, 4/5 non-triggering low-recall scan documents in
  the full corpus).
* **Genuine conflicts under a correct trigger** — the one case where the
  trigger did fire, the safest available action (`fuse_page`) could not
  turn two divergent readings into anything verified-better. Closing this
  needs the resegmentation/upscale machinery `targeted_recovery.py`
  already has (experiment 014) but that `scan_recovery.py` v1 does not
  call.

## Promotion Decision

No hedging, per instructions:

| | decision |
|---|---|
| **SCAN RECOVERY v1** (`recover_page_elements`: agreement-low trigger → `fuse_page` action) | **REJECT** |

**REJECT**, specifically for this module as currently composed and for
production wiring. The measurement is decisive, not merely insufficient:
6/6 real target documents unchanged, 58/58 full-corpus documents
unchanged, 1/9 real image-bearing pages triggered and 0/9 replaced, for
+39% recovery-stage runtime on every page it touches. It is not buggy —
the decision rule behaves exactly as designed and never regresses anything
— it is simply not useful on this corpus's actual failure distribution,
where the dominant defect (correlated error) is structurally invisible to
its only trigger.

This does **not** reject the underlying primitives it is built from:
`evidence_fusion` remains **PROMOTE** (experiment 013, as a merge policy
*when* two backends are already being run) and `targeted_recovery` remains
**EXPERIMENTAL** (experiment 014, sound but n=2). It rejects specifically
the page-level orchestration in `scan_recovery.py` — agreement-based
triggering wired to fusion-only action — as a thing worth running in
production or continuing to build on without first changing what triggers
it.

## Commit / Push

Committed: `evidence_fusion.py`/`targeted_recovery.py`/`scan_recovery.py`
+ their test suites (275 passed / 10 skipped / 0 failed, unchanged by this
milestone — no code changes, measurement only), experiments
013/014/015 in full, and the refreshed `results_adaptive.json` production
snapshot (mean recall 0.9491, matching this milestone's independent
reproduction). No new regression tests were added: every trigger/decision
path exercised by the real 6-case and 58-document runs — agreement-low
firing, fusion resolving to `conflict`, agreement staying high enough to
skip — is already exhaustively covered by the 5 existing synthetic unit
tests in `tests/test_scan_recovery.py`; this milestone is a corpus-level
empirical finding about *when* those already-tested code paths fire in
practice, not a new code behavior needing its own test.

## Next Highest-Value Step

`scan_quality` remains the corpus's largest unresolved failure class (5 of
6 real documents below full recall, none fixable by this module), and the
root-cause analysis above narrows it further than experiment 014 could:
the blocking mechanism is specifically **correlated error between Docling
and EasyOCR**, not "OCR is sometimes wrong." A cross-backend agreement
trigger cannot, by construction, ever address this — it needs either (a) a
third independent signal that doesn't correlate with either backend's own
failure mode (a plausibility/quality check *without* a second OCR pass —
`text_quality.assess_text` already exists and runs regardless of
agreement, worth checking directly against these 5 documents before
building anything new), or (b) accepting that recall on this failure class
requires a fundamentally different capability (higher-resolution
re-render, or a specialist model) rather than a smarter trigger over the
same two OCR backends.

**Recommended next step**: before any new model or VLM work, check what
`assess_text` alone (no agreement, no second backend) already flags on
the 5 non-triggering real scan documents — cheap to run (no GPU, no new
code), and it directly answers whether the existing plausibility gate
already sees these failures and simply isn't wired to *anything* for
them (a wiring gap, cheap to close) versus not seeing them at all (a real
capability gap, the actual case for new work).

**What NOT to do next:**
1. Do not wire `scan_recovery.py` into `cli.py`/production given the
   REJECT decision above — it would add pure latency for zero measured
   benefit on this corpus.
2. Do not start VLM research yet, per this milestone's own scope — the
   `assess_text`-alone check above is a same-day, no-new-dependency way to
   learn whether a VLM is even the right shape of fix before investing in
   one.
3. Do not extend `scan_recovery.py` to also call `targeted_recovery`'s
   resegmentation/upscale paths without first re-running this exact
   6-case + 58-corpus measurement — the honest next test of "does
   segmentation help" is against `cmb_scan_tiny_vi` specifically (the one
   real case that reached a trigger and still failed), not a broader
   rebuild.

## Reproduce

```bash
python experiments/015_scan_recovery/run_scan_recovery.py --device cuda --resource-state CLEAR
python experiments/015_scan_recovery/run_production_recovery.py --device cuda --resource-state CLEAR
```
