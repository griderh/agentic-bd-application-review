import asyncio
import json
from io import BytesIO

import httpx
import pytest
from agent_framework import BaseChatClient, ChatResponse, Content, FunctionInvocationLayer, Message
from agent_framework_openai import OpenAIChatClient
from openai import AsyncOpenAI
from reportlab.pdfgen.canvas import Canvas

from bd_packet_builder.blob_storage import REVIEWS, PacketBlobStorage
from bd_packet_builder.draft import DraftReview
from bd_packet_builder.form_layout import FormInterpretation
from bd_packet_builder.foundry import FoundryConfig
from bd_packet_builder.grouped import (
    ANSWER_INSTRUCTIONS,
    EVIDENCE_INSTRUCTIONS,
    run_answer_groups,
    run_grouped_packet_agent,
)
from bd_packet_builder.live import LiveRunRequest, prepare_live_run
from bd_packet_builder.run import FileRunStore, RunConflictError, RunInputError
from bd_packet_builder.visual import VisualPage
from tests.integration.test_agent import (
    NAME,
    FakeMapper,
    Setup,
    blank_pdf,
    call,
    nbox,
    visual_item,
    with_result,
)
from tests.integration.test_blob_storage import MemoryBlobs


def ready(tmp_path):
    setup = Setup(tmp_path, blank_pdf())
    tools = setup.tools()
    tools.call("interpret_form", "{}")
    listing = json.loads(tools.call("list_sources", "{}"))["result"]
    source = listing["sources"][0]["source_id"]
    quote = json.loads(
        tools.call("locate_quote", json.dumps({"source_id": source, "page": 1, "quote": NAME}))
    )["result"]
    tools.call("finish_evidence", "{}")
    proposal = {
        "requirement_id": "p1.name",
        "outcome": "proposed",
        "value": {"kind": "text", "value": NAME},
        "citations": [{k: quote[k] for k in ("source_id", "page", "start", "end", "quote")}],
        "confidence": 0.9,
    }
    return setup, tools, proposal


def test_grouped_answering_persists_proposals_and_publishes_through_gate(tmp_path):
    setup, tools, proposal = ready(tmp_path)
    proposal["knowledge_applied"] = [
        {"entry_id": "supporting-documents", "reason": "Inspect the source's legal identity."}
    ]
    calls = []

    async def propose(payload):
        calls.append(payload)
        return json.dumps({"proposals": [proposal]})

    final = asyncio.run(run_answer_groups(tools, propose))
    assert final.status == "published"
    assert len(calls) == 1
    assert [r["requirement_id"] for r in calls[0]["requirements"]] == ["p1.name"]
    record = json.loads(setup.artifact("answer-group-000-attempt-1.json"))
    assert record["status"] == "staged_unvalidated"
    assert record["response"] == json.dumps({"proposals": [proposal]})
    review = json.loads(setup.artifact("answer_review.json"))
    assert review["decisions"][0]["decision"] == "draft_verified"
    saved = json.loads(setup.artifact("draft_request.json"))
    application = saved["proposals"]["proposals"][0]["knowledge_applied"][0]
    assert application["entry_id"] == "supporting-documents"
    assert len(application["reference_sha256"]) == 64
    assert (
        calls[0]["source_context"]["domain_knowledge"]["sha256"] == application["reference_sha256"]
    )
    assert "supporting-documents" in setup.artifact("reviewer-summary.txt").decode()


@pytest.mark.parametrize("changed_word", [False, True])
def test_condition_quote_accepts_line_wrapping_but_not_changed_words(tmp_path, changed_word):
    setup, tools, proposal = ready(tmp_path)

    # The mapped issuer instruction is "Firm legal name"; wrapping does not change its words.
    async def propose(payload):
        return json.dumps(
            {
                "proposals": [proposal],
                "condition_assessments": [
                    {
                        "requirement_id": "p1.name",
                        "criterion_quote": "Firm\nlegal\n" + ("title" if changed_word else "name"),
                        "status": "unresolved",
                        "reason": "not_searched",
                        "explanation": "Synthetic criterion note, not evidence approval.",
                    }
                ],
            }
        )

    final = asyncio.run(run_answer_groups(tools, propose))
    assert final.status == ("failed" if changed_word else "published")
    if changed_word:
        record = json.loads(setup.artifact("answer-group-000-attempt-1.json"))
        assert record["error"]["code"] == "condition_not_in_requirement"


