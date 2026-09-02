#!/usr/bin/env python
"""Phase 6/9 — screen PaddleOCR-VL against the enterprise-hardcases corpus.

What is being screened, and in which role
-----------------------------------------
The HF `transformers` path for this model exposes **element-level
recognition** — you hand it an image and a task prompt ("OCR:",
"Table Recognition:") and it returns text. It is *not* the full PaddleOCR-VL
document pipeline, which additionally runs a separate layout model
(PP-DocLayoutV2) and would require the whole PaddlePaddle framework.

That limitation makes this exactly the right screen for the role the evidence
already favours. Experiment 008 measured that adaptive routing spends 99% of
its cost on 1 document in 14, which argues for an expensive model as a
**recovery rung** reached rarely — not as a page-level default. So two roles
are measured separately:

* ``page``   — whole rendered page in, text out. The "VLM as parser" role.
                Directly comparable with native/adaptive/visual from 008
                because it is scored on the same `must_contain` strings.
* ``region`` — only the difficult region is cropped and sent. The "VLM as
                recovery specialist" role, which is what a cheapest-first
                ladder would actually invoke.

Scoring is deliberately identical to `research/hardcases/run_benchmark.py`:
recall over the case's known strings, NFC-normalized so Vietnamese composed
and decomposed forms compare equal.

Shared-GPU discipline
---------------------
Batch size 1, sequential, no persistent server. GPU state is re-checked
between cases and the run **stops early** if a co-tenant's pressure rises —
a screening job is never worth degrading another project's work.

    python research/experiments/screen_vlm.py --role page region
"""
from __future__ import annotations

import argparse
import json
import sys
import time
import unicodedata
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "src"))

MODEL_ID = "PaddlePaddle/PaddleOCR-VL"
CORPUS = REPO_ROOT / "research" / "hardcases" / "corpus"

# The Phase 6 common screening set: easy EN, easy VI, tiny text, table,
# stamp/occlusion, multi-column, plus the corrupt-encoding case.
SCREEN_CASES = [
    "clean_en", "clean_vi", "tiny_text", "tiny_cells_table",
    "borderless_table", "merged_cells", "stamp_over_text",
    "stamp_over_table", "multicolumn_mixed", "broken_cmap_vi",
]

PROMPT_BY_KIND = {"table": "Table Recognition:", "text": "OCR:"}


def _norm(s: str) -> str:
    return unicodedata.normalize("NFC", s)


def gpu_snapshot(samples: int = 3, mine_mib: float = 0.0):
    """Classify the GPU, discounting this process's own footprint.

    Once the model is resident, `free_mib` already excludes the VRAM *we*
    hold, so re-checking naively makes a job look like it is running out of
    room because of itself. `mine_mib` adds our own allocation back before
    judging headroom, and our PID is excluded from the co-tenant list.

    The co-tenant check itself stays strict: this is what stopped the first
    screening run when a neighbouring job claimed the GPU mid-run.
    """
    import os

    from doc_extraction.utils.resources import classify_gpu, query_gpu

    state = query_gpu(samples=samples, interval_s=0.2)
    if mine_mib:
        state.free_mib = int(state.free_mib + mine_mib)
    verdict, reason = classify_gpu(state, required_mib=3000, safety_margin_mib=2000,
                                   exclude_pids={os.getpid()})
    return state, verdict, reason


def render(pdf: Path, dpi: int, clip=None):
    import pymupdf

    doc = pymupdf.open(pdf)
    pix = doc[0].get_pixmap(matrix=pymupdf.Matrix(dpi / 72, dpi / 72), clip=clip)
    png = pix.tobytes("png")
    doc.close()
    from io import BytesIO

    from PIL import Image
    return Image.open(BytesIO(png)).convert("RGB")


