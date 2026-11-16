from datetime import date

import pytest

from bd_packet_builder.contracts import (
    AnswerProposal,
    Citation,
    HistoricalBasis,
    HistoricalTenure,
    TextValue,
)
from bd_packet_builder.historical_time import (
    adjusted_tenure,
    anniversary_years,
    increment_years,
    signed_date,
)


def tenure_proposal(quote: str, supplied_date: date) -> AnswerProposal:
    citation = Citation(source_id="a" * 64, page=1, start=0, end=len(quote), quote=quote)
    return AnswerProposal(
        requirement_id="years",
        outcome="proposed",
        value=TextValue(kind="text", value="24"),
        citations=(citation,),
        confidence=0.9,
        historical_basis=HistoricalBasis(
            category="tenure",
            context="firm_wide",
            prior_question=citation,
            current_checks=(),
            reviewer_confirmation="Confirm continuity.",
            tenure=HistoricalTenure(
                prior_value="24",
                signed_on=supplied_date,
                date_citation=citation,
                date_context=citation,
            ),
        ),
    )


@pytest.mark.parametrize("year", [2026, 7147, 7202])
def test_tenure_uses_cited_date_without_mutating_original_proposal(year: int) -> None:
    proposal = tenure_proposal("7/14/2026", date(year, 7, 14))
    original = proposal.model_dump_json()

    adjusted = adjusted_tenure(proposal, date(2027, 7, 14))

    assert adjusted.value == TextValue(kind="text", value="25")
    assert adjusted.historical_basis is not None
    assert adjusted.historical_basis.tenure is not None
    assert adjusted.historical_basis.tenure.signed_on == date(2026, 7, 14)
    assert adjusted.historical_basis.tenure.date_citation == proposal.citations[0]
    assert proposal.model_dump_json() == original
    assert adjusted_tenure(adjusted, date(2027, 7, 14)) == adjusted


@pytest.mark.parametrize(
    "quote",
    ["2026", "7/14/26", "2026-02-30", "7/14/2026 and 7/15/2026", "7/14/2028"],
)
def test_tenure_does_not_fall_back_to_model_date_for_unusable_citation(quote: str) -> None:
    proposal = tenure_proposal(quote, date(2025, 7, 14))
    with pytest.raises(ValueError, match="date"):
        adjusted_tenure(proposal, date(2026, 11, 13))


@pytest.mark.parametrize(
    ("start", "end", "expected"),
    [
        (date(2025, 11, 2), date(2026, 11, 1), 0),
        (date(2025, 11, 2), date(2026, 11, 2), 1),
        (date(2023, 11, 2), date(2026, 11, 2), 3),
        (date(2024, 2, 29), date(2025, 2, 28), 1),
        (date(2024, 2, 29), date(2028, 2, 28), 3),
        (date(2024, 2, 29), date(2028, 2, 29), 4),
    ],
)
def test_completed_calendar_anniversaries(start: date, end: date, expected: int) -> None:
    assert anniversary_years(start, end) == expected


def test_future_baseline_is_not_a_negative_adjustment() -> None:
    with pytest.raises(ValueError, match="future"):
        anniversary_years(date(2027, 1, 1), date(2026, 1, 1))


@pytest.mark.parametrize(
    ("prior", "expected"),
    [
        ("26", "28"),
        ("26 years", "28 years"),
        ("Approximately 26", "Approximately 28"),
        ("~26", "~28"),
    ],
)
def test_tenure_preserves_units_and_qualifiers(prior: str, expected: str) -> None:
    assert increment_years(prior, 2) == expected


@pytest.mark.parametrize("prior", ["26-27", "since 1999", "26.5", "26 months", "-1", "2024/01/01"])
def test_tenure_does_not_guess_an_integer(prior: str) -> None:
    with pytest.raises(ValueError, match="integer"):
        increment_years(prior, 1)


@pytest.mark.parametrize("text", ["2025-11-02", "11/02/2025", "November 2, 2025", "Nov 2, 2025"])
def test_explicit_signed_date_formats(text: str) -> None:
    assert signed_date(text) == date(2025, 11, 2)


@pytest.mark.parametrize("text", ["11/02/25", "2025", "2025-02-30", "2025-11-02 / 2026-01-01"])
def test_missing_or_ambiguous_signature_dates_are_rejected(text: str) -> None:
    with pytest.raises(ValueError, match="date"):
        signed_date(text)
