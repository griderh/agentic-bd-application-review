import json

import pytest
from pydantic import ValidationError

from bd_packet_builder.contracts import AnswerProposal
from bd_packet_builder.knowledge import knowledge_context, knowledge_instructions


@pytest.mark.parametrize("phase", ["agent", "answer", "evidence", "native"])
def test_runtime_prompts_do_not_reintroduce_historical_confirmation_barriers(phase):
    from bd_packet_builder.agent import AGENT_INSTRUCTIONS
    from bd_packet_builder.grouped import ANSWER_INSTRUCTIONS, EVIDENCE_INSTRUCTIONS
    from bd_packet_builder.proposals import INSTRUCTIONS

    text = " ".join(
        {
            "agent": AGENT_INSTRUCTIONS,
            "answer": ANSWER_INSTRUCTIONS,
            "evidence": EVIDENCE_INSTRUCTIONS,
            "native": INSTRUCTIONS,
        }[phase].split()
    )
    assert "Do not extend this to financial eligibility, investigations/disclosures" not in text
    assert "Current-source inspection is not a prerequisite" in text
    assert "This verifies what the historical source said, not whether it remains true." in text
    assert "financial periods, signatures and new personal acts remain protected" in text


def test_reference_is_versioned_bounded_and_distinguishes_policy_from_evidence():
    context = knowledge_context()
    assert context["version"] == "domain-knowledge-v2"
    assert len(context["sha256"]) == 64
    entries = context["entries"]
    assert len(entries) == len({e["entry_id"] for e in entries})
    assert len(json.dumps(context)) < 24000
    assert all(e["authority"] and e["applies_to"] and e["limitations"] for e in entries)
    brokercheck = next(e for e in entries if e["entry_id"] == "brokercheck-registration")
    assert "uninterrupted" in " ".join(brokercheck["limitations"])
    assert "not source evidence" in knowledge_instructions()


def test_unknown_or_duplicate_knowledge_references_are_rejected():
    proposal = {
        "requirement_id": "test",
        "outcome": "missing_evidence",
        "explanation": "No checked evidence.",
        "knowledge_applied": [{"entry_id": "invented-rule", "reason": "Not permitted."}],
    }
    with pytest.raises(ValidationError, match="Unknown domain knowledge"):
        AnswerProposal.model_validate_json(json.dumps(proposal))
    proposal["knowledge_applied"] = [
        {"entry_id": "historical-eligibility", "reason": "Checked historical selection."},
    ] * 2
    with pytest.raises(ValidationError, match="Duplicate domain knowledge"):
        AnswerProposal.model_validate_json(json.dumps(proposal))


def test_knowledge_annotation_does_not_replace_required_evidence():
    with pytest.raises(ValidationError, match="citations"):
        AnswerProposal.model_validate_json(
            json.dumps(
                {
                    "requirement_id": "test",
                    "outcome": "proposed",
                    "confidence": 0.9,
                    "value": {"kind": "text", "value": "Unsupported"},
                    "knowledge_applied": [
                        {
                            "entry_id": "historical-eligibility",
                            "reason": "Policy is not source evidence.",
                        }
                    ],
                }
            )
        )


def test_serialized_knowledge_use_rejects_different_reference():
    raw = AnswerProposal.model_validate_json(
        json.dumps(
            {
                "requirement_id": "test",
                "outcome": "missing_evidence",
                "explanation": "No checked evidence.",
                "knowledge_applied": [
                    {
                        "entry_id": "brokercheck-registration",
                        "reason": "No continuity proof.",
                    }
                ],
            }
        )
    ).model_dump(mode="json")
    raw["knowledge_applied"][0]["reference_sha256"] = "0" * 64
    with pytest.raises(ValidationError, match="Domain knowledge changed"):
        AnswerProposal.model_validate_json(json.dumps(raw))