def difficult_region(pdf: Path, max_pt: float = 7.0):
    """Bounding box of the small-text / dense content worth cropping.

    Uses the source text layer's font sizes — a cheap signal available before
    any expensive work, which is the point of a recovery ladder. Returns None
    when nothing on the page qualifies, in which case the region role is
    skipped rather than given the whole page (that would just duplicate the
    page role and inflate its apparent value).
    """
    import pymupdf

    doc = pymupdf.open(pdf)
    boxes = []
    for block in doc[0].get_text("dict")["blocks"]:
        if block.get("type") != 0:
            continue
        sizes = [s["size"] for line in block["lines"] for s in line["spans"]]
        if sizes and min(sizes) <= max_pt:
            boxes.append(block["bbox"])
    doc.close()
    if not boxes:
        return None
    pad = 6
    return pymupdf.Rect(min(b[0] for b in boxes) - pad, min(b[1] for b in boxes) - pad,
                        max(b[2] for b in boxes) + pad, max(b[3] for b in boxes) + pad)


def _patch_causal_mask_kwarg() -> str | None:
    """Work around a bug in the vendor's `trust_remote_code` modeling file.

    `modeling_paddleocr_vl.py` calls
    `create_causal_mask(inputs_embeds=...)`, but transformers exposes that
    parameter as `input_embeds` (no trailing "s" on the first word) in every
    version tested here: 4.53.3, 4.55.0, 4.57.6 and 5.16.1 — including the
    4.55.0 the model's own `config.json` declares. The keyword the vendor
    uses does not exist in any of them, so the transformers path fails at the
    first forward pass regardless of version.

    The shim is a pure keyword rename: same argument, same position, same
    semantics. It changes no model behaviour and is applied only inside this
    screening script — the vendor's file on disk is left untouched.

    Recorded rather than hidden: this is an operational-complexity data point
    about the candidate, and it is reported in the screening results.
    """
    try:
        from transformers import masking_utils
    except Exception:  # noqa: BLE001 - older layouts simply lack the module
        return None
    original = getattr(masking_utils, "create_causal_mask", None)
    if original is None:
        return None
    import inspect

    params = list(inspect.signature(original).parameters)
    if "inputs_embeds" in params:
        return None  # a version that matches the vendor's call; nothing to do

    def shim(*args, **kwargs):
        if "inputs_embeds" in kwargs:
            kwargs["input_embeds"] = kwargs.pop("inputs_embeds")
        return original(*args, **kwargs)

    masking_utils.create_causal_mask = shim
    return f"create_causal_mask(inputs_embeds=) -> (input_embeds=); params were {params[:2]}"


class VLM:
    def __init__(self, device: str = "cuda", dtype: str = "bfloat16"):
        import torch
        from transformers import AutoModelForCausalLM, AutoProcessor

        self.torch = torch
        self.compat_shim = _patch_causal_mask_kwarg()
        started = time.perf_counter()
        self.processor = AutoProcessor.from_pretrained(MODEL_ID, trust_remote_code=True)
        # transformers <5 spells this `torch_dtype`; 5.x renamed it to
        # `dtype`. This model pins transformers 4.55 in its config, so the
        # screening venv is on 4.x and the older spelling is the correct one.
        self.model = AutoModelForCausalLM.from_pretrained(
            MODEL_ID, trust_remote_code=True,
            torch_dtype=getattr(torch, dtype),
        ).to(device).eval()
        self.device = device
        self.load_seconds = time.perf_counter() - started
        self.params = sum(p.numel() for p in self.model.parameters())

    def run(self, image, prompt: str, max_new_tokens: int = 1024) -> tuple[str, float]:
        messages = [{"role": "user", "content": [
            {"type": "image", "image": image}, {"type": "text", "text": prompt}]}]
        text = self.processor.apply_chat_template(
            messages, tokenize=False, add_generation_prompt=True)
        inputs = self.processor(text=[text], images=[image], return_tensors="pt").to(self.device)
        started = time.perf_counter()
        with self.torch.no_grad():
            out = self.model.generate(**inputs, max_new_tokens=max_new_tokens, do_sample=False)
        elapsed = time.perf_counter() - started
        trimmed = out[0][inputs["input_ids"].shape[1]:]
        return self.processor.decode(trimmed, skip_special_tokens=True), elapsed


