"""Run-local representative/bio identity links, not answer or currency approval."""

import re
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Annotated, Literal, Self

from pydantic import Field, model_validator

from bd_packet_builder.contracts import (
    AnswerProposal,
    Citation,
    Contract,
    HistoricalContextCitation,
    Identifier,
    OcrCitation,
    Sha256,
    TextValue,
)
from bd_packet_builder.draft import verify_ocr_citation
from bd_packet_builder.evidence import EvidenceError, resolve_quote
from bd_packet_builder.evidence_tools import EvidenceTools, ToolInputError, ToolLimitError
from bd_packet_builder.historical_context import HistoricalContextCheck
from bd_packet_builder.inventory import Inventory, read_source_bytes
from bd_packet_builder.local_inputs import read_local_input
from bd_packet_builder.retrieval import default_catalog
from bd_packet_builder.scan import (
    SUPPORTED_SCAN_VERSIONS,
    ScanCheck,
    ScanVerificationError,
    check_agreement,
    normalized,
)

BIO_RESOLUTION_VERSION = "representative-bios-v2"
# "email_address" (not "email") keeps tool schemas free of anything resembling a send capability.
ProfileField = Literal["title", "telephone", "email_address"]


class RepresentativeField(Contract):
    """Model-proposed meaning of a related field; code supplies and checks its value."""

    requirement_id: Identifier
    field: ProfileField


class RepresentativeBioRequest(Contract):
    role_requirement_id: Identifier
    requirement_ids: Annotated[tuple[Identifier, ...], Field(min_length=1, max_length=30)]
    role: Annotated[str, Field(min_length=1, max_length=200)]
    person: Annotated[str, Field(min_length=1, max_length=200)] | None = None
    assignment: Citation | OcrCitation | None = None
    historical_context: HistoricalContextCitation | None = None
    field_requirements: Annotated[tuple[RepresentativeField, ...], Field(max_length=29)] = ()

    @model_validator(mode="after")
    def consistent(self) -> Self:
        mapped = [f.requirement_id for f in self.field_requirements]
        if len(set(mapped)) != len(mapped) or any(
            r == self.role_requirement_id or r not in self.requirement_ids for r in mapped
        ):
            raise ValueError("Bio field mappings must name distinct related non-name requirements")
        if self.role_requirement_id not in self.requirement_ids or len(
            set(self.requirement_ids)
        ) != len(self.requirement_ids):
            raise ValueError(
                "Representative requirements must be unique and include the name field"
            )
        if (self.person is None) != (self.assignment is None):
            raise ValueError("A named representative requires assignment evidence")
        if self.historical_context is not None and self.assignment is None:
            raise ValueError("Historical context requires assignment evidence")
        if not self.role.strip() or self.person is not None and not self.person.strip():
            raise ValueError("Representative role and name must not be blank")
        return self


class BioCandidate(Contract):
    source_id: Sha256
    source_sha256: Sha256
    identity: Citation | OcrCitation
    equivalent_source_ids: tuple[Sha256, ...] = ()


class ProfileLine(Contract):
    kind: ProfileField
    text: Annotated[str, Field(min_length=1, max_length=200)]
    start: Annotated[int, Field(ge=0)]
    end: Annotated[int, Field(ge=1)]


class BioProfile(Contract):
    """Name/title/contact card printed in the selected bio; never an assignment or currency."""

    status: Literal["extracted", "not_found", "ambiguous", "not_native"]
    source_id: Sha256
    page: Annotated[int, Field(ge=1)] | None = None
    citation: Citation | None = None
    lines: tuple[ProfileLine, ...] = ()

    @model_validator(mode="after")
    def bound_lines(self) -> Self:
        citation = self.citation
        if (self.status == "extracted") != (citation is not None) or (
            citation is None and self.lines
        ):
            raise ValueError("Only an extracted profile carries a card citation and lines")
        if citation is not None and (
            citation.source_id != self.source_id
            or citation.page != self.page
            or not self.lines
            or any(
                line.start < citation.start
                or line.end > citation.end
                or citation.quote[line.start - citation.start : line.end - citation.start]
                != line.text
                for line in self.lines
            )
        ):
            raise ValueError("Profile lines must be exact spans of the cited card")
        return self

    def span(self, lines: Sequence[ProfileLine]) -> Citation:
        assert self.citation is not None and self.page is not None
        start, end = lines[0].start, lines[-1].end
        offset = self.citation.start
        return Citation(
            source_id=self.source_id,
            page=self.page,
            start=start,
            end=end,
            quote=self.citation.quote[start - offset : end - offset],
        )


