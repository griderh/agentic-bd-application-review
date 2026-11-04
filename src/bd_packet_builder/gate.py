"""Code-only answer validation gate; replaces human pre-write approval for application runs.

The gate turns untrusted model proposals into the writer's decision record using only
deterministic checks. A passed gate means the cited quotes resolve in version-bound sources, the
answer fits its declared type, period and placement, and the requirement is not a signing item.
It does not prove narrative support or business correctness; humans review the draft afterwards.
Model confidence is never an input.
"""

import hashlib
import re
from pathlib import Path

from bd_packet_builder.contracts import (
    EvidenceStatus,
    HistoricalContextCitation,
    IdentifierValue,
    OcrCitation,
    TextValue,
    check_proposal,
)
from bd_packet_builder.draft import (
    DraftDecision,
    DraftError,
    DraftRequest,
    DraftReview,
    historical_answer_citations,
    publish_draft,
    selected_inventory,
    verify_historical_context,
    verify_ocr_citation,
)
from bd_packet_builder.exhibits import ExhibitError, audit_support, extract_exhibit
from bd_packet_builder.historical_context import (
    HistoricalContextCheck,
    verified_question_requirements,
)
from bd_packet_builder.historical_time import prior_tenure_proposal
from bd_packet_builder.history import historical_issues, primary_representative_rule
from bd_packet_builder.local_inputs import read_local_input
from bd_packet_builder.reconciliation import RequirementAssessment
from bd_packet_builder.scan import ExhibitImageCheck, ScanCheck

GATE_VERSION = "answer-gate-v15"
GATE_REVIEWER = "application_validation_gate_v15"
_MAX_REQUEST_BYTES = 2 * 1024 * 1024


def _normalized(text: str) -> str:
    return " ".join(text.casefold().split())