def test_answering_can_verify_observed_quote_and_retry_only_affected_group(tmp_path):
    from tests.integration.test_historical_prefill import call as invoke

    setup = Setup(tmp_path, blank_pdf())
    tools = setup.tools()
    invoke(tools, "interpret_form")
    source = invoke(tools, "list_sources")["sources"][0]["source_id"]
    reading = invoke(tools, "read_page", {"source_id": source, "page": 1})
    invoke(tools, "finish_evidence")
    calls = []

    async def propose(payload):
        calls.append(payload)
        assert any(NAME in c["text"] for c in payload["candidate_readings"])
        if len(calls) == 1:
            assert payload["native_quote_citations"] == []
            return json.dumps(
                {
                    "proposals": [],
                    "verification_requests": [
                        {
                            "requirement_id": "p1.name",
                            "source_id": source,
                            "page": 1,
                            "quote": NAME,
                            "expected_subject": NAME,
                            "method": "native",
                        }
                    ],
                }
            )
        verified = payload["verification_results"][0]
        assert verified["ok"]
        return json.dumps(
            {
                "proposals": [
                    {
                        "requirement_id": "p1.name",
                        "outcome": "proposed",
                        "value": {"kind": "text", "value": NAME},
                        "citations": [verified["citation"]],
                        "confidence": 0.9,
                    }
                ]
            }
        )

    assert NAME in reading["text"]
    result = asyncio.run(run_answer_groups(tools, propose))
    assert result.status == "published"
    assert len(calls) == 2
    assert json.loads(setup.artifact("draft.json"))["written_requirements"] == ["p1.name"]
    assert "answer-group-000-attempt-1-verification.json" in {a.name for a in result.artifacts}


def test_followup_recovery_retains_successful_groups_and_retries_only_unfinished_group(tmp_path):
    from tests.integration.test_agent import visual_page
    from tests.integration.test_historical_prefill import call as invoke

    buffer = BytesIO()
    canvas = Canvas(buffer, pagesize=(612, 792), invariant=True)
    for _ in range(6):
        canvas.drawString(40, 732, "Firm legal name:")
        canvas.drawString(40, 452, "Signature of authorized officer")
        canvas.drawString(40, 392, "Date")
        canvas.showPage()
    canvas.save()
    setup = Setup(
        tmp_path,
        buffer.getvalue(),
        mapper=FakeMapper({page: visual_page() for page in range(1, 7)}),
    )
    tools = setup.tools()
    invoke(tools, "interpret_form")
    source = invoke(tools, "list_sources")["sources"][0]["source_id"]
    invoke(tools, "read_page", {"source_id": source, "page": 1})
    citation = invoke(tools, "locate_quote", {"source_id": source, "page": 1, "quote": NAME})
    citation.pop("occurrences")
    invoke(tools, "finish_evidence")
    second_calls = 0

    def answers(ids, receipt):
        return json.dumps(
            {
                "proposals": [
                    {
                        "requirement_id": rid,
                        "outcome": "proposed",
                        "value": {"kind": "text", "value": NAME},
                        "confidence": 0.9,
                        "citations": [receipt],
                    }
                    for rid in ids
                ]
            }
        )

    async def initial(payload):
        nonlocal second_calls
        ids = payload["assigned_requirement_ids"]
        if len(ids) == 5:
            return answers(ids, citation)
        second_calls += 1
        if second_calls == 1:
            return json.dumps(
                {
                    "proposals": [],
                    "verification_requests": [
                        {
                            "requirement_id": ids[0],
                            "source_id": source,
                            "page": 1,
                            "quote": NAME,
                            "expected_subject": NAME,
                            "method": "native",
                        }
                    ],
                }
            )
        return '{"proposals":[]}'

    assert asyncio.run(run_answer_groups(tools, initial)).status == "failed"
    resumed_calls = []

    async def recovered(payload):
        resumed_calls.append(payload["assigned_requirement_ids"])
        assert payload["assigned_requirement_ids"] == ["p6.name"]
        assert len(payload["verification_results"]) == 1
        return answers(
            payload["assigned_requirement_ids"], payload["verification_results"][0]["citation"]
        )

    assert (
        asyncio.run(run_answer_groups(setup.tools(), recovered, resume=True)).status == "published"
    )
    assert resumed_calls == [["p6.name"]]
    assert setup.mapper.calls == 1
    assert len(json.loads(setup.artifact("draft.json"))["written_requirements"]) == 6


