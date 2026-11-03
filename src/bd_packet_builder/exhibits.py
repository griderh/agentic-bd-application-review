"""Bounded supporting exhibits, never whole completed applications or current certifications."""

import hashlib
import re
from contextlib import closing
from io import BytesIO
from pathlib import Path
from typing import Annotated, Self

import pypdfium2 as pdfium
from pydantic import Field, model_validator
from pypdf import PdfReader, PdfWriter

from bd_packet_builder.contracts import (
    AnswerProposal,
    Citation,
    Contract,
    Identifier,
    NarrativeValue,
    Nonblank,
    OcrCitation,
    TextValue,
)
from bd_packet_builder.evidence import EvidenceError, resolve_quote
from bd_packet_builder.inventory import Inventory, read_source_bytes
from bd_packet_builder.scan import ExhibitImageCheck, ScanVerificationError


class ExhibitError(ValueError):
    """An exhibit selection is unsafe, unresolved or outside the supported contract."""


class HistoricalExhibit(Contract):
    requirement_id: Identifier
    title: Citation | OcrCitation
    pages: Annotated[tuple[Annotated[int, Field(ge=1)], ...], Field(min_length=1, max_length=5)]
    reason: Nonblank
    limitation: Nonblank

    @model_validator(mode="after")
    def bounded_pages(self) -> Self:
        if self.pages != tuple(range(self.pages[0], self.pages[-1] + 1)):
            raise ValueError("Exhibit pages must be a contiguous, increasing selection")
        if self.title.page != self.pages[0]:
            raise ValueError("Exhibit title must occur on its first page")
        if isinstance(self.title, OcrCitation) and self.pages != (self.title.page,):
            raise ValueError("Image exhibits require one independently checked page per selection")
        return self

    @property
    def exhibit_id(self) -> str:
        selection = f"{self.title.source_id}:{','.join(str(p) for p in self.pages)}"
        return "exhibit-" + hashlib.sha256(selection.encode()).hexdigest()[:24]


_FORM_TEXT = re.compile(
    r"\b(signature|signed\s+packet|printed\s+name|qualified\s+representative|"
    r"primary\s+representative|backup\s+representative|"
    r"does\s+your\s+firm|name\s+of\s+(?:firm|dealer)|"
    r"certif(?:y|ication)|attest(?:ation)?)\b",
    re.IGNORECASE,
)


def extract_exhibit(
    root: Path,
    inventory: Inventory,
    exhibit: HistoricalExhibit,
    *,
    proposals: tuple[AnswerProposal, ...] = (),
    image_checks: tuple[ExhibitImageCheck, ...] = (),
) -> bytes:
    """Recheck native title, source version and page safety before copying a small exhibit.

    Image titles require a separate checked receipt, not a model's assertion.
    These checks constrain publication; they do not prove relevance or current truth.
    """
    source = next((s for s in inventory.sources if s.source_id == exhibit.title.source_id), None)
    if source is None or source.family != "historical_reference":
        raise ExhibitError("Exhibit must come from an approved historical reference")
    if source.page_count is None or exhibit.pages[-1] > source.page_count:
        raise ExhibitError("Exhibit page is outside its version-bound source")
    if len(exhibit.pages) >= source.page_count:
        raise ExhibitError("A completed packet cannot be selected as an exhibit")
    form_pages = {
        citation.page
        for proposal in proposals
        if proposal.historical_basis is not None
        for citation in (proposal.historical_basis.prior_question, *proposal.citations)
        if citation.source_id == source.source_id
    }
    if form_pages & set(exhibit.pages):
        raise ExhibitError("Historical answer/question pages cannot be supporting exhibits")
    checked_image_text: str | None = None
    if isinstance(exhibit.title, OcrCitation):
        check = next((c for c in image_checks if c.citation == exhibit.title), None)
        if check is None:
            raise ExhibitError("Image exhibit has no independent title verification")
        try:
            checked_image_text = check.verify(root, inventory)
        except ScanVerificationError:
            raise ExhibitError("Image exhibit title/source verification failed") from None
    else:
        try:
            resolve_quote(root, inventory, exhibit.title.text_citation())
        except EvidenceError:
            raise ExhibitError("Exhibit title does not resolve exactly") from None
    data = read_source_bytes(root, inventory, source.source_id)
    reader = PdfReader(BytesIO(data))
    with pdfium.PdfDocument(data) as document:
        for number in exhibit.pages:
            with closing(document[number - 1]) as page, closing(page.get_textpage()) as text:
                native = text.get_text_range(errors="strict")
            if checked_image_text is not None:
                native += "\n" + checked_image_text
            if len(native.strip()) < 40 or _FORM_TEXT.search(native):
                raise ExhibitError("Exhibit contains form/signing text or insufficient native text")
            if reader.pages[number - 1].get("/Annots"):
                raise ExhibitError("Annotated or interactive historical pages are not exhibits")
    with closing(PdfWriter()) as writer:
        for number in exhibit.pages:
            writer.add_page(reader.pages[number - 1], excluded_keys=("/Annots", "/AA"))
        writer.add_metadata({"/Title": "Historical supporting exhibit - continuity unconfirmed"})
        buffer = BytesIO()
        writer.write(buffer)
    return buffer.getvalue()


class SupportingDocumentAudit(Contract):
    requirement_id: Identifier
    current_source_ids: tuple[str, ...]
    missing_current_source_ids: tuple[str, ...]
    historical_exhibits: tuple[str, ...]
    referenced_support: tuple[str, ...]
    issues: tuple[str, ...]


def audit_support(
    proposals: tuple[AnswerProposal, ...],
    inventory: Inventory,
    attached: tuple[str, ...],
    exhibits: tuple[HistoricalExhibit, ...],
) -> tuple[SupportingDocumentAudit, ...]:
    """Audit physical dependencies, not narrative truth or exhibit date compatibility."""
    historical = {s.source_id for s in inventory.sources if s.family == "historical_reference"}
    audits: list[SupportingDocumentAudit] = []
    for proposal in proposals:
        if proposal.outcome != "proposed":
            continue
        citations = list(proposal.citations)
        if proposal.historical_basis is not None:
            citations.extend(c.citation for c in proposal.historical_basis.current_checks)
        current = tuple(
            dict.fromkeys(c.source_id for c in citations if c.source_id not in historical)
        )
        missing = tuple(s for s in current if s not in attached)
        linked = tuple(
            e.exhibit_id for e in exhibits if e.requirement_id == proposal.requirement_id
        )
        references = list(proposal.supporting_references)
        # A legacy answer may predate explicit reference declarations.
        if isinstance(proposal.value, TextValue | NarrativeValue):
            references.extend(
                re.findall(
                    r"(?:Bloomberg\s+)?League\s+Tables?",
                    proposal.value.value,
                    re.IGNORECASE,
                )
            )
        issues = []
        if missing:
            issues.append("current_comparison_or_answer_document_not_attached")
        if references and not linked:
            issues.append("referenced_exhibit_not_linked")
        if linked:
            issues.append("historical_exhibit_scope_and_period_require_review")
        audits.append(
            SupportingDocumentAudit(
                requirement_id=proposal.requirement_id,
                current_source_ids=current,
                missing_current_source_ids=missing,
                historical_exhibits=linked,
                referenced_support=tuple(dict.fromkeys(references)),
                issues=tuple(issues),
            )
        )
    return tuple(audits)
