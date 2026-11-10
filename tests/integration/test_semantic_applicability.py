import asyncio
import hashlib
import json
from pathlib import Path

import pytest
from pypdf import PdfReader

from bd_packet_builder.draft import DraftRequest, DraftReview, publish_draft
from bd_packet_builder.gate import validate_answers
from bd_packet_builder.grouped import run_answer_groups
from tests.integration.test_historical_context import NAME, setup_page
from tests.integration.test_historical_prefill import call


def semantic_request(tmp_path, monkeypatch, *, schema_version=1, grouped=False):
    setup, tools, _, prior, current = setup_page(
        tmp_path,
        monkeypatch,
        primary_role="Firm identity",
        historical_policy="answer_first_review",
        draft_schema_version=schema_version,
    )
    first = call(tools, "read_historical_page", {"source_id": prior["source_id"], "page": 1})[
        "associations"
    ][0]
    quote = call(
        tools,
        "locate_quote",
        {
            "source_id": current["source_id"],
            "page": 1,
            "quote": "Firm legal name: Insperex Fictional Securities LLC",
        },
    )
    quote.pop("occurrences")
    proposal = {
        "requirement_id": "p1.name",
        "outcome": "proposed",
        "confidence": 0.9,
        "value": {"kind": "text", "value": NAME},
        "citations": [first["answer_citation"]],
        "historical_basis": {
            "category": "firm_description",
            "context": "firm_wide",
            "prior_question": first["context_citation"],
            "role": None,
            "current_checks": [
                {
                    "citation": quote,
                    "finding": "not_corroborated",
                    "explanation": "Different firm evidence does not confirm this name.",
                }
            ],
            "reviewer_confirmation": "Confirm firm identity continuity.",
        },
    }
    call(tools, "finish_evidence")
    if grouped:
        calls = []

        async def propose(payload):
            calls.append(payload)
            proposal["historical_basis"]["correspondence"] = {
                "target_question": payload["requirements"][0]["instruction"],
                "assessment": "applicable",
                "differences": "Name under Firm identity is the target firm legal identity. "
                "Current continuity is unconfirmed.",
                "reason": "The verified historical answer supplies the requested legal name.",
            }
            return json.dumps({"proposals": [proposal]})

        final = asyncio.run(run_answer_groups(tools, propose))
        assert final.status == "published"
        assert len(calls) == 1
        assert calls[0]["historical_candidates"]
    else:
        call(tools, "submit_answers", {"proposals": [proposal]})
    return (
        setup,
        DraftRequest.model_validate_json(setup.artifact("draft_request.json")),
        DraftReview.model_validate_json(setup.artifact("answer_review.json")),
    )


def test_new_agent_request_requires_correspondence_and_records_schema_version(
    tmp_path, monkeypatch
):
    _, request, review = semantic_request(tmp_path, monkeypatch, schema_version=2)
    assert request.schema_version == 2
    assert review.decisions[0].decision == "withhold"
    assert "historical_question_correspondence_required" in review.decisions[0].reason


def test_grouped_new_form_correspondence_is_generated_in_existing_call_and_archived(
    tmp_path, monkeypatch
):
    setup, request, review = semantic_request(tmp_path, monkeypatch, schema_version=2, grouped=True)
    assert request.schema_version == 2
    assert review.decisions[0].decision == "draft_verified"
    record = json.loads(setup.artifact("answer-group-000-attempt-1.json"))
    assert record["status"] == "staged_unvalidated"
    saved = json.loads(record["response"])["proposals"][0]["historical_basis"]["correspondence"]
    assert saved["assessment"] == "applicable"
    assert saved["target_question"] == request.requirements.requirements[0].instruction


@pytest.mark.parametrize(
    ("assessment", "expected_code"),
    [
        ("applicable", None),
        ("uncertain", "historical_question_applicability_uncertain"),
        ("partially_applicable", "historical_question_partially_applicable"),
        ("incompatible", "historical_question_incompatible"),
        (None, "historical_question_correspondence_required"),
    ],
)
def test_semantic_applicability_is_distinct_from_continuity_and_rechecked_by_writer(
    tmp_path, monkeypatch, assessment, expected_code
):
    setup, request, review = semantic_request(tmp_path, monkeypatch)
    raw = request.model_dump(mode="json")
    raw["schema_version"] = 2
    raw["historical_policy"] = "answer_first_review"
    basis = raw["proposals"]["proposals"][0]["historical_basis"]
    basis["correspondence"] = (
        {
            "target_question": request.requirements.requirements[0].instruction,
            "assessment": assessment,
            "differences": "Historical Name field asks the same firm identity; "
            "current continuity is not independently confirmed.",
            "reason": "Verified historical answer supplies the requested firm legal name.",
        }
        if assessment
        else None
    )
    # Missing current corroboration alone must not prevent an applicable historical prefill.
    basis["current_checks"] = []
    altered = DraftRequest.model_validate_json(json.dumps(raw))
    data = altered.model_dump_json().encode()
    digest = hashlib.sha256(data).hexdigest()
    gated = validate_answers(
        setup.evidence_root,
        altered,
        digest,
        historical_context_checks=review.historical_context_checks,
    )
    decision = gated.decisions[0]
    assert (decision.decision == "draft_verified") == (expected_code is None), decision.reason
    if expected_code:
        assert expected_code in decision.reason
    # Even a forged positive review must not bypass the writer's applicability check.
    forced = gated.model_copy(
        update={
            "decisions": tuple(
                d.model_copy(update={"decision": "draft_verified"})
                if d.requirement_id == "p1.name"
                else d
                for d in gated.decisions
            )
        }
    )
    blank = setup.evidence_root / altered.source
    blank.parent.mkdir(parents=True, exist_ok=True)
    blank.write_bytes(setup.blank)
    path = Path("outputs/semantic-request.json")
    (setup.evidence_root / path).write_bytes(data)
    output = publish_draft(
        setup.evidence_root,
        path,
        data,
        altered,
        forced,
        forced.model_dump_json().encode(),
        None,
    )
    report = json.loads((output / "draft.json").read_bytes())
    assert ("p1.name" in report["written_requirements"]) == (expected_code is None)
    assert (NAME in PdfReader(output / "draft-packet.pdf").pages[0].extract_text()) == (
        expected_code is None
    )
    if expected_code is None:
        summary = (output / "reviewer-summary.txt").read_text()
        assert "HISTORICAL - CONTINUITY UNCONFIRMED" in summary
        assert "QUESTION CORRESPONDENCE" in summary
    elif assessment is not None:
        summary = (output / "reviewer-summary.txt").read_text()
        assert f"QUESTION CORRESPONDENCE ({assessment}" in summary


