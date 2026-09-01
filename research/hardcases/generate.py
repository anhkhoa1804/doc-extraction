#!/usr/bin/env python
"""Generate the `enterprise-hardcases` corpus.

Why synthesize rather than collect
----------------------------------
The production corpus this project serves is confidential (see data/README.md)
and cannot be committed, benchmarked publicly, or shared with a model API. A
synthetic corpus solves three problems at once:

* **Gold labels are free.** We draw the text, so we know exactly what should
  come back. No annotation effort, and no annotator disagreement. This is the
  cheapest possible answer to "did the text survive?".
* **Difficulty is controlled.** Each case isolates one failure mode, so a
  regression can be attributed to a cause instead of to "hard documents".
* **It is distributable.** Nothing here contains real enterprise data.

The obvious cost: synthetic documents are not real ones. A model that handles
these may still fail on a genuine low-contrast scan with JPEG artifacts and a
skewed camera angle. So these are **necessary, not sufficient** — they are a
regression floor and a diagnostic instrument, not a substitute for evaluating
on real documents. Cases that reproduce a *mechanism* faithfully (the broken
CMap case already in tests/fixtures.py is the model here) are worth much more
than cases that merely look superficially messy.

Language coverage is English + Vietnamese, matching the production target.
Vietnamese matters specifically because its diacritics are where encoding,
font-subsetting and OCR failures concentrate — `ệ`, `ữ`, `ậ` are precisely the
characters a marginal pipeline drops first.

    python research/hardcases/generate.py --out research/hardcases/corpus
"""
from __future__ import annotations

import argparse
import json
import random
from dataclasses import asdict, dataclass, field
from pathlib import Path

import pymupdf

# DejaVu covers Vietnamese precomposed diacritics; PyMuPDF's base-14 fonts do
# not, and silently drop them — which would make every Vietnamese case
# accidentally also a font-coverage case and confound the taxonomy.
VN_FONT = "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"
VN_FONT_BOLD = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"

A4 = (595.0, 842.0)

# Realistic enterprise phrasing, not lorem. These are the kinds of strings the
# production corpus actually contains: legal headers, monetary amounts, IDs.
VI_LINES = [
    "CỘNG HÒA XÃ HỘI CHỦ NGHĨA VIỆT NAM",
    "Độc lập - Tự do - Hạnh phúc",
    "GIẤY CHỨNG NHẬN ĐĂNG KÝ DOANH NGHIỆP",
    "Mã số doanh nghiệp: 0123456789",
    "Địa chỉ trụ sở chính: Số 12, Đường Nguyễn Huệ, Quận 1",
    "Vốn điều lệ: 5.000.000.000 đồng",
    "Người đại diện theo pháp luật: Nguyễn Thị Hương",
]
EN_LINES = [
    "CERTIFICATE OF BUSINESS REGISTRATION",
    "Enterprise code: 0123456789",
    "Registered office: 12 Nguyen Hue Street, District 1",
    "Charter capital: VND 5,000,000,000",
    "Legal representative: Nguyen Thi Huong",
    "Date of first registration: 14 March 2024",
    "This certificate supersedes all previous versions.",
]


@dataclass
class HardCase:
    """One generated case plus everything needed to score it automatically."""

    case_id: str
    document_type: str
    language: str          # en | vi | mixed
    difficulty: str        # easy | medium | hard | extreme
    failure_mode: str      # taxonomy code, see TAXONOMY below
    expected_behavior: str
    # Strings that MUST appear in the extraction for it to count as recovered.
    # Kept short and distinctive so scoring is unambiguous.
    must_contain: list[str] = field(default_factory=list)
    # Strings that must NOT appear — catches hallucination and duplication.
    must_not_contain: list[str] = field(default_factory=list)
    expected_tables: int = 0
    notes: str = ""
    filename: str = ""


