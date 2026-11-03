import asyncio
import json
from datetime import date
from io import BytesIO
from unittest.mock import Mock

import pytest
from reportlab.pdfgen.canvas import Canvas

from bd_packet_builder.contracts import ReportingPeriod
from bd_packet_builder.followup import VerificationRequest
from bd_packet_builder.grouped import run_answer_groups
from bd_packet_builder.scan import ScanTranscript
from bd_packet_builder.visual import VisualPage
from tests.integration.test_agent import Setup, nbox, visual_item
from tests.integration.test_historical_prefill import call

QUESTION = "Report minimum net capital of $10 million on line 3750."
AMOUNT = "12,345,678"
SUBJECT = "Example Firm"
TEXT = f"Name of Firm: {SUBJECT}\nAs of: 2026-07-31\nNet capital $ {AMOUNT} [3750]"


def prepared(tmp_path, monkeypatch, *, image_row=None, line_confidence=96):
    from bd_packet_builder import ocr

    buffer = BytesIO()
    canvas = Canvas(buffer, pagesize=(612, 792), invariant=True)
    canvas.drawString(40, 732, QUESTION)
    canvas.save()
    mapper = Mock()
    mapper.map_pages.return_value = {
        1: VisualPage.model_validate_json(
            json.dumps(
                {
                    "readable": True,
                    "explanation": None,
                    "items": [visual_item("amount", QUESTION, "text", nbox(40, 70, 400, 90))],
                }
            )
        )
    }
    setup = Setup(tmp_path, buffer.getvalue(), mapper=mapper, evidence_text=TEXT, scanned=True)
    reader = Mock()
    reader.transcribe.return_value = ScanTranscript(
        readable=True,
        subject=SUBJECT,
        text=image_row or TEXT,
        reporting_period=ReportingPeriod(start=date(2026, 7, 31), end=date(2026, 7, 31)),
    )
    rows = []
    for line, words in enumerate(TEXT.splitlines(), 1):
        for word, token in enumerate(words.split(), 1):
            confidence = line_confidence if token == "[3750]" else 96
            rows.append(
                f"5\t1\t1\t1\t{line}\t{word}\t{40 + word * 120}\t{100 + line * 70}"
                f"\t110\t40\t{confidence}\t{token}\n"
            )
    tsv = (
        "level\tpage_num\tblock_num\tpar_num\tline_num\tword_num\t"
        "left\ttop\twidth\theight\tconf\ttext\n" + "".join(rows)
    )
    monkeypatch.setattr(
        ocr,
        "_execute",
        lambda command, *_: "tesseract 5.5.0\n" if "--version" in command else tsv,
    )
    tools = setup.tools(scan_reader=reader)
    call(tools, "interpret_form")
    source = call(tools, "list_sources")["sources"][0]["source_id"]
    call(tools, "read_page", {"source_id": source, "page": 1})
    # Verify just identity/date, exactly the discovery gap this slice repairs.
    call(
        tools,
        "verify_scan_quote",
        {
            "source_id": source,
            "page": 1,
            "quote": SUBJECT,
            "expected_subject": SUBJECT,
        },
    )
    call(tools, "finish_evidence")
    return setup, tools, reader, source


