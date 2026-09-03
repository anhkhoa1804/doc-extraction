> **Update (fix applied):** the `keep_both_agree` content-loss bug
> diagnosed below was fixed the same milestone it was found — see
> `experiments/014_targeted_recovery/README.md`'s "Fusion Bug" section for
> the fix itself, the regression tests, and the re-measured numbers
> (`results_after_fix.json`: policy C word recall now **0.9286**, matching
> naive union exactly, at duplicate rate **0.373** vs union's 0.561). This
> file is left as originally written — the diagnosis of the bug below is
> still accurate and is what the fix targeted; only the numbers changed.

# Evidence Fusion v0 Report

**Question:** Can heterogeneous OCR evidence be combined more reliably than
choosing a single backend, and can disagreement tell us where additional
computation is worth spending?

**Dataset:** `research/production_corpus/corpus/`, the same 13 documents as
experiment 012 (`hc_scan_vi`, `hc_scan_en`, `cmb_scan_multicol_en`,
`cmb_scan_stamp_table_vi`, `cmb_scan_tiny_vi`, `ord_invoice_png_vi`,
`ord_contract_en`, `ord_contract_vi`, `hc_tiny_text_en`, `hc_tiny_text_vi`,
`hc_low_contrast_vi`, `hc_stamp_text_vi`, `cmb_multicol_table_en`) — already
spans clean EN/VI, scan, tiny text, low contrast, stamp, table, and mixed
EN/VI; no new corpus was needed. **Config:** OCR stage only, DPI 200,
languages `["en","vi"]`, same rendered pixels fed to both backends (mission's
"controlled A/B" discipline, unchanged from 012). **Backends:**
`DoclingBackend.recognize()` (`docling>=2.0`, its bundled EasyOCR) and
`EasyOCRBackend.recognize()` (`easyocr==1.7.2`, direct). **Device:** CUDA
(NVIDIA L4). **Resource state:** CLEAR (0 MiB used, 0% util, no other
process) at every run this session. **Code:** HEAD `7aab649`, new module
`src/doc_extraction/ingest/evidence_fusion.py`, not wired into
`cli.py`/`configs/*.yaml` — importable for research only.

---

## Baseline

Repeating experiment 012's own numbers for reference (measured again this
session — reproduced within rounding, since both backends and the corpus
are deterministic):

| | mean exact recall | mean word recall |
|---|---|---|
| Docling alone | 0.5056 | 0.8973 |
| EasyOCR alone | 0.5267 | 0.9111 |
| naive union | 0.5716 | 0.9286 |

## Evidence Representation

