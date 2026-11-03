import hashlib
import json
from io import BytesIO
from pathlib import Path

import pytest
from pypdf import PdfReader
from reportlab.pdfgen.canvas import Canvas

from bd_packet_builder.draft import DraftRequest, publish_draft
from bd_packet_builder.gate import validate_answers
from tests.integration.test_historical_context import setup_page
from tests.integration.test_historical_prefill import call


@pytest.mark.parametrize(
    "case",
    [
        "checked",
        "native_context",
        "unrelated_answer_citation",
        "missing",
        "wrong_subject",
        "contradicts",
        "changed_artifact",
    ],
)
def test_current_scan_check_is_not_implicit_answer_support(tmp_path, monkeypatch, case):
    from bd_packet_builder import ocr
    from bd_packet_builder.draft import DraftReview
    from bd_packet_builder.historical_context import HistoricalContextCheck
    from bd_packet_builder.scan import ScanCheck, ScanTranscript

    text = "Firm registration: Example Securities CRD Number 1234567"
    setup, tools, reader, prior, current = setup_page(
        tmp_path, monkeypatch, scanned_current=True, evidence_text=text
    )
    prior_read = call(tools, "read_historical_page", {"source_id": prior["source_id"], "page": 1})
    association = prior_read["associations"][0]
    tokens = text.split()
    tsv = (
        "level\tpage_num\tblock_num\tpar_num\tline_num\tword_num\t"
        "left\ttop\twidth\theight\tconf\ttext\n"
    ) + "".join(
        f"5\t1\t1\t1\t1\t{i + 1}\t{40 + i * 150}\t400\t140\t40\t96\t{token}\n"
        for i, token in enumerate(tokens)
    )
    monkeypatch.setattr(
        ocr,
        "_execute",
        lambda command, *_: "tesseract 5.5.0\n" if "--version" in command else tsv,
    )
    reader.transcribe.return_value = ScanTranscript(
        readable=True, subject="Example Securities", text=text, reporting_period=None
    )
    call(tools, "read_page", {"source_id": current["source_id"], "page": 1})
    checked = call(
        tools,
        "verify_scan_quote",
        {
            "source_id": current["source_id"],
            "page": 1,
            "quote": text,
            "expected_subject": "Example Securities",
        },
    )
    call(tools, "finish_evidence")
    proposal = {
        "requirement_id": "p1.name",
        "outcome": "proposed",
        "confidence": 0.9,
        "value": {"kind": "text", "value": "Avery Example"},
        "citations": [association["answer_citation"]],
        "historical_basis": {
            "category": "contact",
            "context": "issuer_specific",
            "prior_question": association["context_citation"],
            "role": "Primary representative",
            "current_checks": [
                {
                    "citation": checked["citation"],
                    "finding": "contradicts" if case == "contradicts" else "not_corroborated",
                    "explanation": "Firm registration does not establish the assignment.",
                }
            ],
            "reviewer_confirmation": "Confirm current assignment.",
        },
    }
    if case == "native_context":
        historical = json.loads(setup.artifact("historical_context_checks.json"))["checks"]
        proposal["historical_basis"]["prior_question"] = historical[0]["answer"]
    if case == "unrelated_answer_citation":
        proposal["citations"].append(checked["citation"])
    call(tools, "submit_answers", {"proposals": [proposal]})
    request_bytes = setup.artifact("draft_request.json")
    request = DraftRequest.model_validate_json(request_bytes)
    blank = setup.evidence_root / request.source
    blank.parent.mkdir(parents=True, exist_ok=True)
    blank.write_bytes(setup.blank)
    checks = tuple(
        HistoricalContextCheck.model_validate_json(json.dumps(c))
        for c in json.loads(setup.artifact("historical_context_checks.json"))["checks"]
    )
    scans = tuple(
        ScanCheck.model_validate_json(json.dumps(c))
        for c in json.loads(setup.artifact("scan_checks.json"))["checks"]
    )
    if case == "missing":
        scans = ()
    elif case == "wrong_subject":
        scans = (scans[0].model_copy(update={"expected_subject": "Unrelated Firm"}),)
    review = validate_answers(
        setup.evidence_root,
        request,
        hashlib.sha256(request_bytes).hexdigest(),
        historical_context_checks=checks,
        scan_checks=scans,
    )
    assert (review.decisions[0].decision == "draft_verified") == (
        case in ("checked", "native_context", "changed_artifact")
    ), review.decisions[0].reason
    if case == "changed_artifact":
        artifact = setup.evidence_root / checked["citation"]["artifact_path"]
        artifact.write_bytes(artifact.read_bytes() + b"\n")
    # A forged decision must not let missing evidence bypass the independent writer.
    raw_review = review.model_dump(mode="json")
    raw_review["decisions"][0]["decision"] = "draft_verified"
    raw_review["decisions"][0].update(
        evidence_support_confirmed=True, source_approved=True, placement_confirmed=True
    )
    review = DraftReview.model_validate_json(json.dumps(raw_review))
    path = setup.evidence_root / "outputs/scan-current-request.json"
    path.write_bytes(request_bytes)
    output = publish_draft(
        setup.evidence_root,
        Path("outputs/scan-current-request.json"),
        request_bytes,
        request,
        review,
        review.model_dump_json().encode(),
        None,
    )
    packet = PdfReader(output / "draft-packet.pdf")
    assert ("Avery Example" in packet.pages[0].extract_text()) == (
        case in ("checked", "native_context")
    )
    if case in ("checked", "native_context"):
        assert (
            "HISTORICAL - CONTINUITY UNCONFIRMED" in (output / "reviewer-summary.txt").read_text()
        )