@pytest.mark.parametrize("span", [(260, 261), (260, 260 + len(NAME))])
def test_group_restores_unique_checked_native_receipt_without_model_offsets(tmp_path, span):
    setup, tools, proposal = ready(tmp_path)
    original = proposal["citations"][0].copy()
    proposal["citations"][0].update(start=span[0], end=span[1])
    raw = json.dumps({"proposals": [proposal]})

    async def propose(payload):
        return raw

    final = asyncio.run(run_answer_groups(tools, propose))
    assert final.status == "published", json.loads(
        setup.artifact("answer-group-000-attempt-1.json")
    ).get("error")
    saved = json.loads(setup.artifact("draft_request.json"))
    assert saved["proposals"]["proposals"][0]["citations"] == [original]
    record = json.loads(setup.artifact("answer-group-000-attempt-1.json"))
    assert record["response"] == raw
    assert record["resolved_citation_paths"] == ["proposals.0.citations.0"]
    review = json.loads(setup.artifact("answer_review.json"))
    assert review["decisions"][0]["decision"] == "draft_verified"


@pytest.mark.parametrize("change", ["quote", "source", "page", "extra", "ambiguous"])
def test_group_does_not_guess_unknown_or_ambiguous_receipts(tmp_path, monkeypatch, change):
    setup, tools, proposal = ready(tmp_path)
    handoff = tools.answer_handoff()
    citation = proposal["citations"][0]
    if change == "ambiguous":
        other = citation | {"start": 900, "end": 900 + len(NAME)}
        handoff["native_quote_citations"].append(other)
        monkeypatch.setattr(tools, "answer_handoff", lambda: handoff)
    else:
        citation.update(
            {
                "quote": {"quote": "Invented unsupported quote"},
                "source": {"source_id": "unapproved-source"},
                "page": {"page": 999},
                "extra": {"unexpected": True},
            }[change]
        )
    citation.update(start=260, end=261)

    async def propose(payload):
        return json.dumps({"proposals": [proposal]})

    final = asyncio.run(run_answer_groups(tools, propose))
    assert final.status == "failed"
    record = json.loads(setup.artifact("answer-group-000-attempt-1.json"))
    assert record["status"] == "invalid_response"
    assert not record.get("resolved_citation_paths")
    assert "draft_request.json" not in {a.name for a in final.artifacts}


@pytest.mark.parametrize("wrong_context", [False, True])
def test_group_resolves_scanned_receipt_and_keeps_context_checks(
    tmp_path, monkeypatch, wrong_context
):
    from tests.integration.test_historical_context import setup_page
    from tests.integration.test_historical_prefill import call as historical_call

    setup, tools, _, prior, _ = setup_page(tmp_path, monkeypatch, scanned_answer=True)
    reading = historical_call(
        tools,
        "read_historical_page",
        {
            "source_id": prior["source_id"],
            "page": 1,
        },
    )
    association = reading["associations"][0]
    checked = association["answer_citation"]
    assert checked["evidence_kind"] == "ocr"
    historical_call(tools, "finish_evidence")
    proposal = {
        "requirement_id": "p1.name",
        "outcome": "proposed",
        "value": {"kind": "text", "value": checked["quote"]},
        "citations": [
            {
                "source_id": checked["source_id"],
                "page": checked["page"],
                "quote": checked["quote"],
                "start": 260,
                "end": 261,
            }
        ],
        "confidence": 0.9,
        "historical_basis": {
            "category": "contact",
            "context": "firm_wide",
            "role": "Primary representative",
            "prior_question": (reading["associations"][1] if wrong_context else association)[
                "context_citation"
            ],
            "current_checks": [],
            "reviewer_confirmation": "Confirm the historical representative.",
        },
    }

    async def propose(payload):
        return json.dumps({"proposals": [proposal]})

    final = asyncio.run(run_answer_groups(tools, propose))
    assert final.status == "published", json.loads(
        setup.artifact("answer-group-000-attempt-1.json")
    ).get("error")
    saved = json.loads(setup.artifact("draft_request.json"))
    assert saved["proposals"]["proposals"][0]["citations"] == [checked]
    review = json.loads(setup.artifact("answer_review.json"))
    if not wrong_context:
        assert review["historical_context_checks"]
    assert (review["decisions"][0]["decision"] == "draft_verified") == (not wrong_context)


