# Fusion + Recovery Milestone

**Question:** Can disagreement be converted into a cheap, targeted recovery
action that improves extraction without introducing more noise than it
removes?

**Dataset:** same 13-document OCR corpus as experiments 012/013
(`research/production_corpus/corpus/`), plus full re-runs of the 58-document
production-shaped corpus and the 14-document `research/hardcases/` corpus
for regression confirmation. **Config:** OCR stage isolated for the fusion
work (DPI 200, `["en","vi"]`); full pipeline (`--strategy adaptive`) for the
two regression benchmarks. **Backends:** `DoclingBackend` (`docling>=2.0`),
`EasyOCRBackend` (`easyocr==1.7.2`, direct). **Device:** CUDA (NVIDIA L4).
**Resource state:** CLEAR (0 MiB used, 0% util, no other process) confirmed
via `nvidia-smi` before every GPU run this session. **Code:** built on top
of HEAD `7aab649` (still unmodified — nothing committed); new/changed files
`src/doc_extraction/ingest/evidence_fusion.py` (bug fix),
`src/doc_extraction/ingest/targeted_recovery.py` (new),
`tests/test_evidence_fusion.py` (+3), `tests/test_targeted_recovery.py`
(new, 7 tests), `experiments/013_evidence_fusion/` (re-measured),
`experiments/014_targeted_recovery/` (this report).

---

## Fusion Bug

**OBSERVED:** experiment 013 diagnosed that `EvidenceGroup.fused_text()`'s
`keep_both_agree` branch emitted only the EasyOCR side of an agreeing
region, which could silently drop a word that existed only on the Docling
side (the "Section 1. Scope" case: Docling's reading contained the digit
`1` that EasyOCR's reading of the same region lacked; word-Jaccard
similarity was 0.80 — correctly judged "agree" — but not identical).

**Fix:** `EvidenceGroup._merge_agreeing_tokens()` in `evidence_fusion.py`.
Structured, not a string hack: EasyOCR's tokens are always kept; a Docling
token is appended to the output **only if** its own normalized word set
contains at least one word absent from the combined EasyOCR reading of
that region. A Docling token that is a pure subset of what EasyOCR already
covers contributes nothing and is excluded — so a region where the two
sides read identically (the common case) still emits exactly one copy.
Operates on `EvidenceToken` objects (text + bbox), never on raw
concatenated strings.

**Regression tests added** (`tests/test_evidence_fusion.py`):
`test_agree_branch_preserves_word_only_docling_has` (reproduces the exact
"Section 1. Scope" case and asserts `1` and `applies` both survive),
`test_agree_branch_does_not_duplicate_when_sides_are_identical` (guards
against re-introducing duplication for the identical-content case),
`test_agree_branch_adds_only_the_docling_token_with_new_words` (guards a
multi-token group: a fully-redundant Docling token must not create a
second copy). All 3 pass; full suite is 270 passed / 10 skipped (was 260
before this milestone).

**LIMITATION:** the fix is a subset check at token granularity, not word
order or phrase structure — a recovered word is appended at its source
token's position, which can read awkwardly (e.g. a stray digit inserted
mid-sentence) even though the word itself is now present. This project's
own recall scoring is word-set-based, so this doesn't cost measured recall,
but a consumer expecting fluent prose from fused text would notice.

## Fusion Results

Full re-run of experiment 013's 13-document A/B/C comparison, same corpus,
same rendering, GPU CLEAR:

| policy | word recall | exact recall | duplicate rate | conflict rate |
|---|---|---|---|---|
| A — EasyOCR alone | 0.9111 | 0.5267 | 0.188 | — |
| B — naive union | 0.9286 | 0.5716 | 0.561 | — |
| C — evidence fusion (pre-fix) | 0.9158 | 0.5364 | 0.245 | 0.042 |
| **C — evidence fusion (post-fix)** | **0.9286** | **0.562** | **0.373** | **0.042** |

**OBSERVED:** the fix closes the entire recall gap to naive union — C's
word recall now equals B's exactly (0.9286 = 0.9286), and exact recall
(0.562) is within 1 point of B's (0.5716), while duplicate rate stays
**33% lower than naive union's** (0.373 vs 0.561). Conflict rate is
unaffected (0.042, same 2/96 groups) — expected, since the fix only
touches the `keep_both_agree` branch, not conflict detection.