@pytest.mark.parametrize(
    "case",
    [
        "ocr",
        "image",
        "no_resolution",
        "wrong_person",
        "wrong_label",
        "third_value",
        "same_source",
        "verified_scan",
        "unverified_scan",
        "tampered_check",
        "native_numeric",
        "native_numeric_low_confidence",
        "native_numeric_disagrees",
    ],
)
def test_disputed_identifier_requires_identity_linked_independent_evidence(
    tmp_path, monkeypatch, case
):
    from bd_packet_builder import ocr

    chosen = "765432" if case == "image" else "7654321"
    if case == "third_value":
        chosen = "9999999"
    subject = "Blair Example" if case == "wrong_person" else "Avery Example"
    label = "Telephone" if case == "wrong_label" else "CRD Number"
    current_text = f"Individual registration record: {subject} {label}: {chosen}"
    scan_current = case in ("verified_scan", "unverified_scan", "tampered_check")
    native_numeric = case.startswith("native_numeric")
    setup, tools, reader, prior, current = setup_page(
        tmp_path,
        monkeypatch,
        scanned_answer=not native_numeric,
        primary_question="CRD Number",
        primary_answer="9999999"
        if case == "native_numeric_disagrees"
        else "7654321"
        if native_numeric
        else "765432",
        secondary_role="Primary representative",
        secondary_answer="Avery Example",
        historical_policy="answer_first_review",
        evidence_text=current_text + ". Synthetic evidence only.",
        scanned_current=scan_current,
    )
    if native_numeric:
        transcript = reader.transcribe.return_value.model_dump(mode="json")
        transcript["historical_fields"][0]["answer"]["text"] = "765432"
        transcript["text"] = transcript["text"].replace("7654321", "765432")
        from bd_packet_builder.scan import ScanTranscript

        reader.transcribe.return_value = ScanTranscript.model_validate_json(json.dumps(transcript))
    execute = ocr._execute

    def numeric_ocr(command, *args):
        output = execute(command, *args)
        if "--version" in command:
            return output
        lines = []
        for line in output.splitlines():
            fields = line.split("\t")
            if len(fields) == 12 and fields[7] == "330":
                if fields[-1] == "CRD Number":
                    fields[8] = "70"
                    fields[-1] = "CRD"
                    lines.append("\t".join(fields))
                    fields[6], fields[-1] = "260", "Number"
                    line = "\t".join(fields)
                if fields[-1] == "Example":
                    continue
                if fields[-1] == "Avery":
                    fields[-1] = "7654321"
                    if case == "native_numeric_low_confidence":
                        fields[10] = "40"
                    line = "\t".join(fields)
            lines.append(line)
        return "\n".join(lines) + "\n"

    monkeypatch.setattr(ocr, "_execute", numeric_ocr)
    reading = call(tools, "read_historical_page", {"source_id": prior["source_id"], "page": 1})
    disputed, name = reading["associations"]
    assert disputed["answer_citation"]["quote"] == "7654321"
    assert any(d["image_reading"] == "765432" for d in disputed["discrepancies"])
    assert disputed["candidate_answer"] == ("7654321" if case == "native_numeric" else None)
    if scan_current:
        # A separate synthetic OCR boundary and blind reading for the current report.
        tokens = current_text.split()
        header = (
            "level\tpage_num\tblock_num\tpar_num\tline_num\tword_num\t"
            "left\ttop\twidth\theight\tconf\ttext\n"
        )
        tsv = header + "".join(
            f"5\t1\t1\t1\t1\t{i + 1}\t{40 + i * 150}\t400\t140\t40\t96\t{token}\n"
            for i, token in enumerate(tokens)
        )
        monkeypatch.setattr(
            ocr,
            "_execute",
            lambda command, *_: "tesseract 5.5.0\n" if "--version" in command else tsv,
        )
        from bd_packet_builder.scan import ScanTranscript

        reader.transcribe.return_value = ScanTranscript(
            readable=True,
            subject=subject,
            text=current_text,
            reporting_period=None,
        )
        call(tools, "read_page", {"source_id": current["source_id"], "page": 1})
        verified = call(
            tools,
            "verify_scan_quote",
            {
                "source_id": current["source_id"],
                "page": 1,
                "quote": current_text,
                "expected_subject": subject,
            },
        )
        citation = verified["citation"]
    else:
        citation = call(
            tools,
            "locate_quote",
            {"source_id": current["source_id"], "page": 1, "quote": current_text},
        )
        citation.pop("occurrences")
    call(tools, "finish_evidence")
    proposal = {
        "requirement_id": "p1.name",
        "outcome": "proposed",
        "confidence": 0.9,
        "value": {"kind": "identifier", "value": chosen},
        "citations": [disputed["answer_citation"], citation],
        "historical_basis": {
            "category": "contact",
            "context": "issuer_specific",
            "prior_question": disputed["context_citation"],
            "role": "Primary representative",
            "current_checks": [],
            "reviewer_confirmation": "Confirm current assignment.",
        },
    }
    if scan_current:
        proposal["historical_basis"]["current_checks"] = [
            {
                "citation": citation
                | ({"artifact_sha256": "0" * 64} if case == "tampered_check" else {}),
                "finding": "corroborates",
                "explanation": "Current subject-aware checked scan supports the identifier.",
            }
        ]
    if case != "no_resolution" and not native_numeric:
        proposal["historical_basis"]["reading_resolution"] = {
            "subject": "Avery Example",
            "subject_context": name["context_citation"],
            "field_label": "CRD Number",
            "citation": disputed["answer_citation"] if case == "same_source" else citation,
        }
    # Build the trusted form contract independently of the untrusted model proposal.
    call(tools, "submit_answers", {"proposals": [proposal]})
    raw = json.loads(setup.artifact("draft_request.json"))
    requirement = raw["requirements"]["requirements"][0]
    requirement.update(kind="identifier", instruction="CRD Number")
    raw["layout"]["responses"][0]["requirement"] = requirement
    raw["proposals"]["proposals"] = [
        proposal if p["requirement_id"] == "p1.name" else p for p in raw["proposals"]["proposals"]
    ]
    buffer = BytesIO()
    canvas = Canvas(buffer, pagesize=(612, 792), invariant=True)
    canvas.drawString(40, 732, "CRD Number")
    canvas.drawString(40, 452, "Signature of authorized officer")
    canvas.drawString(40, 392, "Date")
    canvas.save()
    blank_bytes = buffer.getvalue()
    digest = hashlib.sha256(blank_bytes).hexdigest()
    raw["layout"]["application_sha256"] = digest
    for r in raw["requirements"]["requirements"]:
        r["application_sha256"] = digest
    for m in raw["layout"]["responses"]:
        m["requirement"]["application_sha256"] = digest
    request_bytes = json.dumps(raw).encode()
    request = DraftRequest.model_validate_json(request_bytes)
    blank = setup.evidence_root / request.source
    blank.parent.mkdir(parents=True, exist_ok=True)
    blank.write_bytes(blank_bytes)
    from bd_packet_builder.historical_context import HistoricalContextCheck

    checks = tuple(
        HistoricalContextCheck.model_validate_json(json.dumps(c))
        for c in json.loads(setup.artifact("historical_context_checks.json"))["checks"]
    )
    assert "crd number" in " ".join(checks[0].question.quote.lower().split()), checks[0].question
    from bd_packet_builder.scan import ScanCheck

    scans = (
        tuple(
            ScanCheck.model_validate_json(json.dumps(c))
            for c in json.loads(setup.artifact("scan_checks.json"))["checks"]
        )
        if case != "unverified_scan"
        else ()
    )
    review = validate_answers(
        setup.evidence_root,
        request,
        hashlib.sha256(request_bytes).hexdigest(),
        historical_context_checks=checks,
        scan_checks=scans,
    )
    accepted = case in ("ocr", "image", "verified_scan", "native_numeric")
    assert (review.decisions[0].decision == "draft_verified") == accepted, review.decisions[
        0
    ].reason
    (setup.evidence_root / "outputs/resolution-request.json").write_bytes(request_bytes)
    output = publish_draft(
        setup.evidence_root,
        Path("outputs/resolution-request.json"),
        request_bytes,
        request,
        review,
        review.model_dump_json().encode(),
        None,
    )
    summary = (output / "reviewer-summary.txt").read_text()
    if accepted:
        report = json.loads((output / "draft.json").read_text())
        assert report["written_requirements"] == ["p1.name"]
        assert report["render_checks"]["outside_allowed_regions_changed_pixels"] == 0
        assert chosen in PdfReader(output / "draft-packet.pdf").pages[0].extract_text()
        assert "FILLED AFTER RECONCILIATION" in summary
        assert chosen in summary
        assert "7654321" in summary and "765432" in summary
        if native_numeric:
            assert report["answers"][0]["historical_candidate_status"] == (
                "reconciled_with_native_text_and_ocr"
            )
        # A forged review must not make the writer trust a different corroborating identity.
        bad = request.model_dump(mode="json")
        if native_numeric:
            bad["proposals"]["proposals"][0]["value"]["value"] = "9999999"
        else:
            bad["proposals"]["proposals"][0]["historical_basis"]["reading_resolution"][
                "subject"
            ] = "Someone Else"
        altered = json.dumps(bad).encode()
        forged = review.model_copy(update={"request_sha256": hashlib.sha256(altered).hexdigest()})
        (setup.evidence_root / "outputs/altered-resolution.json").write_bytes(altered)
        bad_output = publish_draft(
            setup.evidence_root,
            Path("outputs/altered-resolution.json"),
            altered,
            DraftRequest.model_validate_json(altered),
            forged,
            forged.model_dump_json().encode(),
            None,
        )
        assert json.loads((bad_output / "draft.json").read_text())["written_requirements"] == []
    else:
        assert json.loads((output / "draft.json").read_text())["written_requirements"] == []
        assert "LEFT BLANK" in summary
        assert "ACTION: Verify" in summary
