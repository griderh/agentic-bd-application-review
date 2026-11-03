"""Reviewed requirement coverage, separate from physical inclusion and answer generation."""

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Annotated, Literal, Self

from pydantic import Field, model_validator

from bd_packet_builder.contracts import (
    Citation,
    Contract,
    Identifier,
    Nonblank,
    OcrCitation,
    Requirement,
    Sha256,
)
from bd_packet_builder.evidence import EvidenceError, resolve_quote
from bd_packet_builder.history import requires_personal_action
from bd_packet_builder.inventory import Inventory


class ReconciliationError(ValueError):
    """Reviewed coverage does not match the form or its approved evidence."""


class CoverageCriterion(Contract):
    issuer_quote: Nonblank
    status: Literal[
        "supported", "missing", "needs_review", "period_mismatch", "human_action", "not_applicable"
    ]
    evidence: Annotated[tuple[Citation | OcrCitation, ...], Field(max_length=20)] = ()
    explanation: Nonblank
    action: Nonblank

    @model_validator(mode="after")
    def supported_evidence(self) -> Self:
        if self.status == "supported" and not self.evidence:
            raise ValueError("Supported criteria require current evidence")
        return self


class HistoricalReviewNote(Contract):
    citation: Citation
    explanation: Nonblank
    action: Nonblank


class RequirementAssessment(Contract):
    """Trusted local review input, not a model-selected applicability override or authentication."""

    requirement_id: Identifier
    application_sha256: Sha256
    requirement_quote: Nonblank
    reviewer: Nonblank
    reason: Nonblank
    applicability: Literal["required", "optional", "not_applicable"] = "required"
    criteria: Annotated[tuple[CoverageCriterion, ...], Field(max_length=30)] = ()
    depends_on: Annotated[tuple[Identifier, ...], Field(max_length=100)] = ()
    historical_notes: Annotated[tuple[HistoricalReviewNote, ...], Field(max_length=10)] = ()

    @model_validator(mode="after")
    def meaningful(self) -> Self:
        if self.applicability == "required" and not (
            self.criteria or self.depends_on or self.historical_notes
        ):
            raise ValueError("Required assessment needs criteria, dependencies or a review note")
        if len(set(self.depends_on)) != len(self.depends_on):
            raise ValueError("Requirement dependencies cannot repeat")
        return self


class RequirementAssessments(Contract):
    assessments: Annotated[tuple[RequirementAssessment, ...], Field(max_length=100)]


def validate_assessments(
    root: Path,
    inventory: Inventory,
    requirements: tuple[Requirement, ...],
    assessments: tuple[RequirementAssessment, ...],
    form_text: dict[int, str],
    *,
    verify_ocr: Callable[[OcrCitation], None] | None = None,
) -> None:
    declared = {r.requirement_id: r for r in requirements}
    reviewed = {a.requirement_id: a for a in assessments}
    if len(reviewed) != len(assessments):
        raise ReconciliationError("Requirement assessments cannot repeat")
    sources = {s.source_id: s for s in inventory.sources}
    for assessment in assessments:
        req = declared.get(assessment.requirement_id)
        if req is None or (
            req.application_sha256 != assessment.application_sha256
            or req.instruction != assessment.requirement_quote
        ):
            raise ReconciliationError("Requirement assessment version or wording does not match")
        if req.instruction not in form_text.get(req.page, ""):
            raise ReconciliationError("Assessed requirement is not anchored in the issuer form")
        if assessment.applicability != "required" and requires_personal_action(req):
            raise ReconciliationError("Applicability review cannot suppress a personal action")
        if assessment.depends_on and req.kind != "attachment":
            raise ReconciliationError(
                "Packet-completion dependencies require an attachment requirement"
            )
        if not set(assessment.depends_on) <= declared.keys():
            raise ReconciliationError("Requirement dependency is unknown")
        for criterion in assessment.criteria:
            if criterion.issuer_quote not in form_text.get(req.page, ""):
                raise ReconciliationError(
                    "Criterion is not an exact quotation on the requirement page"
                )
            for citation in criterion.evidence:
                source = sources.get(citation.source_id)
                if source is None or (
                    criterion.status == "supported" and source.family == "historical_reference"
                ):
                    raise ReconciliationError(
                        "Supported criterion requires approved current evidence"
                    )
                if isinstance(citation, OcrCitation):
                    if verify_ocr is None:
                        raise ReconciliationError(
                            "OCR assessment evidence requires artifact verification"
                        )
                    verify_ocr(citation)
                else:
                    try:
                        resolve_quote(root, inventory, citation.text_citation())
                    except EvidenceError:
                        raise ReconciliationError(
                            "Assessment evidence quote does not resolve"
                        ) from None
        for note in assessment.historical_notes:
            source = sources.get(note.citation.source_id)
            if source is None or source.family != "historical_reference":
                raise ReconciliationError("Historical review note requires an approved reference")
            try:
                resolve_quote(root, inventory, note.citation.text_citation())
            except EvidenceError:
                raise ReconciliationError("Historical review note quote does not resolve") from None

    def visit(identity: str, active: set[str], complete: set[str]) -> None:
        if identity in active:
            raise ReconciliationError("Requirement dependency cycle")
        if identity in complete:
            return
        active.add(identity)
        item = reviewed.get(identity)
        for dependency in item.depends_on if item else ():
            visit(dependency, active, complete)
        active.remove(identity)
        complete.add(identity)

    complete: set[str] = set()
    for identity in reviewed:
        visit(identity, set(), complete)


@dataclass(frozen=True)
class ReconciledRequirement:
    satisfied: bool
    evidence_state: str
    included_source_ids: tuple[str, ...]
    missing_packet_source_ids: tuple[str, ...]
    blocked_dependencies: tuple[str, ...]
    actions: tuple[str, ...]


COMPLETE_STATUSES = frozenset(
    ("written_to_draft", "requirement_satisfied", "not_applicable", "optional_not_supplied")
)


def reconcile_requirement(
    assessment: RequirementAssessment,
    effective_statuses: dict[str, str],
    attached: tuple[str, ...],
) -> ReconciledRequirement:
    needed = tuple(
        dict.fromkeys(c.source_id for criterion in assessment.criteria for c in criterion.evidence)
    )
    included = tuple(s for s in needed if s in attached)
    missing = tuple(s for s in needed if s not in attached)
    blocked = tuple(
        d for d in assessment.depends_on if effective_statuses.get(d) not in COMPLETE_STATUSES
    )
    satisfied = assessment.applicability != "required" or (
        bool(assessment.criteria or assessment.depends_on)
        and all(c.status in ("supported", "not_applicable") for c in assessment.criteria)
        and not missing
        and not blocked
    )
    statuses = {c.status for c in assessment.criteria}
    state = next(
        (
            s
            for s in ("period_mismatch", "missing", "human_action", "needs_review")
            if s in statuses
        ),
        "supported" if satisfied else "needs_review",
    )
    actions = [
        c.action for c in assessment.criteria if c.status not in ("supported", "not_applicable")
    ]
    actions.extend(f"Resolve required item {d}." for d in blocked)
    if missing:
        state = "not_in_packet"
        actions.append("Include the cited supporting evidence in the packet.")
    return ReconciledRequirement(
        satisfied, state, included, missing, blocked, tuple(dict.fromkeys(actions))
    )