class RepresentativeBioResolution(Contract):
    request: RepresentativeBioRequest
    status: Literal[
        "selected", "assignment_unresolved", "missing_bio", "ambiguous_bio", "bio_review_required"
    ]
    assignment_status: Literal[
        "unresolved", "explicit_source_assignment", "historical_assignment_unconfirmed"
    ]
    candidates: tuple[BioCandidate, ...] = ()
    selected_source_id: Sha256 | None = None
    issues: tuple[str, ...] = ()
    profile: BioProfile | None = None
    currency: Literal["not_confirmed"] = "not_confirmed"
    scope: Literal["identity_link_not_answer_or_assignment_approval"] = (
        "identity_link_not_answer_or_assignment_approval"
    )


def _native_quote(root: Path, inventory: Inventory, citation: Citation) -> None:
    try:
        resolve_quote(root, inventory, citation.text_citation())
    except EvidenceError:
        raise ToolInputError("Representative evidence quote does not resolve") from None


def _scan_quote(
    root: Path, inventory: Inventory, citation: OcrCitation, checks: tuple[ScanCheck, ...]
) -> ScanCheck:
    check = next((c for c in checks if c.citation == citation), None)
    if check is None:
        raise ToolInputError("Representative OCR evidence needs an independent checked reading")
    issue, artifact, _ = verify_ocr_citation(root, inventory, citation, {})
    if (
        issue
        or artifact is None
        or check.prompt_version not in SUPPORTED_SCAN_VERSIONS
        or not check.agrees_with_artifact(artifact)
    ):
        raise ToolInputError("Representative OCR artifact no longer verifies")
    try:
        check_agreement(check.transcript, check.expected_subject, citation.quote)
    except ScanVerificationError:
        raise ToolInputError("Representative OCR evidence no longer verifies") from None
    return check


def _assignment_status(
    root: Path,
    inventory: Inventory,
    request: RepresentativeBioRequest,
    historical_checks: tuple[HistoricalContextCheck, ...],
    scan_checks: tuple[ScanCheck, ...],
) -> Literal["unresolved", "explicit_source_assignment", "historical_assignment_unconfirmed"]:
    citation = request.assignment
    if citation is None:
        return "unresolved"
    source = next((s for s in inventory.sources if s.source_id == citation.source_id), None)
    if source is None or source.family == "bios":
        raise ToolInputError("A biography cannot establish the application role assignment")
    if source.family not in {f.folder for f in default_catalog().families} | {
        "historical_reference"
    }:
        raise ToolInputError("Representative assignment source is outside the approved catalog")
    read_source_bytes(root, inventory, source.source_id)
    if source.family == "historical_reference":
        check = next(
            (c for c in historical_checks if c.context_citation == request.historical_context), None
        )
        if (
            check is None
            or check.answer != citation
            or check.field.control is not None
            or check.answer_disputed
            or normalized(check.field.answer.text) != normalized(request.person or "")
            or check.context_role is None
            or normalized(check.context_role.quote) != normalized(request.role)
            or any(d.part == "role" for d in check.discrepancies)
        ):
            raise ToolInputError("Historical assignment requires a checked matching name and role")
        artifact = read_local_input(
            root, Path(check.question.artifact_path), Path("outputs"), 2 * 1024 * 1024
        )
        if not check.recheck(root, inventory, artifact, allow_disagreements=True):
            raise ToolInputError("Historical representative assignment no longer verifies")
        return "historical_assignment_unconfirmed"
    if request.historical_context is not None:
        raise ToolInputError("Current assignment cannot claim historical context")
    if isinstance(citation, Citation):
        _native_quote(root, inventory, citation)
    else:
        _scan_quote(root, inventory, citation, scan_checks)
    explicit = re.compile(
        re.escape(normalized(request.role))
        + r"\s*:\s*"
        + re.escape(normalized(request.person or ""))
        + r"(?![\w'-])"
    )
    if not explicit.search(normalized(citation.quote)):
        raise ToolInputError("Assignment evidence must explicitly link the role label to the name")
    return "explicit_source_assignment"