# The taxonomy is discovered/extended by adding cases here, not declared up
# front. Each code is a *mechanism*, not a document category.
TAXONOMY = {
    "T-CLEAN": "control: clean born-digital text, must not regress",
    "T-TINY": "text below the resolution the default render DPI can resolve",
    "T-LOWCON": "low contrast between ink and background",
    "T-ROT": "page or region rotated away from horizontal",
    "T-SKEW": "small skew angle, as from a scanner or camera",
    "T-NOISE": "scan noise / speckle",
    "T-CMAP": "text layer present but wrongly decoded (broken ToUnicode)",
    "T-DIACRITIC": "Vietnamese diacritics specifically at risk",
    "O-STAMP": "opaque stamp/seal overlapping text",
    "O-WATERMARK": "large translucent watermark across the page",
    "O-HANDWRITE": "handwriting-like strokes over printed text",
    "L-MULTICOL": "multi-column layout with a real gutter",
    "L-HEADFOOT": "repeated header/footer across pages",
    "B-BORDERLESS": "table with no ruling lines",
    "B-MERGED": "table with merged cells",
    "B-TINYCELL": "table with small text inside cells",
    "X-COMBO": "two failure modes interacting on one page",
}


def _insert_vi(page, point, text, size=11, font_path=VN_FONT, color=(0, 0, 0),
               rotate=0, angle=None):
    """Vietnamese-safe text insertion. Always goes through an embedded TTF.

    `rotate` takes PyMuPDF's quadrant rotations (0/90/180/270). `angle` takes
    an arbitrary degree value and is applied as a morph about the insertion
    point — needed for a diagonal watermark, which is not a quadrant rotation.
    """
    kwargs = dict(fontsize=size, fontfile=font_path, fontname="dv", color=color)
    if angle is not None:
        pivot = pymupdf.Point(*point)
        matrix = pymupdf.Matrix(1, 1).prerotate(angle)
        page.insert_text(point, text, morph=(pivot, matrix), **kwargs)
    else:
        page.insert_text(point, text, rotate=rotate, **kwargs)


def _new_doc():
    return pymupdf.open()


def _save(doc, out_dir: Path, name: str) -> str:
    path = out_dir / name
    # DejaVu embeds ~780 KB unsubsetted; subsetting keeps the corpus small
    # enough to version-control comfortably without changing what is rendered.
    try:
        doc.subset_fonts()
    except Exception:  # noqa: BLE001 - subsetting is an optimization, not a requirement
        pass
    doc.save(path, garbage=4, deflate=True)
    doc.close()
    return name


# --------------------------------------------------------------------------
# Individual case builders. Each returns a HardCase and writes one file.
# --------------------------------------------------------------------------

def case_clean_vi(out: Path) -> HardCase:
    doc = _new_doc(); page = doc.new_page(width=A4[0], height=A4[1])
    for i, line in enumerate(VI_LINES):
        _insert_vi(page, (60, 90 + i * 26), line, size=12)
    name = _save(doc, out, "clean_vi.pdf")
    return HardCase(
        case_id="clean_vi", document_type="business_license", language="vi",
        difficulty="easy", failure_mode="T-CLEAN",
        expected_behavior="native digital route; all diacritics preserved exactly",
        must_contain=["Độc lập", "Hạnh phúc", "0123456789", "Nguyễn Thị Hương"],
        notes="Control case. Any diacritic loss here invalidates every harder Vietnamese result.",
        filename=name)


def case_clean_en(out: Path) -> HardCase:
    doc = _new_doc(); page = doc.new_page(width=A4[0], height=A4[1])
    for i, line in enumerate(EN_LINES):
        _insert_vi(page, (60, 90 + i * 26), line, size=12)
    name = _save(doc, out, "clean_en.pdf")
    return HardCase(
        case_id="clean_en", document_type="business_license", language="en",
        difficulty="easy", failure_mode="T-CLEAN",
        expected_behavior="native digital route; exact text",
        must_contain=["CERTIFICATE OF BUSINESS REGISTRATION", "0123456789", "5,000,000,000"],
        filename=name)