**INTERPRETATION:** fusion now strictly dominates naive union on this
corpus: equal-or-better recall on every one of the 13 documents (verified
per-document, not just in the mean), meaningfully less duplication, plus
provenance and conflict-flagging that naive union has no equivalent of.
This was not true before the fix (2/13 documents regressed against union).

**LIMITATION:** duplicate rate (0.373) rose from the pre-fix number
(0.245) — expected and correct, not a new defect: the fix's whole purpose
is to stop silently dropping content, and doing so means some groups that
were wrongly collapsed to one copy now correctly include both readings'
distinct words. n=13, synthetic corpus, as every number in this milestone.

## Correlated Errors

**OBSERVED:** the two documents flagged by experiment 013
(`ord_contract_vi`, agreement 0.93; `hc_low_contrast_vi`, agreement 0.98 —
both with word recall 0.782) were tested against 5 signals for whether any
cheaply distinguishes "genuine agreement" from "correlated wrong
agreement," using a comparison set of 5 genuinely-high-recall,
high-agreement documents (`hc_scan_en`, `cmb_scan_multicol_en`,
`ord_contract_en`, `hc_tiny_text_en`, `cmb_multicol_table_en`):

| signal | `ord_contract_vi` | `hc_low_contrast_vi` | comparison set range |
|---|---|---|---|
| mean bbox_overlap (geometry) | 0.981 | 0.970 | 0.904–0.975 |
| mean EasyOCR confidence | 0.815 | 0.904 | 0.802–0.943 |
| min EasyOCR confidence | 0.543 | 0.489 | 0.606–0.741 |
| `assess_text` on fused doc | not suspicious | not suspicious | not suspicious (all) |

**`ord_contract_vi` has the *highest* geometry overlap of the entire set
(0.981)**, and both correlated-error documents' mean confidence sits
inside or above the comparison set's range. Only *minimum* confidence is
somewhat lower for the two error cases (0.543, 0.489 vs 0.606–0.741) — a
weak, single-signal hint, not a clean separator, and n=2 vs n=5 is too
small to trust a single lower-tail statistic. `assess_text`'s language
plausibility gate — now genuinely engaged at whole-document granularity
(200+ chars) — passes cleanly on every document in both groups: **wrong
OCR output that reads as fluent, correctly-scripted text is invisible to
a plausibility gate by design**, since plausibility checks decoding
sanity, not correctness against ground truth.

**INTERPRETATION — answering section 6's exact question:** with the four
cheap signals tested (geometry, mean confidence, min confidence, language
plausibility), **none cleanly distinguishes true agreement from correlated
wrong agreement** on this corpus. This is a clean negative result, not an
inconclusive one: `ord_contract_vi`'s geometry score being the *highest in
the entire comparison* is a specific, falsifiable counterexample to
"tighter geometric alignment implies more trustworthy," not just an absence
of correlation.

**LIMITATION:** "layout context" (document position, e.g. title vs. body,
table vs. paragraph) was named in the mission but not tested — `OCRToken`
does not currently carry a layout-role field, and adding one is plumbing
work this milestone's scope (no redesign) does not justify for an n=2
investigation. Recorded as untested, not as tested-and-failed. n=2 known
error cases is far too small to rule out a real signal existing that this
sample happens not to reveal — the honest conclusion is "the four cheap
signals available now don't help," not "no signal could ever help."

## Targeted OCR

Built `targeted_recovery.py`: crop the group's bbox (+10px padding) → try
plain re-OCR, 3x-upscaled re-OCR, and (if the crop's projection profile
finds >1 line band) resegmented-then-re-OCR'd — then a decision rule that
only replaces if the best candidate clears both a plausibility gate and a
similarity-improvement margin.

Run against the two real CONFLICT groups this corpus produces (not
hand-picked — the only two the fusion engine itself flags):

| document | docling | easyocr | plain re-OCR | upscale re-OCR | resegment re-OCR | decision |
|---|---|---|---|---|---|---|
| `cmb_multicol_table_en` | `"Ijob"` | `"job"` | `"job"` (conf 0.9998, sim 1.00) | `"Ijob"` (conf 0.804, sim 1.00 to docling) | `"Ijob"` (conf 0.968) | **REPLACED** — plain re-OCR chosen, similarity 1.00 > max(0.00, 0.5) |
| `cmb_scan_tiny_vi` | (garbled) | (garbled) | best sim 0.49 | best sim 0.39 | best sim 0.37 | **KEPT OLD** — no candidate cleared max(0.23, 0.5) |