def _identity_heading(text: str, person: str) -> str | None:
    # A name mentioned in prose is not proof that this is that employee's biography.
    name = r"\s+".join(re.escape(word) for word in person.split())
    match = re.search(
        r"(?im)^[ \t]*(?:(?P<meet>meet)[ \t]+|name:[ \t]*|"
        r"biography(?:[ \t]+of)?[: \t]+)?" + name + r"(?(meet)(?:[ \t]+of[ \t]+[^\n]+)?)[ \t]*$",
        text,
    )
    return match.group().strip() if match is not None else None


def resolve_representative_bio(
    root: Path,
    inventory: Inventory,
    tools: EvidenceTools,
    request: RepresentativeBioRequest,
    *,
    historical_checks: tuple[HistoricalContextCheck, ...] = (),
    scan_checks: tuple[ScanCheck, ...] = (),
) -> RepresentativeBioResolution:
    assignment = _assignment_status(root, inventory, request, historical_checks, scan_checks)
    if request.person is None:
        return RepresentativeBioResolution(
            request=request, status="assignment_unresolved", assignment_status=assignment
        )
    candidates: dict[str, BioCandidate] = {}
    issues: list[str] = []
    pages_by_source: dict[str, list[tuple[int, str | None]]] = {}
    try:
        listing = tools.list_sources(family="bios")
        for source in listing.sources:
            digest = next(s.sha256 for s in inventory.sources if s.source_id == source.source_id)
            if source.format != "pdf" or source.page_count is None:
                issues.append("bio_identity_reading_unverified")
                continue
            identity: Citation | OcrCitation | None = None
            source_issues: list[str] = []
            for page in range(1, source.page_count + 1):
                reading = tools.read_page(source.source_id, page)
                pages_by_source.setdefault(source.source_id, []).append(
                    (page, reading.text if reading.mode == "native" and reading.citable else None)
                )
                if reading.mode == "native" and reading.citable:
                    heading = _identity_heading(reading.text, request.person)
                    if heading is not None and identity is None:
                        location = tools.locate_quote(source.source_id, page, heading)
                        identity = Citation.model_validate_json(
                            location.model_dump_json(exclude={"occurrences"})
                        )
                    elif (
                        re.search(
                            r"(?<![\w'-])" + re.escape(normalized(request.person)) + r"(?![\w'-])",
                            normalized(reading.text),
                        )
                        and heading is None
                    ):
                        source_issues.append("bio_subject_identity_ambiguous")
                else:
                    checked = tuple(
                        c
                        for c in scan_checks
                        if c.citation.source_id == source.source_id and c.citation.page == page
                    )
                    if not checked:
                        source_issues.append("bio_identity_reading_unverified")
                    for check in checked:
                        _scan_quote(root, inventory, check.citation, scan_checks)
                        if normalized(check.expected_subject) == normalized(request.person):
                            if re.search(
                                r"(?<![\w'-])"
                                + re.escape(normalized(request.person))
                                + r"(?![\w'-])",
                                normalized(check.citation.quote),
                            ):
                                if identity is None:
                                    identity = check.citation
                            else:
                                source_issues.append("bio_identity_reading_unverified")
            if identity is not None:
                candidate = BioCandidate(
                    source_id=source.source_id, source_sha256=digest, identity=identity
                )
                previous = candidates.get(digest)
                if previous is not None:
                    candidate = previous.model_copy(
                        update={
                            "equivalent_source_ids": (
                                *previous.equivalent_source_ids,
                                source.source_id,
                            )
                        }
                    )
                candidates[digest] = candidate
            else:
                issues.extend(source_issues)
    except ToolLimitError:
        issues.append("bio_search_incomplete")
    status: Literal["selected", "missing_bio", "ambiguous_bio", "bio_review_required"] = (
        "bio_review_required"
        if issues
        else "ambiguous_bio"
        if len(candidates) > 1
        else "selected"
        if candidates
        else "missing_bio"
    )
    selected = next(iter(candidates.values())).source_id if status == "selected" else None
    return RepresentativeBioResolution(
        request=request,
        status=status,
        assignment_status=assignment,
        candidates=tuple(candidates.values()),
        selected_source_id=selected,
        issues=tuple(dict.fromkeys(issues)),
        profile=_profile(root, inventory, selected, request.person, pages_by_source[selected])
        if selected is not None
        else None,
    )


