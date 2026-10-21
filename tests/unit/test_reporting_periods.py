from datetime import date

import pytest

from bd_packet_builder.evidence import PageEvidence, check_reporting_period


def page(text: str, number: int = 1) -> PageEvidence:
    return PageEvidence("a" * 64, number, text, ())


@pytest.mark.parametrize(
    ("family", "filename_period", "text", "observed"),
    [
        ("Focus_Reports", "2026-08", "Reporting period ended August 31, 2026", date(2026, 8, 31)),
        ("Focus_Reports", "2026-08", "As of: 2026-08-31", date(2026, 8, 31)),
        (
            "Focus_Reports",
            "2026-08",
            "For the period beginning July 1, 2026 and ending August 31, 2026",
            date(2026, 8, 31),
        ),
        (
            "Audited_Financials",
            "2025",
            "STATEMENT OF FINANCIAL CONDITION\nDecember 31, 2025",
            date(2025, 12, 31),
        ),
        (
            "Audited_Financials",
            "2025",
            "Statement of Financial Condition\nAs of December 31, 2025",
            date(2025, 12, 31),
        ),
    ],
)
def test_labeled_report_dates_have_exact_page_spans(
    family: str, filename_period: str, text: str, observed: date
) -> None:
    result = check_reporting_period(
        family, filename_period, (page("Unrelated cover"), page(text, 2))
    )
    assert result.status == "filename_period_corroborated"
    assert result.observations[0].date == observed
    citation = result.observations[0].citation
    assert citation.source_id == "a" * 64
    assert citation.page == 2
    assert text[citation.start : citation.end] == citation.quote
    assert citation.quote in text


@pytest.mark.parametrize(
    "text",
    [
        "Printed on August 31, 2026",
        "The report was filed September 17, 2026.",
        "As of 08/31/2026",  # Ambiguous numeric formats are not guessed.
        "As of February 30, 2026",
        "As of August 2026",  # No invented day.
        "In 2026 our capital increased.",
        "Signature date: August 31, 2026",
        "Auditor's report dated September 17, 2026",
    ],
)
def test_unlabeled_ambiguous_or_invalid_dates_do_not_corroborate(text: str) -> None:
    result = check_reporting_period("Focus_Reports", "2026-08", (page(text),))
    assert result.status == "reporting_period_unverified"


def test_distinct_labeled_dates_are_conflicting_even_if_in_the_same_month() -> None:
    result = check_reporting_period(
        "Focus_Reports",
        "2026-08",
        (page("As of August 30, 2026\nAs of August 31, 2026"),),
    )
    assert result.status == "conflicting_reporting_dates"
    assert len(result.observations) == 2


def test_repeated_same_date_is_not_a_conflict() -> None:
    result = check_reporting_period(
        "Focus_Reports", "2026-08", (page("As of August 31, 2026\nAs of August 31, 2026"),)
    )
    assert result.status == "filename_period_corroborated"
    assert len(result.observations) == 2


def test_content_date_mismatch_does_not_replace_filename_or_claim_approval() -> None:
    result = check_reporting_period("Focus_Reports", "2026-08", (page("As of July 31, 2026"),))
    assert result.status == "filename_content_period_mismatch"
    assert result.filename_period == "2026-08"
    assert result.observations[0].date == date(2026, 7, 31)


def test_unknown_filename_period_stays_unresolved_despite_content_date() -> None:
    result = check_reporting_period("Focus_Reports", None, (page("As of August 31, 2026"),))
    assert result.status == "filename_period_unresolved"
    assert len(result.observations) == 1


def test_unconfigured_family_does_not_get_generic_reporting_date_inference() -> None:
    result = check_reporting_period("bios", None, (page("As of August 31, 2026"),))
    assert result.status == "period_check_not_configured"
    assert result.observations == ()


def test_partial_page_coverage_cannot_corroborate_a_whole_document_period() -> None:
    result = check_reporting_period(
        "Focus_Reports",
        "2026-08",
        (page("As of August 31, 2026"), PageEvidence("a" * 64, 2, "", ("no_native_text",))),
    )
    assert result.status == "reporting_period_unverified"
    assert len(result.observations) == 1


def test_annual_year_match_does_not_claim_fiscal_year_end_verified() -> None:
    result = check_reporting_period(
        "Audited_Financials", "2025", (page("Statement of Financial Condition June 30, 2025"),)
    )
    assert result.status == "filename_period_corroborated"
    assert result.precision == "year"


def test_valid_date_does_not_hide_an_unrecognized_labeled_date() -> None:
    result = check_reporting_period(
        "Focus_Reports", "2026-08", (page("As of August 31, 2026\nAs of 07/31/2026"),)
    )
    assert result.status == "reporting_period_unverified"
    assert result.flags == ("unrecognized_reporting_date",)
    assert len(result.observations) == 1