def case_tiny_text(out: Path) -> HardCase:
    """Small print — the mechanism behind footnotes, legal fine print and
    dense table cells. 4pt is deliberately below what 200 DPI resolves well."""
    doc = _new_doc(); page = doc.new_page(width=A4[0], height=A4[1])
    _insert_vi(page, (60, 80), "SCHEDULE 3 - FEES AND CHARGES", size=13)
    fine = [
        "Late payment interest accrues at 1.5% per month on overdue amounts.",
        "Phí dịch vụ hàng tháng là 2.500.000 đồng chưa bao gồm thuế.",
        "Termination requires ninety (90) days written notice to the Registrar.",
    ]
    for i, line in enumerate(fine):
        _insert_vi(page, (60, 120 + i * 12), line, size=4)
    name = _save(doc, out, "tiny_text.pdf")
    return HardCase(
        case_id="tiny_text", document_type="contract", language="mixed",
        difficulty="hard", failure_mode="T-TINY",
        expected_behavior="native route recovers it exactly (text layer intact); "
                          "the visual route needs higher DPI than the 200 default",
        must_contain=["1.5% per month", "2.500.000", "ninety (90) days"],
        notes="Native and visual routes should diverge sharply here — that divergence "
              "is the measurement, not a bug.",
        filename=name)


def case_low_contrast(out: Path) -> HardCase:
    doc = _new_doc(); page = doc.new_page(width=A4[0], height=A4[1])
    page.draw_rect(pymupdf.Rect(0, 0, A4[0], A4[1]), color=None, fill=(0.82, 0.82, 0.80))
    for i, line in enumerate(EN_LINES[:5]):
        _insert_vi(page, (60, 100 + i * 26), line, size=12, color=(0.62, 0.62, 0.60))
    name = _save(doc, out, "low_contrast.pdf")
    return HardCase(
        case_id="low_contrast", document_type="scanned_form", language="en",
        difficulty="hard", failure_mode="T-LOWCON",
        expected_behavior="native text layer is intact so the native route must succeed; "
                          "OCR on the render is where contrast matters",
        must_contain=["Enterprise code", "0123456789"],
        filename=name)


def case_rotated(out: Path) -> HardCase:
    doc = _new_doc(); page = doc.new_page(width=A4[0], height=A4[1])
    _insert_vi(page, (60, 80), "ROTATED ANNEX - READ SIDEWAYS", size=12)
    for i, line in enumerate(EN_LINES[:4]):
        _insert_vi(page, (500, 150 + i * 30), line, size=11, rotate=90)
    name = _save(doc, out, "rotated_region.pdf")
    return HardCase(
        case_id="rotated_region", document_type="annex", language="en",
        difficulty="hard", failure_mode="T-ROT",
        expected_behavior="rotated text must still be recovered; reading order will "
                          "likely be wrong and that is a separate, recorded failure",
        must_contain=["Enterprise code", "ROTATED ANNEX"],
        filename=name)


def case_stamp_over_text(out: Path) -> HardCase:
    """An opaque red seal over body text — the canonical Vietnamese business
    document occlusion. The covered line is deliberately recoverable from the
    text layer but not from pixels."""
    doc = _new_doc(); page = doc.new_page(width=A4[0], height=A4[1])
    for i, line in enumerate(VI_LINES):
        _insert_vi(page, (60, 90 + i * 26), line, size=12)
    centre = pymupdf.Point(180, 200)
    for r in (58, 52):
        page.draw_circle(centre, r, color=(0.75, 0.05, 0.10), width=2.4)
    page.draw_circle(centre, 56, color=(0.75, 0.05, 0.10), fill=(0.95, 0.80, 0.82), width=0)
    _insert_vi(page, (centre.x - 44, centre.y - 4), "CÔNG TY TNHH", size=9,
               font_path=VN_FONT_BOLD, color=(0.75, 0.05, 0.10))
    _insert_vi(page, (centre.x - 30, centre.y + 12), "ĐÃ DUYỆT", size=9,
               font_path=VN_FONT_BOLD, color=(0.75, 0.05, 0.10))
    name = _save(doc, out, "stamp_over_text.pdf")
    return HardCase(
        case_id="stamp_over_text", document_type="business_license", language="vi",
        difficulty="extreme", failure_mode="O-STAMP",
        expected_behavior="native route recovers the occluded text (it is under the seal, "
                          "not replaced); the visual route cannot and should say so",
        must_contain=["Mã số doanh nghiệp", "ĐÃ DUYỆT"],
        notes="The point of this case is that native and visual routes fail DIFFERENTLY. "
              "A fusion strategy should beat either alone.",
        filename=name)


