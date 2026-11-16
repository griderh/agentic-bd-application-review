"""Paid opt-in protocol/grounding cases, separate from offline contract verification."""

import json
import os

import pytest

from bd_packet_builder.foundry import FoundryConfig, request_structured
from bd_packet_builder.grouped import ANSWER_INSTRUCTIONS, _GroupAnswers


@pytest.mark.skipif(
    os.environ.get("BD_RUN_PROPOSAL_REPAIR_EVAL") != "1",
    reason="Opt in with BD_RUN_PROPOSAL_REPAIR_EVAL=1; paid synthetic correction evaluation",
)
@pytest.mark.parametrize("supported", [True, False])
def test_model_repairs_only_assigned_proposal_without_inventing_missing_evidence(supported):
    citation = {
        "source_id": "1" * 64,
        "page": 1,
        "quote": "Firm: Example LLC",
        "start": 0,
        "end": 17,
    }
    result = request_structured(
        FoundryConfig(
            endpoint=os.environ["BD_FOUNDRY_ENDPOINT"],
            deployment=os.environ["BD_FOUNDRY_DEPLOYMENT"],
            timeout_seconds=180,
        ),
        allow_paid=True,
        instructions=ANSWER_INSTRUCTIONS,
        input_json=json.dumps(
            {
                "requirements": [
                    {
                        "requirement_id": "p1.name",
                        "kind": "text",
                        "instruction": "Firm legal name",
                        "choices": None,
                    }
                ],
                "assigned_requirement_ids": ["p1.name"],
                "repair_requirement_ids": ["p1.name"],
                "retained_group_answers": {
                    "proposals": [
                        {
                            "requirement_id": "p1.city",
                            "outcome": "missing_evidence",
                            "explanation": "No approved city evidence.",
                        }
                    ]
                },
                "native_quote_citations": [citation] if supported else [],
                "candidate_readings": [],
                "historical_candidates": [],
                "scan_quotes": [],
                "verification_results": [],
                "verification_budget": {"followup_allowed": False, "requests_remaining": 0},
                "previous_errors": [
                    {
                        "code": "proposal_validation_failed",
                        "problems": [
                            {"requirement_id": "p1.name", "code": "proposal_schema_invalid"}
                        ],
                    }
                ],
            }
        ),
        response_type=_GroupAnswers,
        max_output_tokens=4096,
    ).value
    assert not result.verification_requests
    assert [p.requirement_id for p in result.proposals] == ["p1.name"]
    proposal = result.proposals[0]
    if supported:
        assert proposal.outcome == "proposed"
        assert proposal.value is not None and proposal.value.value == "Example LLC"
        assert [c.model_dump(mode="json") for c in proposal.citations] == [citation]
    else:
        assert proposal.outcome == "missing_evidence" and proposal.value is None


@pytest.mark.skipif(
    os.environ.get("BD_RUN_EVIDENCE_FOLLOWUP_EVAL") != "1",
    reason="Opt in with BD_RUN_EVIDENCE_FOLLOWUP_EVAL=1; paid synthetic evaluation",
)
@pytest.mark.parametrize("case", ["agreed_observation", "disputed_observation", "missing_source"])
def test_model_requests_verification_instead_of_discarding_candidate_evidence(case):
    instruction = "Report minimum net capital of $10 million on line 3750."
    observation = {
        "source_id": "1" * 64,
        "source_sha256": "2" * 64,
        "page": 8,
        "mode": "ocr",
        "text": "Name of Firm: Example Firm\nNet capital 12,345,678 [3750]",
        "scope": "candidate_observation_not_verified_answer_evidence",
    }
    candidates = [] if case == "missing_source" else [observation]
    if case == "disputed_observation":
        candidates.append(
            {
                **observation,
                "mode": "image",
                "text": "Name of Firm: Example Firm\nNet capital 1,234,567 3750",
            }
        )
    config = FoundryConfig(
        endpoint=os.environ["BD_FOUNDRY_ENDPOINT"],
        deployment=os.environ["BD_FOUNDRY_DEPLOYMENT"],
        timeout_seconds=180,
    )
    result = request_structured(
        config,
        allow_paid=True,
        instructions=ANSWER_INSTRUCTIONS,
        input_json=json.dumps(
            {
                "requirements": [
                    {
                        "requirement_id": "p2.capital",
                        "kind": "text",
                        "instruction": instruction,
                        "choices": None,
                    }
                ],
                "assigned_requirement_ids": ["p2.capital"],
                "candidate_readings": candidates,
                "native_quote_citations": [],
                "scan_quotes": [],
                "historical_candidates": [],
                "verification_results": [],
                "previous_errors": [],
            }
        ),
        response_type=_GroupAnswers,
        max_output_tokens=8192,
    ).value
    if case == "missing_source":
        assert not result.verification_requests
        assert len(result.proposals) == 1
        assert result.proposals[0].outcome == "missing_evidence"
    else:
        assert result.verification_requests
        assert all(
            r.source_id == observation["source_id"] and r.page == 8
            for r in result.verification_requests
        )
        assert all(p.outcome != "proposed" for p in result.proposals)
