"""Pure formatting for internal reviewer text, never submission-packet content."""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from typing import TYPE_CHECKING

from bd_packet_builder.contracts import HistoricalContextCitation, OcrCitation
from bd_packet_builder.exhibits import HistoricalExhibit, SupportingDocumentAudit
from bd_packet_builder.history import historical_review_concerns
from bd_packet_builder.inventory import Inventory, SourceRecord
from bd_packet_builder.responses import PacketPagination, PacketReference

if TYPE_CHECKING:
    from bd_packet_builder.agent import _PlanSupport
    from bd_packet_builder.draft import DraftRequest, DraftReview


_PLAIN_HISTORICAL_REASONS = {
    "historical_question_correspondence_required": (
        "The historical answer lacks an assessment tied to this exact target question."
    ),
    "historical_question_applicability_uncertain": (
        "It is uncertain whether the historical answer addresses this question. This is "
        "different from unconfirmed current continuity."
    ),
    "historical_question_partially_applicable": (
        "Only part of the question has applicable historical support. Partial-response "
        "writing is not enabled; supported and missing parts are identified below."
    ),
    "historical_composition_has_unsupported_text": (
        "The proposed answer does not exactly equal the cited historical answer pieces joined "
        "in order. A 'see supplement' pointer cited as an answer piece causes this."
    ),
    "historical_question_link_not_a_pointer": (
        "A record cited as a 'see supplement' link does not read as a short pointer."
    ),
    "historical_question_link_question_mismatch": (
        "The 'see supplement' link belongs to a different question than the cited answer."
    ),
    "historical_question_link_context_mismatch": (
        "The 'see supplement' link is from a different packet, section or answer type."
    ),
    "historical_question_link_receipt_missing": (
        "The 'see supplement' link has no checked page-reading record."
    ),
    "historical_question_link_repeats_answer": (
        "The same record was cited as both an answer piece and a 'see supplement' link."
    ),
    "historical_question_link_text_or_geometry_disagrees": (
        "The 'see supplement' link no longer matches the page text or position on recheck."
    ),
}


