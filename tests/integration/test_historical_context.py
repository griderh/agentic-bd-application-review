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
    primary_answer: str = NAME,
    control_state: str | None = None,
    second_control: bool = False,
    subheader: bool = False,
    historical_policy: str = "conservative",
    control_on_right: bool = False,
    secondary_role: str = "Backup representative",
    secondary_question: str = "Name",
    secondary_answer: str = "Blair Example",
    primary_role: str = "Primary representative",
    evidence_text: str = EVIDENCE_TEXT,
    scanned_current: bool = False,
    primary_write_in: str | None = None,
    primary_x_offset: int = 0,
    unboxed_control: bool = False,
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
                canvas.line(x + 5, 709, x + 17, 730)
                canvas.setLineWidth(1)
            else:
                canvas.line(x + 2, 710, x + 10, 718)
                canvas.line(x + 2, 718, x + 10, 710)
    if second_control:
        canvas.rect(278, 708, 12, 12)
        canvas.line(280, 710, 288, 718)
        canvas.line(280, 718, 288, 710)
    if scanned_answer:
        canvas.drawString((470 if right_column else 180) + primary_x_offset, 710, primary_answer)
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
        if primary_write_in is not None:
            for index, line in enumerate(primary_write_in.splitlines()):
                canvas.drawString(240 + primary_x_offset, 710 - index * 12, line)
        if not scanned_answer:
            canvas.drawString(470 if right_column else 180, 710, primary_answer)
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
                    else primary_question
                ),
                "box": box(60, 95, 140, 120),
            },
            "role": {"text": primary_role, "box": box(60, 55, 350, 80)},
            "answer": {"text": primary_answer, "box": box(290, 95, 480, 120)},
        },
        {
            "question": {"text": secondary_question, "box": box(60, 270, 140, 295)},
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
        fields[0]["answer"]["box"] = box(780, 95, 960, 120)
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
    if competing_header:
        words[2:2] = [("Desk", 1375, 170), ("manager", 1600, 170)]
    if primary_x_offset:
        words[:5] = [(text, x + primary_x_offset * 2500 // 600, y) for text, x, y in words[:5]]
    header = (
        "level\tpage_num\tblock_num\tpar_num\tline_num\tword_num\t"
        "left\ttop\twidth\theight\tconf\ttext\n"
    )
    tsv = header + "".join(
        f"5\t1\t1\t1\t{i + 1}\t1\t{x}\t{y}\t180\t40\t"
        f"{89 if repeated_answer and text in ('Avery', 'Example') else confidence}\t{text}\n"
        for i, (text, x, y) in enumerate(words)
    )
    monkeypatch.setattr(
        "bd_packet_builder.ocr._execute",
        lambda command, *_: "tesseract 5.5.0\n" if "--version" in command else tsv,
    )
    tools = setup.tools(scan_reader=reader, evidence_limits=evidence_limits)
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


def validated_page(setup, tools, prior, current, expected_answered=1):
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
        "value": {"kind": "text", "value": NAME},
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
    ["historical-page-context-v4", "historical-page-context-v5", "historical-page-context-v6"],
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
    if version != "historical-page-context-v6":
        raw["field"].pop("write_in")
    if version == "historical-page-context-v4":
        raw["field"].pop("control")
    for field in raw["transcript"]["historical_fields"]:
        if version != "historical-page-context-v6":
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