def _profile(
    root: Path,
    inventory: Inventory,
    source_id: str,
    person: str,
    pages: list[tuple[int, str | None]],
) -> BioProfile:
    found: dict[tuple[tuple[str, str], ...], tuple[int, str, tuple[ProfileLine, ...]]] = {}
    ambiguous = False
    for page, text in pages:
        if text is None:
            continue
        card, status = extract_contact_card(text, person)
        ambiguous |= status == "ambiguous"
        if card is not None:
            found.setdefault(tuple((line.kind, line.text) for line in card), (page, text, card))
    if ambiguous or len(found) > 1:
        return BioProfile(status="ambiguous", source_id=source_id)
    if not found:
        return BioProfile(
            status="not_native" if any(t is None for _, t in pages) else "not_found",
            source_id=source_id,
        )
    page, text, card = next(iter(found.values()))
    start, end = card[0].start, card[-1].end
    citation = Citation(source_id=source_id, page=page, start=start, end=end, quote=text[start:end])
    _native_quote(root, inventory, citation)
    return BioProfile(
        status="extracted", source_id=source_id, page=page, citation=citation, lines=card
    )


_PHONE = re.compile(
    r"(?<!\d)(?:\+?1[\s.-]?)?\(?(\d{3})\)?[\s.-]?(\d{3})[\s.-]?(\d{4})"
    r"(?:\s*(?:x|ext\.?|extension)\s*(\d{1,6}))?(?!\d)",
    re.IGNORECASE,
)
_PHONE_LABELS = {
    "work": "work",
    "office": "work",
    "direct": "work",
    "desk": "work",
    "main": "work",
    "w": "work",
    "o": "work",
    "d": "work",
    "cell": "mobile",
    "mobile": "mobile",
    "c": "mobile",
    "m": "mobile",
    "fax": "fax",
    "f": "fax",
    "tel": "unspecified",
    "telephone": "unspecified",
    "phone": "unspecified",
    "p": "unspecified",
    "t": "unspecified",
}
_LABEL = "|".join(sorted(_PHONE_LABELS, key=len, reverse=True))
_PREFIX = re.compile(r"(?i)(?:^|[^a-z])(" + _LABEL + r")\W*$")
_PHONE_RESIDUE = re.compile(r"(?i)[\s,;/:.()-]*(?:(?:" + _LABEL + r")\b[\s,;/:.()-]*)*")
_EMAIL = re.compile(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+")
_EMAIL_LINE = re.compile(r"(?i)(?:e-?mail\s*:?\s*)?(" + _EMAIL.pattern + ")")


@dataclass(frozen=True)
class PhoneNumber:
    key: str
    kind: Literal["work", "mobile", "fax", "unspecified"]
    display: str


def phone_numbers(text: str) -> tuple[PhoneNumber, ...]:
    """Numbers compare by digits and extension; labels are kept as a type, not as identity."""
    found: list[PhoneNumber] = []
    boundary = 0
    for match in _PHONE.finditer(text):
        segment = text[boundary : match.start()]
        segment = re.split(r"[,;/\n]", segment)[-1]
        label = _PREFIX.search(segment)
        area, exchange, line, extension = match.groups()
        found.append(
            PhoneNumber(
                key=area + exchange + line + (f"x{extension}" if extension else ""),
                kind=_PHONE_LABELS[label.group(1).casefold()]  # type: ignore[arg-type]
                if label
                else "unspecified",
                display=f"{area}-{exchange}-{line}" + (f" x{extension}" if extension else ""),
            )
        )
        boundary = match.end()
    return tuple(found)


def _contact_kind(line: str) -> Literal["telephone", "email_address"] | None:
    if _EMAIL_LINE.fullmatch(line):
        return "email_address"
    if phone_numbers(line) and _PHONE_RESIDUE.fullmatch(_PHONE.sub(" ", line)):
        return "telephone"
    return None


def _title_line(line: str) -> bool:
    return (
        len(line) <= 80
        and len(line.split()) <= 10
        and re.search(r"[A-Za-z]", line) is not None
        and "@" not in line
        and not line.endswith(".")
        and not phone_numbers(line)
    )


def extract_contact_card(
    text: str, person: str
) -> tuple[tuple[ProfileLine, ...] | None, Literal["extracted", "not_found", "ambiguous"]]:
    """Find the bio's printed name, title and contact block by structure, never prose."""
    lines: list[tuple[int, str]] = []
    offset = 0
    for raw in text.splitlines(keepends=True):
        body = raw.rstrip("\r\n")
        stripped = body.strip()
        lines.append((offset + len(body) - len(body.lstrip()), stripped))
        offset += len(raw)
    name = normalized(person)

    def is_name(line: str) -> bool:
        return normalized(re.sub(r"(?i)^name\s*:\s*", "", line)) == name

    cards: dict[tuple[tuple[str, str], ...], tuple[ProfileLine, ...]] = {}
    for index, (_, line) in enumerate(lines):
        if not is_name(line):
            continue
        cursor = index + 1
        while cursor < len(lines) and (not lines[cursor][1] or is_name(lines[cursor][1])):
            cursor += 1
        card: list[ProfileLine] = []
        while (
            cursor < len(lines)
            and lines[cursor][1]
            and _contact_kind(lines[cursor][1]) is None
            and _title_line(lines[cursor][1])
        ):
            start, body = lines[cursor]
            card.append(ProfileLine(kind="title", text=body, start=start, end=start + len(body)))
            cursor += 1
        if len(card) > 3:
            continue
        contacts = 0
        while cursor < len(lines) and (kind := _contact_kind(lines[cursor][1])) is not None:
            start, body = lines[cursor]
            card.append(ProfileLine(kind=kind, text=body, start=start, end=start + len(body)))
            contacts += 1
            cursor += 1
        if contacts:
            cards.setdefault(tuple((line.kind, line.text) for line in card), tuple(card))
    if not cards:
        return None, "not_found"
    if len(cards) > 1:
        return None, "ambiguous"
    return next(iter(cards.values())), "extracted"


class FieldReconciliation(Contract):
    """Deterministic comparison of one mapped field with the selected bio's printed card."""

    requirement_id: Identifier
    role: str
    person: str | None
    field: ProfileField
    source_id: Sha256 | None
    decision: Literal["bio_value_used", "answer_kept_bio_confirmed", "bio_value_unavailable"]
    value: str | None
    prior_value: str | None
    bio_values: tuple[str, ...] = ()
    confirmed: tuple[str, ...] = ()
    historical_only: tuple[str, ...] = ()
    bio_not_in_answer: tuple[str, ...] = ()
    meaningful_difference: bool = False


def _tokens(text: str) -> list[str]:
    return re.findall(r"[a-z0-9]+", text.casefold())


def _run(lines: Sequence[ProfileLine], kind: ProfileField) -> list[ProfileLine]:
    run: list[ProfileLine] = []
    for line in lines:
        usable = line.kind == kind and (
            kind != "telephone" or any(p.kind != "fax" for p in phone_numbers(line.text))
        )
        if usable:
            run.append(line)
        elif run:
            break
    return run


def reconcile_representative_fields(
    proposals: tuple[AnswerProposal, ...], resolutions: Sequence[RepresentativeBioResolution]
) -> tuple[tuple[AnswerProposal, ...], tuple[FieldReconciliation, ...]]:
    """Bio titles take precedence; contacts keep a prior answer only if it includes a bio value.

    A value absent from the bio is historical-only, not a contradiction. Unselected bios and
    cards that were not structurally extracted never supply or confirm a value.
    """
    answers = {p.requirement_id: p for p in proposals}
    records: list[FieldReconciliation] = []
    for resolution in resolutions:
        profile = resolution.profile
        usable = (
            resolution.status == "selected"
            and profile is not None
            and profile.status == "extracted"
            and profile.source_id == resolution.selected_source_id
        )
        for mapping in resolution.request.field_requirements:
            rid = mapping.requirement_id
            prior = answers.get(rid)
            prior_value = (
                prior.value.value
                if prior is not None
                and prior.outcome == "proposed"
                and isinstance(prior.value, TextValue)
                else None
            )
            run = _run(profile.lines, mapping.field) if usable and profile is not None else []
            unavailable = FieldReconciliation(
                requirement_id=rid,
                role=resolution.request.role,
                person=resolution.request.person,
                field=mapping.field,
                source_id=resolution.selected_source_id if run else None,
                decision="bio_value_unavailable",
                value=prior_value,
                prior_value=prior_value,
            )
            if not run or profile is None:
                records.append(unavailable)
                continue
            confirmed: list[str] = []
            historical_only: list[str] = []
            missing: list[str] = []
            if mapping.field == "title":
                bio_values = [", ".join(line.text for line in run)]
                keep = prior_value is not None and normalized(prior_value) == normalized(
                    bio_values[0]
                )
                different = prior_value is not None and _tokens(prior_value) != _tokens(
                    bio_values[0]
                )
            elif mapping.field == "telephone":
                bio = [p for line in run for p in phone_numbers(line.text) if p.kind != "fax"]
                bio_values = [p.display for p in bio]
                old = list(phone_numbers(prior_value or ""))
                keys = {p.key for p in bio}
                keep = any(p.key in keys for p in old)
                confirmed = [p.display for p in old if p.key in keys]
                historical_only = [
                    p.display + ("" if p.kind == "unspecified" else f" ({p.kind})")
                    for p in old
                    if p.key not in keys
                ]
                missing = [p.display for p in bio if p.key not in {o.key for o in old}]
                different = prior_value is not None and not keep
            else:
                bio_values = [m.group(1) for line in run if (m := _EMAIL_LINE.fullmatch(line.text))]
                old_emails = _EMAIL.findall(prior_value or "")
                folded = {e.casefold() for e in bio_values}
                keep = any(e.casefold() in folded for e in old_emails)
                confirmed = [e for e in old_emails if e.casefold() in folded]
                historical_only = [e for e in old_emails if e.casefold() not in folded]
                missing = [
                    e for e in bio_values if e.casefold() not in {o.casefold() for o in old_emails}
                ]
                different = prior_value is not None and not keep
            if keep and prior is not None and prior_value is not None:
                records.append(
                    unavailable.model_copy(
                        update={
                            "decision": "answer_kept_bio_confirmed",
                            "bio_values": tuple(bio_values),
                            "confirmed": tuple(confirmed),
                            "historical_only": tuple(historical_only),
                            "bio_not_in_answer": tuple(missing),
                        }
                    )
                )
                continue
            value = (
                bio_values[0]
                if mapping.field == "email_address"
                else bio_values[0]
                if mapping.field == "title"
                else ", ".join(line.text for line in run)
            )
            citation = profile.span(run[:1] if mapping.field == "email_address" else run)
            answers[rid] = AnswerProposal(
                requirement_id=rid,
                outcome="proposed",
                value=TextValue(kind="text", value=value),
                citations=(citation,),
                confidence=1.0,
                explanation=(
                    f"Code-derived from the {mapping.field} printed in the selected "
                    f"identity-linked biography for {resolution.request.role}; the biography's "
                    "currency is not confirmed."
                ),
            )
            records.append(
                unavailable.model_copy(
                    update={
                        "decision": "bio_value_used",
                        "value": value,
                        "bio_values": tuple(bio_values),
                        "meaningful_difference": different,
                    }
                )
            )
    return tuple(answers[p.requirement_id] for p in proposals), tuple(records)