def draft_reviewer_summary(
    request: DraftRequest,
    review: DraftReview,
    *,
    completion: dict[str, int],
    additional_form_manifest: list[dict[str, object]],
    results: list[dict[str, object]],
    placements: dict[str, dict[str, object]],
    sources: dict[str, SourceRecord],
    pagination: PacketPagination,
    attachment_ids: list[str],
    support_audits: tuple[SupportingDocumentAudit, ...],
    approved_exhibits: tuple[HistoricalExhibit, ...],
    minimum_short_font: float,
) -> str:
    requirements = {r.requirement_id: r for r in request.requirements.requirements}
    assessments = {a.requirement_id: a for a in review.requirement_assessments}
    decisions = {d.requirement_id: d for d in review.decisions}
    summary = [
        "INTERNAL REVIEW - NOT PART OF THE SUBMISSION PACKET",
        "INCOMPLETE DRAFT - NOT FOR SUBMISSION",
        f"Mode: {request.mode}",
        "Coverage: declared subset only; all other form fields remain unresolved.",
        "Signatures and signature dates must be completed only by humans at signing.",
        f"Completion: {completion}. Conditional not-applicable is NOT a populated answer.",
    ]
    for form in additional_form_manifest:
        summary.append(
            "Additional issuer form appended: "
            f"{form['path']}; approved mirrored fields: {form['written_requirements']}."
        )
    if review.reviewer_notes:
        summary.extend(["", "Reviewer notes:"])
        summary.extend(f"- {note}" for note in review.reviewer_notes)
    summary.extend(["", "REVIEWER ACTION LIST (internal only):"])
    for item in results:
        identity = str(item["requirement_id"])
        proposal_record = item.get("proposal")
        printed_details = item.get("historical_printed_readings")
        printed_records = (
            [r for r in printed_details if isinstance(r, dict)]
            if isinstance(printed_details, list)
            else []
        )
        resolved_printed = any(r.get("status") == "resolved" for r in printed_records)
        if printed_records:
            for reading in printed_records:
                summary.append(
                    f"- Form page {requirements[identity].page}, {identity}: "
                    f"PRINTED-WORDING CHECK: {reading['part']}; "
                    f"status={reading['status']}; method="
                    + (
                        "localized source-native text"
                        if reading["native"]
                        else "blind focused image reread"
                        if reading["focused"]
                        else "reread budget exhausted"
                    )
                    + ". Original readings remain below; this does not establish "
                    "current business truth or approve a selection."
                )
        extraction_details = item.get("historical_extraction_discrepancies")
        extraction_parts = (
            tuple(
                dict.fromkeys(
                    str(d["part"])
                    for d in extraction_details
                    if isinstance(d, dict)
                    and d.get("code") != "historical_question_presentation_resolved"
                )
            )
            if isinstance(extraction_details, list)
            else ()
        )
        if isinstance(extraction_details, list) and any(
            isinstance(d, dict) and d.get("code") == "historical_question_presentation_resolved"
            for d in extraction_details
        ):
            summary.append(
                f"- {identity}: QUESTION PRESENTATION RESOLVED; substantive wording agrees. "
                "Original readings retained; applicability, answer support and historical "
                "continuity are separate checks."
            )
        if item["status"] in ("blank", "requirement_satisfied") or identity in assessments:
            assessment = assessments.get(identity)
            summary.append(
                f"- Form page {requirements[identity].page}, {identity}: "
                f"{'LEFT BLANK' if item['status'] == 'blank' else item['status']}; "
                + (
                    "Historical question transcription was reconciled against source "
                    "evidence, but the answer was not written; see validation details."
                    if item.get("historical_question_reconciliation")
                    else "Historical extraction differs in: "
                    + ", ".join(extraction_parts)
                    + ". Question wording, answer text and selected marks are checked "
                    "separately; a question-reading problem does not mean the checkbox "
                    "could not be read."
                    if "question" in extraction_parts
                    else "Conflicting readings were not resolved with verified evidence "
                    "linking the same subject, field and value."
                    if extraction_parts
                    else str(item.get("effective_explanation") or item["review_reason"])
                )
            )
            if item["status"] == "blank":
                basis = next(
                    p.historical_basis
                    for p in request.proposals.proposals
                    if p.requirement_id == identity
                )
                if basis is not None and basis.correspondence is not None:
                    correspondence = basis.correspondence
                    summary.append(
                        f"  QUESTION CORRESPONDENCE ({correspondence.assessment}; "
                        "model interpretation, not semantic approval): "
                        f"{correspondence.reason} "
                        f"Differences/coverage gap: {correspondence.differences}. "
                        f"Historical source: {basis.prior_question.source_id}, "
                        f"page {basis.prior_question.page}."
                    )
                summary.append(
                    f"  Validation details: {item['review_reason']}; "
                    f"writer checks: {item['issues']}"
                )
                codes = f"{item['review_reason']} {item['issues']}"
                summary.extend(
                    f"  Plain-language reason: {text}"
                    for code, text in _PLAIN_HISTORICAL_REASONS.items()
                    if code in codes
                )
            if item.get("historical_extraction_discrepancies"):
                summary.append(
                    (
                        "  Original extraction readings (question transcription reconciled): "
                        if item.get("historical_question_reconciliation")
                        else "  Conflicting extraction readings (originals): "
                    )
                    + json.dumps(item["historical_extraction_discrepancies"])
                )
            if assessment is not None:
                summary.append(
                    f"  Reviewed applicability: {assessment.applicability}; "
                    f"reviewer/provenance: {assessment.reviewer}. "
                    "Local review input is not authenticated approval."
                )
                for criterion in assessment.criteria:
                    summary.append(
                        f"  Issuer criterion: {criterion.issuer_quote}; "
                        f"coverage={criterion.status}. {criterion.explanation}"
                    )
                    if criterion.status not in ("supported", "not_applicable"):
                        summary.append(f"  ACTION: {criterion.action}")
                    for assessed_citation in criterion.evidence:
                        assessed_source = sources[assessed_citation.source_id]
                        in_packet = assessed_citation.source_id in attachment_ids
                        packet_page = (
                            pagination.resolve(
                                PacketReference(
                                    section_id=assessed_citation.source_id,
                                    page=assessed_citation.page,
                                ),
                                role="evidence",
                            )
                            if in_packet
                            else "not included"
                        )
                        summary.append(
                            f"  Evidence: {assessed_source.path}; "
                            f"sha256={assessed_source.sha256}; "
                            f"source page {assessed_citation.page}; packet page {packet_page}; "
                            "inclusion alone is not requirement satisfaction."
                        )
                if assessment.depends_on:
                    summary.append(
                        "  Completion evaluated from actual required-item outcomes: "
                        + str(item.get("coverage"))
                    )
                for note in assessment.historical_notes:
                    assessed_source = sources[note.citation.source_id]
                    summary.append(
                        f"  HISTORICAL LIMITATION, NOT INITIALS OR CURRENT CONFIRMATION: "
                        f"{note.citation.quote}; {note.explanation} "
                        f"Source: {assessed_source.path}; sha256={assessed_source.sha256}; "
                        f"page {note.citation.page}. ACTION: {note.action}"
                    )
            elif item["status"] == "blank":
                summary.append(
                    "  ACTION: Resolve the proposal-processing exception using the saved "
                    "source and diagnostics. Do not infer missing evidence or approve the "
                    "rejected answer. The field remains blank pending supported resolution."
                    if isinstance(proposal_record, dict)
                    and proposal_record.get("outcome") == "technical_review_required"
                    else "  ACTION: Question transcription is already resolved. Review the "
                    "remaining validation issues or regenerate the answer proposal; do not "
                    "request new business evidence solely for this OCR defect."
                    if item.get("historical_question_reconciliation")
                    else "  ACTION: Inspect the original historical question and its selected "
                    "answer together. Resolve the specific question wording difference; "
                    "current business evidence is not required merely to repair transcription."
                    if "question" in extraction_parts
                    and not item.get("historical_question_reconciliation")
                    else "  ACTION: Verify the conflicting readings against an independent "
                    "source for the same subject and field; enter the supported value "
                    "only after verification."
                    if extraction_parts
                    else "  ACTION: "
                    + str(item.get("effective_explanation") or item["review_reason"])
                )
        elif item["status"] == "written_to_draft":
            proposal = next(p for p in request.proposals.proposals if p.requirement_id == identity)
            basis = proposal.historical_basis
            if basis is not None and basis.reading_resolution is not None:
                summary.append(
                    f"- Form page {requirements[identity].page}, {identity}: "
                    "FILLED AFTER RECONCILIATION; selected value "
                    + str(proposal.value.model_dump(mode="json") if proposal.value else None)
                    + "; independent identity/field evidence "
                    + basis.reading_resolution.citation.model_dump_json()
                    + "; original readings "
                    + json.dumps(item.get("historical_extraction_discrepancies", []))
                )
            elif item.get("historical_candidate_status") == "reconciled_with_native_text_and_ocr":
                summary.append(
                    f"- Form page {requirements[identity].page}, {identity}: "
                    "FILLED AFTER RECONCILIATION; exact native digits and high-confidence "
                    "OCR agree within the historical answer region. Original readings: "
                    + json.dumps(item.get("historical_extraction_discrepancies", []))
                )
            elif resolved_printed:
                summary.append(
                    f"- Form page {requirements[identity].page}, {identity}: "
                    "FILLED AFTER PRINTED-WORDING RESOLUTION. Local source evidence resolved "
                    "the transcription difference; the selected answer was checked separately. "
                    "Historical continuity remains unconfirmed."
                )
            elif item.get("historical_question_reconciliation"):
                summary.append(
                    f"- Form page {requirements[identity].page}, {identity}: "
                    "FILLED AFTER QUESTION-TEXT RECONCILIATION; the historical image question "
                    "matches the native blank, and bounded OCR alignment passed. "
                    "The selected answer was checked separately. Historical continuity "
                    "remains unconfirmed."
                )
                summary.append(
                    "  Historical selected answer: "
                    + "; ".join(
                        c.field.answer.text
                        for c in review.historical_context_checks
                        if c.supports(proposal, requirements[identity])
                    )
                )
                if isinstance(extraction_details, list):
                    for difference in extraction_details:
                        if isinstance(difference, dict) and difference.get("part") == "question":
                            summary.extend(
                                [
                                    "  Image question: " + str(difference["image_reading"]),
                                    "  OCR question: " + str(difference["ocr_reading"]),
                                ]
                            )
    adjusted = [
        (identity, placement)
        for identity, placement in placements.items()
        if placement.get("fit") not in (None, "standard")
    ]
    if adjusted:
        summary.extend(
            [
                "",
                "SHORT-FIELD FIT (internal; reduced font, wrapped or moved to the supplement; "
                f"minimum {minimum_short_font:g} pt; check legibility):",
            ]
        )
        for identity, placement in adjusted:
            summary.append(
                f"- {identity}: below_minimum_font; written in Supplemental Answers."
                if placement["mode"] == "supplement"
                else f"- {identity}: {placement['fit']}; {placement['font_size']:g} pt, "
                f"{placement['line_count']} line(s)."
            )
    summary.extend(["", "Supporting-document completeness (not semantic approval):"])
    for audit in support_audits:
        summary.append(
            f"- {audit.requirement_id}: current documents="
            f"{','.join(audit.current_source_ids) or 'none'}; "
            f"historical exhibits={','.join(audit.historical_exhibits) or 'none'}; "
            "referenced support="
            f"{'; '.join(audit.referenced_support) or 'none declared/detected'}; "
            f"issues={','.join(audit.issues) or 'no physical dependency gaps detected'}."
        )
    for exhibit in approved_exhibits:
        summary.append(
            f"- HISTORICAL EXHIBIT {exhibit.exhibit_id}, requirement {exhibit.requirement_id}: "
            f"{sources[exhibit.title.source_id].path}, source hash "
            f"{sources[exhibit.title.source_id].sha256}, pages {exhibit.pages}. "
            f"{exhibit.reason} LIMITATION: {exhibit.limitation} "
            "Historical inclusion does not verify current truth or satisfy a dated claim."
        )
    proposals_by_id = {p.requirement_id: p for p in request.proposals.proposals}
    for item in results:
        proposal = proposals_by_id[str(item["requirement_id"])]
        summary_decision = decisions.get(proposal.requirement_id)
        packet_pages = placements.get(proposal.requirement_id, {}).get("evidence_packet_pages", [])
        summary.extend(
            [
                "",
                f"{item['requirement_id']}: {item['status']} - {item['issues']}",
                f"Question: {requirements[proposal.requirement_id].instruction}",
                f"Form page: {requirements[proposal.requirement_id].page}",
                "Proposed value: "
                + (
                    "(not applicable; no answer written)"
                    if item["status"] == "not_applicable"
                    else proposal.value.model_dump_json()
                    if proposal.value
                    else "(blank)"
                ),
                f"Review: {item['review_reason']}",
                f"Explanation: {item.get('effective_explanation') or '(none supplied)'}",
                f"Evidence packet pages: {packet_pages}",
                "MODEL-REPORTED KNOWLEDGE APPLICATION (not verified reasoning): "
                + (
                    "; ".join(f"{use.entry_id}: {use.reason}" for use in proposal.knowledge_applied)
                    if proposal.knowledge_applied
                    else "none reported"
                ),
            ]
        )
        if item["status"] == "not_applicable" or (
            item["status"] != "written_to_draft" and item.get("conditional") is not None
        ):
            continue
        if proposal.historical_basis is not None and isinstance(
            proposal.historical_basis.prior_question, HistoricalContextCitation
        ):
            receipt = next(
                (
                    c
                    for c in review.historical_context_checks
                    if c.context_citation == proposal.historical_basis.prior_question
                ),
                None,
            )
            summary.append(
                "Question/answer association: localized OCR and independent image reading, "
                "with source/render hashes and normalized question/answer/role boxes; "
                "not human approval or current role confirmation."
            )
            if receipt is not None:
                extraction_details = item.get("historical_extraction_discrepancies", [])
                if isinstance(extraction_details, list):
                    for discrepancy in extraction_details:
                        summary.append(
                            "EXTRACTION DISCREPANCY - ORIGINAL READINGS "
                            "(see final disposition): " + json.dumps(discrepancy)
                        )
                summary.append(
                    "Image-proposed association regions (0-1000, full image, top-left; "
                    "also checked against local text geometry): " + receipt.field.model_dump_json()
                )
        if proposal.historical_basis is not None:
            summary.extend(
                historical_review_concerns(requirements[proposal.requirement_id], proposal)
            )
            basis = proposal.historical_basis
            status = (
                "HISTORICAL - CONTINUITY UNCONFIRMED"
                if item["evidence_status"] == "historical_continuity_unconfirmed"
                else str(item["evidence_status"]).upper()
            )
            summary.extend(
                [
                    f"HISTORICAL BASIS: {status}; not human approval.",
                    f"Context: {basis.context}; category={basis.category}; "
                    f"role={basis.role or 'none'}",
                    f"Prior question/context: {basis.prior_question.quote}",
                    f"REVIEWER MUST CONFIRM: {basis.reviewer_confirmation}",
                    "Historical originals are internal only and are NOT appended to the packet.",
                ]
            )
            if basis.tenure is not None:
                summary.append(
                    f"DERIVED TENURE: prior={basis.tenure.prior_value}; "
                    f"signed={basis.tenure.signed_on}; calculated as of="
                    f"{request.calculation_date}; completed calendar anniversaries "
                    "(February 29 anniversaries use February 28 in non-leap years). "
                    f"Signing metadata provenance: {basis.tenure.model_dump_json()}. "
                    "Not a verified founding/hire date or confirmation of continuity."
                )
            for entry in request.historical_archive.entries if request.historical_archive else ():
                if any(
                    sources.get(c.source_id) and sources[c.source_id].path == entry.path
                    for c in proposal.citations
                ):
                    summary.append(
                        f"Prior issuer: {entry.issuer}; packet date: "
                        f"{str(entry.completed_on) if entry.completed_on else 'unknown'}; "
                        f"source: {entry.path}; sha256={entry.sha256}"
                    )
            if not basis.current_checks:
                summary.append("Current corroboration: no cited current-source checks.")
            for current_check in basis.current_checks:
                checked = sources.get(current_check.citation.source_id)
                summary.append(
                    f"Current check (model assessment, not proof): {current_check.finding}; "
                    f"{checked.path if checked else 'UNRESOLVED SOURCE'}; "
                    f"sha256={checked.sha256 if checked else 'unknown'}; "
                    f"page {current_check.citation.page}; {current_check.explanation}"
                )
        for citation in proposal.citations:
            source = sources.get(citation.source_id)
            summary.append(
                f"Evidence: {source.path if source else 'UNRESOLVED SOURCE'}; "
                f"sha256={source.sha256 if source else citation.source_id}; "
                f"source page {citation.page}"
            )
            if isinstance(citation, OcrCitation):
                summary.append(
                    f"OCR quote: {citation.quote}; artifact {citation.artifact_path}; "
                    f"word range [{citation.word_start}, {citation.word_end}); "
                    "see draft.json for exact pixel bounds and render hash."
                )
        if any(isinstance(c, OcrCitation) for c in proposal.citations):
            confirmed_subject = (
                summary_decision.confirmed_source_subject if summary_decision else "(not confirmed)"
            )
            visual_confirmation = (
                summary_decision.ocr_visual_confirmed if summary_decision else False
            )
            summary.append(
                "OCR review: "
                f"source subject confirmed as {confirmed_subject}; "
                f"visual confirmation={visual_confirmation}."
            )
            if item.get("ocr_review_method") == "machine_cross_checked_draft_not_human_approval":
                summary.append(
                    "Machine evidence processing: see localized receipt and any extraction "
                    "discrepancies above; agreement must not be presumed. "
                    "not human visual approval or proof of semantic support. "
                    "See answer_review.json for subject, period, prompt/model and transcript."
                )
    summary.extend(
        [
            "",
            "Detailed checks, quotations and output hashes: see draft.json.",
            "Prior-packet comparison and signer-specific copies: not performed.",
        ]
    )
    return "\n".join(summary) + "\n"


