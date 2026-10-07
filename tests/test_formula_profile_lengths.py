from benchmarks.scripts.profile_docling_formula import (
    generation_input_kwargs,
    summarize_generated_rows,
)


def test_formula_profile_counts_each_row_to_eos_and_ignores_batch_padding():
    result = summarize_generated_rows(
        [[10, 11, 21, 0, 0], [10, 11, 31, 32, 0]],
        input_tokens=2,
        eos_token_id=21,
        pad_token_id=0,
        max_new_tokens=4,
    )

    assert result == [
        {
            "generated_tokens": 1,
            "completion_observation": "eos_observed",
            "cap_length_observed": False,
        },
        {
            "generated_tokens": 2,
            "completion_observation": "pad_observed_without_prior_eos",
            "cap_length_observed": False,
        },
    ]


def test_formula_profile_marks_cap_length_without_claiming_stop_cause():
    result = summarize_generated_rows(
        [[10, 11, 31, 32, 33]],
        input_tokens=2,
        eos_token_id=21,
        pad_token_id=0,
        max_new_tokens=3,
    )

    assert result == [
        {
            "generated_tokens": 3,
            "completion_observation": "cap_length_observed",
            "cap_length_observed": True,
        }
    ]


def test_formula_profile_keeps_missing_input_length_unavailable():
    assert summarize_generated_rows(
        [[10, 11]],
        input_tokens=None,
        eos_token_id=21,
        pad_token_id=0,
        max_new_tokens=3,
    ) is None


def test_formula_cap_override_is_opt_in_and_formula_only():
    formula = {"prompt": "<formula>", "max_new_tokens": 2048}
    code = {"prompt": "<code>", "max_new_tokens": 2048}

    assert generation_input_kwargs(formula, formula_cap_override=None) == formula
    assert generation_input_kwargs(formula, formula_cap_override=1024) == {
        "prompt": "<formula>",
        "max_new_tokens": 1024,
    }
    assert generation_input_kwargs(code, formula_cap_override=1024) == code
    assert formula["max_new_tokens"] == 2048
