"""Deterministic filename-period selection, independent of storage and models."""

import re
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Literal

SelectionFlag = Literal[
    "missing_document",
    "unparseable_period",
    "ambiguous_period",
    "requested_period_unavailable",
]
Cadence = Literal["monthly", "annual"]
_YEAR = re.compile(r"(?<!\d)(20\d{2})(?!\d)")
_PERIOD = re.compile(r"(?<!\d)(20\d{2})[-_](0[1-9]|1[0-2])(?!\d|[-_]\d)")
_MONTH_NAMES = (
    "jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|may|jun(?:e)?|"
    "jul(?:y)?|aug(?:ust)?|sep(?:t(?:ember)?)?|oct(?:ober)?|nov(?:ember)?|dec(?:ember)?"
)
_NAMED_PERIOD = re.compile(rf"(?<![a-z])({_MONTH_NAMES})[\s_-]*(20\d{{2}})(?!\d)", re.IGNORECASE)
_MONTHS = {
    name: index
    for index, name in enumerate(
        ("jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"),
        start=1,
    )
}


@dataclass(frozen=True)
class DocumentSelection:
    path: Path | None
    period: date | None
    flags: tuple[SelectionFlag, ...] = ()


def select_document(
    paths: Iterable[Path],
    *,
    requested_period: date | None = None,
    cadence: Cadence = "monthly",
) -> DocumentSelection:
    """Select within one homogeneous family, using filename metadata only.

    Missing requested periods return the latest available evidence with an explicit
    mismatch. This is not a determination that the evidence satisfies the request.
    """
    _validate_cadence(cadence)
    if requested_period is not None:
        if requested_period.day != 1:
            raise ValueError("A reporting period must use the first day of the month")
        if cadence == "annual" and requested_period.month != 1:
            raise ValueError("An annual reporting period must use January first")
    candidates = sorted(set(paths))
    if not candidates:
        return DocumentSelection(None, None, ("missing_document",))

    by_period: dict[date, list[Path]] = {}
    for path in candidates:
        period = filename_period(path, cadence=cadence)
        if period is None:
            return DocumentSelection(None, None, ("unparseable_period",))
        by_period.setdefault(period, []).append(path)

    flags: tuple[SelectionFlag, ...] = ()
    if requested_period is not None and requested_period in by_period:
        selected_period = requested_period
    else:
        selected_period = max(by_period)
        if requested_period is not None:
            flags = ("requested_period_unavailable",)
    matches_for_period = by_period[selected_period]
    if len(matches_for_period) != 1:
        return DocumentSelection(None, None, (*flags, "ambiguous_period"))
    return DocumentSelection(matches_for_period[0], selected_period, flags)


def _validate_cadence(cadence: Cadence) -> None:
    if cadence not in ("monthly", "annual"):
        raise ValueError("Unsupported reporting cadence")


def filename_period(path: Path, *, cadence: Cadence) -> date | None:
    """Parse a single period; never use timestamps or infer ambiguous compact dates."""
    _validate_cadence(cadence)
    years = list(_YEAR.finditer(path.stem))
    numeric = list(_PERIOD.finditer(path.stem))
    named = list(_NAMED_PERIOD.finditer(path.stem))
    if len(years) != 1:
        return None
    if cadence == "annual":
        # Annual families must not silently truncate a more precise filename date.
        if numeric or named or re.search(r"20\d{2}[-_.]\d", path.stem):
            return None
        return date(int(years[0][1]), 1, 1)
    if len(numeric) + len(named) != 1:
        return None
    if numeric:
        return date(int(numeric[0][1]), int(numeric[0][2]), 1)
    return date(int(named[0][2]), _MONTHS[named[0][1][:3].lower()], 1)
