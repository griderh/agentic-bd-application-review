"""Local contract-review harness, not application interpretation or packet approval."""

import hashlib
from collections import Counter
from dataclasses import asdict
from datetime import UTC, datetime
from pathlib import Path
from typing import Annotated, Literal, Self

import pypdfium2 as pdfium
import pypdfium2.raw as pdfium_raw
from pydantic import Field, ValidationError, model_validator

from bd_packet_builder.contracts import (
    AnswerProposal,
    ApplicationRequirements,
    Contract,
    ProposalCheck,
    check_proposal,
)
from bd_packet_builder.inventory import build_inventory, publish_json_run
from bd_packet_builder.local_inputs import LocalInputError, read_local_input

_BLANK = Path("bd_agreements/Blank")
_OUTPUTS = Path("outputs")


class ReviewError(ValueError):
    """Safe batch/input failures with no raw payloads or PDF content."""


class AnswerProposals(Contract):
    schema_version: Literal[1] = 1
    proposals: Annotated[tuple[AnswerProposal, ...], Field(max_length=500)]

    @model_validator(mode="after")
    def unique_ids(self) -> Self:
        if len({p.requirement_id for p in self.proposals}) != len(self.proposals):
            raise ValueError("Duplicate proposal requirement identities")
        return self


def _read_input(root: Path, relative: Path, boundary: Path, limit: int) -> bytes:
    try:
        return read_local_input(root, relative, boundary, limit)
    except LocalInputError as error:
        raise ReviewError(str(error)) from None


def run_review(root: Path, source: Path, requirements: Path, proposals: Path) -> Path:
    """Check every supplied requirement; never claim complete field discovery."""
    root = root.resolve(strict=True)
    if source.suffix.lower() != ".pdf":
        raise ReviewError("Application must be a blank-tree PDF")
    inputs = (
        (source, _BLANK, 64 * 1024 * 1024),
        (requirements, _OUTPUTS, 2 * 1024 * 1024),
        (proposals, _OUTPUTS, 2 * 1024 * 1024),
    )
    snapshots = tuple(_read_input(root, *item) for item in inputs)
    digests = tuple(hashlib.sha256(data).hexdigest() for data in snapshots)
    try:
        request = ApplicationRequirements.model_validate_json(snapshots[1])
        answers = AnswerProposals.model_validate_json(snapshots[2])
    except ValidationError:
        raise ReviewError(
            "Invalid requirements or proposals JSON; check strict schemas, IDs and value types"
        ) from None
    try:
        with pdfium.PdfDocument(snapshots[0]) as document:
            if pdfium_raw.FPDF_GetSecurityHandlerRevision(document) >= 0 or len(document) < 1:
                raise ReviewError("Application must be a nonempty unencrypted PDF")
            page_count = len(document)
    except pdfium.PdfiumError:
        raise ReviewError(
            "Application is unreadable or encrypted; no review report published"
        ) from None
    if any(r.application_sha256 != digests[0] for r in request.requirements):
        raise ReviewError("Requirement application hash does not match the selected blank PDF")
    if any(r.page > page_count for r in request.requirements):
        raise ReviewError("Requirement page is outside the selected application")
    requirement_ids = {r.requirement_id for r in request.requirements}
    if any(p.requirement_id not in requirement_ids for p in answers.proposals):
        raise ReviewError("Proposal refers to an unknown requirement")
    by_id = {p.requirement_id: p for p in answers.proposals}
    inventory = build_inventory(root)
    items: list[dict[str, object]] = []
    counts: Counter[str] = Counter()
    for requirement in request.requirements:
        proposal = by_id.get(requirement.requirement_id)
        if proposal is not None:
            check = check_proposal(root, inventory, requirement, proposal)
        elif requirement.kind in ("signature", "signature_date"):
            check = ProposalCheck(
                requirement.requirement_id, "deferred_to_signing", ("human_signing_required",)
            )
        else:
            check = ProposalCheck(requirement.requirement_id, "unanswered", ("missing_proposal",))
        counts[check.status] += 1
        items.append(
            {
                "requirement": requirement.model_dump(mode="json"),
                "proposal": proposal.model_dump(mode="json") if proposal is not None else None,
                "check": asdict(check),
            }
        )

    def verify() -> None:
        for item, digest in zip(inputs, digests, strict=True):
            if hashlib.sha256(_read_input(root, *item)).hexdigest() != digest:
                raise ReviewError("Review input changed; report was not published")

    payload: dict[str, object] = {
        "schema_version": 1,
        "status": "internal_review_only_no_packet",
        "coverage": "supplied_requirements_only_not_full_form",
        "created_at": datetime.now(UTC).isoformat(),
        "application": {"path": source.as_posix(), "sha256": digests[0], "page_count": page_count},
        "input_versions": [
            {"path": item[0].as_posix(), "sha256": digest}
            for item, digest in zip(inputs[1:], digests[1:], strict=True)
        ],
        "counts": dict(counts),
        "items": items,
        "inventory_issues": [asdict(issue) for issue in inventory.issues],
    }
    return publish_json_run(root, "review", payload, inventory, verify_inputs=verify)
