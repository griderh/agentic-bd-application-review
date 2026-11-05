import hashlib
import json
from contextlib import closing
from io import BytesIO
from pathlib import Path
from unittest.mock import Mock

import pypdfium2 as pdfium
import pytest
from reportlab.lib.utils import ImageReader
from reportlab.pdfbase.pdfmetrics import stringWidth
from reportlab.pdfgen.canvas import Canvas

from bd_packet_builder.draft import DraftDecision, DraftRequest, DraftReview, publish_draft
from bd_packet_builder.evidence_tools import EvidenceLimits
from bd_packet_builder.foundry import FoundryConfig
from bd_packet_builder.gate import validate_answers
from bd_packet_builder.history import ArchiveEntry, ArchiveManifest
from bd_packet_builder.live import LiveRunRequest, prepare_live_run
from bd_packet_builder.scan import ScanTranscript
from bd_packet_builder.visual import VisualPage
from tests.integration.test_agent import Setup, nbox
from tests.integration.test_historical_prefill import call
from tests.unit.test_question_reading import QUESTION


def question_run(
    tmp_path,
    monkeypatch,
    ocr_question,
    *,
    mark=True,
    interleaved=False,
    image_question=QUESTION,
    native=False,
    focused=None,
    answer_label="No",
    image_answer=None,
    image_budget=5,
    confidence=96,
    focused_readable=True,
):
    def form(selected):
        data = BytesIO()
        canvas = Canvas(data, pagesize=(612, 792), invariant=True)
        canvas.setFont("Helvetica", 9)
        canvas.drawString(40, 740, QUESTION)
        for x, label in ((40, "Yes"), (140, answer_label)):
            canvas.rect(x, 698, 10, 10)
            canvas.drawString(x + 20, 700, label)
        if selected:
            canvas.line(142, 700, 148, 706)
            canvas.line(142, 706, 148, 700)
        canvas.save()
        return data.getvalue()

    blank, prior = form(False), form(mark)
    mapper = Mock()
    mapper.map_pages.return_value = {
        1: VisualPage.model_validate_json(
            json.dumps(
                {
                    "readable": True,
                    "explanation": None,
                    "items": [
                        {
                            "item_id": "q6",
                            "instruction": QUESTION,
                            "kind": "single_select",
                            "region": None,
                            "explanation": None,
                            "instruction_box": nbox(35, 40, 580, 65),
                            "options": [
                                {
                                    "option_id": "yes" if x == 40 else "no",
                                    "label": label,
                                    "instruction": label,
                                    "control": "checkbox",
                                    "write_in_region": None,
                                    "box": nbox(x, 84, x + 10, 94),
                                    "label_box": nbox(
                                        x + 20, 81, x + 20 + stringWidth(label, "Helvetica", 9), 96
                                    ),
                                }
                                for x, label in ((40, "Yes"), (140, answer_label))
                            ],
                        }
                    ],
                }
            )
        )
    }
    setup = Setup(tmp_path, blank, mapper=mapper)
    target = setup.evidence_root / "bd_agreements/Blank/application.pdf"
    target.parent.mkdir(parents=True)
    target.write_bytes(blank)
    relative = "bd_agreements/Completed/Synthetic/prior.pdf"
    path = setup.evidence_root / relative
    path.parent.mkdir(parents=True)
    if native:
        path.write_bytes(prior)
    else:
        with (
            pdfium.PdfDocument(prior) as document,
            closing(document[0]) as page,
            closing(page.render(scale=2)) as bitmap,
            closing(bitmap.to_pil()) as image,
        ):
            canvas = Canvas(str(path), pagesize=(612, 792), invariant=True)
            canvas.drawImage(ImageReader(image), 0, 0, 612, 792)
            canvas.save()
    setup.manifest = prepare_live_run(
        setup.store,
        LiveRunRequest(
            blank_name="Synthetic.pdf",
            requester_id="offline",
            evidence_set_id="synthetic-question",
            issuer="Synthetic",
            historical_policy="answer_first_review",
            historical_archive=ArchiveManifest(
                entries=(
                    ArchiveEntry(
                        path=relative,
                        sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
                        partition="reference",
                        issuer="Synthetic",
                    ),
                )
            ),
        ),
        blank,
        setup.evidence_root,
        FoundryConfig(endpoint="https://example.openai.azure.com/openai/v1", deployment="test"),
    )
    reader = Mock()
    reader.transcribe.return_value = ScanTranscript.model_validate_json(
        json.dumps(
            {
                "readable": True,
                "subject": None,
                "reporting_period": None,
                "text": QUESTION + "\nNo",
                "historical_fields": [
                    {
                        "question": {"text": image_question, "box": nbox(35, 40, 580, 65)},
                        "role": None,
                        "answer": {
                            "text": image_answer or answer_label,
                            "box": nbox(
                                148 if image_answer else 160,
                                81,
                                300 if image_answer else 185,
                                96,
                            ),
                        },
                        "control": {"state": "selected", "box": nbox(140, 84, 150, 94)},
                    }
                ],
            }
        )
    )
    if focused is not None:
        reader.transcribe.side_effect = [
            reader.transcribe.return_value,
            ScanTranscript(
                readable=focused_readable, subject=None, reporting_period=None, text=focused
            ),
        ]
    header = (
        "level\tpage_num\tblock_num\tpar_num\tline_num\tword_num\t"
        "left\ttop\twidth\theight\tconf\ttext\n"
    )
    words = []
    x = 40.0
    for word in ocr_question.split():
        width = stringWidth(word, "Helvetica", 9)
        words.append((word, x, 44, width, 1))
        x += width + stringWidth(" ", "Helvetica", 9)
    words.append(("Yes", 60, 83, 16, 2))
    x = 160.0
    for word in answer_label.split():
        width = stringWidth(word, "Helvetica", 9)
        words.append((word, x, 83, width, 2))
        x += width + stringWidth(" ", "Helvetica", 9)
    if interleaved:
        words.insert(5, ("unrelated", 595, 44, 10, 3))
    scale = 300 / 72
    tsv = header + "".join(
        f"5\t1\t1\t1\t{line}\t{i + 1}\t{round(x * scale)}\t{round(y * scale)}\t"
        f"{max(1, round(width * scale))}\t38\t{confidence}\t{word}\n"
        for i, (word, x, y, width, line) in enumerate(words)
    )
    monkeypatch.setattr("bd_packet_builder.ocr.shutil.which", lambda _: "/local/tesseract")
    monkeypatch.setattr(
        "bd_packet_builder.ocr._execute",
        lambda command, *_: "tesseract 5.5.0\n" if "--version" in command else tsv,
    )
    tools = setup.tools(
        scan_reader=reader, evidence_limits=EvidenceLimits(max_ocr_pages=image_budget)
    )
    call(tools, "interpret_form")
    sources = call(tools, "list_sources")["sources"]
    source = next(s for s in sources if s["family"] == "historical_reference")
    result = call(tools, "read_historical_page", {"source_id": source["source_id"], "page": 1})
    call(tools, "finish_evidence")
    return setup, tools, result


