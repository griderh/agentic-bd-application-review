"""Untrusted proposal schemas and fail-closed checks, not an answer approval service."""

from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from pathlib import Path
from typing import Annotated, Literal, Self

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    StringConstraints,
    field_validator,
    model_validator,
)

from bd_packet_builder.evidence import EvidenceError, TextCitation, resolve_quote
from bd_packet_builder.inventory import Inventory

Nonblank = Annotated[str, StringConstraints(min_length=1, max_length=20_000, pattern=r"\S")]
Identifier = Annotated[str, StringConstraints(min_length=1, max_length=128, pattern=r"^[\w.-]+$")]
Sha256 = Annotated[str, StringConstraints(pattern=r"^[0-9a-f]{64}$")]
Unit = Annotated[str, StringConstraints(min_length=1, max_length=64, pattern=r"\S")]
RequirementKind = Literal[
    "text",
    "identifier",
    "money",
    "date",
    "boolean",
    "attachment",
    "signature",
    "signature_date",
    "single_select",
    "multi_select",
    "narrative",
]


class Contract(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid", frozen=True, hide_input_in_errors=True)

    @field_validator("schema_version", mode="before", check_fields=False)
    @classmethod
    def integer_version(cls, value: object) -> object:
        if type(value) is not int:
            raise ValueError("Schema version must be an integer")
        return value


class ReportingPeriod(Contract):
    start: date
    end: date

    @model_validator(mode="after")
    def ordered(self) -> Self:
        if self.start > self.end:
            raise ValueError("Reporting period start must not follow end")
        return self


class ChoiceOption(Contract):
    option_id: Identifier
    label: Nonblank
    instruction: Nonblank
    write_in: bool = False


class ChoiceGroup(Contract):
    options: Annotated[tuple[ChoiceOption, ...], Field(min_length=2, max_length=100)]

    @model_validator(mode="after")
    def unique_options(self) -> Self:
        if len({o.option_id for o in self.options}) != len(self.options):
            raise ValueError("Choice option identities must be unique")
        return self


class Requirement(Contract):
    """An interpreted requirement; its issuer wording/location still needs validation."""

    requirement_id: Identifier
    application_sha256: Sha256
    page: Annotated[int, Field(ge=1)]
    instruction: Nonblank
    kind: RequirementKind
    unit: Unit | None = None
    requested_period: ReportingPeriod | None = None
    required_signer_role: Nonblank | None = None
    choices: ChoiceGroup | None = None

    @model_validator(mode="after")
    def units(self) -> Self:
        if (self.kind == "money") != (self.unit is not None):
            raise ValueError("Money requirements need explicit units; other kinds must omit units")
        if (self.kind in ("single_select", "multi_select")) != (self.choices is not None):
            raise ValueError("Choice requirements need options; other kinds must omit options")
        return self


class ApplicationRequirements(Contract):
    schema_version: Literal[1] = 1
    requirements: Annotated[tuple[Requirement, ...], Field(min_length=1, max_length=500)]

    @model_validator(mode="after")
    def unique_ids(self) -> Self:
        if len({r.requirement_id for r in self.requirements}) != len(self.requirements):
            raise ValueError("Duplicate requirement identities")
        if len({r.application_sha256 for r in self.requirements}) != 1:
            raise ValueError("Requirement set must refer to one application version")
        return self


class TextValue(Contract):
    kind: Literal["text"]
    value: Nonblank


class IdentifierValue(Contract):
    kind: Literal["identifier"]
    value: Identifier


class MoneyValue(Contract):
    kind: Literal["money"]
    amount: Annotated[
        str, StringConstraints(max_length=128, pattern=r"^-?(?:0|[1-9]\d*)(?:\.\d+)?$")
    ]
    unit: Unit

    @property
    def decimal_amount(self) -> Decimal:
        return Decimal(self.amount)


class DateValue(Contract):
    kind: Literal["date"]
    value: date


class BooleanValue(Contract):
    kind: Literal["boolean"]
    value: bool


class AttachmentValue(Contract):
    kind: Literal["attachment"]
    source_id: Sha256


class ChoiceWriteIn(Contract):
    option_id: Identifier
    text: Nonblank


class MultiSelectValue(Contract):
    kind: Literal["multi_select"]
    selected: Annotated[tuple[Identifier, ...], Field(min_length=1, max_length=100)]
    write_ins: Annotated[tuple[ChoiceWriteIn, ...], Field(max_length=100)] = ()

    @model_validator(mode="after")
    def unique_selections(self) -> Self:
        if len(set(self.selected)) != len(self.selected):
            raise ValueError("Selected options must be unique")
        if len({w.option_id for w in self.write_ins}) != len(self.write_ins):
            raise ValueError("Option write-ins must be unique")
        return self


class SingleSelectValue(Contract):
    kind: Literal["single_select"]
    selected: Annotated[tuple[Identifier, ...], Field(min_length=1, max_length=1)]
    write_ins: Annotated[tuple[ChoiceWriteIn, ...], Field(max_length=1)] = ()


class NarrativeValue(Contract):
    kind: Literal["narrative"]
    value: Nonblank


AnswerValue = Annotated[
    TextValue
    | IdentifierValue
    | MoneyValue
    | DateValue
    | BooleanValue
    | AttachmentValue
    | SingleSelectValue
    | MultiSelectValue
    | NarrativeValue,
    Field(discriminator="kind"),
]


class Citation(Contract):
    source_id: Sha256
    page: Annotated[int, Field(ge=1)]
    start: Annotated[int, Field(ge=0)]
    end: Annotated[int, Field(ge=1)]
    quote: Nonblank

    @model_validator(mode="after")
    def valid_span(self) -> Self:
        if self.end <= self.start or self.end - self.start != len(self.quote):
            raise ValueError("Citation offsets must delimit the exact quote")
        return self

    def text_citation(self) -> TextCitation:
        return TextCitation(self.source_id, self.page, self.start, self.end, self.quote)


class AnswerProposal(Contract):
    schema_version: Literal[1] = 1
    requirement_id: Identifier
    outcome: Literal[
        "proposed",
        "missing_evidence",
        "conflicting_evidence",
        "unresolved_signer",
        "unreadable_form",
        "unsupported_requirement",
        "deferred_to_signing",
    ]
    value: AnswerValue | None = None
    citations: Annotated[tuple[Citation, ...], Field(max_length=20)] = ()
    claimed_period: ReportingPeriod | None = None
    confidence: Annotated[float, Field(ge=0, le=1, allow_inf_nan=False)] | None = None
    explanation: Nonblank | None = None

    @model_validator(mode="after")
    def complete_outcome(self) -> Self:
        if self.outcome == "proposed":
            if self.value is None or not self.citations or self.confidence is None:
                raise ValueError("Proposed answers require a value, citations and confidence")
        elif self.value is not None or self.explanation is None:
            raise ValueError("Unanswered outcomes require an explanation and no value")
        return self


@dataclass(frozen=True)
class ProposalCheck:
    requirement_id: str
    status: Literal["rejected", "unanswered", "deferred_to_signing", "review_required"]
    issues: tuple[str, ...]
    resolved_citations: int = 0
    fill_value: None = None


def check_native_citations(
    root: Path, inventory: Inventory, citations: tuple[Citation, ...]
) -> tuple[int, tuple[str, ...]]:
    """Resolve exact native quotes; technical freshness/access errors propagate."""
    issues: list[str] = []
    resolved = 0
    for citation in citations:
        source = next((s for s in inventory.sources if s.source_id == citation.source_id), None)
        if source is None or source.page_count is None or citation.page > source.page_count:
            issues.append("citation_unresolved")
            continue
        try:
            resolve_quote(root, inventory, citation.text_citation())
        except EvidenceError:
            issues.append("citation_quote_mismatch")
        else:
            resolved += 1
    return resolved, tuple(dict.fromkeys(issues))


def check_proposal(
    root: Path, inventory: Inventory, requirement: Requirement, proposal: AnswerProposal
) -> ProposalCheck:
    """Resolve native quotes, not semantic support, source approval, or form placement.

    Unknown IDs/pages and literal quote mismatches reject the proposal. Source
    mutation and I/O errors propagate as technical failures, not review exceptions.
    """
    identity = requirement.requirement_id
    if proposal.requirement_id != identity:
        return ProposalCheck(identity, "rejected", ("requirement_id_mismatch",))
    if requirement.kind in ("signature", "signature_date"):
        return ProposalCheck(identity, "deferred_to_signing", ("human_signing_required",))

    issues: list[str] = []
    if proposal.value is not None:
        if proposal.value.kind != requirement.kind:
            issues.append("answer_kind_mismatch")
        if isinstance(proposal.value, MoneyValue) and proposal.value.unit != requirement.unit:
            issues.append("unit_mismatch")
        if isinstance(proposal.value, AttachmentValue) and not any(
            citation.source_id == proposal.value.source_id for citation in proposal.citations
        ):
            issues.append("attachment_source_not_cited")
        if isinstance(proposal.value, (SingleSelectValue, MultiSelectValue)):
            if requirement.choices is None:
                issues.append("choice_structure_missing")
            else:
                options = {o.option_id: o for o in requirement.choices.options}
                selected = set(proposal.value.selected)
                write_ins = {w.option_id for w in proposal.value.write_ins}
                if not selected <= options.keys():
                    issues.append("unknown_choice_option")
                if write_ins - selected:
                    issues.append("choice_write_in_not_selected")
                if any(key not in options or not options[key].write_in for key in write_ins):
                    issues.append("choice_write_in_not_allowed")
                if any(
                    options[key].write_in and key not in write_ins
                    for key in selected & options.keys()
                ):
                    issues.append("choice_write_in_missing")
    resolved, citation_issues = check_native_citations(root, inventory, proposal.citations)
    issues.extend(citation_issues)
    if issues:
        return ProposalCheck(identity, "rejected", tuple(dict.fromkeys(issues)), resolved)
    if proposal.outcome != "proposed":
        return ProposalCheck(identity, "unanswered", (proposal.outcome,), resolved)
    issues.extend(
        (
            "semantic_support_unverified",
            "source_approval_unverified",
            "application_requirement_unverified",
        )
    )
    if requirement.requested_period is not None:
        issues.append("reporting_period_unverified")
        if (
            proposal.claimed_period is not None
            and proposal.claimed_period != requirement.requested_period
        ):
            issues.append("requested_period_mismatch")
    if requirement.required_signer_role is not None:
        issues.append("signer_role_unverified")
    return ProposalCheck(identity, "review_required", tuple(issues), resolved)
