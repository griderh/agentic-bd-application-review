"""Bounded native PDF text and literal date corroboration, not approved answers."""

import re
from contextlib import closing
from dataclasses import asdict, dataclass
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Literal

import pypdfium2 as pdfium

from bd_packet_builder.inventory import (
    EvidenceReference,
    Inventory,
    SourceRecord,
    publish_json_run,
    read_source_bytes,
    resolve_reference,
)

_MONTHS = {
    name: index
    for index, name in enumerate(
        (
            "january",
            "february",
            "march",
            "april",
            "may",
            "june",
            "july",
            "august",
            "september",
            "october",
            "november",
            "december",
        ),
        start=1,
    )
}
_DATE = re.compile(
    rf"(?P<iso>20\d{{2}}-\d{{2}}-\d{{2}})(?!\d)|"
    rf"(?P<month>{'|'.join(_MONTHS)})[ \t]+(?P<day>\d{{1,2}}),[ \t]+"
    r"(?P<year>20\d{2})(?!\d)",
    re.IGNORECASE,
)
_MONTHLY_LABEL = re.compile(
    r"^[ \t]*(?:as of|(?:reporting )?period ended|"
    r"for the period beginning[^\n]{1,100}?\band ending)[: \t\r\n]{1,12}",
    re.IGNORECASE | re.MULTILINE,
)
_ANNUAL_LABEL = re.compile(
    r"^[ \t]*statement of financial condition[ \t\r\n:]{1,12}"
    r"(?:as of[: \t\r\n]{1,12})?",
    re.IGNORECASE | re.MULTILINE,
)


class EvidenceError(ValueError):
    """Safe extraction/quote validation failures without document payloads."""


@dataclass(frozen=True)
class ExtractionLimits:
    max_pages_per_document: int = 500
    max_chars_per_page: int = 100_000
    max_chars_per_run: int = 5_000_000

    def __post_init__(self) -> None:
        for limit in (self.max_pages_per_document, self.max_chars_per_page, self.max_chars_per_run):
            if type(limit) is not int or limit < 1:
                raise EvidenceError("Each extraction limit must be a positive integer")


_DEFAULT_LIMITS = ExtractionLimits()


@dataclass(frozen=True)
class PageEvidence:
    source_id: str
    page: int
    text: str
    flags: tuple[str, ...]


@dataclass(frozen=True)
class TextCitation:
    """Offsets are Python string indices into CRLF-normalized native page-area text."""

    source_id: str
    page: int
    start: int
    end: int
    quote: str

    def __post_init__(self) -> None:
        EvidenceReference(self.source_id, self.page)
        if (
            type(self.start) is not int
            or type(self.end) is not int
            or not 0 <= self.start < self.end
            or not isinstance(self.quote, str)
            or not self.quote
        ):
            raise EvidenceError("Invalid quote offsets or text")


@dataclass(frozen=True)
class ReportingDate:
    date: date
    citation: TextCitation


@dataclass(frozen=True)
class PeriodCheck:
    filename_period: str | None
    precision: Literal["month", "year"] | None
    status: str
    observations: tuple[ReportingDate, ...]
    flags: tuple[str, ...] = ()


@dataclass(frozen=True)
class DocumentEvidence:
    source: SourceRecord
    pages: tuple[PageEvidence, ...]
    period_check: PeriodCheck
    flags: tuple[str, ...]


@dataclass(frozen=True)
class EvidenceBundle:
    created_at: datetime
    limits: ExtractionLimits
    documents: tuple[DocumentEvidence, ...]
    flags: tuple[str, ...] = ("not_semantic_grounding",)


def _observations(
    pages: tuple[PageEvidence, ...], label: re.Pattern[str]
) -> tuple[tuple[ReportingDate, ...], bool]:
    observations: list[ReportingDate] = []
    unrecognized = False
    for page in pages:
        for match in label.finditer(page.text):
            value = _DATE.match(page.text, match.end())
            if value is None:
                unrecognized = True
                continue
            try:
                observed = (
                    date.fromisoformat(value["iso"])
                    if value["iso"] is not None
                    else date(
                        int(value["year"]), _MONTHS[value["month"].lower()], int(value["day"])
                    )
                )
            except ValueError:
                unrecognized = True
                continue
            observations.append(
                ReportingDate(
                    observed,
                    TextCitation(
                        page.source_id,
                        page.page,
                        match.start(),
                        value.end(),
                        page.text[match.start() : value.end()],
                    ),
                )
            )
    return tuple(observations), unrecognized


def check_reporting_period(
    family: str, filename_period: str | None, pages: tuple[PageEvidence, ...]
) -> PeriodCheck:
    """Compare only explicit, narrowly labeled dates; never approve evidence adequacy."""
    if family not in ("Focus_Reports", "Audited_Financials"):
        return PeriodCheck(filename_period, None, "period_check_not_configured", ())
    monthly = family == "Focus_Reports"
    observations, unrecognized = _observations(pages, _MONTHLY_LABEL if monthly else _ANNUAL_LABEL)
    dates = {observation.date for observation in observations}
    flags = ("unrecognized_reporting_date",) if unrecognized else ()
    if len(dates) > 1:
        status = "conflicting_reporting_dates"
    elif filename_period is None:
        status = "filename_period_unresolved"
    elif not dates or unrecognized or not pages or any(page.flags for page in pages):
        status = "reporting_period_unverified"
    else:
        observed = next(iter(dates))
        period = observed.strftime("%Y-%m") if monthly else str(observed.year)
        status = (
            "filename_period_corroborated"
            if period == filename_period
            else "filename_content_period_mismatch"
        )
    return PeriodCheck(filename_period, "month" if monthly else "year", status, observations, flags)


