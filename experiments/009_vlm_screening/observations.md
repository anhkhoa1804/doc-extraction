# Observations — 009

## 1. The headline: rejected as a page parser, on evidence

| Strategy | Mean recall (10 cases) | Total compute |
|---|---|---|
| native | 83% | ~0.4 s |
| **adaptive** | **93%** | ~37 s (14 docs) |
| visual | 66% | ~194 s |
| **PaddleOCR-VL, page** | **68%** | **1483 s** |

Roughly **40× the compute of the shipped adaptive router, for 25 points less
recall**. It strictly beats every cheaper strategy on **1 of 10** cases and
loses on **5**.

That is a clear answer to the question the mission poses — *which component
gives the best marginal value for this production target* — and the answer is
not "the newest model".

## 2. Where it actually wins, and it is worth having

| Case | native | adaptive | visual | **VLM** |
|---|---|---|---|---|
| `merged_cells` | 67% | 67% | 33% | **100%** |

One case, but a real one. The merged header cell that the native PyMuPDF
finder loses is recovered intact by the VLM's `Table Recognition:` prompt.
This is the only place in the corpus where the expensive model recovers
information that nothing cheaper can.

That is exactly the profile of a **specialist**, not a default: invoked on
tables where a cheap gate judges the native grid untrustworthy, which the
corpus suggests is roughly one document in ten.

## 3. Where it fails, and why the failures are structural

**`stamp_over_text`: 0%.** Native scores 100%. The seal covers the pixels, and
a vision model sees only pixels — the text underneath is not recoverable from
the image at all, while the PDF text layer still holds it perfectly.

This is the sharpest illustration in the whole corpus that **more capable is
not more informed**. No amount of model quality substitutes for having the
right evidence source. It also refutes the intuition (§13's warning) that a
VLM "solves" occlusion.

**`tiny_cells_table`: 33%** against 100% for native, and it took **456 s** —
the slowest case measured. Dense small text produces many vision tokens and
long generation, so the hardest cases are also the most expensive, which is
the worst possible cost curve for a recovery rung.

## 4. A disqualifying result for the production target

**`clean_vi`: 50%.**

Not a scan, not occluded, not small — a perfectly clean born-digital
Vietnamese page. The model dropped `Hạnh phúc` and `Nguyễn Thị Hương`, both
diacritic-dense. It returned 263 characters, so it read the page; it read it
wrongly.

Vietnamese is half the stated production population. A component that loses
half of a *clean* page in that language cannot be a default for this system,
whatever it scores on a public leaderboard. This is precisely the gap the
internal EN/VI corpus exists to expose and that OmniDocBench — which contains
no Vietnamese at all — structurally cannot.

## 5. Region role: the right shape, unproven at scale

| Case | Role | Recall | Seconds | Pixels |
|---|---|---|---|---|
| `tiny_text` | region | 100% | **4.08** | 868×227 |
| `tiny_cells_table` | region | 67% | 277.03 | 2227×895 |

`tiny_text` is the encouraging one: **4.08 s versus 94.75 s** for the same
case as a full page — 23× cheaper, same 100% recall. Cost scales with the
pixels you send, so cropping to the difficult region is the whole game.

`tiny_cells_table` shows the limit: its "region" is most of the page, so the
crop saves little and still costs 277 s. A recovery ladder only pays when the
difficult region is genuinely small.

Two cases is not a result. It is a promising shape that needs a real test.

## 6. VRAM: the weights are not the cost

| Stage | VRAM |
|---|---|
| after model load | **1,840 MiB** |
| peak, full-page inference | **12,992 MiB** |

A 0.96B model at bfloat16 is ~2 GB of weights, but page-level inference peaked
near **13 GB** — vision tokens for a 1653×2339 image, not parameters.

This matters twice over. It confirms the earlier correction that the paper's
"43.7 GB" figure was vLLM's preallocated pool rather than a requirement — but
it also shows the honest number is not 2 GB either. On a shared 23 GB L4,
13 GB means the VLM cannot co-exist with a co-tenant using more than ~9 GB,
which is a real scheduling constraint rather than a footnote.

## 7. Operational complexity is a genuine cost, not a footnote

The `transformers` path calls `create_causal_mask(inputs_embeds=...)`. That
keyword exists in **none** of 4.53.3, 4.55.0, 4.57.6 or 5.16.1 — including the
4.55.0 the model's own `config.json` declares. Every version tested exposes
`input_embeds`. A one-line keyword shim was required to run the model at all.

Additionally, the supported `paddleocr` path would downgrade numpy and pyyaml
inside the validated environment, so a separate 6.8 GB venv was needed.

None of this is fatal, and all of it is cost. §7 lists operational complexity
as an evaluation criterion precisely because a component that needs a shim and
a private environment is more expensive to own than its benchmark score
suggests.

## 8. What was NOT evaluated, and why it matters

This screened the **element-level transformers path**, not the full
PaddleOCR-VL pipeline. The published 96.33% OmniDocBench figure comes from the
complete system, which additionally runs PP-DocLayoutV2 for layout and reading
order before the VLM ever sees a region.

So the fair statement is: *this path, in this role, on this corpus* is not
competitive. The full pipeline might be materially better as a page parser and
remains unscreened — it would require the PaddlePaddle framework in its own
environment.

The result that does **not** depend on that caveat is the Vietnamese one: the
recognition model is the same in both paths, so `clean_vi` at 50% is a
property of the model, not of the plumbing around it.

## 9. Resource discipline held, and was tested

The first attempt at this screening was **aborted mid-run by its own guard**
when a neighbouring project's job claimed the GPU — exactly the intended
behaviour, and the first time that path has fired in anger.

An initial misreading is worth recording: I assumed the guard had misfired on
my own model's memory. It had not. The process holding VRAM was the
neighbour's `openvocab_rel.train`, restarted at 20:08. The guard was right and
my first interpretation was wrong.

It *was* over-conservative in one respect, and that is now fixed: it counted
this process's own allocation against its own headroom, so a long-running job
looked like it was running out of room because of itself. It now discounts its
own footprint and excludes its own PID.

Final postflight: 0 MiB, no compute apps. Nothing leaked.

## 10. Decision

**Page-level parser: REJECTED.** Worse than the shipped router at 40× the
cost, and disqualified on Vietnamese independently of that.

**Table specialist: CANDIDATE, narrow.** One measured win on `merged_cells`.
Before promotion it needs (a) more than one table case, (b) a cheap gate that
can decide *when* the native grid is untrustworthy, and (c) confirmation that
the win survives on real, non-synthetic tables.

**Region recovery: PROMISING, unproven.** 23× cheaper than full-page on the one
case where the difficult region was genuinely small. Needs a real corpus.
