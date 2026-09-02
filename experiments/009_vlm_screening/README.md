# 009 — Does a document VLM earn a place in this pipeline?

## Question

Experiment 008 measured that adaptive routing spends 99% of its cost on one
document in fourteen. That cost profile — a spike, not a tax — is what makes
an expensive component affordable *if* it is placed at the right rung.

So the question is not "is a VLM good" but: **which role, if any, earns its
compute for EN/VI enterprise documents?**

Two roles were measured separately (§9 of the mission):

* **page** — whole rendered page in, text out. The "VLM as parser" role.
* **region** — only the difficult region cropped and sent. The "VLM as
  recovery specialist" role.

## Candidate

**PaddleOCR-VL** (`PaddlePaddle/PaddleOCR-VL`), 0.96B params, Apache-2.0,
bfloat16. Selected in `docs/backend-landscape.md` as the only screened
candidate that is simultaneously small enough for a shared L4, permissively
licensed, and specifically strong on the mechanisms this corpus targets
(reported seal-recognition NED 0.138 against a 235B model's 0.382).

Screened via the `transformers` `trust_remote_code` path, which exposes
**element-level recognition**. This is *not* the full PaddleOCR-VL pipeline
(which adds PP-DocLayoutV2 and needs the PaddlePaddle framework) — see
`observations.md` §8 for what that caveat does and does not affect.

## Method

Ten cases from `research/hardcases/`, scored **identically** to experiment 008
— recall over each case's `must_contain` strings, NFC-normalized — so the
numbers are directly comparable with native / adaptive / visual rather than
being a separate leaderboard.

Environment: dedicated `~/.venvs/vlm-screen` (transformers 4.55.0, the version
the model's own config declares; torch 2.11.0+cu128). A separate venv was
required because `paddleocr` downgrades numpy and pyyaml inside the validated
extraction environment.

**Resource state: CLEAR** at launch — 0 MiB used, 0% utilization, no compute
apps. Batch 1, sequential, GPU re-checked between every case.

## Results

| | mean recall | total compute |
|---|---|---|
| native | 83% | ~0.4 s |
| adaptive (shipped) | **93%** | ~37 s |
| visual | 66% | ~194 s |
| **VLM, page** | 68% | **1483 s** |

VLM strictly beats every cheaper strategy on **1 of 10** cases and loses on 5.

Full per-case numbers in `results.json`; interpretation in `observations.md`.

## Verdict

* **Page parser — REJECTED.** 40× the compute for 25 points less recall, and
  independently disqualified by 50% recall on a *clean* Vietnamese page.
* **Table specialist — CANDIDATE.** One measured win (`merged_cells`, 100% vs
  67%), the only place anything recovers what the native finder loses.
* **Region recovery — PROMISING, unproven.** 23× cheaper than full-page on the
  one case whose difficult region was genuinely small.

## Reproduce

```bash
# needs a CLEAR GPU; the script refuses to compete for a busy one
python research/experiments/screen_vlm.py --device cuda --role page region \
    --json <out>.json
```
