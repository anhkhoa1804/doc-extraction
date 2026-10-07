from doc_extraction.ingest.language_routing import (
    BASELINE_OCR_LANGUAGES,
    HAN_OCR_LANGUAGES,
    select_ocr_language_route,
    select_routed_markdown,
)
from doc_extraction.schemas.page import Page


def _page(*notes: str) -> Page:
    return Page(index=0, width=100, height=100, notes=list(notes))


def _select(candidate="候选文本", *, page=None, error=None, valid=True):
    return select_routed_markdown(
        candidate_markdown=candidate,
        baseline_markdown="baseline text",
        candidate_page=page or _page(),
        candidate_error=error,
        candidate_valid=valid,
    )


def test_osd_unavailable_falls_back_to_baseline_languages():
    route = select_ocr_language_route(None)
    assert route.languages == BASELINE_OCR_LANGUAGES
    assert route.reason == "tesseract_osd_unavailable"


def test_osd_non_han_falls_back_to_baseline_languages():
    assert select_ocr_language_route("Latin").languages == BASELINE_OCR_LANGUAGES
    assert select_ocr_language_route("Cyrillic").languages == BASELINE_OCR_LANGUAGES


def test_osd_han_selects_supported_chinese_english_configuration():
    route = select_ocr_language_route(" Han ")
    assert route.languages == HAN_OCR_LANGUAGES
    assert route.is_han_route


def test_good_chinese_candidate_is_kept():
    selected = _select()
    assert selected.selected_markdown == "候选文本"
    assert not selected.used_baseline_fallback
    assert selected.reason is None


def test_empty_candidate_markdown_falls_back_to_baseline():
    selected = _select(candidate=" \n")
    assert selected.selected_markdown == "baseline text"
    assert selected.used_baseline_fallback
    assert selected.reason == "candidate_markdown_empty"


def test_severe_nonempty_text_collapse_falls_back_to_baseline():
    selected = select_routed_markdown(
        candidate_markdown="x" * 22,
        baseline_markdown="b" * 50,
    )
    assert selected.selected_markdown == "b" * 50
    assert selected.used_baseline_fallback
    assert selected.reason == "candidate_text_length_collapse"


def test_candidate_ocr_empty_warning_falls_back_to_baseline():
    page = _page(
        "OCR returned no text tokens for 8 detected text/formula region(s); page extraction may be incomplete"
    )
    selected = _select(page=page)
    assert selected.selected_markdown == "baseline text"
    assert selected.reason == "candidate_ocr_empty_for_detected_regions"


def test_empty_ocr_fallback_selects_baseline_canonical_page():
    baseline_page = _page("baseline page")
    candidate_page = _page(
        "OCR returned no text tokens for 8 detected text/formula region(s); page extraction may be incomplete"
    )
    selected = select_routed_markdown(
        candidate_markdown="\n",
        baseline_markdown="baseline text",
        candidate_page=candidate_page,
        baseline_page=baseline_page,
    )
    assert selected.selected_page is baseline_page
    assert selected.used_baseline_fallback


def test_candidate_exception_falls_back_to_baseline():
    selected = _select(error="OCR failed")
    assert selected.selected_markdown == "baseline text"
    assert selected.reason == "candidate_ocr_or_pipeline_error"


def test_missing_candidate_result_falls_back_to_baseline():
    selected = select_routed_markdown(
        candidate_markdown=None,
        baseline_markdown="baseline text",
    )
    assert selected.selected_markdown == "baseline text"
    assert selected.reason == "candidate_result_missing"


def test_malformed_candidate_result_falls_back_to_baseline():
    selected = select_routed_markdown(
        candidate_markdown={"text": "not markdown"},
        baseline_markdown="baseline text",
    )
    assert selected.selected_markdown == "baseline text"
    assert selected.used_baseline_fallback
    assert selected.reason == "candidate_result_malformed"


def test_invalid_candidate_falls_back_to_baseline():
    selected = _select(valid=False)
    assert selected.selected_markdown == "baseline text"
    assert selected.reason == "candidate_result_invalid"


def test_mixed_page_with_han_signal_uses_specialist_but_can_fall_back():
    route = select_ocr_language_route("Han")
    assert route.languages == HAN_OCR_LANGUAGES
    selected = _select(page=_page("OCR returned no text tokens for 1 detected region(s)"))
    assert selected.used_baseline_fallback


def test_false_positive_han_is_not_gt_special_cased():
    # Runtime decision takes only the OSD signal; no filename or GT is accepted.
    assert select_ocr_language_route("Han").languages == HAN_OCR_LANGUAGES


def test_route_and_fallback_decisions_are_deterministic():
    routes = [select_ocr_language_route("Han") for _ in range(3)]
    selections = [_select(candidate="\n") for _ in range(3)]
    assert routes[0] == routes[1] == routes[2]
    assert selections[0] == selections[1] == selections[2]