@pytest.mark.parametrize("part", ["question", "option"])
@pytest.mark.parametrize("method", ["native", "focused", "unresolved"])
def test_printed_wording_resolution_preserves_selection(tmp_path, monkeypatch, part, method):
    wrong_question = QUESTION.replace("temporarily", "permanently")
    label = "Regional 3760" if part == "option" else "No"
    setup, tools, result = question_run(
        tmp_path,
        monkeypatch,
        QUESTION,
        image_question=wrong_question if part == "question" else QUESTION,
        native=method == "native",
        focused=(QUESTION if part == "question" else label)
        if method == "focused"
        else "unresolved wording",
        answer_label=label,
        image_answer="Regional 3670" if part == "option" else None,
    )
    candidate = result["associations"][0]
    assert bool(candidate.get("printed_resolutions")) == (method != "unresolved")
    if method != "unresolved":
        assert candidate["question"] == QUESTION
        assert candidate["candidate_answer"] == label
        if part == "question":
            assert candidate["question_reconciliation"]["status"] == (
                "resolved_against_historical_source"
            )
        assert candidate["discrepancies"]  # Original readings must remain auditable.
        assert (
            json.loads(setup.artifact("answer_handoff.json"))["historical_candidates"][0][
                "printed_resolutions"
            ]
            == candidate["printed_resolutions"]
        )
    call(
        tools,
        "submit_answers",
        {
            "proposals": [
                {
                    "requirement_id": "p1.q6",
                    "outcome": "proposed",
                    "confidence": 0.9,
                    "value": {"kind": "single_select", "selected": ["no"]},
                    "citations": [candidate["answer_citation"]],
                    "historical_basis": {
                        "category": "disclosure",
                        "context": "firm_wide",
                        "prior_question": candidate["context_citation"],
                        "current_checks": [],
                        "reviewer_confirmation": "Confirm historical continuity.",
                    },
                }
            ]
        },
    )
    request = DraftRequest.model_validate_json(setup.artifact("draft_request.json"))
    review = DraftReview.model_validate_json(setup.artifact("answer_review.json"))
    assert (review.decisions[0].decision == "draft_verified") == (method != "unresolved"), (
        review.decisions[0].reason
    )
    if method != "unresolved":
        conservative = validate_answers(
            setup.evidence_root,
            request.model_copy(update={"historical_policy": "conservative"}),
            "a" * 64,
            historical_context_checks=review.historical_context_checks,
        )
        assert conservative.decisions[0].decision == "withhold"
    # Even a positive review cannot bypass unresolved or tampered printed wording.
    raw = request.model_dump_json().encode()
    (setup.evidence_root / "outputs/printed-request.json").write_bytes(raw)
    forged = review.model_copy(
        update={
            "request_sha256": hashlib.sha256(raw).hexdigest(),
            "decisions": (
                DraftDecision(
                    requirement_id="p1.q6",
                    decision="draft_verified",
                    reason="Test review",
                    evidence_status="historical_continuity_unconfirmed",
                    evidence_support_confirmed=True,
                    source_approved=True,
                    placement_confirmed=True,
                ),
            ),
        }
    )
    output = publish_draft(
        setup.evidence_root,
        Path("outputs/printed-request.json"),
        raw,
        request,
        forged,
        forged.model_dump_json().encode(),
        None,
    )
    report = json.loads((output / "draft.json").read_bytes())
    assert bool(report["written_requirements"]) == (method != "unresolved")
    assert report["render_checks"]["outside_allowed_regions_changed_pixels"] == 0
    summary = (output / "reviewer-summary.txt").read_text()
    assert "PRINTED-WORDING CHECK" in summary
    usage = json.loads(setup.artifact("answer_handoff.json"))["reading_usage"]
    assert usage["independent_image_pages"] == (1 if method == "native" else 2)
    if method != "unresolved":
        from bd_packet_builder.draft import selected_inventory

        check = review.historical_context_checks[0]
        assert check.printed_readings
        reading = check.printed_readings[0]
        forged_reading = reading.model_copy(
            update={
                "native": reading.native.model_copy(update={"quote": "not the source"})
                if reading.native
                else None,
                "crop_sha256": "f" * 64 if reading.focused else None,
            }
        )
        tampered = check.model_copy(update={"printed_readings": (forged_reading,)})
        citation = check.question
        raw_ocr = setup.store.read_artifact(
            setup.manifest.run_id, f"ocr-{citation.artifact_sha256}.json"
        )
        assert not tampered.recheck(
            setup.evidence_root,
            selected_inventory(setup.evidence_root, request),
            raw_ocr,
            allow_disagreements=True,
        )