@pytest.mark.parametrize("tamper", ["target", "contradiction", "receipt", "role", "period"])
def test_applicable_model_assessment_does_not_override_deterministic_safeguards(
    tmp_path, monkeypatch, tamper
):
    setup, request, review = semantic_request(tmp_path, monkeypatch)
    raw = request.model_dump(mode="json")
    raw["schema_version"] = 2
    raw["historical_policy"] = "answer_first_review"
    basis = raw["proposals"]["proposals"][0]["historical_basis"]
    basis["correspondence"] = {
        "target_question": "Other question"
        if tamper == "target"
        else request.requirements.requirements[0].instruction,
        "assessment": "applicable",
        "differences": "Model claims matching context.",
        "reason": "Model claims evidence supports the answer.",
    }
    if tamper == "contradiction":
        basis["current_checks"][0]["finding"] = "contradicts"
    elif tamper == "receipt":
        basis["prior_question"]["check_sha256"] = "0" * 64
    elif tamper == "role":
        basis["role"] = "Backup representative"
    elif tamper == "period":
        raw["requirements"]["requirements"][0]["requested_period"] = {
            "start": "2026-01-01",
            "end": "2026-12-31",
        }
        raw["layout"]["responses"][0]["requirement"]["requested_period"] = raw["requirements"][
            "requirements"
        ][0]["requested_period"]
    altered = DraftRequest.model_validate_json(json.dumps(raw))
    gated = validate_answers(
        setup.evidence_root,
        altered,
        hashlib.sha256(altered.model_dump_json().encode()).hexdigest(),
        historical_context_checks=review.historical_context_checks,
    )
    assert gated.decisions[0].decision == "withhold"


@pytest.mark.parametrize(("version", "policy"), [(1, "answer_first_review"), (2, "conservative")])
def test_legacy_and_conservative_uncertainty_policy_is_preserved(
    tmp_path, monkeypatch, version, policy
):
    setup, request, review = semantic_request(tmp_path, monkeypatch)
    raw = request.model_dump(mode="json")
    raw["schema_version"] = version
    raw["historical_policy"] = policy
    raw["proposals"]["proposals"][0]["historical_basis"]["correspondence"] = {
        "target_question": request.requirements.requirements[0].instruction,
        "assessment": "uncertain",
        "differences": "Legacy review candidate.",
        "reason": "Legacy policy retains reviewable interpretation.",
    }
    altered = DraftRequest.model_validate_json(json.dumps(raw))
    gated = validate_answers(
        setup.evidence_root,
        altered,
        hashlib.sha256(altered.model_dump_json().encode()).hexdigest(),
        historical_context_checks=review.historical_context_checks,
    )
    assert gated.decisions[0].decision == "draft_verified", gated.decisions[0].reason


@pytest.mark.parametrize(("version", "policy"), [(1, "answer_first_review"), (2, "conservative")])
def test_new_partial_assessment_never_enables_incomplete_answer_writing(
    tmp_path, monkeypatch, version, policy
):
    setup, request, review = semantic_request(tmp_path, monkeypatch)
    raw = request.model_dump(mode="json")
    raw["schema_version"] = version
    raw["historical_policy"] = policy
    raw["proposals"]["proposals"][0]["historical_basis"]["correspondence"] = {
        "target_question": request.requirements.requirements[0].instruction,
        "assessment": "partially_applicable",
        "differences": "Requested information remains unsupported.",
        "reason": "Only part of the requested answer is supported.",
    }
    altered = DraftRequest.model_validate_json(json.dumps(raw))
    gated = validate_answers(
        setup.evidence_root,
        altered,
        hashlib.sha256(altered.model_dump_json().encode()).hexdigest(),
        historical_context_checks=review.historical_context_checks,
    )
    assert gated.decisions[0].decision == "withhold"
    assert "historical_question_partially_applicable" in gated.decisions[0].reason
