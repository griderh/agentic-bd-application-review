"""Explicit archive partitions, historical discovery and bounded draft-reuse checks."""

import hashlib
import re
from contextlib import closing
from dataclasses import asdict, dataclass
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Annotated, Literal, Self

import pypdfium2 as pdfium
import pypdfium2.raw as pdfium_raw
from pydantic import Field, ValidationError, model_validator

from bd_packet_builder.contracts import (
    AnswerProposal,
    AnswerValue,
    ApplicationRequirements,
    Citation,
    Contract,
    EvidenceStatus,
    Identifier,
    IdentifierValue,
    MoneyValue,
    NarrativeValue,
    Nonblank,
    OcrCitation,
    ReportingPeriod,
    Requirement,
    Sha256,
    TextValue,
    check_native_citations,
    check_proposal,
)
from bd_packet_builder.inventory import (
    Inventory,
    InventoryError,
    SourceRecord,
    build_inventory,
    publish_json_run,
)
from bd_packet_builder.local_inputs import LocalInputError, read_local_input
from bd_packet_builder.review import AnswerProposals

_ARCHIVE = Path("bd_agreements/Completed")


class HistoryError(ValueError):
    """Safe archive/path/schema failures without historical document contents."""


class ArchiveEntry(Contract):
    path: Nonblank
    sha256: Sha256
    partition: Literal["reference", "evaluation"]
    issuer: Nonblank
    completed_on: date | None = None
    reporting_period: ReportingPeriod | None = None

    @model_validator(mode="after")
    def archive_path(self) -> Self:
        path = Path(self.path)
        if (
            path.is_absolute()
            or ".." in path.parts
            or not path.is_relative_to(_ARCHIVE)
            or path.suffix.lower() != ".pdf"
            or path.as_posix() != self.path
        ):
            raise ValueError("Archive entry requires a canonical Completed-tree PDF path")
        return self


class ArchiveManifest(Contract):
    schema_version: Literal[1] = 1
    entries: Annotated[tuple[ArchiveEntry, ...], Field(min_length=1, max_length=500)]

    @model_validator(mode="after")
    def separated(self) -> Self:
        if len({entry.path for entry in self.entries}) != len(self.entries):
            raise ValueError("Duplicate archive paths")
        references = {entry.sha256 for entry in self.entries if entry.partition == "reference"}
        evaluation = {entry.sha256 for entry in self.entries if entry.partition == "evaluation"}
        if references & evaluation:
            raise ValueError("Content cannot occur in both archive partitions")
        return self


class HistoricalComparison(Contract):
    requirement_id: Identifier
    path: Nonblank
    sha256: Sha256
    page: Annotated[int, Field(ge=1)]
    quote: Nonblank
    question: Nonblank
    value: AnswerValue
    signer_role: Nonblank | None = None


class HistoryRequest(Contract):
    schema_version: Literal[1] = 1
    issuer: Nonblank
    requirements: ApplicationRequirements
    proposals: AnswerProposals
    comparisons: Annotated[tuple[HistoricalComparison, ...], Field(max_length=100)]

    @model_validator(mode="after")
    def linked(self) -> Self:
        ids = {item.requirement_id for item in self.requirements.requirements}
        linked_ids = [item.requirement_id for item in self.proposals.proposals]
        linked_ids.extend(item.requirement_id for item in self.comparisons)
        if any(identity not in ids for identity in linked_ids):
            raise ValueError("Unknown requirement identity")
        keys = [(item.requirement_id, item.path) for item in self.comparisons]
        if len(set(keys)) != len(keys):
            raise ValueError("Duplicate historical comparison")
        return self


def _read(root: Path, path: Path, boundary: Path, limit: int) -> bytes:
    try:
        return read_local_input(root, path, boundary, limit)
    except LocalInputError as error:
        raise HistoryError(str(error)) from None


@dataclass(frozen=True)
class ReferenceArchive:
    """Only explicitly permitted references are exposed; evaluation bytes are never returned."""

    root: Path
    references: tuple[ArchiveEntry, ...]
    evaluation_hashes: frozenset[str]

    def read_reference(self, path: str) -> bytes:
        entry = next((entry for entry in self.references if entry.path == path), None)
        if entry is None:
            raise HistoryError("Historical reference is not allowed by the partition manifest")
        data = _read(self.root, Path(entry.path), _ARCHIVE, 64 * 1024 * 1024)
        digest = hashlib.sha256(data).hexdigest()
        if digest != entry.sha256 or digest in self.evaluation_hashes:
            raise HistoryError("Archive source changed or crosses the evaluation partition")
        return data


