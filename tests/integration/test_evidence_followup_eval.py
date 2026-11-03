"""Paid opt-in protocol/grounding cases, separate from offline contract verification."""

import json
import os

import pytest

from bd_packet_builder.foundry import FoundryConfig, request_structured
from bd_packet_builder.grouped import ANSWER_INSTRUCTIONS, _GroupAnswers


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