def validate_answers(
    root: Path,
    request: DraftRequest,
    request_sha256: str,
    *,
    selected_attachment_source_ids: tuple[str, ...] = (),
    scan_checks: tuple[ScanCheck, ...] = (),
    historical_context_checks: tuple[HistoricalContextCheck, ...] = (),
    exhibit_image_checks: tuple[ExhibitImageCheck, ...] = (),
    requirement_assessments: tuple[RequirementAssessment, ...] = (),
    blank: bytes | None = None,
) -> DraftReview:
    """Return one decision per proposal; per-answer failures become withheld decisions.

    Technical failures such as changed or unreadable sources propagate instead of being
    reported as review exceptions.
    """
    inventory = selected_inventory(root, request)
    if not set(selected_attachment_source_ids) <= set(request.attachments):
        raise DraftError("Explicit selection contains an unknown attachment")
    requirements = {r.requirement_id: r for r in request.requirements.requirements}
    mappings = {m.requirement.requirement_id: m for m in request.layout.responses}
    attached = set(request.attachments)
    historical = {s.source_id for s in inventory.sources if s.family == "historical_reference"}
    if attached & historical:
        raise DraftError("Historical packets must never be submission attachments")
    needed: dict[str, HistoricalContextCheck] = {}
    receipts_by_hash = {c.context_citation.check_sha256: c for c in historical_context_checks}
    for historical_receipt in historical_context_checks:
        for proposal in request.proposals.proposals:
            basis = proposal.historical_basis
            context = basis.prior_question if basis is not None else None
            main_receipt = (
                receipts_by_hash.get(context.check_sha256)
                if isinstance(context, HistoricalContextCitation)
                else None
            )
            same_control_group = (
                historical_receipt.field.control is not None
                and isinstance(context, HistoricalContextCitation)
                and context.source_id == historical_receipt.question.source_id
                and context.page == historical_receipt.question.page
                and context.quote == historical_receipt.context_citation.quote
                and main_receipt is not None
                and historical_receipt.transcript == main_receipt.transcript
            )
            value = prior_tenure_proposal(proposal).value
            write_in_receipt = (
                historical_receipt.field.control is None
                and historical_receipt.answer in proposal.citations
                and value is not None
                and value.kind in ("single_select", "multi_select")
                and any(
                    _normalized(w.text) == _normalized(historical_receipt.field.answer.text)
                    for w in value.write_ins
                )
            )
            if (
                write_in_receipt
                or same_control_group
                or (
                    historical_receipt.answer in proposal.citations
                    and any(d.part == "question" for d in historical_receipt.discrepancies)
                )
                or (
                    basis is not None
                    and (
                        basis.prior_question == historical_receipt.context_citation
                        or basis.reading_resolution is not None
                        and basis.reading_resolution.subject_context
                        == historical_receipt.context_citation
                    )
                )
                or (
                    basis is not None
                    and basis.tenure is not None
                    and basis.tenure.date_context == historical_receipt.context_citation
                )
                or (
                    basis is not None
                    and basis.additional_contexts
                    and (
                        historical_receipt.context_citation in basis.additional_contexts
                        or basis.prior_question == historical_receipt.context_citation
                    )
                )
                or historical_receipt.supports(proposal, requirements[proposal.requirement_id])
            ):
                needed[historical_receipt.context_citation.check_sha256] = historical_receipt
                break
    historical_context_checks = tuple(needed.values())
    question_requirements = (
        verified_question_requirements(
            blank
            if blank is not None
            else read_local_input(
                root, Path(request.source), Path("bd_agreements/Blank"), 64 * 1024 * 1024
            ),
            request.requirements.requirements,
        )
        if any(
            c.field.control is not None and any(d.part == "question" for d in c.discrepancies)
            for c in historical_context_checks
        )
        else ()
    )
    decisions: list[DraftDecision] = []
    supporting: list[str] = list(selected_attachment_source_ids)
    render_hashes: dict[tuple[str, int], str] = {}
    for proposal in request.proposals.proposals:
        requirement = requirements[proposal.requirement_id]
        check = check_proposal(root, inventory, requirement, proposal)
        issues: list[str] = []
        evidence_status: EvidenceStatus = "unsupported"
        if requirement.kind in ("signature", "signature_date"):
            issues.append("human_signing_required")
        elif proposal.outcome != "proposed":
            issues.append(proposal.outcome)
        else:
            context_issues, context_snapshots = verify_historical_context(
                root,
                inventory,
                proposal,
                historical_context_checks,
                render_hashes,
                requirement,
                request.historical_policy == "answer_first_review",
                mappings.get(proposal.requirement_id),
                scan_checks,
                question_requirements=question_requirements,
            )
            answer_citations = historical_answer_citations(proposal, context_snapshots)
            context_verified = bool(answer_citations) and not context_issues
            issues.extend(context_issues)
            history_issues, evidence_status = historical_issues(
                root,
                inventory,
                request.historical_archive,
                request.issuer,
                requirement,
                proposal,
                navigation_context=request.navigation_context.get(proposal.requirement_id, ""),
                context_verified=context_verified,
                historical_policy=request.historical_policy,
                calculation_date=request.calculation_date,
                verified_current_scans=tuple(c for c, _ in context_snapshots),
            )
            issues.extend(history_issues)
            for citation in proposal.citations:
                if isinstance(citation, OcrCitation):
                    if context_verified and citation in answer_citations:
                        continue
                    if not any(
                        receipt.citation == citation and receipt.supports(requirement, proposal)
                        for receipt in scan_checks
                    ):
                        issues.append("ocr_evidence_requires_machine_verification")
                    else:
                        issue, snapshot, _ = verify_ocr_citation(
                            root, inventory, citation, render_hashes
                        )
                        if issue is not None:
                            issues.append(issue)
                        elif snapshot is None or not any(
                            receipt.citation == citation
                            and receipt.supports(requirement, proposal)
                            and receipt.agrees_with_artifact(snapshot)
                            for receipt in scan_checks
                        ):
                            issues.append("scan_ocr_subject_or_confidence_disagrees")
            if check.status == "rejected":
                issues.extend(check.issues)
            if proposal.requirement_id not in mappings:
                issues.append("placement_not_available")
            period = requirement.requested_period
            if period is not None and proposal.claimed_period != period:
                issues.append("requested_period_not_confirmed")
            if any(c.source_id not in attached | historical for c in proposal.citations):
                issues.append("supporting_evidence_not_attached")
            quotes = [c.quote for c in proposal.citations]
            value = prior_tenure_proposal(proposal).value
            if isinstance(value, IdentifierValue) and not any(
                re.search(r"(?<!\w)" + re.escape(value.value) + r"(?!\w)", q) for q in quotes
            ):
                issues.append("identifier_not_in_cited_evidence")
            if (
                isinstance(value, TextValue)
                and not context_verified
                and not any(_normalized(value.value) in _normalized(q) for q in quotes)
            ):
                issues.append("text_value_not_in_cited_evidence")
        unique = tuple(dict.fromkeys(issues))
        verified = not unique
        if verified:
            supporting.extend(
                c.source_id for c in proposal.citations if c.source_id not in historical
            )
            if proposal.historical_basis is not None:
                for current_check in proposal.historical_basis.current_checks:
                    if current_check.citation.source_id not in historical:
                        supporting.append(current_check.citation.source_id)
        decisions.append(
            DraftDecision(
                requirement_id=proposal.requirement_id,
                decision="draft_verified" if verified else "withhold",
                evidence_support_confirmed=verified,
                source_approved=verified,
                placement_confirmed=verified,
                reason=(
                    f"{GATE_VERSION}: code checks passed; no human approval."
                    + (
                        " Sponsor Broward role rule: Qualified Representative defaults to "
                        "Primary Representative for printed identity only."
                        if primary_representative_rule(
                            request.issuer,
                            requirement,
                            request.navigation_context.get(proposal.requirement_id, ""),
                        )
                        else ""
                    )
                    if verified
                    else f"{GATE_VERSION}: " + ", ".join(unique)
                ),
                evidence_status=evidence_status if verified else "unsupported",
            )
        )
    notes: list[str] = []
    exhibit_ids = []
    for exhibit in request.historical_exhibits:
        try:
            extract_exhibit(
                root,
                inventory,
                exhibit,
                proposals=request.proposals.proposals,
                image_checks=exhibit_image_checks,
            )
        except ExhibitError as error:
            notes.append(f"Historical exhibit {exhibit.exhibit_id} withheld: {error}")
        else:
            exhibit_ids.append(exhibit.exhibit_id)
    attached_ids = tuple(
        identity for identity in request.attachments if identity in set(supporting)
    )
    for audit in audit_support(
        request.proposals.proposals,
        inventory,
        attached_ids,
        tuple(e for e in request.historical_exhibits if e.exhibit_id in exhibit_ids),
    ):
        if audit.issues:
            notes.append(
                f"Supporting documents for {audit.requirement_id}: {', '.join(audit.issues)}. "
                "Inclusion does not establish semantic support, matching dates or current validity."
            )
    if selected_attachment_source_ids:
        notes.append(
            "Explicitly selected supporting PDFs are included independently of filled answers. "
            "Inclusion does not confirm an attachment requirement, reporting period, "
            "registration sufficiency or attestation has been satisfied."
        )
    if scan_checks:
        notes.append(
            "Scanned scalar answers use OCR/independent-image transcription agreement, "
            "not human visual approval or proof of semantic support. "
            "Reporting periods come from the image reading, not a filename."
        )
        for receipt in scan_checks:
            source = next(
                (s for s in inventory.sources if s.source_id == receipt.citation.source_id), None
            )
            period = receipt.transcript.reporting_period
            if source is not None and source.period is not None and period is not None:
                printed = period.end.strftime(
                    "%Y-%m" if source.period_precision == "monthly" else "%Y"
                )
                if printed != source.period:
                    notes.append(
                        f"Scanned source {source.source_id}: catalog/filename period "
                        f"{source.period} differs from image-read period "
                        f"{period.start.isoformat()} through {period.end.isoformat()}; "
                        "reviewer verification required."
                    )
    return DraftReview(
        request_sha256=request_sha256,
        reviewer=GATE_REVIEWER,
        decisions=tuple(decisions),
        attachment_source_ids=tuple(
            identity for identity in request.attachments if identity in set(supporting)
        ),
        reviewer_notes=tuple(dict.fromkeys(notes)),
        scan_checks=scan_checks,
        historical_context_checks=historical_context_checks,
        historical_exhibit_ids=tuple(exhibit_ids),
        exhibit_image_checks=exhibit_image_checks,
        requirement_assessments=requirement_assessments,
    )


def run_application_draft(root: Path, request_path: Path) -> Path:
    """Validate answers in code, then publish one incomplete draft for later human review."""
    root = root.resolve(strict=True)
    raw = read_local_input(root, request_path, Path("outputs"), _MAX_REQUEST_BYTES)
    request = DraftRequest.model_validate_json(raw)
    review = validate_answers(root, request, hashlib.sha256(raw).hexdigest())
    return publish_draft(
        root, request_path, raw, request, review, review.model_dump_json().encode(), None
    )
