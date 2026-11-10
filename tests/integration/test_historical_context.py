import hashlib
import json
from contextlib import closing
from io import BytesIO
from pathlib import Path
from unittest.mock import Mock

import pypdfium2 as pdfium
import pytest
from pypdf import PdfReader
from reportlab.lib.utils import ImageReader
from reportlab.pdfgen.canvas import Canvas

from bd_packet_builder.contracts import HistoricalContextCitation, NarrativeValue, TextValue
from bd_packet_builder.draft import DraftRequest, DraftReview, publish_draft
from bd_packet_builder.evidence_tools import EvidenceLimits
from bd_packet_builder.foundry import FoundryConfig
from bd_packet_builder.gate import validate_answers
from bd_packet_builder.historical_context import HistoricalContextCheck
from bd_packet_builder.history import ArchiveEntry, ArchiveManifest
from bd_packet_builder.live import LiveRunRequest, prepare_live_run
from bd_packet_builder.scan import ScanTranscript
from tests.integration.test_agent import EVIDENCE_TEXT, Setup, blank_pdf
from tests.integration.test_historical_prefill import call

PRIOR = "bd_agreements/Completed/Broward/mixed.pdf"
NAME = "Avery Example"


def test_text_candidate_case_difference_does_not_invalidate_checked_association(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from bd_packet_builder.contracts import AnswerProposal, HistoricalBasis

    setup, tools, _, prior, _ = setup_page(tmp_path, monkeypatch)
    call(tools, "read_historical_page", {"source_id": prior["source_id"], "page": 1})
    call(tools, "finish_evidence")
    receipt = next(
        HistoricalContextCheck.model_validate_json(json.dumps(c))
        for c in json.loads(setup.artifact("historical_context_checks.json"))["checks"]
        if c["field"]["role"]["text"] == "Primary representative"
    )
    citation = receipt.answer.model_copy(update={"quote": receipt.answer.quote.upper()})
    checked = receipt.model_copy(update={"answer": citation})
    proposal = AnswerProposal(
        requirement_id="email",
        outcome="proposed",
        value=TextValue(kind="text", value=NAME),
        citations=(citation,),
        confidence=0.9,
        historical_basis=HistoricalBasis(
            category="contact",
            context="firm_wide",
            prior_question=checked.context_citation,
            role=None,
            current_checks=(),
            reviewer_confirmation="Confirm current email.",
        ),
    )
    assert checked.supports(proposal)


@pytest.mark.parametrize("change", ["none", "extra_claim", "different_role", "missing_receipt"])
def test_composed_printed_identity_requires_exact_same_role_parts(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    change: str,
) -> None:
    from bd_packet_builder.contracts import (
        AnswerProposal,
        HistoricalBasis,
        HistoricalCorrespondence,
    )
    from bd_packet_builder.draft import verify_historical_context
    from bd_packet_builder.history import with_historical_sources
    from bd_packet_builder.inventory import build_inventory

    setup, tools, _, prior, _ = setup_page(
        tmp_path,
        monkeypatch,
        secondary_question="Title",
        secondary_answer="Managing Director",
        secondary_role="Backup representative"
        if change == "different_role"
        else "Primary representative",
    )
    call(tools, "read_historical_page", {"source_id": prior["source_id"], "page": 1})
    call(tools, "finish_evidence")
    checks = tuple(
        HistoricalContextCheck.model_validate_json(json.dumps(c))
        for c in json.loads(setup.artifact("historical_context_checks.json"))["checks"]
    )
    assert len(checks) == 2
    proposal = AnswerProposal(
        requirement_id="printed_identity",
        outcome="proposed",
        confidence=0.9,
        value=TextValue(
            kind="text",
            value=NAME
            + "; Managing Director"
            + ("; authorized signer" if change == "extra_claim" else ""),
        ),
        citations=tuple(c.answer for c in checks),
        historical_basis=HistoricalBasis(
            category="contact",
            context="firm_wide",
            role="Primary representative",
            prior_question=checks[0].context_citation,
            additional_contexts=(checks[1].context_citation,),
            current_checks=(),
            reviewer_confirmation="Printed identity only; confirm assignment.",
            correspondence=HistoricalCorrespondence(
                target_question="Printed Name & Title",
                assessment="uncertain",
                differences="Separate prior name and title fields; combined target field.",
                reason="Same representative's printed identity, not signing authority.",
            ),
        ),
    )
    inventory = with_historical_sources(
        setup.evidence_root,
        build_inventory(setup.evidence_root),
        setup.store.load(setup.manifest.run_id).request.historical_archive,
    )
    issues, snapshots = verify_historical_context(
        setup.evidence_root,
        inventory,
        proposal,
        checks[:1] if change == "missing_receipt" else checks,
        {},
    )
    assert (not issues and bool(snapshots)) == (change == "none")


@pytest.mark.parametrize(
    "change",
    [
        "none",
        "pointer_as_answer_fragment",
        "not_a_pointer",
        "different_question",
        "different_role",
        "missing_receipt",
        "link_repeats_answer",
        "omitted_pointer_number",
        "omitted_answer_number",
        "number_punctuation",
        "conflicting_numbers",
        "changed_condition",
        "forged_link_hash",
        "native_truncated_heading",
        "native_truncated_midword",
        "native_truncated_wrong_partial",
        "native_punctuation_transposed",
        "native_punctuation_decorated",
        "image_only_punctuation_transposed",
        "image_only_truncated_heading",
    ],
)
def test_supplement_pointer_is_a_question_link_not_answer_text(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    change: str,
) -> None:
    from bd_packet_builder.contracts import (
        AnswerProposal,
        HistoricalBasis,
        HistoricalCorrespondence,
    )
    from bd_packet_builder.draft import historical_answer_citations, verify_historical_context
    from bd_packet_builder.history import with_historical_sources
    from bd_packet_builder.inventory import build_inventory

    setup, tools, _, prior, _ = setup_page(
        tmp_path,
        monkeypatch,
        primary_answer="Blair Example" if change == "not_a_pointer" else "See supplement",
        historical_policy="answer_first_review",
        native_questions=change
        in (
            "native_truncated_heading",
            "native_truncated_midword",
            "native_truncated_wrong_partial",
            "native_punctuation_transposed",
            "native_punctuation_decorated",
        ),
        primary_question="3. Name"
        if change in ("omitted_answer_number", "number_punctuation", "conflicting_numbers")
        else "Name if authorized"
        if change
        in (
            "native_truncated_heading",
            "native_truncated_midword",
            "native_truncated_wrong_partial",
            "image_only_truncated_heading",
            "image_only_punctuation_transposed",
            "native_punctuation_transposed",
            "native_punctuation_decorated",
        )
        else "Name",
        secondary_question={
            "different_question": "Title",
            "omitted_pointer_number": "3: Name",
            "number_punctuation": "3: NAME",
            "conflicting_numbers": "4. Name",
            "changed_condition": "Name if authorized",
            "native_truncated_heading": "Name-:",
            "native_truncated_midword": "Na-:",
            "native_truncated_wrong_partial": "Nx-:",
            "native_punctuation_transposed": "Name-:",
            "native_punctuation_decorated": "Name-:",
            "image_only_punctuation_transposed": "Name-:",
            "image_only_truncated_heading": "Name-:",
        }.get(change, "Name"),
        secondary_image_question=(
            "Name:-"
            if change in ("native_punctuation_transposed", "image_only_punctuation_transposed")
            else "Name?!:-"
            if change == "native_punctuation_decorated"
            else None
        ),
        secondary_role="Backup representative"
        if change == "different_role"
        else "Primary representative",
    )
    if change in (
        "omitted_pointer_number",
        "omitted_answer_number",
        "number_punctuation",
        "conflicting_numbers",
        "changed_condition",
        "native_truncated_heading",
        "native_truncated_midword",
        "native_truncated_wrong_partial",
        "native_punctuation_transposed",
        "native_punctuation_decorated",
        "image_only_punctuation_transposed",
        "image_only_truncated_heading",
    ):
        from bd_packet_builder import ocr

        execute = ocr._execute

        def word_level_ocr(command, *args):
            result = execute(command, *args)
            if "--version" in command:
                return result
            rows = result.splitlines()
            separated = [rows[0]]
            for row in rows[1:]:
                columns = row.split("\t")
                tokens = columns[-1].split()
                width = int(columns[8]) // len(tokens)
                for offset, token in enumerate(tokens):
                    word = columns.copy()
                    word[6] = str(int(columns[6]) + offset * width)
                    word[8] = str(width)
                    word[-1] = token
                    separated.append("\t".join(word))
            return "\n".join(separated) + "\n"

        monkeypatch.setattr(ocr, "_execute", word_level_ocr)
    call(tools, "read_historical_page", {"source_id": prior["source_id"], "page": 1})
    call(tools, "finish_evidence")
    checks = tuple(
        HistoricalContextCheck.model_validate_json(json.dumps(c))
        for c in json.loads(setup.artifact("historical_context_checks.json"))["checks"]
    )
    assert len(checks) == 2
    pointer, answer = checks
    links = (
        (answer.context_citation,)
        if change == "link_repeats_answer"
        else ()
        if change == "pointer_as_answer_fragment"
        else (pointer.context_citation,)
    )
    if change == "forged_link_hash":
        links = (pointer.context_citation.model_copy(update={"check_sha256": "0" * 64}),)
    proposal = AnswerProposal(
        requirement_id="references",
        outcome="proposed",
        confidence=0.9,
        value=TextValue(kind="text", value="Blair Example"),
        citations=(answer.answer,),
        historical_basis=HistoricalBasis(
            category="reference",
            context="issuer_specific",
            role="Backup representative"
            if change == "different_role"
            else "Primary representative",
            prior_question=answer.context_citation,
            additional_contexts=(
                (pointer.context_citation,) if change == "pointer_as_answer_fragment" else ()
            ),
            question_links=links,
            current_checks=(),
            reviewer_confirmation="Confirm the references are current.",
            correspondence=HistoricalCorrespondence(
                target_question="References",
                assessment="applicable",
                differences="The prior main form pointed to its supplemental answer.",
                reason="Same issuer question answered on the supplement.",
            ),
        ),
    )
    inventory = with_historical_sources(
        setup.evidence_root,
        build_inventory(setup.evidence_root),
        setup.store.load(setup.manifest.run_id).request.historical_archive,
    )
    issues, snapshots = verify_historical_context(
        setup.evidence_root,
        inventory,
        proposal,
        (answer,) if change == "missing_receipt" else checks,
        {},
        allow_disagreements=change
        in (
            "native_punctuation_transposed",
            "native_punctuation_decorated",
            "image_only_punctuation_transposed",
        ),
    )
    accepted = change in (
        "none",
        "omitted_pointer_number",
        "omitted_answer_number",
        "number_punctuation",
        "native_truncated_heading",
        "native_truncated_midword",
        "native_punctuation_transposed",
        "native_punctuation_decorated",
    )
    assert (not issues and bool(snapshots)) == accepted
    if accepted:
        # The pointer is navigation only; it never becomes answer evidence.
        answer_citations = historical_answer_citations(proposal, snapshots)
        assert answer_citations
        assert all(c.quote != "See supplement" for c in answer_citations)
    else:
        assert issues == (
            {
                "pointer_as_answer_fragment": "historical_composition_has_unsupported_text",
                "not_a_pointer": "historical_question_link_not_a_pointer",
                "different_question": "historical_question_link_question_mismatch",
                "different_role": "historical_question_link_context_mismatch",
                "missing_receipt": "historical_question_link_receipt_missing",
                "link_repeats_answer": "historical_question_link_repeats_answer",
                "conflicting_numbers": "historical_question_link_question_mismatch",
                "changed_condition": "historical_question_link_question_mismatch",
                "forged_link_hash": "historical_question_link_receipt_missing",
                "image_only_truncated_heading": "historical_question_link_question_mismatch",
                "native_truncated_wrong_partial": "historical_question_link_question_mismatch",
                "image_only_punctuation_transposed": "historical_question_link_question_mismatch",
            }[change],
        )
    if change in (
        "omitted_pointer_number",
        "omitted_answer_number",
        "number_punctuation",
        "conflicting_numbers",
        "changed_condition",
        "native_punctuation_transposed",
        "native_punctuation_decorated",
    ):
        if change.startswith("native_punctuation"):
            handoff = json.loads(setup.artifact("answer_handoff.json"))
            association = next(
                c
                for c in handoff["historical_candidates"]
                if c["context_citation"]["check_sha256"] == answer.context_citation.check_sha256
            )
            assert association["discrepancies"][0]["code"] == (
                "historical_question_presentation_resolved"
            )
            assert answer.discrepancies[0].code == "historical_text_or_region_disagrees"
        target = next(
            r
            for r in json.loads(setup.artifact("form_interpretation.json"))["requirements"][
                "requirements"
            ]
            if r["requirement_id"] == "p1.name"
        )
        staged = proposal.model_copy(
            update={
                "requirement_id": "p1.name",
                "historical_basis": proposal.historical_basis.model_copy(
                    update={
                        "category": "contact",
                        "context": "firm_wide",
                        "role": None,
                        "correspondence": proposal.historical_basis.correspondence.model_copy(
                            update={"target_question": target["instruction"]}
                        ),
                    }
                ),
            }
        )
        call(tools, "submit_answers", {"proposals": [staged.model_dump(mode="json")]})
        decision = next(
            d
            for d in json.loads(setup.artifact("answer_review.json"))["decisions"]
            if d["requirement_id"] == "p1.name"
        )
        assert (decision["decision"] == "draft_verified") == accepted, decision["reason"]
        call(tools, "assemble_packet")
        call(tools, "publish_results")
        report = json.loads(setup.artifact("draft.json"))
        assert ("p1.name" in report["written_requirements"]) == accepted
        packet_text = PdfReader(BytesIO(setup.artifact("packet.pdf"))).pages[0].extract_text()
        assert ("Blair Example" in packet_text) == accepted
        assert "See supplement" not in packet_text
        assert report["render_checks"]["outside_allowed_regions_changed_pixels"] == 0
        if accepted:
            summary = setup.artifact("reviewer-summary.txt").decode()
            assert "HISTORICAL - CONTINUITY UNCONFIRMED" in summary
            if change.startswith("native_punctuation"):
                assert "QUESTION PRESENTATION RESOLVED" in summary
                assert "Neither reading is preferred" not in summary
        if change == "conflicting_numbers":
            request = DraftRequest.model_validate_json(setup.artifact("draft_request.json"))
            review = DraftReview.model_validate_json(setup.artifact("answer_review.json"))
            forced = review.model_copy(
                update={
                    "decisions": tuple(
                        d.model_copy(update={"decision": "draft_verified"})
                        if d.requirement_id == "p1.name"
                        else d
                        for d in review.decisions
                    )
                }
            )
            blank = setup.evidence_root / request.source
            blank.parent.mkdir(parents=True, exist_ok=True)
            blank.write_bytes(setup.blank)
            request_path = Path("outputs/forged-link-review-request.json")
            raw = setup.artifact("draft_request.json")
            (setup.evidence_root / request_path).write_bytes(raw)
            output = publish_draft(
                setup.evidence_root,
                request_path,
                raw,
                request,
                forced,
                forced.model_dump_json().encode(),
                None,
            )
            assert (
                "Blair Example"
                not in PdfReader(output / "draft-packet.pdf").pages[0].extract_text()
            )
            assert (
                "p1.name"
                not in json.loads((output / "draft.json").read_bytes())["written_requirements"]
            )


@pytest.mark.parametrize("change", ["none", "invented_anchor", "conflicting_dates", "discrepancy"])
def test_native_tenure_with_image_date_requires_independently_rechecked_signing_metadata(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    change: str,
) -> None:
    from datetime import date

    from bd_packet_builder.contracts import (
        AnswerProposal,
        Citation,
        HistoricalBasis,
        HistoricalTenure,
    )
    from bd_packet_builder.draft import verify_historical_context
    from bd_packet_builder.history import with_historical_sources
    from bd_packet_builder.inventory import build_inventory

    setup, tools, reader, prior, _ = setup_page(
        tmp_path,
        monkeypatch,
        primary_question="Date",
        primary_answer="2024-11-02",
        primary_role="Primary representative"
        if change == "invented_anchor"
        else "Signature section",
        secondary_question="Date" if change == "conflicting_dates" else "Name",
        secondary_answer="November 2, 2025" if change == "conflicting_dates" else "Blair Example",
    )
    reader.transcribe.return_value = reader.transcribe.return_value.model_copy(
        update={
            "text": "Signature section\nDate 2024-11-02",
        }
    )
    call(tools, "read_historical_page", {"source_id": prior["source_id"], "page": 1})
    call(tools, "finish_evidence")
    checks = tuple(
        HistoricalContextCheck.model_validate_json(json.dumps(c))
        for c in json.loads(setup.artifact("historical_context_checks.json"))["checks"]
    )
    date_check = next(c for c in checks if c.field.answer.text == "2024-11-02")
    if change == "discrepancy":
        from bd_packet_builder.historical_context import ExtractionDiscrepancy

        date_check = date_check.model_copy(
            update={
                "discrepancies": (
                    ExtractionDiscrepancy(
                        code="historical_text_or_region_disagrees",
                        part="answer",
                        image_reading="2024-11-02",
                        ocr_reading="2024-11-03",
                        selection_reason="Synthetic date uncertainty; not a verified baseline.",
                    ),
                ),
            }
        )
        checks = (date_check,) + tuple(c for c in checks if c.field.answer.text != "2024-11-02")
    assert isinstance(date_check.answer, Citation)
    # Native tenure context and image date context deliberately take different verification paths.
    proposal = AnswerProposal(
        requirement_id="years",
        outcome="proposed",
        value=TextValue(kind="text", value="28"),
        citations=(date_check.answer,),
        confidence=0.9,
        historical_basis=HistoricalBasis(
            category="tenure",
            context="firm_wide",
            prior_question=date_check.answer,
            current_checks=(),
            reviewer_confirmation="Confirm operating continuity.",
            tenure=HistoricalTenure(
                prior_value="26",
                signed_on=date(2024, 11, 2),
                date_citation=date_check.answer,
                date_context=date_check.context_citation,
            ),
        ),
    )
    inventory = with_historical_sources(
        setup.evidence_root,
        build_inventory(setup.evidence_root),
        setup.store.load(setup.manifest.run_id).request.historical_archive,
    )
    issues, snapshots = verify_historical_context(
        setup.evidence_root,
        inventory,
        proposal,
        checks,
        {},
    )
    assert (not issues and bool(snapshots)) == (change == "none")


@pytest.mark.parametrize(
    ("ocr_question", "image_question", "resolved"),
    [
        ("Name-:", "Name:-", True),
        ("Name:", "Name?!", True),
        ("3. Name:", "Name?", True),
        ("Name:", "(3) Name?", True),
        ("Name:", "NAME;", True),
        ("Name:", "Name if authorized", False),
        ("3. Name", "4. Name", False),
        ("Capital $10.5 million", "Capital $105 million", False),
        ("Rule 15c3-1", "Rule 15c31", False),
        ("Value -5", "Value 5", False),
    ],
)
def test_question_presentation_is_resolved_in_handoff_without_changing_receipts(
    tmp_path, monkeypatch, ocr_question, image_question, resolved
):
    setup, tools, reader, prior, _ = setup_page(
        tmp_path,
        monkeypatch,
        secondary_question=ocr_question,
        secondary_image_question=image_question,
        historical_policy="answer_first_review",
    )
    reading = call(tools, "read_historical_page", {"source_id": prior["source_id"], "page": 1})
    candidate = reading["associations"][1]
    call(tools, "finish_evidence")
    checks = json.loads(setup.artifact("historical_context_checks.json"))["checks"]
    # Receipts retain original evidence; resolution is derived for the answering handoff.
    matching = next(c for c in checks if c["field"]["question"]["text"] == image_question)
    if matching["discrepancies"]:
        assert matching["discrepancies"][0]["code"] == "historical_text_or_region_disagrees"
    differences = candidate["discrepancies"]
    if differences:
        assert (differences[0]["code"] == "historical_question_presentation_resolved") == resolved
    handoff = json.loads(setup.artifact("answer_handoff.json"))
    assert handoff["historical_candidates"][1] == candidate
    assert reader.transcribe.call_count == 1


@pytest.mark.parametrize("image_question", ["Name:-", "(3) Name?!", "NAME;"])
def test_selected_control_presentation_does_not_spend_a_focused_reread(
    tmp_path, monkeypatch, image_question
):
    setup, tools, reader, prior, current = setup_page(
        tmp_path,
        monkeypatch,
        primary_question="Name-:",
        primary_image_question=image_question,
        control_state="selected",
        historical_policy="answer_first_review",
    )
    request, review = validated_page(setup, tools, prior, current)
    assert review.decisions[0].decision == "draft_verified", review.decisions[0].reason
    assert reader.transcribe.call_count == 1
    handoff = json.loads(setup.artifact("answer_handoff.json"))
    assert handoff["historical_candidates"][0]["printed_resolutions"] == []
    assert any(
        d["code"] == "historical_question_presentation_resolved"
        for d in handoff["historical_candidates"][0]["discrepancies"]
    )


def box(left: int, top: int, right: int, bottom: int) -> dict:
    return dict(left=left, top=top, right=right, bottom=bottom)


def setup_page(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    *,
    swapped: bool = False,
    scanned_answer: bool = False,
    confidence: int = 96,
    evidence_limits: EvidenceLimits | None = None,
    right_column: bool = False,
    competing_header: bool = False,
    repeated_answer: bool = False,
    question_prefix: str = "",
    primary_question: str = "Name",
    primary_image_question: str | None = None,
    primary_answer: str = NAME,
    control_state: str | None = None,
    second_control: bool = False,
    subheader: bool = False,
    historical_policy: str = "conservative",
    control_on_right: bool = False,
    secondary_role: str = "Backup representative",
    secondary_question: str = "Name",
    secondary_image_question: str | None = None,
    secondary_answer: str = "Blair Example",
    primary_role: str = "Primary representative",
    evidence_text: str = EVIDENCE_TEXT,
    scanned_current: bool = False,
    primary_write_in: str | None = None,
    primary_x_offset: int = 0,
    unboxed_control: bool = False,
    check_rise: int = 21,
    native_questions: bool = False,
    draft_schema_version: int = 1,
    primary_ocr_answer: str | None = None,
    primary_ocr_confidence: int = 96,
    primary_image_answer: str | None = None,
):
    setup = Setup(tmp_path, blank_pdf(), evidence_text=evidence_text, scanned=scanned_current)
    target = setup.evidence_root / PRIOR
    target.parent.mkdir(parents=True)
    background = BytesIO()
    canvas = Canvas(background, pagesize=(600, 800), invariant=True)
    canvas.drawString(40 + primary_x_offset, 740, primary_role)
    if competing_header:
        canvas.drawString(330, 740, "Desk manager")
    canvas.drawString(
        (400 if right_column else 40) + primary_x_offset,
        770 if subheader else 710,
        question_prefix + primary_question,
    )
    canvas.drawString(40, 600, secondary_role)
    canvas.drawString(40, 570, secondary_question)
    if control_state is not None:
        x = (294 if control_on_right else 158) + primary_x_offset
        if not unboxed_control:
            canvas.rect(x, 708, 12, 12)
        if control_state == "selected":
            if unboxed_control:
                canvas.setLineWidth(2)
                canvas.line(x, 715, x + 5, 709)
                canvas.line(x + 5, 709, x + 17, 709 + check_rise)
                canvas.setLineWidth(1)
            else:
                canvas.line(x + 2, 710, x + 10, 718)
                canvas.line(x + 2, 718, x + 10, 710)
    if second_control:
        canvas.rect(278, 708, 12, 12)
        canvas.line(280, 710, 288, 718)
        canvas.line(280, 718, 288, 710)
    if scanned_answer:
        for index, line in enumerate(primary_answer.splitlines()):
            canvas.drawString(
                (470 if right_column else 180) + primary_x_offset, 710 - index * 12, line
            )
        canvas.drawString(180, 570, NAME if repeated_answer else secondary_answer)
    canvas.save()
    with (
        pdfium.PdfDocument(background.getvalue()) as document,
        closing(document[0]) as page,
        closing(page.render(scale=2)) as bitmap,
        closing(bitmap.to_pil()) as image,
    ):
        canvas = Canvas(str(target), pagesize=(600, 800), invariant=True)
        canvas.drawImage(ImageReader(image), 0, 0, 600, 800)
        if native_questions:
            canvas.drawString(40, 710, primary_question)
            canvas.drawString(40, 570, secondary_question)
        if primary_write_in is not None:
            for index, line in enumerate(primary_write_in.splitlines()):
                canvas.drawString(240 + primary_x_offset, 710 - index * 12, line)
        if not scanned_answer:
            for index, line in enumerate(primary_answer.splitlines()):
                canvas.drawString(470 if right_column else 180, 710 - index * 12, line)
            if second_control:
                canvas.drawString(300, 710, "No")
            canvas.drawString(180, 570, NAME if repeated_answer else secondary_answer)
        canvas.save()
    manifest = ArchiveManifest(
        entries=(
            ArchiveEntry(
                path=PRIOR,
                sha256=hashlib.sha256(target.read_bytes()).hexdigest(),
                partition="reference",
                issuer="Broward",
            ),
        )
    )
    setup.manifest = prepare_live_run(
        setup.store,
        LiveRunRequest(
            blank_name="Form.pdf",
            requester_id="offline",
            evidence_set_id="historical-mixed",
            issuer="Broward",
            historical_archive=manifest,
            historical_policy=historical_policy,
        ),
        setup.blank,
        setup.evidence_root,
        FoundryConfig(endpoint="https://example.openai.azure.com/openai/v1", deployment="test"),
    )
    fields = [
        {
            "question": {
                "text": (
                    question_prefix + " " + primary_question
                    if question_prefix
                    else primary_image_question or primary_question
                ),
                "box": box(60, 95, 140, 120),
            },
            "role": {"text": primary_role, "box": box(60, 55, 350, 80)},
            "answer": {
                "text": primary_image_answer or primary_answer,
                "box": box(
                    290, 95, 480, 120 + 15 * ((primary_image_answer or primary_answer).count("\n"))
                ),
            },
        },
        {
            "question": {
                "text": secondary_image_question or secondary_question,
                "box": box(60, 270, 140, 295),
            },
            "role": {"text": secondary_role, "box": box(60, 230, 350, 255)},
            "answer": {
                "text": NAME if repeated_answer else secondary_answer,
                "box": box(290, 270, 480, 295),
            },
        },
    ]
    if control_state is not None:
        fields[0]["control"] = {
            "box": box(490, 100, 511, 115) if control_on_right else box(263, 100, 284, 115),
            "state": control_state,
        }
    if primary_x_offset:
        for part in fields[0].values():
            if part is not None:
                part["box"]["left"] += primary_x_offset * 1000 // 600
                part["box"]["right"] += primary_x_offset * 1000 // 600
    if subheader:
        fields[0]["question"]["box"] = box(60, 15, 140, 45)
    if swapped:
        fields[0]["answer"] = fields[1]["answer"]
    if right_column:
        fields[0]["question"]["box"] = box(660, 95, 750, 120)
        fields[0]["answer"]["box"] = box(
            780, 95, 960, 120 + 15 * ((primary_image_answer or primary_answer).count("\n"))
        )
    if competing_header:
        fields.append(
            {
                "question": fields[0]["question"],
                "answer": fields[0]["answer"],
                "role": {"text": "Desk manager", "box": box(550, 55, 780, 80)},
            }
        )
    if second_control:
        second = json.loads(json.dumps(fields[0]))
        second["answer"] = {"text": "No", "box": box(490, 95, 550, 120)}
        second["control"] = {"box": box(463, 100, 484, 115), "state": "selected"}
        fields.insert(1, second)
    reader = Mock()
    reader.transcribe.return_value = ScanTranscript.model_validate_json(
        json.dumps(
            {
                "readable": True,
                "subject": None,
                "text": "",
                "reporting_period": None,
                "historical_fields": fields,
            }
        )
    )
    monkeypatch.setattr("bd_packet_builder.ocr.shutil.which", lambda _: "/local/tesseract")
    words = [
        (primary_role.split()[0], 180, 170),
        (primary_role.split()[1], 430, 170),
        (
            question_prefix + primary_question,
            1667 if right_column else 180,
            80 if subheader else 330,
        ),
        ("Avery", 1960 if right_column else 760, 330),
        ("Example", 2180 if right_column else 980, 330),
        (secondary_role.split()[0], 180, 760),
        (secondary_role.split()[1], 430, 760),
        (secondary_question, 180, 915),
        ("Avery" if repeated_answer else secondary_answer.split()[0], 760, 915),
        ("Example" if repeated_answer else secondary_answer.split()[1], 980, 915),
    ]
    if primary_ocr_answer is not None:
        words[3:5] = [
            (word, (1960 if right_column else 760) + 140 * i, 330 + 50 * line_index)
            for line_index, line in enumerate(primary_ocr_answer.splitlines())
            for i, word in enumerate(line.split())
        ]
    if competing_header:
        words[2:2] = [("Desk", 1375, 170), ("manager", 1600, 170)]
    if primary_x_offset:
        words[:5] = [(text, x + primary_x_offset * 2500 // 600, y) for text, x, y in words[:5]]
    header = (
        "level\tpage_num\tblock_num\tpar_num\tline_num\tword_num\t"
        "left\ttop\twidth\theight\tconf\ttext\n"
    )

    def word_confidence(text, x, y):
        if primary_ocr_answer is not None and y == 330 and x >= 760:
            return primary_ocr_confidence
        return 89 if repeated_answer and text in ("Avery", "Example") else confidence

    tsv = header + "".join(
        f"5\t1\t1\t1\t{i + 1}\t1\t{x}\t{y}\t180\t40\t{word_confidence(text, x, y)}\t{text}\n"
        for i, (text, x, y) in enumerate(words)
    )
    monkeypatch.setattr(
        "bd_packet_builder.ocr._execute",
        lambda command, *_: "tesseract 5.5.0\n" if "--version" in command else tsv,
    )
    tools = setup.tools(
        scan_reader=reader,
        evidence_limits=evidence_limits,
        draft_schema_version=draft_schema_version,
    )
    call(tools, "interpret_form")
    sources = call(tools, "list_sources")["sources"]
    prior = next(s for s in sources if s["family"] == "historical_reference")
    current = next(s for s in sources if s["family"] != "historical_reference")
    return setup, tools, reader, prior, current


def test_mixed_page_relationship_survives_gate_writer_and_private_archive(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    setup, tools, reader, prior, current = setup_page(tmp_path, monkeypatch)
    result = call(tools, "read_historical_page", {"source_id": prior["source_id"], "page": 1})
    assert len(result["associations"]) == 2
    first, second = result["associations"]
    assert first["answer_citation"]["quote"] == NAME
    assert second["answer_citation"]["quote"] == "Blair Example"
    assert first["context_citation"]["quote"] == "Primary representative\nName"
    assert first["context_citation"] != second["context_citation"]
    HistoricalContextCitation.model_validate_json(json.dumps(first["context_citation"]))
    # Repeated access must reuse the blind read and OCR, not spend additional remote calls.
    assert (
        call(tools, "read_historical_page", {"source_id": prior["source_id"], "page": 1}) == result
    )
    assert reader.transcribe.call_count == 1
    assert len(reader.transcribe.call_args.args) == 1
    assert isinstance(reader.transcribe.call_args.args[0], bytes)
    quote = "Firm legal name: Insperex Fictional Securities LLC"
    current_check = call(
        tools,
        "locate_quote",
        {
            "source_id": current["source_id"],
            "page": 1,
            "quote": quote,
        },
    )
    current_check.pop("occurrences")
    proposal = {
        "requirement_id": "p1.name",
        "outcome": "proposed",
        "confidence": 0.9,
        "value": {"kind": "text", "value": NAME},
        "citations": [first["answer_citation"]],
        "historical_basis": {
            "category": "contact",
            "context": "issuer_specific",
            "prior_question": first["context_citation"],
            "role": "Primary representative",
            "current_checks": [
                {
                    "citation": current_check,
                    "finding": "not_corroborated",
                    "explanation": "Firm identity does not confirm the prior contact.",
                }
            ],
            "reviewer_confirmation": "Confirm the contact is unchanged.",
        },
    }
    call(tools, "finish_evidence")
    assert call(tools, "submit_answers", {"proposals": [proposal]})["answered"] == 1
    call(tools, "assemble_packet")
    call(tools, "publish_results")
    packet = PdfReader(BytesIO(setup.artifact("packet.pdf")))
    assert len(packet.pages) == 2
    current_pdf = PdfReader(setup.evidence_root / current["path"])
    assert (
        packet.pages[1].get_contents().get_data() == current_pdf.pages[0].get_contents().get_data()
    )
    assert NAME in packet.pages[0].extract_text()
    assert "Blair" not in packet.pages[0].extract_text()
    summary = setup.artifact("reviewer-summary.txt").decode()
    assert "HISTORICAL - CONTINUITY UNCONFIRMED" in summary
    assert "Primary representative" in summary
    assert "Question/answer association" in summary
    receipt = json.loads(setup.artifact("historical_context_checks.json"))
    assert len(receipt["checks"]) == 2
    assert receipt["checks"][0]["field"]["question"]["box"]["top"] == 95
    report = json.loads(setup.artifact("draft.json"))
    assert report["render_checks"]["outside_allowed_regions_changed_pixels"] == 0


def test_selected_control_can_follow_its_option_label(tmp_path, monkeypatch):
    _, tools, _, prior, _ = setup_page(
        tmp_path, monkeypatch, primary_answer="Yes", control_state="selected", control_on_right=True
    )
    result = call(tools, "read_historical_page", {"source_id": prior["source_id"], "page": 1})
    assert any(a["answer_citation"]["quote"] == "Yes" for a in result["associations"]), result[
        "issues"
    ]


def test_tall_check_stroke_stays_associated_with_its_label_line(tmp_path, monkeypatch):
    _, tools, reader, prior, _ = setup_page(
        tmp_path,
        monkeypatch,
        control_state="selected",
        unboxed_control=True,
        check_rise=34,
    )
    raw = json.loads(reader.transcribe.return_value.model_dump_json())
    raw["historical_fields"][0]["control"]["box"] = box(263, 80, 292, 115)
    reader.transcribe.return_value = ScanTranscript.model_validate_json(json.dumps(raw))
    result = call(tools, "read_historical_page", {"source_id": prior["source_id"], "page": 1})
    assert any(a["answer_citation"]["quote"] == NAME for a in result["associations"]), result[
        "issues"
    ]


@pytest.mark.parametrize(
    ("other_control", "accepted"),
    [((266, 90, 290, 104), True), ((286, 100, 298, 112), False)],
    ids=["same-column-neighbour", "between-mark-and-label"],
)
def test_only_controls_between_mark_and_label_intervene(
    tmp_path, monkeypatch, other_control, accepted
):
    _, tools, reader, prior, _ = setup_page(tmp_path, monkeypatch, control_state="selected")
    raw = json.loads(reader.transcribe.return_value.model_dump_json())
    raw["historical_fields"][1]["control"] = {"box": box(*other_control), "state": "unselected"}
    reader.transcribe.return_value = ScanTranscript.model_validate_json(json.dumps(raw))
    result = call(tools, "read_historical_page", {"source_id": prior["source_id"], "page": 1})
    assert any(a["answer_citation"]["quote"] == NAME for a in result["associations"]) == accepted
    assert (
        {"field_index": 0, "code": "historical_control_label_geometry_disagrees", "part": "control"}
        in result["issues"]
    ) != accepted, result["issues"]


def test_distant_trailing_control_cannot_skip_over_other_words(tmp_path, monkeypatch):
    _, tools, _, prior, _ = setup_page(
        tmp_path,
        monkeypatch,
        primary_answer="Yes",
        control_state="selected",
        control_on_right=True,
        primary_write_in="Other option",
    )
    result = call(tools, "read_historical_page", {"source_id": prior["source_id"], "page": 1})
    assert "Yes" not in [a["answer_citation"]["quote"] for a in result["associations"]]
    assert any(
        i["code"] == "historical_control_label_geometry_disagrees" for i in result["issues"]
    ), result["issues"]


@pytest.mark.parametrize("scanned_answer", [False, True])
@pytest.mark.parametrize("unboxed_control", [False, True])
@pytest.mark.parametrize(
    ("control_box", "label_left"),
    [
        ((263, 100, 284, 115), 290),
        ((263, 98, 292, 118), 266),
        ((262, 96, 290, 116), 270),
        ((264, 100, 283, 114), 250),
    ],
)
def test_control_label_relationship_uses_page_geometry_not_model_box_edges(
    tmp_path, monkeypatch, scanned_answer, unboxed_control, control_box, label_left
):
    _, tools, reader, prior, _ = setup_page(
        tmp_path,
        monkeypatch,
        control_state="selected",
        scanned_answer=scanned_answer,
        unboxed_control=unboxed_control,
    )
    raw = json.loads(reader.transcribe.return_value.model_dump_json())
    raw["historical_fields"][0]["control"]["box"] = box(*control_box)
    raw["historical_fields"][0]["answer"]["box"]["left"] = label_left
    reader.transcribe.return_value = ScanTranscript.model_validate_json(json.dumps(raw))
    result = call(tools, "read_historical_page", {"source_id": prior["source_id"], "page": 1})
    assert any(
        " ".join(a["answer_citation"]["quote"].split()) == NAME for a in result["associations"]
    ), result["issues"]
    assert not [i for i in result["issues"] if i["field_index"] == 0]


@pytest.mark.parametrize("allow", [False, True])
def test_mark_cannot_select_a_label_on_another_line(tmp_path, monkeypatch, allow):
    _, tools, reader, prior, _ = setup_page(
        tmp_path,
        monkeypatch,
        control_state="selected",
        historical_policy="answer_first_review" if allow else "conservative",
    )
    raw = json.loads(reader.transcribe.return_value.model_dump_json())
    field = raw["historical_fields"][0]
    field["answer"] = {"text": "Blair Example", "box": box(290, 140, 480, 300)}
    reader.transcribe.return_value = ScanTranscript.model_validate_json(json.dumps(raw))
    result = call(tools, "read_historical_page", {"source_id": prior["source_id"], "page": 1})
    assert not [
        a
        for a in result["associations"]
        if a["answer_citation"]["quote"] == "Blair Example"
        and " ".join(a["role"].split()) == "Primary representative"
    ]
    assert any(i["field_index"] == 0 for i in result["issues"]), result


def test_marks_cannot_be_reassigned_to_other_option_labels(tmp_path, monkeypatch):
    _, tools, reader, prior, _ = setup_page(
        tmp_path, monkeypatch, primary_answer="Yes", control_state="selected", second_control=True
    )
    raw = json.loads(reader.transcribe.return_value.model_dump_json())
    # The model assigns the first mark to the farther "No" label.
    raw["historical_fields"][1]["control"]["box"] = box(263, 100, 284, 115)
    raw["historical_fields"][0]["control"]["box"] = box(463, 100, 484, 115)
    reader.transcribe.return_value = ScanTranscript.model_validate_json(json.dumps(raw))
    result = call(tools, "read_historical_page", {"source_id": prior["source_id"], "page": 1})
    assert "No" not in [a["answer_citation"]["quote"] for a in result["associations"]]
    assert any(
        i["code"] == "historical_control_label_geometry_disagrees" for i in result["issues"]
    ), result["issues"]


@pytest.mark.parametrize("extra", ["e", "not", "100"])
def test_control_label_ignores_only_local_mark_or_bullet_noise(tmp_path, monkeypatch, extra):
    from bd_packet_builder import ocr

    _, tools, _, prior, _ = setup_page(
        tmp_path,
        monkeypatch,
        primary_question="Eligibility",
        primary_answer="Regional dealer complies",
        scanned_answer=True,
        control_state="selected",
        historical_policy="answer_first_review",
    )
    execute = ocr._execute

    def contaminated(command, *args):
        output = execute(command, *args)
        if "--version" in command:
            return output
        rows = output.splitlines()
        for i, row in enumerate(rows):
            columns = row.split("\t")
            if len(columns) != 12 or columns[7] != "330":
                continue
            if columns[-1] == "Avery":
                columns[-1] = "Regional"
            elif columns[-1] == "Example":
                columns[-1] = "dealer"
            rows[i] = "\t".join(columns)
        position = next(i for i, row in enumerate(rows) if row.endswith("\tdealer")) + 1
        rows[position:position] = [
            f"5\t1\t1\t1\t20\t1\t725\t370\t20\t20\t96\t{extra}",
            "5\t1\t1\t1\t20\t2\t1050\t370\t150\t20\t96\tcomplies",
        ]
        return "\n".join(rows) + "\n"

    monkeypatch.setattr(ocr, "_execute", contaminated)
    result = call(tools, "read_historical_page", {"source_id": prior["source_id"], "page": 1})
    assert result["associations"], result["issues"]
    first = next(a for a in result["associations"] if a["question"] == "Eligibility")
    assert (first["candidate_answer"] == "Regional dealer complies") == (extra == "e")
    if extra == "e":
        assert first["discrepancies"][0]["code"] == "historical_control_label_layout_reconciled"


@pytest.mark.parametrize("current_finding", [None, "not_corroborated", "contradicts"])
@pytest.mark.parametrize("padded_control", [False, True])
def test_unboxed_historical_eligibility_writes_flagged_draft_without_current_recertification(
    tmp_path,
    monkeypatch,
    current_finding,
    padded_control,
):
    contradiction = current_finding == "contradicts"
    from bd_packet_builder.history import with_historical_sources
    from bd_packet_builder.inventory import build_inventory

    setup, tools, reader, prior, current = setup_page(
        tmp_path,
        monkeypatch,
        primary_question="Eligibility",
        primary_answer="Regional dealer",
        scanned_answer=True,
        control_state="selected",
        unboxed_control=True,
        historical_policy="answer_first_review",
    )
    if padded_control:
        transcript = reader.transcribe.return_value.model_dump(mode="json")
        transcript["historical_fields"][0]["control"]["box"] = box(270, 90, 299, 115)
        reader.transcribe.return_value = ScanTranscript.model_validate_json(json.dumps(transcript))
    from bd_packet_builder import ocr

    execute = ocr._execute
    monkeypatch.setattr(
        ocr,
        "_execute",
        lambda command, *args: (
            execute(command, *args)
            .replace("\tAvery\n", "\tRegional\n")
            .replace("\tExample\n", "\tdealer\n")
        ),
    )
    result = call(tools, "read_historical_page", {"source_id": prior["source_id"], "page": 1})
    first = next(a for a in result["associations"] if a["candidate_answer"] == "Regional dealer")
    current_citation = (
        call(
            tools,
            "locate_quote",
            {
                "source_id": current["source_id"],
                "page": 1,
                "quote": "Firm legal name: Insperex Fictional Securities LLC",
            },
        )
        if current_finding is not None
        else None
    )
    if current_citation is not None:
        current_citation.pop("occurrences")
    call(tools, "finish_evidence")
    checks = tuple(
        HistoricalContextCheck.model_validate_json(json.dumps(c))
        for c in json.loads(setup.artifact("historical_context_checks.json"))["checks"]
    )
    stream = BytesIO()
    canvas = Canvas(stream, pagesize=(600, 800), invariant=True)
    canvas.drawString(40, 740, "Eligibility")
    canvas.rect(40, 690, 10, 10)
    canvas.drawString(60, 690, "Regional dealer")
    canvas.rect(40, 650, 10, 10)
    canvas.drawString(60, 650, "National dealer")
    canvas.save()
    blank = stream.getvalue()
    digest = hashlib.sha256(blank).hexdigest()
    requirement = dict(
        requirement_id="eligibility",
        application_sha256=digest,
        page=1,
        instruction="Eligibility",
        kind="single_select",
        choices={
            "options": [
                dict(option_id="regional", label="Regional dealer", instruction="Regional dealer"),
                dict(option_id="national", label="National dealer", instruction="National dealer"),
            ]
        },
    )

    def region(left, bottom, right, top):
        return dict(
            page=1, left=float(left), bottom=float(bottom), right=float(right), top=float(top)
        )

    target = setup.evidence_root / "bd_agreements/Blank/eligibility.pdf"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(blank)
    request = DraftRequest.model_validate_json(
        json.dumps(
            dict(
                mode="reviewed_evidence",
                source="bd_agreements/Blank/eligibility.pdf",
                requirements={"requirements": [requirement]},
                layout=dict(
                    application_sha256=digest,
                    responses=[
                        dict(
                            requirement=requirement,
                            options=[
                                dict(
                                    option_id=option,
                                    control="checkbox",
                                    box=region(40, y, 50, y + 10),
                                    label_box=region(60, y - 3, 160, y + 14),
                                    label_quote=label,
                                )
                                for option, label, y in (
                                    ("regional", "Regional dealer", 690),
                                    ("national", "National dealer", 650),
                                )
                            ],
                        )
                    ],
                ),
                proposals={
                    "proposals": [
                        dict(
                            requirement_id="eligibility",
                            outcome="proposed",
                            confidence=0.9,
                            knowledge_applied=[
                                dict(
                                    entry_id="historical-eligibility",
                                    reason="Checked prior representation; continuity unconfirmed.",
                                )
                            ],
                            value=dict(kind="single_select", selected=["regional"], write_ins=[]),
                            citations=[first["answer_citation"]],
                            historical_basis=dict(
                                category="eligibility",
                                context="firm_wide",
                                prior_question=first["context_citation"],
                                role="Primary representative",
                                current_checks=[
                                    dict(
                                        citation=current_citation,
                                        finding=current_finding,
                                        explanation="Synthetic current-evidence check.",
                                    )
                                ]
                                if current_citation is not None
                                else [],
                                reviewer_confirmation=(
                                    "Historical eligibility; confirm continuity and conditions."
                                ),
                            ),
                        )
                    ]
                },
                sources=[
                    dict(path=s.path, sha256=s.sha256)
                    for s in with_historical_sources(
                        setup.evidence_root,
                        build_inventory(setup.evidence_root),
                        setup.manifest.request.historical_archive,
                    ).sources
                ],
                attachments=[],
                protected_regions=[],
                issuer="Broward",
                historical_policy="answer_first_review",
                historical_archive=setup.manifest.request.historical_archive.model_dump(
                    mode="json"
                ),
            )
        )
    )
    raw = request.model_dump_json().encode()
    review = validate_answers(
        setup.evidence_root,
        request,
        hashlib.sha256(raw).hexdigest(),
        historical_context_checks=checks,
    )
    assert (review.decisions[0].decision == "draft_verified") == (not contradiction), (
        review.decisions[0].reason
    )
    (setup.evidence_root / "outputs/eligibility-request.json").write_bytes(raw)
    output = publish_draft(
        setup.evidence_root,
        Path("outputs/eligibility-request.json"),
        raw,
        request,
        review,
        review.model_dump_json().encode(),
        None,
    )
    report = json.loads((output / "draft.json").read_bytes())
    assert report["written_requirements"] == ([] if contradiction else ["eligibility"])
    assert report["render_checks"]["outside_allowed_regions_changed_pixels"] == 0
    assert report["domain_knowledge"]["version"] == "domain-knowledge-v2"
    summary = (output / "reviewer-summary.txt").read_text()
    assert "historical-eligibility" in summary
    assert "MODEL-REPORTED" in summary
    assert "continuity unconfirmed" in summary
    packet_text = " ".join(p.extract_text() for p in PdfReader(output / "draft-packet.pdf").pages)
    assert "historical-eligibility" not in packet_text
    assert "MODEL-REPORTED" not in packet_text
    if not contradiction:
        assert (
            "HISTORICAL - CONTINUITY UNCONFIRMED" in (output / "reviewer-summary.txt").read_text()
        )


@pytest.mark.parametrize("disagreement", ["interleaved", "ocr_spelling"])
def test_disputed_readings_preserve_both_without_selecting_an_unverified_winner(
    tmp_path, monkeypatch, disagreement
):
    from bd_packet_builder import ocr

    setup, tools, _, prior, current = setup_page(
        tmp_path, monkeypatch, scanned_answer=True, historical_policy="answer_first_review"
    )
    execute = ocr._execute

    def interleaved(command, *args):
        output = execute(command, *args)
        if "--version" in command:
            return output
        if disagreement == "ocr_spelling":
            return output.replace("\tExample\n", "\tExamp1e\n")
        lines = output.splitlines()
        index = next(i for i, line in enumerate(lines) if line.endswith("\tExample"))
        lines.insert(index, "5\t1\t1\t1\t20\t1\t180\t330\t180\t40\t96\tUnrelated")
        return "\n".join(lines) + "\n"

    monkeypatch.setattr(ocr, "_execute", interleaved)
    result = call(tools, "read_historical_page", {"source_id": prior["source_id"], "page": 1})
    candidate = result["associations"][0]
    assert candidate["candidate_answer"] is None
    expected = "Avery\nUnrelated\nExample" if disagreement == "interleaved" else "Avery\nExamp1e"
    assert candidate["answer_citation"]["quote"] == expected
    assert candidate["discrepancies"]
    assert "with_extraction_discrepancies" in result["scope"]
    _, review = validated_page(setup, tools, prior, current, expected_answered=0)
    assert review.decisions[0].decision == "withhold"
    assert "reading_conflict_requires_reconciliation" in review.decisions[0].reason
    call(tools, "assemble_packet")
    call(tools, "publish_results")
    summary = setup.artifact("reviewer-summary.txt").decode()
    assert "LEFT BLANK" in summary and "Conflicting extraction readings" in summary
    assert json.loads(setup.artifact("draft.json"))["written_requirements"] == []


def validated_page(setup, tools, prior, current, expected_answered=1, answer=NAME):
    result = call(tools, "read_historical_page", {"source_id": prior["source_id"], "page": 1})
    first = result["associations"][0]
    citation = call(
        tools,
        "locate_quote",
        {
            "source_id": current["source_id"],
            "page": 1,
            "quote": "Firm legal name: Insperex Fictional Securities LLC",
        },
    )
    citation.pop("occurrences")
    proposal = {
        "requirement_id": "p1.name",
        "outcome": "proposed",
        "confidence": 0.9,
        "value": {"kind": "text", "value": answer},
        "citations": [first["answer_citation"]],
        "historical_basis": {
            "category": "contact",
            "context": "issuer_specific",
            "prior_question": first["context_citation"],
            "role": "Primary representative",
            "current_checks": [
                {
                    "citation": citation,
                    "finding": "not_corroborated",
                    "explanation": "Firm identity does not confirm the prior contact.",
                }
            ],
            "reviewer_confirmation": "Confirm the contact is unchanged.",
        },
    }
    call(tools, "finish_evidence")
    assert call(tools, "submit_answers", {"proposals": [proposal]})["answered"] == expected_answered
    raw = setup.artifact("draft_request.json")
    request = DraftRequest.model_validate_json(raw)
    review = DraftReview.model_validate_json(setup.artifact("answer_review.json"))
    return request, review


@pytest.mark.parametrize("ocr_problem", ["low_confidence", "missing_continuation", "table_order"])
def test_native_verified_narrative_is_not_vetoed_by_weaker_layout_signals(
    tmp_path, monkeypatch, ocr_problem
):
    answer = (
        "City A; 555-0101\nCity B; 555-0102"
        if ocr_problem == "table_order"
        else "Managing Director\nInstitutional Sales"
    )
    ocr_answer = {
        "low_confidence": answer,
        "missing_continuation": answer.splitlines()[0],
        "table_order": "City A; City B;\n555-0101 555-0102",
    }[ocr_problem]
    setup, tools, reader, prior, current = setup_page(
        tmp_path,
        monkeypatch,
        primary_answer=answer,
        primary_ocr_answer=ocr_answer,
        primary_ocr_confidence=80 if ocr_problem == "low_confidence" else 96,
        historical_policy="answer_first_review",
    )
    result = call(tools, "read_historical_page", {"source_id": prior["source_id"], "page": 1})
    candidate = result["associations"][0]
    assert candidate["candidate_answer"] == answer
    assert "evidence_kind" not in candidate["answer_citation"]
    assert "answer_layout" not in candidate
    _, review = validated_page(setup, tools, prior, current, answer=answer)
    assert review.decisions[0].decision == "draft_verified"
    call(tools, "assemble_packet")
    call(tools, "publish_results")
    text = " ".join(
        page.extract_text() for page in PdfReader(BytesIO(setup.artifact("packet.pdf"))).pages
    )
    for line in answer.splitlines():
        assert line in text
    assert "HISTORICAL - CONTINUITY UNCONFIRMED" in setup.artifact("reviewer-summary.txt").decode()
    assert reader.transcribe.call_count == 1


def test_native_verified_narrative_with_imperfect_ocr_reaches_the_supplement(tmp_path, monkeypatch):
    answer = "Managing Director\nInstitutional Sales"
    setup, tools, reader, prior, current = setup_page(
        tmp_path,
        monkeypatch,
        primary_answer=answer,
        primary_ocr_answer=answer,
        primary_ocr_confidence=80,
        historical_policy="answer_first_review",
    )
    request, review = validated_page(setup, tools, prior, current, answer=answer)
    raw = request.model_dump(mode="json")
    requirement = raw["requirements"]["requirements"][0]
    requirement["kind"] = "narrative"
    raw["requirements"]["requirements"] = [requirement]
    mapping = raw["layout"]["responses"][0]
    mapping["requirement"] = requirement
    mapping["narrative_region"] = mapping["text_region"]
    mapping["text_region"] = None
    raw["layout"]["responses"] = [mapping]
    raw["proposals"]["proposals"] = raw["proposals"]["proposals"][:1]
    raw["proposals"]["proposals"][0]["value"] = {"kind": "narrative", "value": answer}
    request = DraftRequest.model_validate_json(json.dumps(raw))
    data = request.model_dump_json().encode()
    gated = validate_answers(
        setup.evidence_root,
        request,
        hashlib.sha256(data).hexdigest(),
        historical_context_checks=review.historical_context_checks,
    )
    assert gated.decisions[0].decision == "draft_verified"
    blank = setup.evidence_root / request.source
    blank.parent.mkdir(parents=True, exist_ok=True)
    blank.write_bytes(setup.blank)
    path = Path("outputs/native-narrative.json")
    (setup.evidence_root / path).write_bytes(data)
    output = publish_draft(
        setup.evidence_root, path, data, request, gated, gated.model_dump_json().encode(), None
    )
    report = json.loads((output / "draft.json").read_bytes())
    assert report["placements"]["p1.name"]["mode"] == "supplement"
    assert report["render_checks"]["supplement_pages_rendered_and_text_checked"] == 1
    assert report["render_checks"]["outside_allowed_regions_changed_pixels"] == 0
    packet = PdfReader(output / "draft-packet.pdf")
    for line in answer.splitlines():
        assert line in packet.pages[1].extract_text()
    assert "See Supplemental Answers, p1.name, packet page 2." in packet.pages[0].extract_text()
    assert reader.transcribe.call_count == 1


@pytest.mark.parametrize(
    ("answer", "instruction", "allowed"),
    [
        ("Yes", "Does your firm have offices in Florida?", True),
        ("No", "Does your firm have offices in Florida?", True),
        ("Yes", "Has your firm been investigated?", False),
        ("No", "Has this person read and understands the policy?", False),
    ],
)
@pytest.mark.parametrize("policy", ["conservative", "answer_first_review"])
def test_checked_historical_boolean_respects_reuse_policy_and_personal_act_exclusions(
    tmp_path, monkeypatch, answer, instruction, allowed, policy
):
    setup, tools, _, prior, current = setup_page(
        tmp_path, monkeypatch, primary_question="Offices", primary_answer=answer
    )
    result = call(tools, "read_historical_page", {"source_id": prior["source_id"], "page": 1})
    first = result["associations"][0]
    citation = call(
        tools,
        "locate_quote",
        {
            "source_id": current["source_id"],
            "page": 1,
            "quote": "Firm legal name: Insperex Fictional Securities LLC",
        },
    )
    citation.pop("occurrences")
    call(tools, "finish_evidence")
    call(
        tools,
        "submit_answers",
        {
            "proposals": [
                {
                    "requirement_id": "p1.name",
                    "outcome": "proposed",
                    "confidence": 0.9,
                    "value": {"kind": "text", "value": answer},
                    "citations": [first["answer_citation"]],
                    "historical_basis": {
                        "category": "firm_description",
                        "context": "issuer_specific",
                        "prior_question": first["context_citation"],
                        "role": "Primary representative",
                        "current_checks": [
                            {
                                "citation": citation,
                                "finding": "not_corroborated",
                                "explanation": "Firm identity does not confirm office operations.",
                            }
                        ],
                        "reviewer_confirmation": "Confirm the prior office answer still applies.",
                    },
                }
            ]
        },
    )
    raw = json.loads(setup.artifact("draft_request.json"))
    raw["historical_policy"] = policy
    if "investigated" in instruction:
        raw["proposals"]["proposals"][0]["historical_basis"]["category"] = "disclosure"
        allowed = policy == "answer_first_review"
    if policy == "answer_first_review":
        raw["proposals"]["proposals"][0]["historical_basis"]["current_checks"] = []
    raw["requirements"]["requirements"][0].update(kind="boolean", instruction=instruction)
    raw["layout"]["responses"][0]["requirement"] = raw["requirements"]["requirements"][0]
    raw["proposals"]["proposals"][0]["value"] = {"kind": "boolean", "value": answer == "Yes"}
    request = DraftRequest.model_validate_json(json.dumps(raw))
    checks = DraftReview.model_validate_json(
        setup.artifact("answer_review.json")
    ).historical_context_checks
    review = validate_answers(
        setup.evidence_root,
        request,
        hashlib.sha256(request.model_dump_json().encode()).hexdigest(),
        historical_context_checks=checks,
    )
    assert (review.decisions[0].decision == "draft_verified") == allowed, review.decisions[0].reason
    if allowed:
        buffer = BytesIO()
        canvas = Canvas(buffer, pagesize=(612, 792), invariant=True)
        canvas.drawString(40, 732, instruction)
        canvas.drawString(40, 452, "Signature of authorized officer")
        canvas.drawString(40, 392, "Date")
        canvas.save()
        new_blank = buffer.getvalue()
        digest = hashlib.sha256(new_blank).hexdigest()
        for requirement in raw["requirements"]["requirements"]:
            requirement["application_sha256"] = digest
        raw["layout"]["application_sha256"] = digest
        for mapping in raw["layout"]["responses"]:
            mapping["requirement"]["application_sha256"] = digest
        request = DraftRequest.model_validate_json(json.dumps(raw))
        review = validate_answers(
            setup.evidence_root,
            request,
            hashlib.sha256(request.model_dump_json().encode()).hexdigest(),
            historical_context_checks=checks,
        )
        blank = setup.evidence_root / request.source
        blank.parent.mkdir(parents=True, exist_ok=True)
        blank.write_bytes(new_blank)
        (setup.evidence_root / "outputs/boolean-request.json").write_bytes(
            request.model_dump_json().encode()
        )
        output = publish_draft(
            setup.evidence_root,
            Path("outputs/boolean-request.json"),
            request.model_dump_json().encode(),
            request,
            review,
            review.model_dump_json().encode(),
            None,
        )
        report = json.loads((output / "draft.json").read_text())
        assert report["written_requirements"] == ["p1.name"]
        assert report["answers"][0]["evidence_status"] == "historical_continuity_unconfirmed"
        assert report["render_checks"]["outside_allowed_regions_changed_pixels"] == 0
    else:
        assert "historical_sensitive_requirement" in review.decisions[0].reason


@pytest.mark.parametrize("scanned_answer", [False, True])
def test_context_receipt_rechecks_native_and_ocr_answers(tmp_path, monkeypatch, scanned_answer):
    setup, tools, _, prior, current = setup_page(
        tmp_path,
        monkeypatch,
        scanned_answer=scanned_answer,
    )
    request, review = validated_page(setup, tools, prior, current)
    expected_kind = "ocr" if scanned_answer else None
    assert (
        getattr(request.proposals.proposals[0].citations[0], "evidence_kind", None) == expected_kind
    )
    call(tools, "assemble_packet")
    assert NAME in PdfReader(BytesIO(setup.artifact("packet.pdf"))).pages[0].extract_text()
    # A missing runtime receipt may not be replaced by the model's well-formed citation.
    denied = validate_answers(
        setup.evidence_root,
        request,
        review.request_sha256,
        historical_context_checks=(),
    )
    assert denied.decisions[0].decision == "withhold"
    assert "receipt_missing_or_mismatched" in denied.decisions[0].reason


@pytest.mark.parametrize("tamper", ["role", "context_hash", "question_region", "answer_region"])
def test_forged_or_replayed_context_is_withheld_by_gate_and_writer(tmp_path, monkeypatch, tamper):
    setup, tools, _, prior, current = setup_page(tmp_path, monkeypatch)
    request, review = validated_page(setup, tools, prior, current)
    raw = request.model_dump(mode="json")
    checks = review.historical_context_checks
    basis = raw["proposals"]["proposals"][0]["historical_basis"]
    if tamper == "role":
        basis["role"] = "Backup representative"
    elif tamper == "context_hash":
        basis["prior_question"]["check_sha256"] = "0" * 64
    else:
        changed = checks[0].model_dump(mode="json")
        changed["field"]["question" if tamper == "question_region" else "answer"]["box"] = box(
            600,
            600,
            900,
            650,
        )
        forged = HistoricalContextCheck.model_validate_json(json.dumps(changed))
        checks = (forged,)
        basis["prior_question"] = forged.context_citation.model_dump(mode="json")
    altered = DraftRequest.model_validate_json(json.dumps(raw))
    digest = hashlib.sha256(altered.model_dump_json().encode()).hexdigest()
    gated = validate_answers(
        setup.evidence_root,
        altered,
        digest,
        historical_context_checks=checks,
    )
    assert gated.decisions[0].decision == "withhold"
    # The writer independently rechecks instead of trusting a prior positive decision.
    stale = review.model_copy(
        update={"request_sha256": digest, "historical_context_checks": checks}
    )
    blank = setup.evidence_root / altered.source
    blank.parent.mkdir(parents=True, exist_ok=True)
    blank.write_bytes(setup.blank)
    request_path = Path(f"outputs/tampered-{tamper}.json")
    (setup.evidence_root / request_path).write_bytes(altered.model_dump_json().encode())
    output = publish_draft(
        setup.evidence_root,
        request_path,
        altered.model_dump_json().encode(),
        altered,
        stale,
        stale.model_dump_json().encode(),
        None,
    )
    assert NAME not in PdfReader(output / "draft-packet.pdf").pages[0].extract_text()
    assert json.loads((output / "draft.json").read_bytes())["answers"][0]["status"] == "blank"


def test_ocr_artifact_mutation_is_not_accepted(tmp_path, monkeypatch):
    setup, tools, _, prior, current = setup_page(tmp_path, monkeypatch)
    request, review = validated_page(setup, tools, prior, current)
    citation = review.historical_context_checks[0].question
    artifact = setup.evidence_root / citation.artifact_path
    artifact.write_bytes(artifact.read_bytes() + b"\n")
    gated = validate_answers(
        setup.evidence_root,
        request,
        review.request_sha256,
        historical_context_checks=review.historical_context_checks,
    )
    assert gated.decisions[0].decision == "withhold"
    assert "ocr_artifact_hash_mismatch" in gated.decisions[0].reason


@pytest.mark.parametrize(
    "version",
    [
        "historical-page-context-v4",
        "historical-page-context-v5",
        "historical-page-context-v6",
        "historical-page-context-v7",
    ],
)
def test_legacy_relationship_identity_does_not_change_when_control_fields_are_added(
    tmp_path,
    monkeypatch,
    version,
):
    setup, tools, _, prior, current = setup_page(tmp_path, monkeypatch)
    _, review = validated_page(setup, tools, prior, current)
    raw = json.loads(review.historical_context_checks[0].model_dump_json())
    raw["version"] = version
    raw["prompt_version"] = "scan-cross-check-v2"
    raw.pop("discrepancies")
    raw.pop("printed_readings")
    if version not in ("historical-page-context-v6", "historical-page-context-v7"):
        raw["field"].pop("write_in")
    if version == "historical-page-context-v4":
        raw["field"].pop("control")
    for field in raw["transcript"]["historical_fields"]:
        if version not in ("historical-page-context-v6", "historical-page-context-v7"):
            field.pop("write_in")
        if version == "historical-page-context-v4":
            field.pop("control")
    legacy = json.dumps(raw, separators=(",", ":"), ensure_ascii=False).encode()
    parsed = HistoricalContextCheck.model_validate_json(legacy)
    assert parsed.context_citation.check_sha256 == hashlib.sha256(legacy).hexdigest()


def test_review_retains_needed_receipts_not_every_discovered_candidate(tmp_path, monkeypatch):
    setup, tools, _, prior, current = setup_page(tmp_path, monkeypatch)
    request, review = validated_page(setup, tools, prior, current)
    checks = tuple(
        HistoricalContextCheck.model_validate_json(json.dumps(c))
        for c in json.loads(setup.artifact("historical_context_checks.json"))["checks"]
    )
    result = validate_answers(
        setup.evidence_root,
        request,
        review.request_sha256,
        historical_context_checks=(checks[0], *(checks[1] for _ in range(110))),
    )
    assert result.decisions[0].decision == "draft_verified"
    assert len(result.historical_context_checks) == 1


def test_low_confidence_context_is_an_explicit_page_issue(tmp_path, monkeypatch):
    _, tools, _, prior, _ = setup_page(tmp_path, monkeypatch, confidence=89)
    result = call(tools, "read_historical_page", {"source_id": prior["source_id"], "page": 1})
    assert not result["associations"]
    assert {issue["code"] for issue in result["issues"]} == {"historical_low_word_confidence"}


@pytest.mark.parametrize("disagreement", ["confidence", "question"])
def test_answer_first_keeps_localized_disagreements_as_explicit_review_candidates(
    tmp_path, monkeypatch, disagreement
):
    setup, tools, reader, prior, current = setup_page(
        tmp_path,
        monkeypatch,
        confidence=89 if disagreement == "confidence" else 96,
        historical_policy="answer_first_review",
    )
    if disagreement == "question":
        raw = json.loads(reader.transcribe.return_value.model_dump_json())
        raw["historical_fields"][0]["question"]["text"] = "Printed Name"
        reader.transcribe.return_value = ScanTranscript.model_validate_json(json.dumps(raw))
    result = call(tools, "read_historical_page", {"source_id": prior["source_id"], "page": 1})
    assert result["associations"], result["issues"]
    assert result["associations"][0]["discrepancies"]
    request, review = validated_page(setup, tools, prior, current)
    assert review.decisions[0].decision == "draft_verified"
    call(tools, "assemble_packet")
    call(tools, "publish_results")
    summary = setup.artifact("reviewer-summary.txt").decode()
    assert "EXTRACTION DISCREPANCY" in summary
    assert "image_reading" in summary
    assert "ocr_reading" in summary
    conservative = request.model_copy(update={"historical_policy": "conservative"})
    assert (
        validate_answers(
            setup.evidence_root,
            conservative,
            "a" * 64,
            historical_context_checks=review.historical_context_checks,
        )
        .decisions[0]
        .decision
        == "withhold"
    )


@pytest.mark.parametrize(
    ("kind", "selected", "answer", "instruction", "allowed"),
    [
        ("single_select", ["yes"], "Yes", "Do you offer agency securities?", True),
        ("single_select", ["no"], "Yes", "Do you offer agency securities?", False),
        ("single_select", ["unknown"], "Yes", "Do you offer agency securities?", False),
        ("multi_select", ["yes", "no"], "Yes; No", "Select available services", True),
        ("multi_select", ["yes"], "Yes; No", "Select available services", False),
        ("multi_select", ["yes", "no"], "Yes", "Select available services", False),
        ("single_select", ["yes"], "Yes", "Has the firm been investigated?", False),
        ("single_select", ["yes"], "Yes", "I acknowledge the policy", False),
    ],
)
@pytest.mark.parametrize("policy", ["conservative", "answer_first_review"])
@pytest.mark.parametrize("graphical", [False, True])
def test_checked_historical_choices_require_exact_answer_and_preserve_exclusions(
    tmp_path, monkeypatch, kind, selected, answer, instruction, allowed, policy, graphical
):
    setup, tools, _, prior, current = setup_page(
        tmp_path,
        monkeypatch,
        primary_question="Services",
        primary_answer="Yes" if graphical and answer == "Yes; No" else answer,
        control_state="selected" if graphical else None,
        second_control=graphical and answer == "Yes; No",
    )
    result = call(tools, "read_historical_page", {"source_id": prior["source_id"], "page": 1})
    association = result["associations"][0]
    answer_citations = [association["answer_citation"]]
    if graphical and answer == "Yes; No":
        answer_citations.append(result["associations"][1]["answer_citation"])
    citation = call(
        tools,
        "locate_quote",
        {
            "source_id": current["source_id"],
            "page": 1,
            "quote": "Firm legal name: Insperex Fictional Securities LLC",
        },
    )
    citation.pop("occurrences")
    call(tools, "finish_evidence")
    basis = {
        "category": "trading_capability",
        "context": "firm_wide",
        "role": None,
        "prior_question": association["context_citation"],
        "current_checks": [
            {
                "citation": citation,
                "finding": "not_corroborated",
                "explanation": "Identity does not confirm services.",
            }
        ],
        "reviewer_confirmation": "Confirm the historically stated service remains offered.",
        "correspondence": {
            "target_question": instruction,
            "assessment": "uncertain",
            "differences": "The prior synthetic question is a generic Services label.",
            "reason": "The label does not establish exact semantic equivalence; review required.",
        },
    }
    call(
        tools,
        "submit_answers",
        {
            "proposals": [
                {
                    "requirement_id": "p1.name",
                    "outcome": "proposed",
                    "confidence": 0.9,
                    "value": {"kind": "text", "value": answer},
                    "citations": answer_citations,
                    "historical_basis": basis,
                }
            ]
        },
    )
    raw = json.loads(setup.artifact("draft_request.json"))
    raw["historical_policy"] = policy
    if "investigated" in instruction and policy == "answer_first_review":
        allowed = True
        basis["current_checks"] = []
    raw["issuer"] = "Another Municipality"
    requirement = raw["requirements"]["requirements"][0]
    requirement.update(
        kind=kind,
        instruction=instruction,
        choices={
            "options": [
                {"option_id": "yes", "label": "Yes", "instruction": "Yes"},
                {"option_id": "no", "label": "No", "instruction": "No"},
            ]
        },
    )
    raw["layout"]["responses"][0]["requirement"] = requirement
    raw["layout"]["responses"][0]["text_region"] = None
    raw["layout"]["responses"][0]["options"] = [
        {
            "option_id": option,
            "control": "checkbox",
            "box": {
                "page": 1,
                "left": 40 + i * 100,
                "bottom": 600,
                "right": 50 + i * 100,
                "top": 610,
            },
            "label_box": {
                "page": 1,
                "left": 55 + i * 100,
                "bottom": 600,
                "right": 90 + i * 100,
                "top": 610,
            },
            "label_quote": option.title(),
        }
        for i, option in enumerate(("yes", "no"))
    ]
    raw["proposals"]["proposals"][0] = {
        "requirement_id": requirement["requirement_id"],
        "outcome": "proposed",
        "confidence": 0.9,
        "value": {"kind": kind, "selected": selected},
        "citations": answer_citations,
        "historical_basis": basis,
    }
    request = DraftRequest.model_validate_json(json.dumps(raw))
    checks = DraftReview.model_validate_json(
        setup.artifact("answer_review.json")
    ).historical_context_checks
    review = validate_answers(
        setup.evidence_root, request, "a" * 64, historical_context_checks=checks
    )
    assert (review.decisions[0].decision == "draft_verified") == allowed, review.decisions[0].reason
    if allowed:
        buffer = BytesIO()
        canvas = Canvas(buffer, pagesize=(612, 792), invariant=True)
        canvas.drawString(40, 732, instruction)
        canvas.drawString(55, 600, "Yes")
        canvas.drawString(155, 600, "No")
        canvas.save()
        blank = buffer.getvalue()
        digest = hashlib.sha256(blank).hexdigest()
        raw["layout"]["application_sha256"] = digest
        for item in raw["requirements"]["requirements"]:
            item["application_sha256"] = digest
        for mapping in raw["layout"]["responses"]:
            mapping["requirement"]["application_sha256"] = digest
        request = DraftRequest.model_validate_json(json.dumps(raw))
        request_raw = request.model_dump_json().encode()
        review = validate_answers(
            setup.evidence_root,
            request,
            hashlib.sha256(request_raw).hexdigest(),
            historical_context_checks=checks,
        )
        target = setup.evidence_root / request.source
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(blank)
        (setup.evidence_root / "outputs/choice-request.json").write_bytes(request_raw)
        output = publish_draft(
            setup.evidence_root,
            Path("outputs/choice-request.json"),
            request_raw,
            request,
            review,
            review.model_dump_json().encode(),
            None,
        )
        report = json.loads((output / "draft.json").read_bytes())
        assert report["written_requirements"] == ["p1.name"]
        assert report["render_checks"]["outside_allowed_regions_changed_pixels"] == 0
        assert report["answers"][0]["evidence_status"] == "historical_continuity_unconfirmed"
        summary = (output / "reviewer-summary.txt").read_text()
        if "investigated" in instruction:
            assert "DISCLOSURE REVIEW" in summary


@pytest.mark.parametrize("state", ["selected", "unselected"])
def test_historical_controls_use_label_citations_and_do_not_infer_negative_answers(
    tmp_path, monkeypatch, state
):
    setup, tools, reader, prior, _ = setup_page(
        tmp_path,
        monkeypatch,
        primary_question="Services",
        primary_answer="Yes",
        control_state=state,
    )
    result = call(tools, "read_historical_page", {"source_id": prior["source_id"], "page": 1})
    assert len(result["controls"]) == 1
    assert result["controls"][0]["control"]["state"] == state
    labels = [a["answer_citation"]["quote"] for a in result["associations"]]
    assert ("Yes" in labels) == (state == "selected"), result["issues"]
    assert "No" not in labels
    assert not [issue for issue in result["issues"] if issue["part"] == "control"]
    reader.transcribe.assert_called_once()


def test_model_cannot_claim_an_empty_historical_box_is_selected(tmp_path, monkeypatch):
    setup, tools, reader, prior, _ = setup_page(
        tmp_path,
        monkeypatch,
        primary_question="Services",
        primary_answer="Yes",
        control_state="unselected",
    )
    raw = json.loads(reader.transcribe.return_value.model_dump_json())
    raw["historical_fields"][0]["control"]["state"] = "selected"
    reader.transcribe.return_value = ScanTranscript.model_validate_json(json.dumps(raw))
    result = call(tools, "read_historical_page", {"source_id": prior["source_id"], "page": 1})
    assert "Yes" not in [a["answer_citation"]["quote"] for a in result["associations"]]
    assert any(i["code"] == "historical_control_mark_disagrees" for i in result["issues"])


@pytest.mark.parametrize("shift,padding", [(-1, -1), (0, 0), (1, 1)])
def test_checkmark_hint_variations_survive_gate_and_independent_writer(
    tmp_path, monkeypatch, shift, padding
):
    setup, tools, reader, prior, current = setup_page(
        tmp_path, monkeypatch, control_state="selected", unboxed_control=True
    )
    raw = json.loads(reader.transcribe.return_value.model_dump_json())
    bounds = raw["historical_fields"][0]["control"]["box"]
    bounds["left"] += shift - padding
    bounds["top"] += shift - padding
    bounds["right"] += shift + padding
    bounds["bottom"] += shift + padding
    reader.transcribe.return_value = ScanTranscript.model_validate_json(json.dumps(raw))
    request, review = validated_page(setup, tools, prior, current)
    assert review.decisions[0].decision == "draft_verified"
    blank = setup.evidence_root / request.source
    blank.parent.mkdir(parents=True, exist_ok=True)
    blank.write_bytes(setup.blank)
    request_path = Path("outputs/checkmark-request.json")
    request_raw = request.model_dump_json().encode()
    (setup.evidence_root / request_path).write_bytes(request_raw)
    output = publish_draft(
        setup.evidence_root,
        request_path,
        request_raw,
        request,
        review,
        review.model_dump_json().encode(),
        None,
    )
    report = json.loads((output / "draft.json").read_bytes())
    assert report["written_requirements"] == ["p1.name"]
    assert report["render_checks"]["outside_allowed_regions_changed_pixels"] == 0


def test_control_subsection_header_may_follow_its_governing_question(tmp_path, monkeypatch):
    _, tools, _, prior, _ = setup_page(
        tmp_path,
        monkeypatch,
        primary_question="Services",
        primary_answer="Yes",
        control_state="selected",
        subheader=True,
    )
    result = call(tools, "read_historical_page", {"source_id": prior["source_id"], "page": 1})
    assert any(a["answer_citation"]["quote"] == "Yes" for a in result["associations"]), result[
        "issues"
    ]


def test_answer_first_policy_and_control_diagnostics_survive_handoff(tmp_path, monkeypatch):
    setup, tools, _, prior, current = setup_page(
        tmp_path,
        monkeypatch,
        control_state="selected",
        historical_policy="answer_first_review",
    )
    request, _ = validated_page(setup, tools, prior, current)
    assert request.historical_policy == "answer_first_review"
    assert tools.manifest().request.historical_policy == request.historical_policy
    handoff = json.loads(setup.artifact("answer_handoff.json"))
    assert handoff["historical_policy"] == request.historical_policy
    diagnostics = handoff["historical_extraction_diagnostics"]
    assert diagnostics[0]["control_observations"][0]["control"]["state"] == "selected"
    assert diagnostics[0]["scope"] == "raw_control_observations_not_verified_answers"


@pytest.mark.parametrize(
    ("change", "issue"),
    [
        ("contradiction", "historical_current_contradiction"),
        ("period", "historical_current_period_requires_current_evidence"),
        ("personal", "historical_sensitive_requirement"),
    ],
)
def test_answer_first_does_not_override_contradictions_periods_or_new_personal_acts(
    tmp_path, monkeypatch, change, issue
):
    setup, tools, _, prior, current = setup_page(tmp_path, monkeypatch)
    request, review = validated_page(setup, tools, prior, current)
    raw = json.loads(request.model_dump_json())
    raw["historical_policy"] = "answer_first_review"
    if change == "contradiction":
        raw["proposals"]["proposals"][0]["historical_basis"]["current_checks"][0]["finding"] = (
            "contradicts"
        )
    else:
        requirement = raw["requirements"]["requirements"][0]
        if change == "period":
            requirement["requested_period"] = {"start": "2026-01-01", "end": "2026-12-31"}
        else:
            requirement["instruction"] = "I certify that I have reviewed these documents."
        raw["layout"]["responses"][0]["requirement"] = requirement
    changed = DraftRequest.model_validate_json(json.dumps(raw))
    gated = validate_answers(
        setup.evidence_root,
        changed,
        "a" * 64,
        historical_context_checks=review.historical_context_checks,
    )
    assert gated.decisions[0].decision == "withhold"
    assert issue in gated.decisions[0].reason


def test_historical_tool_obeys_existing_ocr_budget_before_remote_call(tmp_path, monkeypatch):
    _, tools, reader, prior, _ = setup_page(
        tmp_path,
        monkeypatch,
        evidence_limits=EvidenceLimits(max_ocr_pages=0),
    )
    denied = json.loads(
        tools.call(
            "read_historical_page",
            json.dumps({"source_id": prior["source_id"], "page": 1}),
        )
    )
    assert not denied["ok"]
    assert "OCR page limit" in denied["error"]["message"]
    reader.transcribe.assert_not_called()


def test_native_partial_word_is_not_a_verified_image_answer(tmp_path, monkeypatch):
    _, tools, reader, prior, _ = setup_page(tmp_path, monkeypatch)
    raw = reader.transcribe.return_value.model_dump(mode="json")
    raw["historical_fields"][0]["answer"]["text"] = "Ave"
    reader.transcribe.return_value = ScanTranscript.model_validate_json(json.dumps(raw))
    result = call(tools, "read_historical_page", {"source_id": prior["source_id"], "page": 1})
    assert len(result["associations"]) == 1
    assert result["associations"][0]["answer_citation"]["quote"] == "Blair Example"
    assert result["issues"][0]["code"] == "historical_text_or_region_disagrees"


def test_model_cannot_shorten_a_verified_answer_to_a_partial_word(tmp_path, monkeypatch):
    setup, tools, _, prior, current = setup_page(tmp_path, monkeypatch)
    request, review = validated_page(setup, tools, prior, current)
    proposal = request.proposals.proposals[0].model_copy(
        update={
            "value": TextValue(kind="text", value="Ave"),
        }
    )
    changed = request.model_copy(
        update={
            "proposals": request.proposals.model_copy(update={"proposals": (proposal,)}),
        }
    )
    gated = validate_answers(
        setup.evidence_root,
        changed,
        review.request_sha256,
        historical_context_checks=review.historical_context_checks,
    )
    assert gated.decisions[0].decision == "withhold"


def test_section_header_can_govern_right_column_fields(tmp_path, monkeypatch):
    _, tools, _, prior, _ = setup_page(tmp_path, monkeypatch, right_column=True)
    result = call(tools, "read_historical_page", {"source_id": prior["source_id"], "page": 1})
    assert len(result["associations"]) == 2
    assert result["associations"][0]["answer_citation"]["quote"] == NAME
    assert result["associations"][0]["role"].split()[0] == "Primary"


def test_finish_evidence_reoffers_all_checked_candidates_for_completion_pass(tmp_path, monkeypatch):
    _, tools, _, prior, _ = setup_page(tmp_path, monkeypatch)
    checked = call(tools, "read_historical_page", {"source_id": prior["source_id"], "page": 1})
    result = call(tools, "finish_evidence")
    assert result["historical_candidates"] == checked["associations"]
    assert result["requirements"][0]["requirement_id"] == "p1.name"
    assert "continuity_unconfirmed" in result["completion_policy"]
    assert result["reading_usage"]["independent_image_pages"] == 1


def test_repeated_native_values_are_resolved_by_actual_field_geometry(tmp_path, monkeypatch):
    setup, tools, _, prior, current = setup_page(tmp_path, monkeypatch, repeated_answer=True)
    result = call(tools, "read_historical_page", {"source_id": prior["source_id"], "page": 1})
    assert len(result["associations"]) == 2
    first, second = [a["answer_citation"] for a in result["associations"]]
    assert "evidence_kind" not in first and "evidence_kind" not in second
    assert first["quote"] == second["quote"] == NAME
    assert first["start"] != second["start"]
    _, review = validated_page(setup, tools, prior, current)
    assert review.decisions[0].evidence_status == "historical_continuity_unconfirmed"
    call(tools, "assemble_packet")
    assert NAME in PdfReader(BytesIO(setup.artifact("packet.pdf"))).pages[0].extract_text()


@pytest.mark.parametrize("prefix", ["10.", "13)"])
def test_historical_question_number_spacing_preserves_literal_ocr_context(
    tmp_path,
    monkeypatch,
    prefix,
):
    setup, tools, _, prior, current = setup_page(
        tmp_path,
        monkeypatch,
        question_prefix=prefix,
    )
    result = call(tools, "read_historical_page", {"source_id": prior["source_id"], "page": 1})
    assert len(result["associations"]) == 2
    assert result["associations"][0]["context_citation"]["quote"].endswith(prefix + "Name")
    _, review = validated_page(setup, tools, prior, current)
    assert review.decisions[0].decision == "draft_verified"


def test_question_number_normalization_does_not_change_the_number(tmp_path, monkeypatch):
    _, tools, reader, prior, _ = setup_page(tmp_path, monkeypatch, question_prefix="10.")
    raw = reader.transcribe.return_value.model_dump(mode="json")
    raw["historical_fields"][0]["question"]["text"] = "11. Name"
    reader.transcribe.return_value = ScanTranscript.model_validate_json(json.dumps(raw))
    result = call(tools, "read_historical_page", {"source_id": prior["source_id"], "page": 1})
    assert len(result["associations"]) == 1
    assert result["associations"][0]["role"].startswith("Backup")
    assert result["issues"][0]["code"] == "historical_text_or_region_disagrees"


def test_competing_column_header_prevents_cross_role_association(tmp_path, monkeypatch):
    _, tools, _, prior, _ = setup_page(
        tmp_path,
        monkeypatch,
        right_column=True,
        competing_header=True,
    )
    result = call(tools, "read_historical_page", {"source_id": prior["source_id"], "page": 1})
    assert len(result["associations"]) == 2
    assert all("Primary" not in a["role"] for a in result["associations"])
    assert result["issues"][0]["code"] == "historical_role_region_mismatch"


def test_swapped_section_roles_are_withheld(tmp_path, monkeypatch):
    _, tools, reader, prior, _ = setup_page(tmp_path, monkeypatch)
    raw = reader.transcribe.return_value.model_dump(mode="json")
    fields = raw["historical_fields"]
    fields[0]["role"], fields[1]["role"] = fields[1]["role"], fields[0]["role"]
    reader.transcribe.return_value = ScanTranscript.model_validate_json(json.dumps(raw))
    result = call(tools, "read_historical_page", {"source_id": prior["source_id"], "page": 1})
    assert not result["associations"]
    assert {issue["code"] for issue in result["issues"]} == {"historical_role_region_mismatch"}


def test_large_image_box_cannot_hide_cross_role_native_answer(tmp_path, monkeypatch):
    _, tools, reader, prior, _ = setup_page(tmp_path, monkeypatch)
    raw = reader.transcribe.return_value.model_dump(mode="json")
    raw["historical_fields"][0]["answer"] = {
        "text": "Blair Example",
        "box": box(290, 90, 480, 295),
    }
    reader.transcribe.return_value = ScanTranscript.model_validate_json(json.dumps(raw))
    result = call(tools, "read_historical_page", {"source_id": prior["source_id"], "page": 1})
    assert len(result["associations"]) == 1
    assert result["associations"][0]["role"].split()[0] == "Backup"
    assert result["issues"][0]["code"] == "historical_answer_not_adjacent_to_question"


def test_historical_scanned_narrative_uses_relationship_not_scalar_receipt(tmp_path, monkeypatch):
    setup, tools, _, prior, current = setup_page(tmp_path, monkeypatch, scanned_answer=True)
    request, review = validated_page(setup, tools, prior, current)
    proposal = request.proposals.proposals[0].model_copy(
        update={
            "value": NarrativeValue(kind="narrative", value=NAME),
        }
    )
    requirement = request.requirements.requirements[0].model_copy(update={"kind": "narrative"})
    changed = request.model_copy(
        update={
            "requirements": request.requirements.model_copy(
                update={"requirements": (requirement,)}
            ),
            "proposals": request.proposals.model_copy(update={"proposals": (proposal,)}),
        }
    )
    gated = validate_answers(
        setup.evidence_root,
        changed,
        review.request_sha256,
        historical_context_checks=review.historical_context_checks,
    )
    assert gated.decisions[0].decision == "draft_verified"


NARRATIVE = "Agency bond desk"


def narrative_dispute(
    tmp_path, monkeypatch, *, native=False, outcome="resolved", limit=None, confidence=96
):
    setup, tools, reader, prior, current = setup_page(
        tmp_path,
        monkeypatch,
        scanned_answer=not native,
        historical_policy="answer_first_review",
        evidence_limits=limit,
        primary_answer=NARRATIVE,
        primary_ocr_answer=NARRATIVE,
        primary_ocr_confidence=confidence,
    )
    initial = reader.transcribe.return_value.model_dump(mode="json")
    # Omit an interior word from the image reading, not the source or local OCR.
    initial["historical_fields"][0]["answer"]["text"] = "Agency desk"
    initial = ScanTranscript.model_validate_json(json.dumps(initial))
    focused = ScanTranscript(
        readable=outcome != "unreadable",
        subject=None,
        text=(
            NARRATIVE
            if outcome in ("resolved", "unreadable")
            else "Treasury desk"
            if outcome == "third_reading"
            else "Agency desk"
        ),
        reporting_period=None,
    )
    reader.transcribe.side_effect = [initial, focused]
    return setup, tools, reader, prior, current


@pytest.mark.parametrize("native", [False, True])
def test_plain_answer_dispute_is_recovered_before_answering(tmp_path, monkeypatch, native):
    setup, tools, reader, prior, _ = narrative_dispute(tmp_path, monkeypatch, native=native)
    result = call(tools, "read_historical_page", {"source_id": prior["source_id"], "page": 1})
    first = result["associations"][0]
    assert first["candidate_answer"] == NARRATIVE
    assert first["printed_reading_issues"] == []
    assert len(first["printed_resolutions"]) == 1
    assert first["discrepancies"][0]["code"] == "historical_printed_text_resolved"
    assert reader.transcribe.call_count == (1 if native else 2)
    # Blind: only image bytes, never the alternative readings or suggested answer.
    assert all(len(c.args) == 1 and not c.kwargs for c in reader.transcribe.call_args_list)
    call(tools, "finish_evidence")
    receipt = HistoricalContextCheck.model_validate_json(
        json.dumps(json.loads(setup.artifact("historical_context_checks.json"))["checks"][0])
    )
    assert receipt.field.answer.text == "Agency desk"
    assert receipt.effective_field.answer.text == NARRATIVE
    # A restarted answering worker consumes persisted receipts, without another model call.
    restarted = setup.tools(scan_reader=reader)
    assert restarted.answer_handoff()["historical_candidates"][0]["candidate_answer"] == NARRATIVE
    assert reader.transcribe.call_count == (1 if native else 2)


def test_focused_recovery_keeps_corroborated_low_confidence_words_without_an_extent_veto(
    tmp_path, monkeypatch
):
    from bd_packet_builder import ocr

    _, tools, reader, prior, _ = narrative_dispute(tmp_path, monkeypatch)
    execute = ocr._execute

    def low_confidence(command, *args):
        output = execute(command, *args)
        if "--version" in command:
            return output
        rows = []
        for line in output.splitlines():
            fields = line.split("\t")
            if len(fields) == 12 and fields[-1] == "Agency":
                fields[10] = "68"
            rows.append("\t".join(fields))
        return "\n".join(rows) + "\n"

    monkeypatch.setattr(ocr, "_execute", low_confidence)
    result = call(tools, "read_historical_page", {"source_id": prior["source_id"], "page": 1})
    candidate = result["associations"][0]
    assert candidate["candidate_answer"] == NARRATIVE
    assert candidate["printed_resolutions"][0]["status"] == "resolved"
    assert "answer_layout" not in candidate
    assert candidate["printed_reading_issues"] == []
    assert reader.transcribe.call_count == 2


@pytest.mark.parametrize(
    ("outcome", "max_pages", "issue", "calls"),
    [
        ("disagrees", 12, "answer:disagrees", 2),
        ("unreadable", 12, "answer:disagrees", 2),
        ("third_reading", 12, "answer:disagrees", 2),
        ("resolved", 1, "answer:budget_exhausted", 1),
    ],
)
def test_plain_answer_recovery_never_chooses_an_unverified_reading(
    tmp_path, monkeypatch, outcome, max_pages, issue, calls
):
    _, tools, reader, prior, _ = narrative_dispute(
        tmp_path,
        monkeypatch,
        outcome=outcome,
        limit=EvidenceLimits(max_ocr_pages=max_pages),
    )
    result = call(tools, "read_historical_page", {"source_id": prior["source_id"], "page": 1})
    first = result["associations"][0]
    assert first["candidate_answer"] is None
    assert first["printed_resolutions"] == []
    assert first["printed_reading_issues"] == [issue]
    assert reader.transcribe.call_count == calls
    assert (
        call(tools, "read_historical_page", {"source_id": prior["source_id"], "page": 1}) == result
    )
    assert reader.transcribe.call_count == calls


def recovered_narrative_draft(tmp_path, monkeypatch, *, outcome="resolved", max_pages=12):
    setup, tools, reader, prior, current = narrative_dispute(
        tmp_path, monkeypatch, outcome=outcome, limit=EvidenceLimits(max_ocr_pages=max_pages)
    )
    request, review = validated_page(
        setup,
        tools,
        prior,
        current,
        answer=NARRATIVE,
        expected_answered=int(outcome == "resolved" and max_pages > 1),
    )
    raw = request.model_dump(mode="json")
    requirement = raw["requirements"]["requirements"][0]
    requirement["kind"] = "narrative"
    raw["requirements"]["requirements"] = [requirement]
    mapping = raw["layout"]["responses"][0]
    mapping["requirement"] = requirement
    mapping["narrative_region"] = {**mapping["text_region"], "bottom": 600.0}
    mapping["text_region"] = None
    raw["layout"]["responses"] = [mapping]
    raw["proposals"]["proposals"][0]["value"] = {"kind": "narrative", "value": NARRATIVE}
    raw["proposals"]["proposals"] = raw["proposals"]["proposals"][:1]
    request = DraftRequest.model_validate_json(json.dumps(raw))
    digest = hashlib.sha256(request.model_dump_json().encode()).hexdigest()
    gated = validate_answers(
        setup.evidence_root,
        request,
        digest,
        historical_context_checks=review.historical_context_checks,
    )
    return setup, reader, request, gated


@pytest.mark.parametrize("tamper", ["none", "crop_hash", "transcription", "confidence"])
def test_recovered_narrative_survives_gate_writer_and_rejects_tampering(
    tmp_path, monkeypatch, tamper
):
    setup, reader, request, review = recovered_narrative_draft(tmp_path, monkeypatch)
    assert review.decisions[0].decision == "draft_verified"
    checks = review.historical_context_checks
    if tamper in ("crop_hash", "transcription"):
        raw = checks[0].model_dump(mode="json")
        reading = raw["printed_readings"][0]
        if tamper == "crop_hash":
            reading["crop_sha256"] = "0" * 64
        else:
            reading["focused"]["text"] = "Agency desk"
        checks = (HistoricalContextCheck.model_validate_json(json.dumps(raw)),)
        basis = request.proposals.proposals[0].historical_basis
        assert basis is not None
        proposal = request.proposals.proposals[0].model_copy(
            update={
                "historical_basis": basis.model_copy(
                    update={"prior_question": checks[0].context_citation}
                )
            }
        )
        request = request.model_copy(
            update={"proposals": request.proposals.model_copy(update={"proposals": (proposal,)})}
        )
    elif tamper == "confidence":
        artifact = setup.evidence_root / checks[0].question.artifact_path
        data = json.loads(artifact.read_bytes())
        data["words"][4]["confidence"] = 20
        artifact.write_text(json.dumps(data))
    digest = hashlib.sha256(request.model_dump_json().encode()).hexdigest()
    gated = validate_answers(setup.evidence_root, request, digest, historical_context_checks=checks)
    assert (gated.decisions[0].decision == "draft_verified") == (tamper == "none")
    # The writer must recheck even a stale positive review.
    stale = review.model_copy(
        update={"request_sha256": digest, "historical_context_checks": checks}
    )
    blank = setup.evidence_root / request.source
    blank.parent.mkdir(parents=True, exist_ok=True)
    blank.write_bytes(setup.blank)
    request_path = Path("outputs/recovered-narrative.json")
    request_bytes = request.model_dump_json().encode()
    (setup.evidence_root / request_path).write_bytes(request_bytes)
    output = publish_draft(
        setup.evidence_root,
        request_path,
        request_bytes,
        request,
        stale,
        stale.model_dump_json().encode(),
        None,
    )
    report = json.loads((output / "draft.json").read_bytes())
    assert (report["answers"][0]["status"] == "written_to_draft") == (tamper == "none")
    text = PdfReader(output / "draft-packet.pdf").pages[0].extract_text()
    assert (NARRATIVE in text) == (tamper == "none")
    if tamper == "none":
        summary = (output / "reviewer-summary.txt").read_text()
        assert "PRINTED-WORDING CHECK: answer; status=resolved" in summary
        assert report["render_checks"]["outside_allowed_regions_changed_pixels"] == 0
    assert reader.transcribe.call_count == 2


def test_recovered_narrative_source_mutation_is_a_technical_failure(tmp_path, monkeypatch):
    from bd_packet_builder.inventory import InventoryError

    setup, _, request, review = recovered_narrative_draft(tmp_path, monkeypatch)
    path = setup.evidence_root / PRIOR
    path.write_bytes(path.read_bytes() + b"\n")
    with pytest.raises(InventoryError, match="Archive source changed"):
        validate_answers(
            setup.evidence_root,
            request,
            review.request_sha256,
            historical_context_checks=review.historical_context_checks,
        )


def test_low_confidence_unmatched_word_stays_disputed_even_after_reread(tmp_path, monkeypatch):
    _, tools, reader, prior, _ = narrative_dispute(tmp_path, monkeypatch, confidence=89)
    result = call(tools, "read_historical_page", {"source_id": prior["source_id"], "page": 1})
    first = result["associations"][0]
    assert first["candidate_answer"] is None
    assert first["printed_reading_issues"] == ["answer:disagrees"]
    assert reader.transcribe.call_count == 2


@pytest.mark.parametrize(
    ("outcome", "max_pages", "status"),
    [("disagrees", 12, "disagrees"), ("resolved", 1, "budget_exhausted")],
)
def test_unresolved_narrative_is_blank_with_recovery_outcome_in_summary(
    tmp_path, monkeypatch, outcome, max_pages, status
):
    setup, reader, request, review = recovered_narrative_draft(
        tmp_path, monkeypatch, outcome=outcome, max_pages=max_pages
    )
    assert review.decisions[0].decision == "withhold"
    blank = setup.evidence_root / request.source
    blank.parent.mkdir(parents=True, exist_ok=True)
    blank.write_bytes(setup.blank)
    raw = request.model_dump_json().encode()
    request_path = Path("outputs/unresolved-narrative.json")
    (setup.evidence_root / request_path).write_bytes(raw)
    output = publish_draft(
        setup.evidence_root,
        request_path,
        raw,
        request,
        review,
        review.model_dump_json().encode(),
        None,
    )
    report = json.loads((output / "draft.json").read_bytes())
    assert report["answers"][0]["status"] == "blank"
    summary = (output / "reviewer-summary.txt").read_text()
    assert f"PRINTED-WORDING CHECK: answer; status={status}" in summary
    assert NARRATIVE not in PdfReader(output / "draft-packet.pdf").pages[0].extract_text()
    assert reader.transcribe.call_count == (1 if max_pages == 1 else 2)


@pytest.mark.parametrize("part", ["question", "role"])
def test_plain_answer_recovery_does_not_resolve_a_disputed_association(tmp_path, monkeypatch, part):
    _, tools, reader, prior, _ = narrative_dispute(tmp_path, monkeypatch)
    initial = reader.transcribe.side_effect
    transcript = next(initial).model_dump(mode="json")
    transcript["historical_fields"][0][part]["text"] = (
        "Account number" if part == "question" else "Account manager"
    )
    reader.transcribe.side_effect = [ScanTranscript.model_validate_json(json.dumps(transcript))]
    result = call(tools, "read_historical_page", {"source_id": prior["source_id"], "page": 1})
    first = result["associations"][0]
    assert first["candidate_answer"] is None
    assert first["printed_resolutions"] == []
    assert any(d["part"] == part for d in first["discrepancies"])
    assert reader.transcribe.call_count == 1


def test_v8_plain_answer_receipts_replay_without_new_recovery(tmp_path, monkeypatch):
    setup, tools, _, prior, _ = narrative_dispute(tmp_path, monkeypatch)
    call(tools, "read_historical_page", {"source_id": prior["source_id"], "page": 1})
    call(tools, "finish_evidence")
    raw = json.loads(setup.artifact("historical_context_checks.json"))["checks"][0]
    raw["version"] = "historical-page-context-v8"
    raw["printed_readings"] = []
    raw["discrepancies"][0]["code"] = "historical_text_or_region_disagrees"
    raw["discrepancies"][0]["selection_reason"] = (
        "Neither reading is preferred. Compare the localized alternatives with "
        "independent identity-linked evidence before choosing a value. "
        "If the difference cannot be resolved, leave the field blank."
    )
    legacy = HistoricalContextCheck.model_validate_json(json.dumps(raw))
    payload = json.dumps(raw, separators=(",", ":"), ensure_ascii=False).encode()
    assert legacy.context_citation.check_sha256 == hashlib.sha256(payload).hexdigest()
    from bd_packet_builder.history import with_historical_sources
    from bd_packet_builder.inventory import build_inventory

    inventory = with_historical_sources(
        setup.evidence_root,
        build_inventory(setup.evidence_root),
        setup.store.load(setup.manifest.run_id).request.historical_archive,
    )
    artifact = (setup.evidence_root / legacy.question.artifact_path).read_bytes()
    assert legacy.printed_readings == ()
    assert legacy.answer_disputed
    assert legacy.recheck(setup.evidence_root, inventory, artifact, allow_disagreements=True)


def test_v9_recovery_receipt_keeps_its_hash_and_replays_without_layout_checks(
    tmp_path, monkeypatch
):
    from bd_packet_builder.history import with_historical_sources
    from bd_packet_builder.inventory import build_inventory

    setup, tools, _, prior, _ = narrative_dispute(tmp_path, monkeypatch)
    call(tools, "read_historical_page", {"source_id": prior["source_id"], "page": 1})
    call(tools, "finish_evidence")
    raw = json.loads(setup.artifact("historical_context_checks.json"))["checks"][0]
    raw["version"] = "historical-page-context-v9"
    raw["prompt_version"] = "scan-cross-check-v6"
    payload = json.dumps(raw, separators=(",", ":"), ensure_ascii=False).encode()
    legacy = HistoricalContextCheck.model_validate_json(payload)
    assert legacy.context_citation.check_sha256 == hashlib.sha256(payload).hexdigest()
    assert not legacy.answer_disputed
    inventory = with_historical_sources(
        setup.evidence_root,
        build_inventory(setup.evidence_root),
        setup.store.load(setup.manifest.run_id).request.historical_archive,
    )
    artifact = (setup.evidence_root / legacy.question.artifact_path).read_bytes()
    assert legacy.recheck(setup.evidence_root, inventory, artifact, allow_disagreements=True)


def test_role_answer_swap_is_withheld_by_page_geometry(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _, tools, _, prior, _ = setup_page(tmp_path, monkeypatch, swapped=True)
    result = call(tools, "read_historical_page", {"source_id": prior["source_id"], "page": 1})
    assert len(result["associations"]) == 1
    assert result["associations"][0]["answer_citation"]["quote"] == "Blair Example"
    assert result["issues"][0]["code"] == "historical_answer_not_adjacent_to_question"


def test_unapproved_source_cannot_use_historical_page_tool(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _, tools, reader, _, current = setup_page(tmp_path, monkeypatch)
    result = json.loads(
        tools.call(
            "read_historical_page",
            json.dumps(
                {
                    "source_id": current["source_id"],
                    "page": 1,
                }
            ),
        )
    )
    assert not result["ok"]
    reader.transcribe.assert_not_called()