def test_citation_resolution_preserves_checked_scan_type_in_current_checks(tmp_path, monkeypatch):
    from bd_packet_builder.contracts import CurrentEvidenceCheck
    from bd_packet_builder.grouped import _resolve_citations
    from tests.integration.test_historical_context import setup_page
    from tests.integration.test_historical_prefill import call as historical_call

    _, tools, _, prior, _ = setup_page(tmp_path, monkeypatch, scanned_answer=True)
    reading = historical_call(
        tools, "read_historical_page", {"source_id": prior["source_id"], "page": 1}
    )
    ocr = reading["associations"][0]["answer_citation"]
    reference = {
        "source_id": ocr["source_id"],
        "page": ocr["page"],
        "quote": ocr["quote"],
        "start": 900,
        "end": 900 + len(ocr["quote"]),
    }
    check = {
        "citation": reference,
        "finding": "not_corroborated",
        "explanation": "Synthetic native-shaped input remains subject to source verification.",
    }
    response = json.dumps(
        {
            "proposals": [
                {
                    "citations": [reference],
                    "historical_basis": {"current_checks": [check]},
                }
            ]
        }
    )
    resolved, paths = _resolve_citations(
        response,
        {
            "historical_candidates": [
                {"answer_citation": ocr},
            ]
        },
    )
    proposal = json.loads(resolved)["proposals"][0]
    assert proposal["citations"] == [ocr]
    assert proposal["historical_basis"]["current_checks"] == [check | {"citation": ocr}]
    CurrentEvidenceCheck.model_validate_json(
        json.dumps(proposal["historical_basis"]["current_checks"][0])
    )
    assert paths == [
        "proposals.0.citations.0",
        "proposals.0.historical_basis.current_checks.0.citation",
    ]


def test_group_never_repairs_supplied_ocr_hashes(tmp_path, monkeypatch):
    from tests.integration.test_historical_context import setup_page
    from tests.integration.test_historical_prefill import call as historical_call

    setup, tools, _, prior, _ = setup_page(tmp_path, monkeypatch, scanned_answer=True)
    reading = historical_call(
        tools, "read_historical_page", {"source_id": prior["source_id"], "page": 1}
    )
    checked = reading["associations"][0]["answer_citation"]
    assert checked["evidence_kind"] == "ocr"
    historical_call(tools, "finish_evidence")
    supplied = checked | {"artifact_sha256": "0" * 64}

    async def propose(payload):
        return json.dumps(
            {
                "proposals": [
                    {
                        "requirement_id": "p1.name",
                        "outcome": "proposed",
                        "value": {"kind": "text", "value": checked["quote"]},
                        "citations": [supplied],
                        "confidence": 0.9,
                    }
                ]
            }
        )

    final = asyncio.run(run_answer_groups(tools, propose))
    assert final.status == "published" and final.outcome == "incomplete"
    record = json.loads(setup.artifact("answer-group-000-attempt-1.json"))
    assert record["resolved_citation_paths"] == []
    saved = json.loads(setup.artifact("draft_request.json"))
    assert saved["proposals"]["proposals"][0]["citations"] == [supplied]
    review = json.loads(setup.artifact("answer_review.json"))
    assert review["decisions"][0]["decision"] == "withhold"


def test_full_ocr_reference_resolves_render_metadata_only_with_exact_artifact_identity(
    tmp_path, monkeypatch
):
    from bd_packet_builder.grouped import _resolve_citations
    from tests.integration.test_historical_context import setup_page
    from tests.integration.test_historical_prefill import call as historical_call

    _, tools, _, prior, _ = setup_page(tmp_path, monkeypatch, scanned_answer=True)
    reading = historical_call(
        tools, "read_historical_page", {"source_id": prior["source_id"], "page": 1}
    )
    checked = reading["associations"][0]["answer_citation"]
    handoff = {"scan_quotes": [{"citation": checked}]}
    supplied = checked | {"render_sha256": "0" * 64}
    response = json.dumps(
        {
            "proposals": [
                {
                    "historical_basis": {
                        "current_checks": [{"citation": supplied, "finding": "not_corroborated"}]
                    }
                }
            ]
        }
    )
    resolved, paths = _resolve_citations(response, handoff)
    assert (
        json.loads(resolved)["proposals"][0]["historical_basis"]["current_checks"][0]["citation"]
        == checked
    )
    assert paths == ["proposals.0.historical_basis.current_checks.0.citation"]
    for key, value in (("artifact_sha256", "1" * 64), ("word_start", 999), ("quote", "Wrong")):
        changed = json.dumps({"proposals": [{"citations": [supplied | {key: value}]}]})
        unchanged, paths = _resolve_citations(changed, handoff)
        assert unchanged == changed
        assert not paths