def open_reference_archive(root: Path, manifest: ArchiveManifest) -> ReferenceArchive:
    """Verify declared file hashes, including duplicates; never extract evaluation content."""
    root = root.resolve(strict=True)
    for entry in manifest.entries:
        data = _read(root, Path(entry.path), _ARCHIVE, 64 * 1024 * 1024)
        if hashlib.sha256(data).hexdigest() != entry.sha256:
            raise HistoryError("Archive source changed; partition manifest must be reviewed")
    return ReferenceArchive(
        root,
        tuple(entry for entry in manifest.entries if entry.partition == "reference"),
        frozenset(entry.sha256 for entry in manifest.entries if entry.partition == "evaluation"),
    )


def historical_inventory(
    root: Path, manifest: ArchiveManifest, *, current: Inventory | None = None
) -> Inventory:
    """Expose only hash-verified reference entries, excluding copies in current sources."""
    try:
        archive = ReferenceArchive(
            root.resolve(strict=True),
            tuple(e for e in manifest.entries if e.partition == "reference"),
            frozenset(e.sha256 for e in manifest.entries if e.partition == "evaluation"),
        )
        if current is not None and (
            {s.sha256 for s in current.sources} & {e.sha256 for e in manifest.entries}
        ):
            raise InventoryError("Archive content cannot be relabeled as current evidence")
        records: list[SourceRecord] = []
        for entry in archive.references:
            data = archive.read_reference(entry.path)
            with pdfium.PdfDocument(data) as document:
                encrypted = pdfium_raw.FPDF_GetSecurityHandlerRevision(document) >= 0
                pages = None if encrypted else len(document)
            identity = hashlib.sha256(
                entry.path.encode() + b"\0" + entry.sha256.encode()
            ).hexdigest()
            records.append(
                SourceRecord(
                    identity,
                    entry.path,
                    entry.sha256,
                    len(data),
                    "pdf",
                    "historical_reference",
                    pages,
                    None,
                    None,
                    None,
                    ("historical_not_current_authority",)
                    + (("encrypted_pdf",) if encrypted else ()),
                )
            )
        return Inventory(datetime.now(UTC), tuple(records), ())
    except (HistoryError, pdfium.PdfiumError) as error:
        raise InventoryError(f"Historical archive access failed: {error}") from None


def with_historical_sources(
    root: Path, current: Inventory, manifest: ArchiveManifest | None
) -> Inventory:
    if manifest is None:
        return current
    history = historical_inventory(root, manifest, current=current)
    return Inventory(current.created_at, current.sources + history.sources, current.issues)


