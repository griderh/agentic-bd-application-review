from datetime import date
from pathlib import Path

import pytest

from bd_packet_builder.sources import select_document


def test_latest_period_not_input_order() -> None:
    older = Path("FOCUS_2026-07.pdf")
    latest = Path("FOCUS_2026-09.pdf")
    result = select_document([latest, older])
    assert result.path == latest
    assert result.period == date(2026, 9, 1)
    assert result.flags == ()


def test_explicit_period_overrides_latest() -> None:
    wanted = Path("FOCUS_2026-07.pdf")
    result = select_document([Path("FOCUS_2026-09.pdf"), wanted], requested_period=date(2026, 7, 1))
    assert result.path == wanted
    assert result.flags == ()


def test_unavailable_period_reports_actual_evidence_and_gap() -> None:
    result = select_document([Path("FOCUS_2026-08.pdf")], requested_period=date(2026, 9, 1))
    assert result.path == Path("FOCUS_2026-08.pdf")
    assert result.period == date(2026, 8, 1)
    assert result.flags == ("requested_period_unavailable",)


@pytest.mark.parametrize(
    ("paths", "flag"),
    [
        ([], "missing_document"),
        ([Path("FOCUS_latest.pdf")], "unparseable_period"),
        ([Path("FOCUS_2026-13.pdf")], "unparseable_period"),
        ([Path("FOCUS_2026-08_2026-09.pdf")], "unparseable_period"),
        (
            [Path("FOCUS_2026-08.pdf"), Path("FOCUS_2026-08_copy.pdf")],
            "ambiguous_period",
        ),
        (
            [Path("FOCUS_2026-08.pdf"), Path("FOCUS_latest.pdf")],
            "unparseable_period",
        ),
    ],
)
def test_unresolved_selection_never_silently_picks_a_file(paths: list[Path], flag: str) -> None:
    result = select_document(paths)
    assert result.path is None
    assert result.period is None
    assert result.flags == (flag,)


def test_older_duplicate_does_not_make_latest_ambiguous() -> None:
    result = select_document([Path("a_2026-07.pdf"), Path("b_2026-07.pdf"), Path("c_2026-08.pdf")])
    assert result.path == Path("c_2026-08.pdf")


def test_period_request_must_identify_month_not_arbitrary_day() -> None:
    with pytest.raises(ValueError, match="first day"):
        select_document([], requested_period=date(2026, 8, 17))


@pytest.mark.parametrize(
    ("filename", "expected"),
    [
        ("FOCUS_Aug2026_Public.pdf", date(2026, 8, 1)),
        ("FOCUS_Feb2023_Public.pdf", date(2023, 2, 1)),
        ("FOCUS Sept 2021 Public.pdf", date(2021, 9, 1)),
        ("FOCUS_September_2021.pdf", date(2021, 9, 1)),
        ("FOCUS_2026_08.pdf", date(2026, 8, 1)),
    ],
)
def test_historical_month_spellings(filename: str, expected: date) -> None:
    result = select_document([Path(filename)])
    assert result.period == expected
    assert result.flags == ()


@pytest.mark.parametrize(
    "filename",
    [
        "FOCUS_Aug2026_Sept2026.pdf",
        "FOCUS_Aug2026_2027.pdf",
        "FOCUS_2026-08-17.pdf",
        "FOCUS_Aug20266.pdf",
        "FOCUS_2026-00.pdf",
    ],
)
def test_multiple_or_more_precise_dates_are_not_silently_interpreted_as_months(
    filename: str,
) -> None:
    assert select_document([Path(filename)]).flags == ("unparseable_period",)


@pytest.mark.parametrize("filename", ["Statement_FY2025.pdf", "Synthetic LLC 2022 FS.pdf"])
def test_annual_selection_requires_explicit_cadence(filename: str) -> None:
    result = select_document([Path(filename)], cadence="annual")
    assert result.period == date(2025 if "2025" in filename else 2022, 1, 1)
    assert result.flags == ()
    assert select_document([Path(filename)]).flags == ("unparseable_period",)


def test_annual_request_must_use_january_first() -> None:
    with pytest.raises(ValueError, match="January"):
        select_document([], cadence="annual", requested_period=date(2025, 8, 1))


def test_annual_parser_does_not_guess_a_year_from_monthly_or_range_names() -> None:
    for filename in ["Statement_2025_2026.pdf", "Statement_2025-08.pdf"]:
        assert select_document([Path(filename)], cadence="annual").path is None


def test_unknown_cadence_is_rejected() -> None:
    with pytest.raises(ValueError, match="cadence"):
        select_document([], cadence="weekly")  # type: ignore[arg-type]