def test_restored_receipt_is_reused_after_restart_without_regenerating_group(tmp_path, monkeypatch):
    setup, tools, proposal = ready(tmp_path)
    original = proposal["citations"][0].copy()
    proposal["citations"][0].update(start=260, end=261)
    dispatch = tools.call

    def interrupt_before_submit(name, arguments):
        if name == "submit_answers":
            raise asyncio.CancelledError
        return dispatch(name, arguments)

    monkeypatch.setattr(tools, "call", interrupt_before_submit)

    async def propose(payload):
        return json.dumps({"proposals": [proposal]})

    with pytest.raises(asyncio.CancelledError):
        asyncio.run(run_answer_groups(tools, propose))

    async def unexpected(payload):
        pytest.fail("A successfully staged group must not be regenerated.")

    final = asyncio.run(run_answer_groups(setup.tools(), unexpected, resume=True))
    assert final.status == "published"
    saved = json.loads(setup.artifact("draft_request.json"))
    assert saved["proposals"]["proposals"][0]["citations"] == [original]
    assert "answer-group-000-attempt-2.json" not in {a.name for a in final.artifacts}


def test_completion_recovery_preserves_rechecked_answers_without_regeneration(tmp_path):
    setup, tools, proposal = ready(tmp_path)

    async def initial(payload):
        return json.dumps({"proposals": [proposal]})

    asyncio.run(run_answer_groups(tools, initial))
    request_raw = setup.artifact("draft_request.json")
    review = DraftReview.model_validate_json(setup.artifact("answer_review.json"))
    interpretation = FormInterpretation.model_validate_json(
        setup.artifact("form_interpretation.json")
    )
    setup.manifest = prepare_live_run(
        setup.store,
        LiveRunRequest(blank_name="Form.pdf", requester_id="offline", evidence_set_id="recovery"),
        setup.blank,
        setup.evidence_root,
        FoundryConfig(endpoint="https://example.openai.azure.com/openai/v1", deployment="test"),
    )
    recovery = setup.tools()
    recovery.seed_completion_recovery(request_raw, review, interpretation, ("p1.name",))
    response = json.loads(recovery.call("finish_evidence", "{}"))
    assert response["ok"], response
    fresh = setup.tools()

    async def unexpected(payload):
        pytest.fail("A retained answer must not be sent for regeneration")

    final = asyncio.run(run_answer_groups(fresh, unexpected))
    assert final.status == "published"
    assert setup.mapper.calls == 1
    output = json.loads(setup.artifact("draft.json"))
    assert output["written_requirements"] == ["p1.name"]
    saved = json.loads(setup.artifact("draft_request.json"))
    assert saved["proposals"]["proposals"][0]["value"] == proposal["value"]


def test_failed_group_records_exact_errors_then_resumes_without_evidence_calls(tmp_path):
    setup, tools, proposal = ready(tmp_path)

    async def malformed(payload):
        return json.dumps({"proposals": [{"requirement_id": "p1.name", "outcome": "proposed"}]})

    final = asyncio.run(run_answer_groups(tools, malformed))
    assert final.status == "failed"
    assert final.failure.code == "answer_groups_incomplete"
    record = json.loads(setup.artifact("answer-group-000-attempt-1.json"))
    assert record["status"] == "invalid_response"
    assert record["error"]["problems"]
    fresh = setup.tools()

    async def fixed(payload):
        assert payload["previous_errors"]
        return json.dumps({"proposals": [proposal]})

    final = asyncio.run(run_answer_groups(fresh, fixed, resume=True))
    assert final.status == "published"
    assert setup.mapper.calls == 1
    assert not any("read_page" in call for call in fresh.trace)
    assert "answer-group-000-attempt-2.json" in {a.name for a in final.artifacts}


def test_resume_rejects_changed_source_before_model_call(tmp_path):
    setup, tools, _ = ready(tmp_path)

    async def malformed(payload):
        return '{"proposals":[]}'

    initial = asyncio.run(run_answer_groups(tools, malformed))
    assert initial.status == "failed"
    source = initial.evidence.items[0]
    path = setup.evidence_root / source.path
    path.write_bytes(path.read_bytes() + b"\n%synthetic source change\n")
    before = setup.store.load(initial.run_id)

    async def unexpected(payload):
        pytest.fail("Changed evidence must be rejected before any model call")

    with pytest.raises(RunInputError, match="Evidence changed.*" + source.path):
        asyncio.run(run_answer_groups(setup.tools(), unexpected, resume=True))
    assert setup.store.load(initial.run_id) == before


