import pytest

from bd_packet_builder.question_presentation import (
    questions_agree,
    truncated_question_continues,
    truncated_question_stem,
)


@pytest.mark.parametrize(
    ("left", "right"),
    [
        ("10. References from public:-", "References from public-:"),
        ("(10) References from public?!-:", "10: references from public-:"),
        ("Name, address; title?", "NAME address title."),
        ("Please provide [references].", "Please provide references!"),
        ("References from public\u2014:", "References from public:\u2014"),
        ("Firm name\u2019s address?", "Firm name's address."),
        ("1. Name", "Name"),
    ],
)
def test_question_presentation_ignores_only_nonsemantic_differences(left, right):
    assert questions_agree(left, right)


@pytest.mark.parametrize(
    ("left", "right"),
    [
        ("1. Name", "2. Name"),
        ("Capital $10.5 million", "Capital $105 million"),
        ("Capital 1,000", "Capital 1.000"),
        ("Value -5", "Value 5"),
        ("Value - 5", "Value 5"),
        ("Value ( 5 )", "Value 5"),
        ("Value 10 . 5", "Value 10 5"),
        ("Rule 15c3-1", "Rule 15 c3-1"),
        ("Value <5", "Value >5"),
        ("CRD AB-123", "CRD AB123"),
        ("Rule 15c3-1", "Rule 15c31"),
        ("Has not traded?", "Has traded?"),
        ("During 2025", "During 2026"),
        ("Public-sector clients", "Public clients"),
        ("Ratio 1/2", "Ratio 12"),
        ("Ratio 1 / 2", "Ratio 1 2"),
        ("A & B", "A B"),
        ("Value +5", "Value 5"),
        ("Value \u22125", "Value 5"),
        ("Rate 5%", "Rate 5"),
        ("Value (5)", "Value 5"),
        ("Capital $5", "Capital 5"),
        ("Name", "Name if authorized"),
    ],
)
def test_question_presentation_preserves_constraints_and_identifiers(left, right):
    assert not questions_agree(left, right)


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("3. References-:", ["references"]),
        ("References:-", ["references"]),
        ("References ?! - ; :", ["references"]),
        ("References\u2014:", ["references"]),
        ("References...", ["references"]),
        ("References\u2026", ["references"]),
        ("References:", None),
        ("References?", None),
        ("References", None),
        ("Value -5", None),
        ("Value-:$", None),
    ],
)
def test_truncation_requires_explicit_presentation_signal(text, expected):
    assert truncated_question_stem(text) == expected


@pytest.mark.parametrize(
    ("truncated", "full", "expected"),
    [
        ("References from public-:", "References from public clients", True),
        ("References from public-:", "References from public-sector clients", True),
        ("References from public:-", "References from public-sector", True),
        ("10. References from pub...", "10.References from public clients", True),
        ("10. References from pub...", "References from public clients", True),
        ("10. References from pub...", "11. References from public clients", False),
        ("References from pub\u2026", "References from public clients", True),
        ("References from pubx-:", "References from public clients", False),
        ("References for public-:", "References from public-sector clients", False),
        ("References from public-:", "References from public", False),
        ("References from public-sector-:", "References from public clients", False),
        ("References from public:", "References from public-sector clients", False),
        ("-:", "References", False),
    ],
)
def test_truncated_question_may_end_inside_the_next_word(truncated, full, expected):
    assert truncated_question_continues(truncated, full) is expected