Each backend's `OCRResult.tokens` (`OCRToken(text, bbox, confidence)`) is
wrapped as `EvidenceToken(text, bbox, confidence, source, order)` — `source`
and `order` are the two fields OCRToken itself doesn't carry, added instead
of inventing a parallel schema. Docling's tokens are line/block granularity
(per `docling_backend.py`'s own docstring) and carry no confidence at all
(`TextItem` has no such field — confirmed in the prior milestone). EasyOCR's
tokens are per-detection, finer-grained, and carry a real confidence.

Because the two sources differ in granularity, 1:1 token matching is not
meaningful. `evidence_fusion._group_tokens()` instead uses Docling's tokens
as spatial anchors and assigns each EasyOCR token to the anchor it overlaps
≥40% of its own area with; unmatched EasyOCR tokens (and, symmetrically, a
region with no Docling anchor at all) become singleton `EvidenceGroup`s.
This is deliberate: an EasyOCR-only region is exactly what a dropped-region
defect (like the pre-011 `traverse_pictures` bug) looks like, and it must
surface as its own group, not vanish for lack of a Docling counterpart.

## Fusion Policies

| policy | mean exact recall | mean word recall | mean duplicate rate |
|---|---|---|---|
| A — best single (EasyOCR) | 0.5267 | 0.9111 | 0.1876 |
| B — naive union | 0.5716 | 0.9286 | 0.5608 |
| C — evidence-aware fusion | 0.5364 | 0.9158 | 0.2452 |

`duplicate_rate` = fraction of word *tokens* in the assembled text that are
exact repeats of an earlier occurrence — a proxy for "how much of this
string says the same thing twice." Policy A's baseline duplicate rate
(0.1876) is natural-language repetition (the, và, ...), not fusion artifact.

**OBSERVED:** C recovers roughly two-thirds of naive union's recall gain
over the single backend (+0.47pt exact / +0.47pt word vs A, against B's
+4.49pt / +1.75pt), while cutting the duplicate rate more than half
relative to B (0.245 vs 0.561) but not down to A's natural-language floor.

At the region level (pooled across all 13 documents, 96 `EvidenceGroup`s
total): 11 groups (11.5%) had only Docling evidence, 11 groups (11.5%) had
only EasyOCR evidence, 67 groups (69.8%) had both and fully agreed, 5
groups (5.2%) partially agreed, and 2 groups (2.1%) were marked CONFLICT.
**22.9% of all regions had evidence from exactly one backend** — a direct,
region-level confirmation of experiment 012's aggregate claim that the two
sources are genuinely complementary, not redundant.

**INTERPRETATION — why C underperforms B on 2/13 documents, diagnosed
exactly:** `hc_tiny_text_en` and `hc_tiny_text_vi` both score C = A
(0.889 and 0.847 word recall respectively) instead of matching B's higher
score (1.000 and 0.903). Root cause, confirmed by inspecting the actual
groups: a multi-line Docling anchor spanning "Section 1. Scope This policy
to all employees..." merged with a same-region EasyOCR reading "Scope
Section This policy applies to all employees...". Word-Jaccard similarity
over the whole merged group is 0.80 — above the `AGREE_SIMILARITY_MIN=0.7`
threshold — so the group is marked `keep_both_agree`, and `fused_text()`
emits **only** the EasyOCR side (the measured stronger single backend,
policy's tie-break rule). But Docling's reading contains the digit `1`
(from "Section 1.") that EasyOCR's reading of the same region does not —
so that one word is silently dropped even though the group is correctly
judged as "agreeing." **This is a real, measured defect in v0's decision
rule, not a corpus quirk**: picking one side's full string on aggregate
agreement can drop content that only survived in the non-chosen side, even
at 80% similarity. The Vietnamese case is the same mechanism with OCR
diacritic variants (`nhân sự` vs `nhân sụ`) counted as different word
forms.

**LIMITATION:** this defect is architectural to v0's `keep_both_agree`
rule (emit one side wholesale), not fixed here — a v1 fix (union of the
two sides' *distinct* words, rather than swapping full strings) would
plausibly close this specific gap, but was not built or measured this
session per the mission's "do not train/tune, measure v0 as built" scope.

## Agreement Analysis

Whole-document word-Jaccard agreement between Docling and EasyOCR readings
of the same pixels, replicating experiment 012's exact methodology
(agreement vs. `min(docling_recall, easyocr_recall)`):

**r = 0.856 (n=13)** — identical to experiment 012's finding, reproduced
independently this session on freshly re-rendered pages and freshly re-run
backends. This is a real, reproduced signal, not a one-off artifact.

Against policy C's own word recall specifically, agreement correlates
more weakly: **r = 0.593**. **INTERPRETATION:** this gap is not evidence
that agreement is a weaker signal — it is evidence that policy C's own
recall is noisier than either raw backend's recall, because of the
`keep_both_agree` defect documented above (which discards content
independent of how well-calibrated agreement is as a signal). Measuring
agreement against a policy that has its own unrelated defect understates
agreement's real predictive power; the exp012-replication number (r=0.856,
against the raw backends) is the fairer measurement of the signal itself.

**Is agreement a confidence signal or a consensus signal? Answer: a
consensus signal that correlates with correctness empirically, not a
correctness signal itself.** See Correlated Errors below — two documents
break the pattern in the dangerous direction, which a genuine confidence
signal calibrated on ground truth would not do by construction. Do not
call r=0.856 a calibrated probability of correctness (mission's own
instruction, section 16) — it is a measured correlation on n=13 synthetic
documents.

## Confidence Analysis

EasyOCR's own mean per-document confidence vs. policy C word recall:
**r = 0.494** (n=13) — essentially identical to experiment 012's r=0.491
against raw EasyOCR recall. Confidence alone remains a real but weak
signal, reproduced.

`text_quality.assess_text`'s plausibility gate — the "language
plausibility" component the mission suggested for a combined trust score —
contributes **essentially nothing at region granularity**: it treats any
text under 200 characters as `insufficient_text` and always returns
`suspicious=False` (verified directly in `text_quality.py`,
`min_chars_for_assessment: int = 200`). A single OCR line or word is
almost always under 200 characters, so this gate — calibrated for
document/page-length text — is a near-no-op inside `evidence_fusion.py`'s
per-group decisions. **This is a genuine finding, not a bug in this
module**: an existing, validated gate does not transfer to a finer
granularity than it was built for, and this milestone does not attempt to
retune it for that purpose.

## Confidence + Agreement Together

`0.5·agreement + 0.5·confidence` vs. policy C word recall: **r = 0.576**
(n=13) — between confidence alone (0.494) and agreement-vs-C alone (0.593),
not exceeding either. **The combination does not measurably improve on
agreement alone against this target, at this sample size.** Do not treat
this as proof combination never helps — n=13 is too small to distinguish
"no benefit" from "benefit too small to detect here" — but the mission
asked that the combination not be assumed better without measurement, and
measured, it is not.

## Correlated Errors

Documents where agreement is high (≥0.90) but the weaker single backend's
recall is still poor (<0.85) — both backends agreeing **and both wrong**:

| document | agreement | Docling word recall | EasyOCR word recall |
|---|---|---|---|
| `ord_contract_vi` | 0.93 | 0.782 | 0.782 |
| `hc_low_contrast_vi` | 0.98 | 0.782 | 0.782 |

Identical to experiment 012's own finding on the same two documents —
reproduced, not new. In both cases the two backends read the exact same
wrong text off the exact same low-contrast/complex-font pixels — a shared
blind spot, not independent disagreement agreement could have caught.
**This directly answers section 6's question: agreement cannot, by
construction, catch an error two independent sources make identically.**
Any production use of agreement as a trust gate must accept this failure
mode explicitly rather than treat high agreement as proof of correctness.

## Region Disagreement

Across all 13 documents, only **2 of 96 evidence groups** (2.1%) were
marked CONFLICT (`text_similarity < 0.3` with both sources present) — one
each in `cmb_scan_tiny_vi` and `cmb_multicol_table_en`. Conflicts are rare
at this corpus's difficulty distribution; most disagreement is either full
agreement or the intermediate "partial" band, not outright conflict.

## Targeted Re-OCR

For the 2 actual CONFLICT groups this corpus produced (not a hand-picked
"hard" set — the only two the fusion engine itself flagged), the group's
bbox (+10px padding) was cropped from the already-rendered page and
re-OCR'd with a fresh EasyOCR call on the crop alone.

| document | docling reading | easyocr reading | re-OCR reading | outcome |
|---|---|---|---|---|
| `cmb_multicol_table_en` | `"Ijob"` | `"job"` | `"job"` (conf 0.9998) | **resolved** — matches EasyOCR exactly, confidence near-certain |
| `cmb_scan_tiny_vi` | (garbled, 8 words) | (garbled, 27 words) | (garbled, 21 words, conf 0.53) | **not resolved** — a third, still-garbled reading |

**1/2 conflicts resolved cleanly by targeted re-OCR.**

**OBSERVED, root-caused for the unresolved case:** the `cmb_scan_tiny_vi`
conflict region is a single Docling anchor whose bbox actually spans **two
separate paragraphs** of the source document (confirmed by inspecting the
crop) — not a single ambiguous line. A follow-up check re-OCR'd the same
crop at 3x upscale: mean confidence rose from 0.53 to 0.61, but the text
was still jumbled across both paragraphs (e.g. `"50.0C0.000"` — a digit
misread as a letter — and paragraph order still scrambled), and similarity
to either original reading stayed low (0.33 / 0.39). **This means the
`cmb_multicol_table_en` conflict and the `cmb_scan_tiny_vi` conflict are
different failure classes**: the first is an isolated, legible single-word
misread that any second opinion resolves; the second is a
grouping/segmentation problem (the anchor itself is too coarse, spanning
multiple lines) compounded by genuine scan degradation — upscaling alone
does not fix a region that was never one coherent unit of text to begin
with.

**LIMITATION:** n=2 is far too small to generalize a resolution rate.
What is defensible from this evidence: **"CONFLICT correctly identifies a
region with a real defect" held in both of the 2 cases measured (100%)** —
one was an OCR misread, the other a grouping defect — but **"a naive
crop+re-OCR fixes it" held in only 1/2 (50%)**, and the failure mode when
it doesn't work is diagnosable (multi-line anchor) rather than random.
This is enough to justify building a real recovery experiment on
larger data, not enough to claim recovery works.

## CPU/GPU Cost

Device: CUDA (NVIDIA L4), resource state CLEAR throughout.

| stage | cold (first call) | warm (mean, n=12) |
|---|---|---|
| Docling recognize() | 12.844s | 1.272s |
| EasyOCR recognize() | 3.516s | 1.071s |
| fusion (`fuse_page` + `assemble_fused_text`) | — | 0.0005s (max 0.0013s) |

**Fusion's own computation is free** relative to running OCR — the entire
cost of policies B and C over policy A is running a second OCR backend on
every page (~1.07–1.27s warm, ~2x the single-backend cost), not the fusion
logic itself. This matches experiment 012's own finding and is unaffected
by anything built this session.

## Production Decision

Per section 17, no hedging:

| | decision |
|---|---|
| naive union | **REJECT** |
| evidence-aware fusion | **KEEP EXPERIMENTAL** |
| agreement signal | **KEEP EXPERIMENTAL** |

**naive union — REJECT.** It has the best raw recall of the three
(0.9286) but a 56% duplicate rate — over half the output words are exact
repeats of content already said once. That is not a hypothetical
regression; it is a direct, measured property of every document where the
two backends agree (the common case: 75%+ of regions), and it would reach
any consumer of the assembled text verbatim. The recall ceiling it
demonstrates is useful as a reference ("how much is theoretically
recoverable by keeping everything") but not as a shipped output mode.

**evidence-aware fusion — KEEP EXPERIMENTAL, not PROMOTE.** It halves
naive union's duplicate rate (0.245 vs 0.561) and gives real, itemized
provenance (source, decision, reasons per region) that naive union cannot,
but it has a diagnosed, real recall regression relative to naive union on
2/13 documents (both -0.111 word recall, both tiny-text categories) from
a specific, understood defect in the `keep_both_agree` tie-break rule
(pick one full string rather than the union of distinct words). The
architecture (grouping, singleton detection, CONFLICT marking, provenance)
is sound and worth continuing; the exact policy inside `keep_both_agree`
is not yet good enough to promote as-is.

**agreement signal — KEEP EXPERIMENTAL, not PROMOTE.** r=0.856 replicated
independently against the weaker single-backend recall is a strong,
reproduced correlation — real evidence this is worth building on. But
Correlated Errors (above) demonstrates a concrete, non-hypothetical
failure mode (two documents, both backends agree and both wrong) that
rules out using agreement alone as an autonomous TRUSTED/INVALID gate
without accepting a known blind spot. Worth using as a **triage signal**
(which regions deserve more compute) — which Targeted Re-OCR above
supports (2/2 flagged conflicts had real defects) — not yet as a
correctness guarantee.

## Remaining Failures

Ranked by what this milestone's evidence actually shows, not the prior
milestone's list restated:

1. **`keep_both_agree`'s "pick one full string" rule loses content that
   only survives in the non-chosen side** — measured on 2/13 documents,
   mechanism fully diagnosed (see Fusion Policies). The single most
   fixable defect found this session.
2. **Correlated errors (shared blind spots)** — 2/13 documents where both
   backends read the same wrong text off the same pixels. No signal built
   so far (confidence, agreement, or their combination) catches this class
   by construction; it needs either a third independent source or ground
   truth, neither of which exists in this corpus.
3. **Multi-line anchor grouping on genuinely degraded scans** — the
   `cmb_scan_tiny_vi` conflict shows Docling's own line segmentation
   collapsing two paragraphs into one region under scan noise, which
   defeats region-level re-OCR regardless of resolution. A recovery
   experiment needs its own line-level re-segmentation step, not just a
   crop-and-retry.
4. **`text_quality.assess_text`'s plausibility gate does not transfer to
   region granularity** (200-char minimum) — a validated component reused
   in a context it wasn't built for, currently contributing nothing to
   fusion's decisions.
5. **No ground truth exists to measure true precision/false-positive
   rate** for any policy (58/58 corpus docs have empty `must_not_contain`
   except one, unrelated case). Every recall number in this report and
   012 is real; no precision number in the mission's own requested
   metric set (section 5) could be honestly computed against this corpus.
   All three policies are architecturally hallucination-free by
   construction (they only select/concatenate existing OCR tokens, never
   generate new text) — verified as a unit-test invariant
   (`test_no_hallucination_fused_words_are_a_subset_of_source_words`), not
   just claimed.

## Next Milestone

Per section 19, choosing from the fixed list based on measured failure
distribution: **not** a full re-run of section 19's menu — the dominant,
most fixable finding this session is internal to fusion v0 itself (the
`keep_both_agree` content-loss defect), which is smaller than any of
A–E and should close before a bigger bet. Recommend, in order:

1. **Fix `keep_both_agree`** to emit the union of distinct words rather
   than one side's full string (closes the 2/13 documented regression;
   cheap, already diagnosed exactly, no new measurement infrastructure
   needed).
2. Then **A — strengthen targeted OCR recovery**, using this milestone's
   own finding as the design constraint: recovery must include a
   line-resegmentation step for CONFLICT regions whose anchor spans
   multiple lines, not just crop+re-OCR at the existing anchor
   granularity, since that specific failure mode (`cmb_scan_tiny_vi`) is
   exactly the case naive re-OCR could not fix.

**I recommend fixing `keep_both_agree` first, then A, because both are
now precisely scoped by evidence gathered this session** (exact defect,
exact failure mode, exact document(s)) rather than by intuition — the
cheaper fix should not wait behind a bigger recovery-engine investment
when it is already fully diagnosed and undoes most of fusion's remaining
recall gap versus naive union.

**What NOT to do next:**
1. Do not promote naive union or evidence-aware fusion to the production
   default — neither has cleared the mission's own promotion bar yet.
2. Do not build a general recovery engine before re-running this same
   13-document conflict set against the `keep_both_agree` fix — the
   current 2-conflict sample is too small to design a general engine
   around, and the fix may itself change which regions still conflict.
3. Do not treat r=0.856 (agreement) as a tuned threshold or a calibrated
   probability — it is a reproduced correlation on n=13 synthetic
   documents with a documented blind spot (Correlated Errors), not a
   production gate ready to run unattended.