@pytest.mark.parametrize("change", ["budget", "unreadable", "low_confidence", "no_mark", "target"])
def test_focused_reading_does_not_override_remaining_constraints(tmp_path, monkeypatch, change):
    observed = QUESTION.replace("temporarily", "permanently") if change == "target" else QUESTION
    setup, tools, result = question_run(
        tmp_path,
        monkeypatch,
        observed,
        image_question=QUESTION.replace("temporarily", "uncertain"),
        focused=observed,
        focused_readable=change != "unreadable",
        image_budget=1 if change == "budget" else 5,
        confidence=80 if change == "low_confidence" else 96,
        mark=change != "no_mark",
    )
    candidate = result["associations"][0]
    assert not candidate["question_reconciliation"]
    assert bool(candidate["printed_resolutions"]) == (change == "target")
    call(
        tools,
        "submit_answers",
        {
            "proposals": [
                {
                    "requirement_id": "p1.q6",
                    "outcome": "proposed",
                    "confidence": 0.9,
                    "value": {"kind": "single_select", "selected": ["no"]},
                    "citations": [candidate["answer_citation"]],
                    "historical_basis": {
                        "category": "disclosure",
                        "context": "firm_wide",
                        "prior_question": candidate["context_citation"],
                        "current_checks": [],
                        "reviewer_confirmation": "Confirm continuity.",
                    },
                }
            ]
        },
    )
    review = DraftReview.model_validate_json(setup.artifact("answer_review.json"))
    assert review.decisions[0].decision == "withhold"