@pytest.mark.parametrize("problem", ["review_hash", "unknown_retained", "wrong_form"])
def test_completion_recovery_rejects_mismatched_baselines(tmp_path, problem):
    setup, tools, proposal = ready(tmp_path)

    async def initial(payload):
        return json.dumps({"proposals": [proposal]})

    asyncio.run(run_answer_groups(tools, initial))
    request_raw = setup.artifact("draft_request.json")
    review = DraftReview.model_validate_json(setup.artifact("answer_review.json"))
    interpretation = FormInterpretation.model_validate_json(
        setup.artifact("form_interpretation.json")
    )
    if problem == "review_hash":
        review = review.model_copy(update={"request_sha256": "0" * 64})
    blank = blank_pdf() + (b"\n%different form\n" if problem == "wrong_form" else b"")
    setup.manifest = prepare_live_run(
        setup.store,
        LiveRunRequest(blank_name="Form.pdf", requester_id="offline", evidence_set_id="recovery"),
        blank,
        setup.evidence_root,
        FoundryConfig(endpoint="https://example.openai.azure.com/openai/v1", deployment="test"),
    )
    recovery = setup.tools()
    with pytest.raises(ValueError, match="exact original|unsupported"):
        recovery.seed_completion_recovery(
            request_raw,
            review,
            interpretation,
            ("unknown",) if problem == "unknown_retained" else ("p1.name",),
        )
    assert recovery.manifest().status == "created"


def test_group_rejects_unassigned_or_missing_requirements(tmp_path):
    setup, tools, proposal = ready(tmp_path)
    proposal["requirement_id"] = "p9.unassigned"

    async def wrong(payload):
        return json.dumps({"proposals": [proposal]})

    final = asyncio.run(run_answer_groups(tools, wrong))
    assert final.status == "failed"
    record = json.loads(setup.artifact("answer-group-000-attempt-1.json"))
    assert record["error"]["code"] == "group_requirement_mismatch"
    assert "draft_request.json" not in {a.name for a in final.artifacts}


def test_saved_model_proposal_is_still_withheld_when_evidence_does_not_support_it(tmp_path):
    setup, tools, proposal = ready(tmp_path)
    proposal["value"]["value"] = "Fabricated unsupported firm"

    async def unsupported(payload):
        return json.dumps({"proposals": [proposal]})

    final = asyncio.run(run_answer_groups(tools, unsupported))
    assert final.status == "published" and final.outcome == "incomplete"
    review = json.loads(setup.artifact("answer_review.json"))
    assert review["decisions"][0]["decision"] == "withhold"
    assert (
        "Fabricated unsupported firm"
        in json.loads(setup.artifact("answer-group-000-attempt-1.json"))["response"]
    )


def test_interrupted_group_has_durable_request_marker_and_can_resume(tmp_path):
    setup, tools, proposal = ready(tmp_path)

    async def interrupted(payload):
        raise asyncio.CancelledError

    with pytest.raises(asyncio.CancelledError):
        asyncio.run(run_answer_groups(tools, interrupted))
    names = {a.name for a in tools.manifest().artifacts}
    assert "answer-group-000-attempt-1-request.json" in names
    assert "answer-group-000-attempt-1.json" not in names

    async def fixed(payload):
        assert payload["previous_errors"] == [{"code": "group_interrupted"}]
        return json.dumps({"proposals": [proposal]})

    assert asyncio.run(run_answer_groups(setup.tools(), fixed, resume=True)).status == "published"


def test_recovery_attempts_are_bounded_and_never_automatically_retried(tmp_path):
    setup, tools, _ = ready(tmp_path)
    calls = []

    async def timeout(payload):
        calls.append(payload["assigned_requirement_ids"])
        raise TimeoutError

    assert asyncio.run(run_answer_groups(tools, timeout)).status == "failed"
    assert len(calls) == 1
    for _ in range(3):
        assert (
            asyncio.run(run_answer_groups(setup.tools(), timeout, resume=True)).status == "failed"
        )
    assert len(calls) == 3
    record = json.loads(setup.artifact("answer-group-000-attempt-1.json"))
    assert record["error"] == {
        "code": "group_model_failed",
        "type": "TimeoutError",
        "causes": ["TimeoutError"],
    }


