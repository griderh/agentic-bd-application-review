"""Draft firm facts with provenance and review exceptions, never self-approval."""

import hashlib
from calendar import monthrange
from dataclasses import asdict, dataclass, replace
from datetime import UTC, date, datetime
from html import escape
from pathlib import Path
from typing import Annotated, Literal, Self

from pydantic import Field, StringConstraints, ValidationError, model_validator

from bd_packet_builder.contracts import (
    Citation,
    Contract,
    Identifier,
    IdentifierValue,
    Nonblank,
    Sha256,
    TextValue,
    check_native_citations,
)
from bd_packet_builder.inventory import Inventory, build_inventory, publish_json_run
from bd_packet_builder.local_inputs import LocalInputError, read_local_input

_DRAFT_LIMIT = 2 * 1024 * 1024
FactKey = Annotated[
    str,
    StringConstraints(max_length=128, pattern=r"^(?:firm|signer_roles)\.[a-z][a-z0-9_]*$"),
]


class FactSheetError(ValueError):
    """Safe draft schema/path failures without raw business facts."""


class Fact(Contract):
    fact_id: Identifier
    key: FactKey
    category: Literal["firm_identity", "signer_role"]
    value: Annotated[TextValue | IdentifierValue, Field(discriminator="kind")]
    role: Nonblank | None = None
    owner: Nonblank
    reviewed_by: Nonblank
    reviewed_on: date
    review_due: date
    effective_from: date
    effective_to: date | None = None
    citations: Annotated[tuple[Citation, ...], Field(max_length=20)] = ()

    @model_validator(mode="after")
    def coherent_fact(self) -> Self:
        if self.review_due <= self.reviewed_on:
            raise ValueError("Review due date must follow the recorded review date")
        if self.effective_to is not None and self.effective_to < self.effective_from:
            raise ValueError("Effective end must not precede effective start")
        if self.category == "signer_role":
            if not self.key.startswith("signer_roles.") or self.role is None:
                raise ValueError("Signer facts require a signer_roles key and explicit role")
            if not isinstance(self.value, TextValue):
                raise ValueError("Signer assignment must identify a person by name")
        elif not self.key.startswith("firm.") or self.role is not None:
            raise ValueError("Firm identity facts require a firm key and no signer role")
        return self


class FactSheet(Contract):
    """Version labels and named reviewers are assertions, not authenticated approvals."""

    schema_version: Literal[1] = 1
    version_id: Identifier
    supersedes_sha256: Sha256 | None = None
    steward: Nonblank
    facts: Annotated[tuple[Fact, ...], Field(min_length=1, max_length=500)]

    @model_validator(mode="after")
    def unique_records(self) -> Self:
        if len({fact.fact_id for fact in self.facts}) != len(self.facts):
            raise ValueError("Duplicate fact record identities")
        return self


@dataclass(frozen=True)
class FactCheck:
    fact_id: str
    issues: tuple[str, ...]
    resolved_citations: int
    usable_for_filling: Literal[False] = False


def check_fact_sheet(
    root: Path, inventory: Inventory, sheet: FactSheet, *, as_of: date
) -> tuple[FactCheck, ...]:
    """Check every record; retain history and conflicts instead of selecting a winner."""
    if type(as_of) is not date:
        raise FactSheetError("Validation as-of must be a date, not a timestamp or string")
    checks: list[FactCheck] = []
    for index, fact in enumerate(sheet.facts):
        issues: list[str] = []
        if fact.effective_from > as_of:
            issues.append("not_yet_effective")
        if fact.effective_to is not None and fact.effective_to < as_of:
            issues.append("no_longer_effective")
        if fact.review_due < as_of:
            issues.append("review_overdue")
        if fact.reviewed_on > as_of:
            issues.append("future_review_date")
        if fact.reviewed_on.year == date.max.year:
            annual_deadline = date.max
        else:
            year = fact.reviewed_on.year + 1
            annual_deadline = date(
                year,
                fact.reviewed_on.month,
                min(fact.reviewed_on.day, monthrange(year, fact.reviewed_on.month)[1]),
            )
        if fact.review_due > annual_deadline:
            issues.append("review_interval_exceeds_annual")
        if not fact.citations:
            issues.append("missing_evidence")
        resolved, citation_issues = check_native_citations(root, inventory, fact.citations)
        issues.extend(citation_issues)
        for other_index, other in enumerate(sheet.facts):
            if index == other_index or fact.key != other.key:
                continue
            if fact.effective_from <= (other.effective_to or date.max) and other.effective_from <= (
                fact.effective_to or date.max
            ):
                same = fact.value == other.value and fact.role == other.role
                issues.append("overlapping_duplicate_fact" if same else "conflicting_fact")
        checks.append(FactCheck(fact.fact_id, tuple(dict.fromkeys(issues)), resolved))
    return tuple(checks)