@pytest.mark.parametrize("case", ["agrees", "wrong_row", "low_line_confidence"])
def test_financial_observation_reaches_answering_as_verified_threshold(tmp_path, monkeypatch, case):
    setup, tools, reader, source = prepared(
        tmp_path,
        monkeypatch,
        image_row=TEXT.replace("[3750]", "3760") if case == "wrong_row" else None,
        line_confidence=50 if case == "low_line_confidence" else 96,
    )
    calls = []

    async def propose(payload):
        calls.append(payload)
        assert any(AMOUNT in c["text"] for c in payload["candidate_readings"])
        if len(calls) == 1:
            return json.dumps(
                {
                    "proposals": [],
                    "verification_requests": [
                        {
                            "requirement_id": "p1.amount",
                            "source_id": source,
                            "page": 1,
                            "method": "scan",
                            "quote": AMOUNT,
                            "expected_subject": SUBJECT,
                            "minimum_amount": {
                                "criterion_quote": QUESTION,
                                "field_label": "Net capital",
                                "line_label": "3750",
                            },
                        }
                    ],
                }
            )
        result = payload["verification_results"][0]
        if case != "agrees":
            assert not result["ok"]
            return json.dumps(
                {
                    "proposals": [
                        {
                            "requirement_id": "p1.amount",
                            "outcome": "conflicting_evidence",
                            "explanation": result["error"],
                        }
                    ]
                }
            )
        assert result["minimum_amount_result"]["value"] == "12345678"
        assert result["minimum_amount_result"]["minimum"] == "10000000"
        assert result["minimum_amount_result"]["meets_minimum"] is True
        return json.dumps(
            {
                "proposals": [
                    {
                        "requirement_id": "p1.amount",
                        "outcome": "proposed",
                        "value": {"kind": "text", "value": AMOUNT},
                        "citations": [result["citation"]],
                        "confidence": 0.9,
                    }
                ],
                "condition_assessments": [
                    {
                        "requirement_id": "p1.amount",
                        "criterion_quote": QUESTION,
                        "status": "supported",
                        "reason": "verified_evidence",
                        "explanation": "Verified amount exceeds the minimum.",
                    }
                ],
            }
        )

    final = asyncio.run(run_answer_groups(tools, propose))
    assert final.status == "published"
    assert len(calls) == 2
    assert reader.transcribe.call_count == 1
    draft = json.loads(setup.artifact("draft.json"))
    assert draft["written_requirements"] == (["p1.amount"] if case == "agrees" else [])
    if case == "agrees":
        assert (
            "Condition (model assessment, not approval)"
            in setup.artifact("reviewer-summary.txt").decode()
        )
        assert "Checked monetary condition:" in setup.artifact("reviewer-summary.txt").decode()
        assert "minimum USD 10000000; MET" in setup.artifact("reviewer-summary.txt").decode()


def test_resume_reuses_verified_followup_without_repeating_image_read(tmp_path, monkeypatch):
    setup, tools, reader, source = prepared(tmp_path, monkeypatch)
    calls = []

    async def first(payload):
        calls.append(payload)
        if len(calls) == 1:
            return json.dumps(
                {
                    "proposals": [],
                    "verification_requests": [
                        {
                            "requirement_id": "p1.amount",
                            "source_id": source,
                            "page": 1,
                            "method": "scan",
                            "quote": AMOUNT,
                            "expected_subject": SUBJECT,
                        }
                    ],
                }
            )
        return '{"proposals":[]}'

    assert asyncio.run(run_answer_groups(tools, first)).status == "failed"
    reader.transcribe.side_effect = AssertionError("Recovery must reuse saved blind reading")
    fresh = setup.tools(scan_reader=reader)

    async def recovered(payload):
        receipt = payload["verification_results"][0]["citation"]
        return json.dumps(
            {
                "proposals": [
                    {
                        "requirement_id": "p1.amount",
                        "outcome": "proposed",
                        "value": {"kind": "text", "value": AMOUNT},
                        "citations": [receipt],
                        "confidence": 0.9,
                    }
                ]
            }
        )

    assert asyncio.run(run_answer_groups(fresh, recovered, resume=True)).status == "published"
    assert reader.transcribe.call_count == 1
    assert json.loads(setup.artifact("draft.json"))["written_requirements"] == ["p1.amount"]


@pytest.mark.parametrize("change", ["source", "page", "quote", "subject", "criterion", "artifact"])
def test_followup_rejects_unobserved_or_changed_evidence(tmp_path, monkeypatch, change):
    setup, tools, reader, source = prepared(tmp_path, monkeypatch)
    raw = {
        "requirement_id": "p1.amount",
        "source_id": source,
        "page": 1,
        "method": "scan",
        "quote": AMOUNT,
        "expected_subject": SUBJECT,
        "minimum_amount": {
            "criterion_quote": QUESTION,
            "field_label": "Net capital",
            "line_label": "3750",
        },
    }
    if change == "source":
        raw["source_id"] = "0" * 64
    elif change == "page":
        raw["page"] = 2
    elif change == "quote":
        raw["quote"] = "99,999,999"
    elif change == "subject":
        raw["expected_subject"] = "Different Firm"
    elif change == "criterion":
        raw["minimum_amount"]["criterion_quote"] = "minimum $1"
    else:
        from pathlib import Path

        handoff = json.loads(setup.artifact("answer_handoff.json"))
        path = next(
            c["artifact_path"] for c in handoff["candidate_readings"] if c.get("artifact_path")
        )
        artifact = setup.evidence_root / Path(path)
        artifact.write_bytes(artifact.read_bytes() + b"\n")
    reader.transcribe.side_effect = AssertionError(
        "Invalid request must not spend another image call"
    )
    request = VerificationRequest.model_validate_json(json.dumps(raw))
    result = tools.verify_answer_evidence(
        request, json.loads(setup.artifact("answer_handoff.json"))
    )
    assert not result["ok"]
    assert result["error"]
    assert reader.transcribe.call_count == 1