def supporting_document_summary(
    unresolved_support: Sequence[_PlanSupport],
    inventory: Inventory,
    selected_source_ids: Sequence[str],
    unassessed: int,
    inspection_readings: Mapping[str, Sequence[Mapping[str, object]]],
) -> str:
    support_summary = [
        "\nSUPPORTING-DOCUMENT REVIEW:",
        f"Selected supporting sources: {len(selected_source_ids)}.",
    ]
    support_summary.append(
        "Attachment version dates are ordering metadata, not capture/publication or "
        "reporting dates. PDF creation time may reflect re-exporting older material."
    )
    for selected_source in inventory.sources:
        if selected_source.source_id in selected_source_ids:
            selected_version = (
                selected_source.version_timestamp or selected_source.version_date or "unknown"
            )
            support_summary.append(
                f"- {selected_source.family} source_id={selected_source.source_id[:12]}: "
                f"version={selected_version}; "
                f"basis={selected_source.version_date_basis or 'unknown'}; "
                f"filename date={selected_source.filename_date or 'unknown'}."
            )
    if unresolved_support:
        support_summary.append("Items requiring follow-up:")
        sources = {s.source_id: s for s in inventory.sources}
        for item in unresolved_support:
            support_summary.append(
                f"- {item.family} ({', '.join(item.requirement_ids)}): {item.reason} "
                f"Limitation: {item.limitation}"
            )
            source = sources.get(item.source_id or "")
            if item.disposition == "review_required" and source is not None:
                inspections = inspection_readings[source.source_id]
                outcomes = [
                    f"page {reading['page']}: {reading['status']}"
                    for reading in inspections
                    if reading["source_id"] == source.source_id
                ]
                version = source.version_timestamp or source.version_date or "unknown"
                support_summary.extend(
                    [
                        f"  Source: {source.path}; source_id={source.source_id}; "
                        f"sha256={source.sha256}; "
                        f"inspected pages={list(item.inspected_pages)}; "
                        f"version={version}; "
                        f"basis={source.version_date_basis or 'unknown'}.",
                        "  Visual inspection: " + ("; ".join(outcomes) or "not performed") + ".",
                        "  Reviewer question: Should this document be included for the "
                        "linked requirement(s)? Inspect the source page(s) and choose "
                        "Include / Exclude / Leave unresolved. Attachment inclusion does "
                        "not verify its figures or approve an application answer.",
                    ]
                )
    if unassessed:
        support_summary.append(
            f"{unassessed} available source(s) have no recorded attachment decision."
        )
    support_summary.append("See attachment-manifest.json for the detailed audit.")
    return "\n".join(support_summary) + "\n"


def representative_bio_summary(resolutions: object, unreviewed_requirement_ids: object) -> str:
    return (
        "\nREPRESENTATIVE BIO IDENTITY LINKS (internal; selected bios are attached "
        "as supporting documents; not assignment or currency approval):\n"
        + json.dumps(
            {
                "resolutions": resolutions,
                "unreviewed_requirement_ids": unreviewed_requirement_ids,
            },
            indent=2,
        )
        + "\n"
    )


def representative_contact_summary(contacts: object) -> str:
    return (
        "\nREPRESENTATIVE TITLE AND CONTACT RECONCILIATION (internal; titles and "
        "contacts come from the attached bio; history and bio differences are listed "
        "for review; currency is not confirmed):\n" + json.dumps(contacts, indent=2) + "\n"
    )