def run_fact_sheet_check(root: Path, source: Path, *, as_of: date) -> Path:
    """Validate a local draft and publish an internal report, not a released fact sheet."""
    return _run_fact_sheet_check(root, source, as_of=as_of, archive_only=False)


def _run_fact_sheet_check(root: Path, source: Path, *, as_of: date, archive_only: bool) -> Path:
    from bd_packet_builder.fact_sheet_excel import export_workbook, import_workbook

    root = root.resolve(strict=True)

    def read_draft() -> bytes:
        try:
            return read_local_input(root, source, Path("outputs"), _DRAFT_LIMIT)
        except LocalInputError as error:
            raise FactSheetError(str(error)) from None

    data = read_draft()
    digest = hashlib.sha256(data).hexdigest()
    inventory = build_inventory(root)
    evidence_rows = None
    evidence_issues: dict[str, tuple[str, ...]] = {}
    if source.suffix.lower() == ".xlsx":
        sheet, evidence_issues, evidence_rows = import_workbook(data, root, inventory)
    elif source.suffix.lower() == ".json":
        try:
            sheet = FactSheet.model_validate_json(data)
        except ValidationError:
            raise FactSheetError(
                "Invalid fact-sheet JSON; check schema, identities, evidence "
                "and review/effective dates"
            ) from None
    else:
        raise FactSheetError("Fact-sheet input must be an .xlsx workbook or internal .json draft")
    checks = check_fact_sheet(root, inventory, sheet, as_of=as_of)
    checks = tuple(
        replace(
            check,
            issues=tuple(dict.fromkeys((*check.issues, *evidence_issues.get(check.fact_id, ())))),
        )
        for check in checks
    )

    def verify() -> None:
        if hashlib.sha256(read_draft()).hexdigest() != digest:
            raise FactSheetError("Fact-sheet draft changed; validation report was not published")

    payload: dict[str, object] = {
        "schema_version": 1,
        "status": "draft_validation_only_not_approved",
        "coverage": "supplied_fact_records_only",
        "created_at": datetime.now(UTC).isoformat(),
        "as_of": as_of.isoformat(),
        "draft": {"path": source.as_posix(), "sha256": digest},
        "version_id": sheet.version_id,
        "supersedes_sha256": sheet.supersedes_sha256,
        "steward": sheet.steward,
        "flags": [
            "approval_not_verified",
            "semantic_support_unverified",
            "reviewer_identity_not_authenticated",
            "no_automatic_filling",
        ],
        "facts_with_exceptions": sum(bool(check.issues) for check in checks),
        "items": [
            {"fact": fact.model_dump(mode="json"), "check": asdict(check)}
            for fact, check in zip(sheet.facts, checks, strict=True)
        ],
        "inventory_issues": [asdict(issue) for issue in inventory.issues],
    }
    if evidence_rows is not None:
        payload["workbook_evidence"] = evidence_rows
    workbook = (
        None
        if archive_only
        else export_workbook(
            sheet, inventory, checks=checks, evidence_rows=evidence_rows, as_of=as_of.isoformat()
        )
    )

    def write_workbook(staging: Path) -> None:
        if workbook is not None:
            (staging / "fact-sheet.xlsx").write_bytes(workbook)
        else:
            (staging / "input.snapshot.xlsx").write_bytes(data)
            rows = "".join(
                f"<tr><td>{escape(fact.fact_id)}</td><td>{escape(fact.key)}</td>"
                f"<td>{escape(fact.value.value)}</td>"
                f"<td>{
                    escape(
                        '; '.join(issue.replace('_', ' ') for issue in check.issues)
                        or 'No mechanical exceptions'
                    )
                }</td></tr>"
                for fact, check in zip(sheet.facts, checks, strict=True)
            )
            report = (
                "<!doctype html><html lang='en'><meta charset='utf-8'>"
                "<title>PoC intake validation</title><h1>Fact-sheet intake validation</h1>"
                f"<p>Evaluated as of {as_of.isoformat()}. "
                f"{sum(bool(check.issues) for check in checks)} facts with exceptions.</p>"
                "<p>No packet or answers generated. Plausible typos and semantic support "
                "are not verified. Continue editing the maintained workbook, not its archive.</p>"
                f"<p>Input: {escape(source.as_posix())}<br>SHA256: {digest}</p>"
                "<table border='1'><tr><th>Record ID</th><th>Fact key</th><th>Value read</th>"
                f"<th>Checks</th></tr>{rows}</table></html>"
            )
            (staging / "validation.html").write_text(report, encoding="utf-8")

    return publish_json_run(
        root,
        "fact-sheet-check",
        payload,
        inventory,
        verify_inputs=verify,
        write_artifacts=write_workbook,
    )