def test_repeated_verification_request_is_not_executed_twice(tmp_path, monkeypatch):
    setup, tools, reader, source = prepared(tmp_path, monkeypatch)
    count = 0

    async def propose(payload):
        nonlocal count
        count += 1
        if count < 3:
            return json.dumps(
                {
                    "proposals": [],
                    "verification_requests": [
                        {
                            "requirement_id": "p1.amount",
                            "source_id": source,
                            "page": 1,
                            "method": "scan",
                            "quote": AMOUNT,
                            "expected_subject": SUBJECT,
                        }
                    ],
                }
            )
        assert (
            payload["verification_results"][-1]["error"] == "verification_request_already_attempted"
        )
        return json.dumps(
            {
                "proposals": [
                    {
                        "requirement_id": "p1.amount",
                        "outcome": "missing_evidence",
                        "explanation": "Duplicate request; no new verification.",
                    }
                ]
            }
        )

    assert asyncio.run(run_answer_groups(tools, propose)).status == "published"
    assert count == 3
    assert reader.transcribe.call_count == 1


def test_verification_budget_exhaustion_is_explicit_before_tool_work(tmp_path, monkeypatch):
    from bd_packet_builder import grouped

    setup, tools, reader, source = prepared(tmp_path, monkeypatch)
    monkeypatch.setattr(grouped, "MAX_VERIFICATION_REQUESTS", 0)

    async def propose(payload):
        return json.dumps(
            {
                "proposals": [],
                "verification_requests": [
                    {
                        "requirement_id": "p1.amount",
                        "source_id": source,
                        "page": 1,
                        "method": "scan",
                        "quote": AMOUNT,
                        "expected_subject": SUBJECT,
                    }
                ],
            }
        )

    final = asyncio.run(run_answer_groups(tools, propose))
    assert final.status == "failed"
    record = json.loads(setup.artifact("answer-group-000-attempt-1.json"))
    assert record["error"]["code"] == "evidence_followup_limit_exceeded"
    assert reader.transcribe.call_count == 1


def test_interrupted_verification_does_not_silently_repeat_unknown_paid_work(tmp_path, monkeypatch):
    setup, tools, reader, source = prepared(tmp_path, monkeypatch)
    request = {
        "requirement_id": "p1.amount",
        "source_id": source,
        "page": 1,
        "method": "scan",
        "quote": AMOUNT,
        "expected_subject": SUBJECT,
    }

    async def propose(payload):
        return json.dumps({"proposals": [], "verification_requests": [request]})

    def interrupted(*args):
        raise RuntimeError("Synthetic interruption after the durable verification request marker")

    monkeypatch.setattr(tools, "verify_answer_evidence", interrupted)
    with pytest.raises(RuntimeError, match="Synthetic interruption"):
        asyncio.run(run_answer_groups(tools, propose))
    fresh = setup.tools(scan_reader=reader)

    async def recovered(payload):
        result = payload["verification_results"][0]
        assert result["request"] == request | {"minimum_amount": None}
        assert result["error"] == "verification_interrupted_do_not_repeat_unknown_paid_work"
        return json.dumps(
            {
                "proposals": [
                    {
                        "requirement_id": "p1.amount",
                        "outcome": "missing_evidence",
                        "explanation": "Interrupted; unknown paid work was not repeated.",
                    }
                ]
            }
        )

    assert asyncio.run(run_answer_groups(fresh, recovered, resume=True)).status == "published"
    assert reader.transcribe.call_count == 1