def case_watermark(out: Path) -> HardCase:
    doc = _new_doc(); page = doc.new_page(width=A4[0], height=A4[1])
    _insert_vi(page, (120, 460), "BẢN SAO", size=76, font_path=VN_FONT_BOLD,
               color=(0.86, 0.86, 0.90), angle=45)
    for i, line in enumerate(VI_LINES[:6]):
        _insert_vi(page, (60, 110 + i * 30), line, size=12)
    name = _save(doc, out, "watermark.pdf")
    return HardCase(
        case_id="watermark", document_type="certified_copy", language="vi",
        difficulty="medium", failure_mode="O-WATERMARK",
        expected_behavior="body text recovered; the watermark itself is content, not noise, "
                          "and should appear rather than be silently dropped",
        must_contain=["Độc lập", "Vốn điều lệ"],
        filename=name)


def case_borderless_table(out: Path) -> HardCase:
    """No ruling lines at all — pure whitespace alignment. This is the case
    PyMuPDF's vector-based table finder structurally cannot see."""
    doc = _new_doc(); page = doc.new_page(width=A4[0], height=A4[1])
    _insert_vi(page, (60, 80), "APPENDIX A - FEE SCHEDULE", size=13)
    rows = [("Service", "Unit", "Amount (VND)"),
            ("Registration", "each", "1,500,000"),
            ("Amendment", "each", "800,000"),
            ("Certified copy", "page", "50,000")]
    for r, row in enumerate(rows):
        for c, cell in enumerate(row):
            _insert_vi(page, (60 + c * 160, 120 + r * 26), cell, size=11)
    name = _save(doc, out, "borderless_table.pdf")
    return HardCase(
        case_id="borderless_table", document_type="contract_appendix", language="en",
        difficulty="hard", failure_mode="B-BORDERLESS",
        expected_behavior="text recovered; table STRUCTURE likely lost by the native finder, "
                          "which keys on vector ruling lines",
        must_contain=["Registration", "1,500,000", "Certified copy"],
        expected_tables=1,
        notes="Expected-fail for the native table backend by construction. The value is "
              "measuring whether a specialist or VLM recovers the grid.",
        filename=name)


def case_merged_cells(out: Path) -> HardCase:
    doc = _new_doc(); page = doc.new_page(width=A4[0], height=A4[1])
    _insert_vi(page, (60, 80), "QUARTERLY SUMMARY", size=13)
    left, top, cw, rh = 60, 110, 150, 28
    for r in range(5):
        page.draw_line(pymupdf.Point(left, top + r * rh),
                       pymupdf.Point(left + 3 * cw, top + r * rh))
    for c in range(4):
        x = left + c * cw
        start_row = 1 if c == 0 else 0   # first column merged across the header
        page.draw_line(pymupdf.Point(x, top + start_row * rh),
                       pymupdf.Point(x, top + 4 * rh))
    _insert_vi(page, (left + 5, top + 19), "Region (merged header)", size=10)
    data = [("North", "Q1", "12,400,000"), ("North", "Q2", "13,100,000"), ("South", "Q1", "9,800,000")]
    for r, row in enumerate(data, start=1):
        for c, cell in enumerate(row):
            _insert_vi(page, (left + c * cw + 5, top + r * rh + 19), cell, size=10)
    name = _save(doc, out, "merged_cells.pdf")
    return HardCase(
        case_id="merged_cells", document_type="financial_report", language="en",
        difficulty="hard", failure_mode="B-MERGED",
        expected_behavior="cell text recovered; row/col spans are the hard part",
        must_contain=["12,400,000", "9,800,000", "Region"],
        expected_tables=1,
        filename=name)