def test_actual_sdk_preserves_schema_invalid_response_for_private_diagnostics(tmp_path):
    setup, tools, _ = ready(tmp_path)
    malformed = '{"proposals":[{"requirement_id":"p1.name","outcome":"proposed"}]}'

    def respond(request):
        return httpx.Response(
            200,
            json={
                "id": "resp_synthetic",
                "object": "response",
                "created_at": 0,
                "status": "completed",
                "model": "synthetic",
                "output": [
                    {
                        "id": "msg_synthetic",
                        "type": "message",
                        "status": "completed",
                        "role": "assistant",
                        "content": [
                            {
                                "type": "output_text",
                                "text": malformed,
                                "annotations": [],
                            }
                        ],
                    }
                ],
            },
        )

    async def execute():
        async with (
            httpx.AsyncClient(transport=httpx.MockTransport(respond)) as http,
            AsyncOpenAI(
                base_url="https://synthetic.invalid/v1",
                api_key="synthetic",
                http_client=http,
                max_retries=0,
            ) as api,
        ):
            return await run_grouped_packet_agent(
                OpenAIChatClient(model="synthetic", async_client=api), tools
            )

    assert asyncio.run(execute()).status == "failed"
    record = json.loads(setup.artifact("answer-group-000-attempt-1.json"))
    assert record["status"] == "invalid_response"
    assert record["response"] == malformed
    assert record["error"]["problems"]


def test_group_wire_schema_requires_numeric_confidence_for_proposed_answers():
    from bd_packet_builder.grouped import group_response_format

    schema = group_response_format()["json_schema"]["schema"]
    branches = schema["properties"]["proposals"]["items"]["anyOf"]
    proposed = next(
        schema["$defs"][branch["$ref"].split("/")[-1]]
        for branch in branches
        if schema["$defs"][branch["$ref"].split("/")[-1]]["properties"]["outcome"].get("const")
        == "proposed"
    )
    assert proposed["properties"]["confidence"]["type"] == "number"
    assert {"confidence", "value", "citations"} <= set(proposed["required"])
    assert proposed["properties"]["citations"]["minItems"] == 1


def test_checkpoint_is_immutable_and_does_not_advance_answer_validation(tmp_path):
    setup, tools, _ = ready(tmp_path)
    store = setup.store
    run_id = tools.manifest().run_id
    store.checkpoint(run_id, name="answer-probe.json", data=b"first")
    assert store.load(run_id).status == "evidence_collected"
    assert store.read_artifact(run_id, "answer-probe.json") == b"first"
    with pytest.raises(RunConflictError):
        store.checkpoint(run_id, name="answer-probe.json", data=b"changed")


def test_failed_answer_run_can_be_restored_to_a_new_isolated_store(tmp_path):
    setup, tools, proposal = ready(tmp_path)

    async def broken(payload):
        return "broken"

    failed = asyncio.run(run_answer_groups(tools, broken))
    restored_root = tmp_path / "restored"
    restored_root.mkdir()
    restored = FileRunStore(restored_root)
    artifacts = {a.name: setup.artifact(a.name) for a in failed.artifacts}
    changed = {**artifacts, "answer_handoff.json": b"changed"}
    with pytest.raises(RunInputError, match="hash"):
        restored.restore_answers(failed, setup.blank, changed)
    restored.restore_answers(failed, setup.blank, artifacts)
    recovered_tools = type(tools)(restored, failed.run_id, setup.evidence_root, setup.mapper)

    async def fixed(payload):
        return json.dumps({"proposals": [proposal]})

    assert asyncio.run(run_answer_groups(recovered_tools, fixed, resume=True)).status == "published"


def test_blob_recovery_retains_hash_checked_group_diagnostics(tmp_path):
    setup, tools, _ = ready(tmp_path)

    async def broken(payload):
        return "broken"

    failed = asyncio.run(run_answer_groups(tools, broken))
    blobs = MemoryBlobs()
    storage = PacketBlobStorage(blobs)
    storage.claim("first", "blank-1", "set-1")
    storage.publish("first", setup.store, failed)
    assert storage.recovery_inputs("first") == ("blank-1", "set-1")
    root = tmp_path / "restored"
    root.mkdir()
    restored = FileRunStore(root)
    assert storage.restore_answers("first", restored) == failed
    name = "answer-group-000-attempt-1.json"
    assert restored.read_artifact(failed.run_id, name) == setup.artifact(name)
    corrupted = tmp_path / "corrupted"
    corrupted.mkdir()
    blobs.data[REVIEWS, f"runs/first/{failed.run_id}/answer_handoff.json"] = b"changed"
    with pytest.raises(RunInputError, match="hash"):
        storage.restore_answers("first", FileRunStore(corrupted))


def test_resume_rejects_changed_source_before_any_model_call(tmp_path):
    setup, tools, _ = ready(tmp_path)

    async def malformed(payload):
        return "not json"

    asyncio.run(run_answer_groups(tools, malformed))
    source = next(setup.evidence_root.rglob("registration.pdf"))
    source.write_bytes(b"changed")
    calls = []

    async def unexpected(payload):
        calls.append(payload)
        return "{}"

    with pytest.raises(ValueError, match="snapshot"):
        asyncio.run(run_answer_groups(setup.tools(), unexpected, resume=True))
    assert calls == []