def _page_text(
    document: pdfium.PdfDocument, source_id: str, index: int, limits: ExtractionLimits
) -> PageEvidence:
    try:
        with closing(document[index]) as page, closing(page.get_textpage()) as textpage:
            if textpage.count_chars() > limits.max_chars_per_page:
                raise EvidenceError("Native text exceeds the per-page character limit")
            text = textpage.get_text_bounded(errors="strict").replace("\r\n", "\n")
            if len(text) > limits.max_chars_per_page:
                raise EvidenceError("Native text exceeds the per-page character limit")
    except (pdfium.PdfiumError, UnicodeError):
        return PageEvidence(source_id, index + 1, "", ("native_text_extraction_failed",))
    flags = () if text.strip() else ("no_native_text",)
    return PageEvidence(source_id, index + 1, text, flags)


def extract_evidence(
    root: Path, inventory: Inventory, *, limits: ExtractionLimits = _DEFAULT_LIMITS
) -> EvidenceBundle:
    """Extract only known, unchanged inventory versions; never silently truncate."""
    documents: list[DocumentEvidence] = []
    total_chars = 0
    for source in inventory.sources:
        data = read_source_bytes(root, inventory, source.source_id)
        pages: list[PageEvidence] = []
        flags: tuple[str, ...] = ()
        if source.format != "pdf" or source.page_count is None:
            flags = ("native_text_unavailable",)
        else:
            if source.page_count > limits.max_pages_per_document:
                raise EvidenceError("PDF exceeds the per-document page limit")
            try:
                with pdfium.PdfDocument(data) as document:
                    if len(document) != source.page_count:
                        raise EvidenceError("PDF page count differs from the inventory")
                    for index in range(len(document)):
                        page = _page_text(document, source.source_id, index, limits)
                        pages.append(page)
                        total_chars += len(page.text)
                        if total_chars > limits.max_chars_per_run:
                            raise EvidenceError("Native text exceeds the run character limit")
            except pdfium.PdfiumError:
                pages = []
                flags = ("native_text_unavailable",)
            if any(page.flags for page in pages):
                flags = (*flags, "partial_native_text")
        read_source_bytes(root, inventory, source.source_id)
        page_tuple = tuple(pages)
        documents.append(
            DocumentEvidence(
                source,
                page_tuple,
                check_reporting_period(source.family, source.period, page_tuple),
                flags,
            )
        )
    return EvidenceBundle(datetime.now(UTC), limits, tuple(documents))


def resolve_quote(
    root: Path,
    inventory: Inventory,
    citation: TextCitation,
    *,
    limits: ExtractionLimits = _DEFAULT_LIMITS,
) -> str:
    """Re-extract a known current page and check exact text, not factual relevance."""
    reference = EvidenceReference(citation.source_id, citation.page)
    resolve_reference(root, inventory, reference)
    data = read_source_bytes(root, inventory, citation.source_id)
    try:
        with pdfium.PdfDocument(data) as document:
            page = _page_text(document, citation.source_id, citation.page - 1, limits)
    except pdfium.PdfiumError:
        raise EvidenceError("Cannot resolve quote from unreadable PDF") from None
    if (
        page.flags
        or citation.end > len(page.text)
        or page.text[citation.start : citation.end] != citation.quote
    ):
        raise EvidenceError("Citation quote does not match the referenced page text")
    read_source_bytes(root, inventory, citation.source_id)
    return citation.quote


def publish_evidence(root: Path, inventory: Inventory, bundle: EvidenceBundle) -> Path:
    """Publish confidential extracted text locally; no external payload loader exists."""
    if tuple(d.source for d in bundle.documents) != inventory.sources:
        raise EvidenceError("Evidence bundle does not match the supplied inventory")
    payload: dict[str, object] = {
        "schema_version": 1,
        "status": "native_text_only_not_approved_answers",
        "extractor_version": "pdfium-native-v1",
        "period_rule_version": "labeled-report-dates-v1",
        "created_at": bundle.created_at.isoformat(),
        "inventory_created_at": inventory.created_at.isoformat(),
        "limits": asdict(bundle.limits),
        "flags": bundle.flags,
        "inventory_issues": [asdict(issue) for issue in inventory.issues],
        "documents": [
            {
                **asdict(document),
                "period_check": {
                    **asdict(document.period_check),
                    "observations": [
                        {"date": observed.date.isoformat(), "citation": asdict(observed.citation)}
                        for observed in document.period_check.observations
                    ],
                },
            }
            for document in bundle.documents
        ],
    }
    return publish_json_run(root, "evidence", payload, inventory)