@pytest.mark.parametrize(
    "change",
    [
        "fragment",
        "spacing",
        "negation",
        "condition",
        "missing",
        "no_mark",
        "interleaved",
        "abstained",
    ],
)
def test_question_reconciliation_reaches_handoff_gate_and_independent_writer(
    tmp_path, monkeypatch, change
):
    ocr = {
        "fragment": QUESTION.replace("temporarily", "emp"),
        "spacing": QUESTION.replace("temporarily", "tempor arily"),
        "negation": QUESTION.replace("ever", "never"),
        "condition": QUESTION.replace("temporarily", "permanently"),
        "missing": QUESTION.replace("temporarily ", ""),
        "no_mark": QUESTION.replace("temporarily", "emp"),
        "interleaved": QUESTION,
        "abstained": QUESTION.replace("temporarily", "emp"),
    }[change]
    setup, tools, result = question_run(
        tmp_path, monkeypatch, ocr, mark=change != "no_mark", interleaved=change == "interleaved"
    )
    candidate = result["associations"][0]
    accepted = change in ("fragment", "spacing")
    assert bool(candidate["question_reconciliation"]) == (accepted or change == "abstained")
    if candidate["question_reconciliation"]:
        assert candidate["question_reconciliation"]["target_requirement_ids"] == ["p1.q6"]
    handoff = json.loads(setup.artifact("answer_handoff.json"))
    assert (
        handoff["historical_candidates"][0]["question_reconciliation"]
        == candidate["question_reconciliation"]
    )
    proposal = {
        "requirement_id": "p1.q6",
        "outcome": "proposed",
        "confidence": 0.9,
        "value": {"kind": "single_select", "selected": ["no"]},
        "citations": [candidate["answer_citation"]],
        "historical_basis": {
            "category": "disclosure",
            "context": "firm_wide",
            "prior_question": candidate["context_citation"],
            "current_checks": [],
            "reviewer_confirmation": "Confirm historical continuity before use.",
        },
    }
    if change == "abstained":
        proposal.update(
            outcome="conflicting_evidence",
            value=None,
            historical_basis=None,
            explanation="Question OCR differs; no answer proposed.",
        )
    call(tools, "submit_answers", {"proposals": [proposal]})
    request = DraftRequest.model_validate_json(setup.artifact("draft_request.json"))
    review = DraftReview.model_validate_json(setup.artifact("answer_review.json"))
    assert (review.decisions[0].decision == "draft_verified") == accepted, review.decisions[
        0
    ].reason
    if not accepted and change not in ("no_mark", "abstained"):
        assert "historical_question_reading_unresolved" in review.decisions[0].reason
    if accepted:
        assert (
            validate_answers(
                setup.evidence_root,
                request.model_copy(update={"historical_policy": "conservative"}),
                "a" * 64,
                historical_context_checks=review.historical_context_checks,
            )
            .decisions[0]
            .decision
            == "withhold"
        )
    # A forged positive gate decision must not bypass the writer's independent checks.
    forged = review.model_copy(
        update={
            "decisions": (
                DraftDecision(
                    requirement_id="p1.q6",
                    decision="draft_verified",
                    reason="Forged test review",
                    evidence_status="historical_continuity_unconfirmed",
                    evidence_support_confirmed=True,
                    source_approved=True,
                    placement_confirmed=True,
                ),
            )
        }
    )
    raw = request.model_dump_json().encode()
    (setup.evidence_root / "outputs/question-request.json").write_bytes(raw)
    forged = forged.model_copy(update={"request_sha256": hashlib.sha256(raw).hexdigest()})
    output = publish_draft(
        setup.evidence_root,
        Path("outputs/question-request.json"),
        raw,
        request,
        forged,
        forged.model_dump_json().encode(),
        None,
    )
    report = json.loads((output / "draft.json").read_bytes())
    assert bool(report["written_requirements"]) == accepted
    assert report["render_checks"]["outside_allowed_regions_changed_pixels"] == 0
    summary = (output / "reviewer-summary.txt").read_text()
    if accepted:
        assert "FILLED AFTER QUESTION-TEXT RECONCILIATION" in summary
        assert "Historical continuity remains unconfirmed" in summary
        assert "image_reading" in summary and "ocr_reading" in summary
    elif change == "abstained":
        assert "Question transcription is already resolved" in summary
        assert "answer was not written" in summary
        assert "do not request new business evidence solely for this OCR defect" in summary
    else:
        assert "Question wording, answer text and selected marks are checked separately" in summary
        if change != "no_mark":
            assert (
                "current business evidence is not required merely to repair transcription"
                in summary
            )