def case_multicolumn(out: Path) -> HardCase:
    doc = _new_doc(); page = doc.new_page(width=A4[0], height=A4[1])
    _insert_vi(page, (60, 70), "TERMS AND CONDITIONS", size=13)
    left_col = ["1. Definitions", "In this Agreement the following",
                "terms shall have the meanings", "set out below."]
    right_col = ["2. Điều khoản chung", "Các bên đồng ý thực hiện",
                 "đầy đủ nghĩa vụ được quy định", "trong hợp đồng này."]
    for i, line in enumerate(left_col):
        _insert_vi(page, (55, 110 + i * 22), line, size=11)
    for i, line in enumerate(right_col):
        _insert_vi(page, (320, 110 + i * 22), line, size=11)
    name = _save(doc, out, "multicolumn_mixed.pdf")
    return HardCase(
        case_id="multicolumn_mixed", document_type="contract", language="mixed",
        difficulty="medium", failure_mode="L-MULTICOL",
        expected_behavior="both columns recovered AND ordered column-by-column, "
                          "not interleaved line-by-line across the gutter",
        must_contain=["Definitions", "Điều khoản chung", "nghĩa vụ"],
        notes="Reading order is the measurement here, not text recovery.",
        filename=name)


def case_tiny_cells(out: Path) -> HardCase:
    doc = _new_doc(); page = doc.new_page(width=A4[0], height=A4[1])
    _insert_vi(page, (60, 70), "DETAILED PRICE LIST", size=12)
    left, top, cw, rh, n = 55, 95, 92, 13, 12
    for r in range(n + 1):
        page.draw_line(pymupdf.Point(left, top + r * rh), pymupdf.Point(left + 5 * cw, top + r * rh))
    for c in range(6):
        page.draw_line(pymupdf.Point(left + c * cw, top), pymupdf.Point(left + c * cw, top + n * rh))
    hdr = ["Code", "Mô tả", "Qty", "Unit", "Total"]
    for c, h in enumerate(hdr):
        _insert_vi(page, (left + c * cw + 2, top + 9), h, size=5)
    rnd = random.Random(7)
    for r in range(1, n):
        vals = [f"SKU-{1000+r}", f"Sản phẩm {r}", str(rnd.randint(1, 99)),
                f"{rnd.randint(10,99)},000", f"{rnd.randint(100,999)},000"]
        for c, v in enumerate(vals):
            _insert_vi(page, (left + c * cw + 2, top + r * rh + 9), v, size=5)
    name = _save(doc, out, "tiny_cells_table.pdf")
    return HardCase(
        case_id="tiny_cells_table", document_type="invoice", language="mixed",
        difficulty="extreme", failure_mode="X-COMBO",
        expected_behavior="ruled table detected; 5pt cell text is the interacting difficulty",
        must_contain=["SKU-1001", "Sản phẩm 1", "Mô tả"],
        expected_tables=1,
        notes="Deliberate interaction of B-TINYCELL and T-TINY: real invoices combine them.",
        filename=name)


def case_headfoot_multipage(out: Path) -> HardCase:
    doc = _new_doc()
    for p in range(3):
        page = doc.new_page(width=A4[0], height=A4[1])
        _insert_vi(page, (60, 45), "ACME HOLDINGS - CONFIDENTIAL", size=8, color=(0.4, 0.4, 0.4))
        _insert_vi(page, (60, 800), f"Page {p+1} of 3 - Contract Ref 2024/ACME/017",
                   size=8, color=(0.4, 0.4, 0.4))
        _insert_vi(page, (60, 120), f"Section {p+1}: Obligations of the Parties", size=13)
        for i, line in enumerate(EN_LINES[:4]):
            _insert_vi(page, (60, 160 + i * 24), line, size=11)
    name = _save(doc, out, "headfoot_multipage.pdf")
    return HardCase(
        case_id="headfoot_multipage", document_type="contract", language="en",
        difficulty="medium", failure_mode="L-HEADFOOT",
        expected_behavior="3 pages; repeated header/footer identifiable as such rather than "
                          "interleaved into body text 3 times",
        must_contain=["Section 1", "Section 3", "Contract Ref 2024/ACME/017"],
        notes="Cross-page structure: the repeated strings are the signal.",
        filename=name)