def historical_issues(
    root: Path,
    inventory: Inventory,
    manifest: ArchiveManifest | None,
    issuer: str | None,
    requirement: Requirement,
    proposal: AnswerProposal,
    *,
    navigation_context: str = "",
) -> tuple[tuple[str, ...], EvidenceStatus]:
    """Check provenance and bounded reuse, not semantic equivalence or human approval."""
    sources = {s.source_id: s for s in inventory.sources}
    prior = [
        c
        for c in proposal.citations
        if c.source_id in sources and sources[c.source_id].family == "historical_reference"
    ]
    basis = proposal.historical_basis
    if not prior:
        return (
            (("historical_citation_required",), "unsupported")
            if basis
            else ((), "current_evidence")
        )
    if basis is None or manifest is None:
        return ("historical_context_required",), "unsupported"
    issues: list[str] = []
    if requirement.kind not in ("text", "identifier", "narrative"):
        issues.append("historical_sensitive_requirement")
    # A model's permissive category must not override recognizable high-risk issuer requests.
    sensitive = re.compile(
        r"\b(signature|signatory|signer|attest\w*|certif\w*|acknowledg\w*|"
        r"disciplin\w*|litigation|lawsuit\w*|disclos\w*|sanction\w*|"
        r"capital|assets|liabilit\w*|revenue|net worth|financial|"
        r"i have|we have reviewed|i understand|i agree|"
        r"convict\w*|criminal|bankrupt\w*|regulatory action)\b",
        re.IGNORECASE,
    )
    if sensitive.search(requirement.instruction) or requirement.required_signer_role:
        issues.append("historical_sensitive_requirement")
    if requirement.requested_period is not None:
        issues.append("historical_current_period_requires_current_evidence")
    entries = {e.path: e for e in manifest.entries if e.partition == "reference"}
    for citation in prior:
        source = sources[citation.source_id]
        entry = entries.get(source.path)
        if entry is None or entry.sha256 != source.sha256:
            issues.append("historical_source_not_approved")
            continue
        if basis.context == "issuer_specific" and (
            issuer is None or entry.issuer.casefold().strip() != issuer.casefold().strip()
        ):
            issues.append("historical_issuer_context_mismatch")
        if basis.prior_question.source_id != citation.source_id:
            issues.append("historical_question_source_mismatch")
        if basis.prior_question.page != citation.page:
            issues.append("historical_question_page_mismatch")
        if isinstance(citation, OcrCitation) and basis.prior_question != citation:
            issues.append("historical_ocr_context_must_be_verified_answer_quote")
        value = proposal.value
        if not isinstance(value, (TextValue, IdentifierValue, NarrativeValue)) or (
            value.value not in citation.quote
        ):
            issues.append("historical_value_not_in_prior_answer")
    if basis.category == "representative_assignment" and (
        basis.context != "issuer_specific"
        or not basis.role
        or basis.role.casefold() not in basis.prior_question.quote.casefold()
        or basis.role.casefold()
        not in (requirement.instruction + " " + navigation_context).casefold()
    ):
        issues.append("historical_role_context_mismatch")

    if isinstance(basis.prior_question, Citation):
        _, quote_issues = check_native_citations(root, inventory, (basis.prior_question,))
        if quote_issues:
            issues.append("historical_question_unresolved")
    elif basis.prior_question not in proposal.citations:
        issues.append("historical_ocr_context_must_be_verified_answer_quote")
    corroborated = False
    if not basis.current_checks and any(
        s.family != "historical_reference" for s in inventory.sources
    ):
        issues.append("historical_current_checks_required")
    for check in basis.current_checks:
        checked_source = sources.get(check.citation.source_id)
        _, check_issues = check_native_citations(root, inventory, (check.citation,))
        if (
            checked_source is None
            or checked_source.family == "historical_reference"
            or check_issues
        ):
            issues.append("historical_current_check_unresolved")
        if check.finding == "contradicts":
            issues.append("historical_current_contradiction")
        if check.finding == "corroborates":
            value = proposal.value
            if not isinstance(value, (TextValue, IdentifierValue, NarrativeValue)) or (
                value.value not in check.citation.quote
            ):
                issues.append("historical_corroboration_value_missing")
            else:
                corroborated = True
    return tuple(dict.fromkeys(issues)), (
        "unsupported"
        if issues
        else "currently_corroborated"
        if corroborated
        else "historical_continuity_unconfirmed"
    )


def _quote_present(data: bytes, comparison: HistoricalComparison) -> bool:
    try:
        with pdfium.PdfDocument(data) as document:
            if pdfium_raw.FPDF_GetSecurityHandlerRevision(document) >= 0 or comparison.page > len(
                document
            ):
                return False
            with (
                closing(document[comparison.page - 1]) as page,
                closing(page.get_textpage()) as text,
            ):
                if text.count_chars() > 100_000:
                    raise HistoryError("Historical page exceeds the native character limit")
                native = text.get_text_bounded(errors="strict").replace("\r\n", "\n")
                if len(native) > 100_000:
                    raise HistoryError("Historical page exceeds the native character limit")
                return comparison.quote in native
    except (pdfium.PdfiumError, UnicodeError):
        return False


