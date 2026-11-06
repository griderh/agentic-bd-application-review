import pytest

from bd_packet_builder.draft import _question_links_agree


@pytest.mark.parametrize(
    ("pointer", "answer", "expected"),
    [
        ("3. Describe services.", "3: DESCRIBE\nservices", True),
        ("Describe services.", "3: Describe services", True),
        ("3) Describe services", "Describe services.", True),
        ("(3) Describe services", "3. Describe services", True),
        ("3.Describe services", "Describe services", True),
        ("3. Describe services", "4: Describe services", False),
        ("Describe services", "Describe services if authorized", False),
        ("Describe services if authorized", "Describe services", False),
        ("Describe services", "Do not describe services", False),
        ("Capital as of 2025", "Capital as of 2026", False),
        ("Capital at least 100", "Capital at least 200", False),
        ("Capital >= 100", "Capital <= 100", False),
        ("Capital > 100", "Capital >= 100", False),
        ("Return -5%", "Return 5%", False),
        ("Return 5%", "Return 5", False),
        ("Capital 3.5 million", "Capital 3,5 million", False),
        ("CRD 001234", "CRD 1234", False),
        ("2026 trading volume", "Trading volume", False),
        ("3.5 million capital", "5 million capital", False),
        ("3.14 million capital", "14 million capital", False),
        ("3 million capital", "Million capital", False),
        ("3.", "Describe services", False),
        ("Describe municipal services", "Describe firm-wide services", False),
        ("Describe services", "Summarize services", False),
    ],
)
def test_question_link_presentation_preserves_substantive_wording(pointer, answer, expected):
    assert _question_links_agree(pointer, answer) == expected


@pytest.mark.parametrize(
    ("pointer", "answer", "expected"),
    [
        ("3. Name if authorized", "3: Name-:", True),
        ("3. Name if authorized", "3: Name...", True),
        ("4. Name if authorized", "3: Name-:", False),
        ("3. Name if authorized", "3: Name", False),
        ("3. Name if authorized", "3: Nam-:", False),
        ("3. Name-:", "3: Name if authorized", False),
    ],
)
def test_only_verified_explicit_supplement_truncation_allows_continuation(
    pointer, answer, expected
):
    assert _question_links_agree(pointer, answer, allow_truncated_answer=True) == expected