def case_stamp_over_table(out: Path) -> HardCase:
    doc = _new_doc(); page = doc.new_page(width=A4[0], height=A4[1])
    left, top, cw, rh = 60, 110, 150, 30
    for r in range(4):
        page.draw_line(pymupdf.Point(left, top + r * rh), pymupdf.Point(left + 3 * cw, top + r * rh))
    for c in range(4):
        page.draw_line(pymupdf.Point(left + c * cw, top), pymupdf.Point(left + c * cw, top + 3 * rh))
    rows = [("Item", "Qty", "Amount"), ("Widget", "12", "3,600,000"), ("Gadget", "5", "1,250,000")]
    for r, row in enumerate(rows):
        for c, cell in enumerate(row):
            _insert_vi(page, (left + c * cw + 6, top + r * rh + 20), cell, size=11)
    centre = pymupdf.Point(left + 2 * cw, top + 2 * rh)
    page.draw_circle(centre, 48, color=(0.10, 0.15, 0.75), fill=(0.80, 0.83, 0.96), width=2)
    _insert_vi(page, (centre.x - 30, centre.y + 4), "ĐÃ THU", size=11,
               font_path=VN_FONT_BOLD, color=(0.10, 0.15, 0.75))
    name = _save(doc, out, "stamp_over_table.pdf")
    return HardCase(
        case_id="stamp_over_table", document_type="invoice", language="mixed",
        difficulty="extreme", failure_mode="X-COMBO",
        expected_behavior="table structure survives; the amount under the stamp is "
                          "recoverable natively but not visually",
        must_contain=["1,250,000", "ĐÃ THU", "Widget"],
        expected_tables=1,
        notes="Interaction of O-STAMP and B-* — the combination real invoices actually present.",
        filename=name)


def case_broken_cmap_vi(out: Path) -> HardCase:
    """Reuses the repository's existing CMap-corruption mechanism, which is
    faithful to the real observed failure rather than pre-garbled text."""
    import sys
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
    from tests.fixtures import make_pdf_with_broken_cmap

    path = out / "broken_cmap_vi.pdf"
    make_pdf_with_broken_cmap(path, n_pages=2)
    return HardCase(
        case_id="broken_cmap_vi", document_type="business_license", language="vi",
        difficulty="hard", failure_mode="T-CMAP",
        expected_behavior="quality gate must reject the text layer and reroute to OCR; "
                          "accepting it silently is the worst possible outcome",
        must_contain=["Cong Hoa", "Doanh Nghiep"],
        must_not_contain=["ЅoҖѸ", "Йoa"],
        notes="Regression lock on the failure the whole routing architecture exists for.",
        filename=path.name)


BUILDERS = [
    case_clean_vi, case_clean_en, case_tiny_text, case_low_contrast, case_rotated,
    case_stamp_over_text, case_watermark, case_borderless_table, case_merged_cells,
    case_multicolumn, case_tiny_cells, case_headfoot_multipage, case_stamp_over_table,
    case_broken_cmap_vi,
]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--out", default=str(Path(__file__).parent / "corpus"))
    args = parser.parse_args(argv)

    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)

    cases = [build(out) for build in BUILDERS]
    manifest = {
        "corpus": "enterprise-hardcases",
        "generated_by": "research/hardcases/generate.py",
        "synthetic": True,
        "contains_real_enterprise_data": False,
        "languages": ["en", "vi", "mixed"],
        "taxonomy": TAXONOMY,
        "cases": [asdict(c) for c in cases],
    }
    (out / "manifest.json").write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8")

    by_mode: dict[str, int] = {}
    for c in cases:
        by_mode[c.failure_mode] = by_mode.get(c.failure_mode, 0) + 1
    print(f"{len(cases)} cases -> {out}")
    for mode, n in sorted(by_mode.items()):
        print(f"  {mode:16s} {n}  {TAXONOMY.get(mode,'')[:60]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