def run_history_check(root: Path, manifest_path: Path, request_path: Path) -> Path:
    """Check manually supplied pairs after current proposals; no retrieval/model/answer filling."""
    root = root.resolve(strict=True)
    paths = (manifest_path, request_path)
    inputs = tuple(_read(root, path, Path("outputs"), 2 * 1024 * 1024) for path in paths)
    try:
        manifest = ArchiveManifest.model_validate_json(inputs[0])
        request = HistoryRequest.model_validate_json(inputs[1])
    except ValidationError:
        raise HistoryError(
            "Invalid archive partition or comparison schema; check IDs and context"
        ) from None
    archive = open_reference_archive(root, manifest)
    inventory = build_inventory(root)
    historical_hashes = {entry.sha256 for entry in manifest.entries}
    if any(source.sha256 in historical_hashes for source in inventory.sources):
        raise HistoryError("Archived packet content is not allowed as current evidence")
    proposals = {item.requirement_id: item for item in request.proposals.proposals}
    requirements = {item.requirement_id: item for item in request.requirements.requirements}
    items: list[dict[str, object]] = []
    for comparison in request.comparisons:
        issues: list[str] = []
        requirement = requirements[comparison.requirement_id]
        proposal = proposals.get(comparison.requirement_id)
        current_check = check_proposal(root, inventory, requirement, proposal) if proposal else None
        if proposal is None or proposal.outcome != "proposed":
            issues.append("current_answer_unavailable")
        if current_check is not None and current_check.status in (
            "rejected",
            "deferred_to_signing",
        ):
            issues.append("current_proposal_rejected")
        entry = next((entry for entry in archive.references if entry.path == comparison.path), None)
        if entry is None:
            issues.append("reference_not_allowed")
        elif entry.sha256 != comparison.sha256:
            issues.append("historical_version_mismatch")
        else:
            if not _quote_present(archive.read_reference(entry.path), comparison):
                issues.append("historical_quote_unresolved")
            if entry.issuer != request.issuer:
                issues.append("issuer_context_mismatch")
            if entry.completed_on is None:
                issues.append("historical_completion_date_unknown")
            if entry.reporting_period != requirement.requested_period:
                issues.append("reporting_period_context_mismatch")
            if requirement.kind == "money" and requirement.requested_period is None:
                issues.append("reporting_period_context_unknown")
        if comparison.question != requirement.instruction:
            issues.append("question_context_mismatch")
        if comparison.signer_role != requirement.required_signer_role:
            issues.append("signer_context_mismatch")
        if comparison.value.kind != requirement.kind:
            issues.append("answer_kind_mismatch")
        if isinstance(comparison.value, MoneyValue) and comparison.value.unit != requirement.unit:
            issues.append("unit_mismatch")
        if comparison.value.kind == "attachment":
            issues.append("attachment_comparison_unsupported")
        if comparison.value.kind in ("single_select", "multi_select"):
            issues.append("historical_choice_mapping_unverified")
        status = "not_comparable"
        if not issues and proposal is not None:
            same = proposal.value == comparison.value
            if isinstance(proposal.value, MoneyValue) and isinstance(comparison.value, MoneyValue):
                same = proposal.value.decimal_amount == comparison.value.decimal_amount
            status = "same_value_unverified" if same else "value_difference_review"
        items.append(
            {
                "requirement_id": comparison.requirement_id,
                "requirement": requirement.model_dump(mode="json"),
                "current_proposal": proposal.model_dump(mode="json") if proposal else None,
                # Disallowed reference payloads may contain held-out annotations; never echo them.
                "reference": comparison.model_dump(mode="json") if entry is not None else None,
                "status": status,
                "issues": [
                    *issues,
                    "historical_answer_support_unverified",
                    "historical_question_mapping_unverified",
                ],
                "current_check": asdict(current_check) if current_check else None,
                "fill_value": None,
            }
        )

    def verify() -> None:
        for path, snapshot in zip(paths, inputs, strict=True):
            if _read(root, path, Path("outputs"), 2 * 1024 * 1024) != snapshot:
                raise HistoryError("Historical-check input changed; no report published")
        open_reference_archive(root, manifest)

    payload: dict[str, object] = {
        "schema_version": 1,
        "status": "historical_review_only_no_packet",
        "coverage": "supplied_pairs_only_not_archive_search",
        "input_versions": [
            {"path": path.as_posix(), "sha256": hashlib.sha256(data).hexdigest()}
            for path, data in zip(paths, inputs, strict=True)
        ],
        "flags": [
            "no_current_grounding_from_history",
            "no_automatic_replacement",
            "application_identity_and_semantics_unverified",
            "partition_assignment_requires_trusted_operator",
        ],
        "items": items,
    }
    return publish_json_run(root, "history-check", payload, inventory, verify_inputs=verify)