def score(case: dict, text: str) -> dict:
    text = _norm(text)
    found = [s for s in case["must_contain"] if _norm(s) in text]
    missing = [s for s in case["must_contain"] if _norm(s) not in text]
    bad = [s for s in case.get("must_not_contain", []) if _norm(s) in text]
    return {"recall": len(found) / (len(case["must_contain"]) or 1),
            "missing": missing, "hallucinated": bad, "chars": len(text)}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--role", nargs="+", default=["page"], choices=["page", "region"])
    ap.add_argument("--dpi", type=int, default=200)
    ap.add_argument("--region-dpi", type=int, default=400)
    ap.add_argument("--device", default="cuda")
    ap.add_argument("--json", default=None)
    ap.add_argument("--cases", nargs="+", default=SCREEN_CASES)
    args = ap.parse_args(argv)

    manifest = json.loads((CORPUS / "manifest.json").read_text(encoding="utf-8"))
    cases = {c["case_id"]: c for c in manifest["cases"]}

    state, verdict, reason = gpu_snapshot(samples=5)
    print(f"GPU preflight: {verdict.upper()} — {reason}")
    if verdict == "protected" and args.device == "cuda":
        print("refusing to compete for a busy GPU; rerun when it is clear or pass --device cpu")
        return 2

    vlm = VLM(device=args.device)
    print(f"model: {vlm.params/1e9:.2f}B params, loaded in {vlm.load_seconds:.1f}s on {args.device}")
    if vlm.compat_shim:
        print(f"compat shim applied: {vlm.compat_shim}")
    peak = vlm.torch.cuda.max_memory_allocated() / 2**20 if args.device == "cuda" else 0.0
    print(f"VRAM after load: {peak:.0f} MiB\n")

    rows = []
    for role in args.role:
        for case_id in args.cases:
            case = cases[case_id]
            pdf = CORPUS / case["filename"]
            clip = difficult_region(pdf) if role == "region" else None
            if role == "region" and clip is None:
                continue
            dpi = args.region_dpi if role == "region" else args.dpi
            image = render(pdf, dpi, clip)
            prompt = PROMPT_BY_KIND["table" if case.get("expected_tables") else "text"]

            text, secs = vlm.run(image, prompt)
            s = score(case, text)
            vram = vlm.torch.cuda.max_memory_allocated() / 2**20 if args.device == "cuda" else 0.0
            rows.append({"role": role, "case_id": case_id, "failure_mode": case["failure_mode"],
                         "language": case["language"], "prompt": prompt, "dpi": dpi,
                         "px": image.size, "seconds": round(secs, 2),
                         "peak_vram_mib": round(vram), **s})
            print(f"  [{role:6s}] {case_id:20s} recall={s['recall']:5.0%} "
                  f"{secs:6.2f}s  {image.size[0]}x{image.size[1]}px  missing={s['missing'][:2]}")

            # Re-check between cases: a screening job must yield if the
            # neighbour's pressure rises.
            mine = (vlm.torch.cuda.memory_reserved() / 2**20) if args.device == "cuda" else 0.0
            _st, vd, rs = gpu_snapshot(samples=3, mine_mib=mine)
            if vd == "protected" and args.device == "cuda":
                print(f"  ! GPU became {vd.upper()} ({rs}) — stopping early, partial results kept")
                break

    print(f"\n{'role':>8s}{'cases':>7s}{'mean recall':>13s}{'median s':>10s}{'peak VRAM':>11s}")
    print("-" * 49)
    for role in args.role:
        sub = [r for r in rows if r["role"] == role]
        if not sub:
            continue
        rec = sorted(r["recall"] for r in sub)
        secs = sorted(r["seconds"] for r in sub)
        print(f"{role:>8s}{len(sub):>7d}{sum(rec)/len(rec):>12.0%}"
              f"{secs[len(secs)//2]:>10.2f}{max(r['peak_vram_mib'] for r in sub):>10d}M")

    if args.json:
        Path(args.json).write_text(json.dumps({
            "model": MODEL_ID, "params_b": round(vlm.params / 1e9, 3),
            "device": args.device, "load_seconds": round(vlm.load_seconds, 2),
            "compat_shim": vlm.compat_shim,
            "gpu_preflight": {"verdict": verdict, "reason": reason,
                              "free_mib": state.free_mib,
                              "utilization_median_pct": state.utilization_pct,
                              "co_tenants": [{"pid": p.pid, "used_mib": p.used_mib}
                                             for p in state.processes]},
            "rows": rows}, indent=2, ensure_ascii=False), encoding="utf-8")
        print(f"\n-> {args.json}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