def test_resume_preserves_successful_groups_and_only_retries_failed_group(tmp_path):
    buffer = BytesIO()
    canvas = Canvas(buffer, pagesize=(612, 792))
    items = []
    for i in range(6):
        y = 60 + i * 70
        canvas.drawString(40, 792 - y, f"Firm legal name {i}:")
        items.append(
            visual_item(f"name{i}", f"Firm legal name {i}", "text", nbox(40, y + 10, 400, y + 30))
        )
    canvas.showPage()
    canvas.save()
    setup = Setup(
        tmp_path,
        buffer.getvalue(),
        mapper=FakeMapper(
            {
                1: VisualPage.model_validate_json(
                    json.dumps({"readable": True, "explanation": None, "items": items})
                )
            }
        ),
    )
    tools = setup.tools()
    tools.call("interpret_form", "{}")
    tools.call("finish_evidence", "{}")
    assigned = []

    async def propose(payload):
        ids = payload["assigned_requirement_ids"]
        assigned.append(ids)
        if ids == ["p1.name5"]:
            return "broken"
        return json.dumps(
            {
                "proposals": [
                    {
                        "requirement_id": rid,
                        "outcome": "missing_evidence",
                        "explanation": "No supported value.",
                    }
                    for rid in ids
                ]
            }
        )

    assert asyncio.run(run_answer_groups(tools, propose)).status == "failed"
    first = setup.artifact("answer-group-000-attempt-1.json")
    recovered = []

    async def fix(payload):
        recovered.extend(payload["assigned_requirement_ids"])
        return json.dumps(
            {
                "proposals": [
                    {
                        "requirement_id": "p1.name5",
                        "outcome": "missing_evidence",
                        "explanation": "No supported value.",
                    }
                ]
            }
        )

    assert asyncio.run(run_answer_groups(setup.tools(), fix, resume=True)).status == "published"
    assert recovered == ["p1.name5"]
    assert setup.artifact("answer-group-000-attempt-1.json") == first


class PhaseClient(FunctionInvocationLayer, BaseChatClient):
    def __init__(self, steps, answer):
        super().__init__()
        self.steps = list(steps)
        self.answer = answer
        self.answer_calls = 0

    def _inner_get_response(self, *, messages, stream, options, **kwargs):
        async def respond():
            if options["instructions"] == EVIDENCE_INSTRUCTIONS:
                transcript = [
                    type("Entry", (), {"role": "tool", "content": str(c.result)})()
                    for m in messages
                    for c in m.contents
                    if c.type == "function_result"
                ]
                turn = self.steps.pop(0)(transcript)
                contents = [
                    Content.from_function_call(t.call_id, t.name, arguments=t.arguments)
                    for t in turn.tool_calls
                ]
            else:
                assert options["instructions"] == ANSWER_INSTRUCTIONS
                assert not options.get("tools")
                schema = options["response_format"]["json_schema"]["schema"]
                assert schema["properties"]["proposals"]["maxItems"] == 5
                self.answer_calls += 1
                contents = [self.answer()]
            return ChatResponse(messages=[Message("assistant", contents)])

        return respond()


def test_real_framework_evidence_loop_hands_control_to_grouped_answering(tmp_path):
    setup = Setup(tmp_path, blank_pdf())
    state = {}

    def locate(listing):
        return "locate_quote", {
            "source_id": listing["result"]["sources"][0]["source_id"],
            "page": 1,
            "quote": NAME,
        }

    def remember(located):
        state["citation"] = {
            k: located["result"][k] for k in ("source_id", "page", "start", "end", "quote")
        }
        return "finish_evidence", {}

    client = PhaseClient(
        [
            call("get_run_status"),
            call("interpret_form"),
            call("list_sources", {}),
            with_result(locate),
            with_result(remember),
        ],
        lambda: json.dumps(
            {
                "proposals": [
                    {
                        "requirement_id": "p1.name",
                        "outcome": "proposed",
                        "value": {"kind": "text", "value": NAME},
                        "confidence": 0.9,
                        "citations": [state["citation"]],
                    }
                ]
            }
        ),
    )
    final = asyncio.run(run_grouped_packet_agent(client, setup.tools()))
    assert final.status == "published"
    assert client.answer_calls == 1
    assert not client.steps