**OBSERVED:** the decision rule worked exactly as designed on real data —
accepted the clean, high-confidence resolution and rejected the unresolved
case rather than swapping in an equally unreliable third guess. Note the
`upscale`/`resegment` attempts on `cmb_multicol_table_en` actually
*regressed toward Docling's wrong reading* (`"Ijob"`, sim 1.00 to Docling)
— the decision rule correctly preferred `plain` (sim 1.00 to EasyOCR,
higher confidence) over these, which is why picking the argmax candidate
by (similarity, confidence) rather than always trusting the "fanciest"
method matters.

## Segmentation

**OBSERVED:** for the unresolved `cmb_scan_tiny_vi` conflict, the
projection-profile line segmenter (`segment_lines`) correctly found **3
clean, evenly-spaced 13px bands** (y-ranges `[15,28]`, `[45,58]`, `[76,89]`
in a 102px-tall crop) — the segmentation itself was not wrong. Yet
resegmented re-OCR scored *worse* (max similarity 0.37) than OCR-ing the
whole crop at once (0.49).

**INTERPRETATION:** the most likely mechanism, given the document is
Vietnamese: this project's own diacritics (`ế`, `ọ`, `ự`, ...) extend
further above and below a line's core ink band than the segmenter's fixed
2px vertical padding allows for, so tightly cropping to each detected
band plausibly clips diacritic marks the recognizer needs. This also
explains why the *earlier* naive-crop finding (experiment 013:
upscaling alone didn't help) wasn't primarily a resolution problem either
— the real defect is that the anchor itself spans genuinely low-quality,
multi-paragraph scan content that a projection-profile split cannot
recover, and adding a coarse pre-segmentation step in front of EasyOCR
(which already runs its own line/word detector, CRAFT, internally) is
redundant on legible input and actively harmful when the pre-segmentation
cuts through content the recognizer needed intact.

**LIMITATION:** n=1 unresolved case. The diacritic-clipping hypothesis is
mechanistically plausible and consistent with the measured direction of
the regression, but was not isolated by a controlled padding sweep this
session (out of scope — "do not add a heavy model," and a padding sweep on
n=1 would not generalize either). If this path is pursued further, the
cheapest next test is enlarging per-band vertical padding (e.g. to a
fraction of estimated line height rather than a fixed 2px) before
concluding resegmentation doesn't help in general.

## Recovery Decision

Implemented exactly as specified: recovery is only invoked on groups
already marked CONFLICT (precondition enforced by the caller, not
re-checked inside `recover_region`); a candidate replaces the old
evidence only if it passes `assess_text`'s plausibility gate, its
confidence clears `LOW_CONFIDENCE_MAX` (0.4, reused from
`evidence_fusion.py` for consistency), and its similarity to *either*
original reading exceeds `max(original_agreement, 0.5)`. Never blindly
replaces — verified against both real conflicts (1 replace, 1 correctly
declined) and 3 unit tests
(`test_recovery_replaces_when_a_candidate_clearly_resolves_the_conflict`,
`test_recovery_keeps_old_evidence_when_nothing_resolves`,
`test_recovery_rejects_low_confidence_even_if_similar` — the last confirms
a high-similarity-but-low-confidence candidate is still rejected, so the
two conditions are independently enforced, not similarity alone).

## Production Impact

**Nothing was wired into `cli.py`, `pipelines/base.py`, or
`configs/*.yaml` this milestone.** Re-running the full pipeline on both
regression corpora confirms this precisely:

| corpus | metric | this session | prior baseline (experiment 011) |
|---|---|---|---|
| 58-doc production (`--strategy adaptive`) | mean recall | 0.9491 | 0.9491 |
| 58-doc production | fully recovered | 52/58 | 52/58 |
| 14-doc hardcases (`adaptive`) | mean recall | 98% | 98% (13/14 full recovery) |

**Zero regression, exactly as expected** — fusion and recovery are
importable, tested research modules, not part of the live OCR path.
Section 9's precondition ("if the recovery prototype clearly improves
hard cases without unacceptable cost, wire ONE production path") is not
met at the *production pipeline* level yet, because its prerequisite —
evidence fusion itself running as part of the live OCR stage — is still
EXPERIMENTAL, not promoted (see Promotion Decisions). Wiring recovery on
top of a fusion layer that isn't in the pipeline would mean building the
generic multi-model integration section 10 explicitly says not to build
yet. This is a scope boundary, not an oversight.

## Runtime

Device: CUDA (NVIDIA L4), resource state CLEAR throughout every
measurement this session.

| operation | latency |
|---|---|
| Docling recognize() (warm) | ~1.27s/page |
| EasyOCR recognize() (warm) | ~1.07s/page |
| `fuse_page` + `assemble_fused_text` | ~0.5ms/page |
| recovery: plain crop re-OCR | 64–620ms/attempt |
| recovery: upscaled crop re-OCR | ~260ms/attempt |
| recovery: one resegmented band re-OCR | ~94ms/attempt |
| full pipeline, 58-doc corpus | p50 0.048s, p90 1.318s, p99 14.839s |
| full pipeline, 14-doc hardcases | 20.0s total |

**INTERPRETATION:** recovery's cost is negligible in aggregate: conflicts
are rare (2/96 groups, 2.1%, in the 13-doc corpus), each conflict costs 2–3
small-crop OCR calls (well under 1s total), and recovery never runs on the
97.9% of groups that aren't flagged. The dominant cost of *any* multi-backend
approach remains running a second full-page OCR pass (fusion's own finding,
unchanged from experiment 012/013) — recovery adds essentially nothing on
top of that.

## GPU

`nvidia-smi` checked before every GPU-using command this session (11
checks). GPU state was **CLEAR** (0 MiB used, 0% utilization, no other
process) at every single check — no LIMITED or PROTECTED state was
encountered, so no yielding or pressure-reduction behavior was exercised
this milestone.

## Tests

270 passed, 10 skipped (was 260 passed / 10 skipped at the start of this
milestone) — 10 new tests: 3 fusion-bug regression tests
(`test_evidence_fusion.py`) + 7 targeted-recovery tests
(`test_targeted_recovery.py`, including 2 genuine bugs the tests caught
and this session fixed before they shipped: see What Failed).

## What Failed

Two real bugs were caught by tests written this session, before any
corpus number depended on them:

1. **Otsu threshold tie-break.** The initial `_otsu_threshold`
   implementation used strict `>` when tracking the maximum between-class
   variance. On a cleanly bimodal image (exactly two intensity levels,
   which a hand-drawn test fixture — and potentially a genuinely
   high-contrast scan — produces), every intensity level *between* the
   two classes ties for maximum variance, and `>` keeps the *first* one
   (right at the dark class's own value), which `ink = gray < threshold`
   then classifies as background — silently detecting zero ink. Fixed by
   using `>=` so the *last* tied threshold is kept, landing the cutoff on
   the correct side of the dark class. Caught by
   `test_otsu_threshold_separates_light_and_dark` and
   `test_segment_lines_finds_two_bands_with_a_real_gap`, both of which
   failed before the fix.
2. **Test fixture bug, not module bug**: `PIL.Image.new("RGB", size,
   color=255)` does not fill all three channels with 255 — passing a
   scalar `color` to a multi-band mode is a genuine PIL gotcha that fills
   only the first channel, producing a dark image, not white. Every
   synthetic test image had to be built in single-band `"L"` mode first,
   then converted to `"RGB"`, to actually be white. Recorded here because
   it is the kind of silent-wrong-input bug that would have made a test
   "pass" for the wrong reason if the segmentation bug above hadn't also
   been present to surface it via a clearly wrong band count.

## What We Learned

1. **A "picks one side" merge rule is unsafe even when the sides
   "agree"** — 70%+ word-Jaccard similarity is not identity, and treating
   it as identity for the purpose of "which string to emit" silently
   drops content. The fix (token-level subset check) generalizes the
   lesson: prefer structural inclusion/exclusion decisions over string
   selection whenever the underlying evidence is still available as
   structured tokens.
2. **Correlated errors remain fundamentally undetectable by the cheap
   signals available** (geometry, confidence, plausibility) — this
   milestone's negative result on 4 signals × 2 known cases is a stronger
   basis for *not* pursuing more threshold-tuning on this specific problem
   than it is for building a fifth signal to try next.
3. **A classical pre-segmentation step is not free** — it can actively
   hurt when the downstream OCR engine already performs equivalent
   segmentation internally (EasyOCR's own line/word detector) and the
   pre-segmentation's assumptions (fixed padding) don't hold for the
   script in question (Vietnamese diacritics).
4. **"Verify before replace" is cheap to build and it worked on the first
   real test**: the decision rule never needed hand-tuning to correctly
   accept the true win and reject the true non-win on the 2 real cases
   available — a good sign for the architecture, though n=2 does not prove
   it will hold at scale.
5. **Bugs hide in test infrastructure as easily as in the code under
   test** — the PIL scalar-color gotcha would have silently invalidated
   every segmentation test's premise if the Otsu bug hadn't also been
   present to make the wrong band-count impossible to miss.

## Promotion Decisions

No hedging, per instructions:

| | decision |
|---|---|
| **FUSION** | **PROMOTE** |
| **TARGETED OCR RECOVERY** | **EXPERIMENTAL** |

**FUSION — PROMOTE**, specifically as *the merge policy to use whenever
two OCR backends' output is being combined* — it now strictly dominates
naive union (equal-or-better recall on all 13 documents, 33% less
duplication, real provenance) with the diagnosed defect fixed and
regression-tested. This does **not** mean "always run two OCR backends in
production" — that is a separate cost decision (doubling OCR-stage time
per page) experiment 012 already declined to make on this corpus size,
and this milestone did not re-open it. It means: *if and when* two
backends are run, fuse them this way, not by naive concatenation.

**TARGETED OCR RECOVERY — EXPERIMENTAL.** The decision rule is sound and
safety-verified (never regresses; correctly resolved the one case that was
resolvable and correctly declined the one that wasn't), but the evidence
base is n=2 real conflicts — nowhere near enough to promote to an
autonomous production path. Worth continuing to build on; not worth
wiring in yet.

**Next highest-value direction: A — scan quality / scan recovery.**
`scan_quality` remains the single largest failure class in the 58-document
corpus this session re-confirmed (n=6, 1 critical, unchanged from
experiment 010/011), and this milestone's *own* unresolved case
(`cmb_scan_tiny_vi`) is a `scan_quality` document — the one place recovery
did not work is exactly the failure class with the most outstanding
production impact. Table intelligence (n=2+2 combined) and real EN/VI data
remain real needs but are smaller by this session's own measured failure
distribution, and a VLM specialist has no motivating case yet — this
milestone did not produce one where "native OCR + direct OCR" was proven
unable to resolve a region.

**I recommend A — scan quality / scan recovery — next, because it is
where this exact milestone's own recovery attempt failed, on the exact
failure class experiment 010 ranked #1 and that ranking has not moved.**
Concretely: investigate whether per-band padding proportional to detected
line height (rather than a fixed 2px) fixes the diacritic-clipping
hypothesis from Segmentation above, and whether Docling's own multi-line
anchor grouping can be split *before* fusion (at the anchor construction
step) rather than only after a conflict is already flagged.

## Next Milestone

Per section 12/19: not scan-quality in the abstract, but the two
concretely scoped follow-ups this milestone's own evidence points to
(padding-proportional resegmentation; splitting multi-line Docling anchors
earlier in the pipeline) — both testable against the same
`cmb_scan_tiny_vi` case this session already instrumented, so the next
session can tell immediately whether either closes it, rather than
re-deriving the problem from scratch.

**What NOT to do next:**
1. Do not wire fusion or recovery into `cli.py`/`configs/*.yaml` yet — the
   FUSION promotion above is a policy-choice endorsement, not a "make this
   the default OCR path" instruction; that remains a separate,
   still-unmade cost decision.
2. Do not build a general recovery engine or a generic fusion framework
   off an n=2 conflict sample — re-run this same instrumentation against
   a larger conflict set (once padding/anchor-splitting fixes exist) before
   generalizing the recovery loop beyond the two paths tested here.
3. Do not chase a fifth "does this catch correlated errors" signal without
   new information (ground truth, a third independent OCR source, or real
   non-synthetic data) — four cheap signals were tested this session and
   none worked; the honest next step there is different data, not more
   threshold engineering on the same 13 documents.
