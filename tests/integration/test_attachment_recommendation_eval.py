"""Opt-in semantic evaluation of general supporting-document recommendations."""

import json
import os
from typing import Literal

import pytest

from bd_packet_builder.agent import AGENT_INSTRUCTIONS
from bd_packet_builder.contracts import Contract, Nonblank
from bd_packet_builder.foundry import FoundryConfig, request_structured


class AttachmentDecision(Contract):
    decision: Literal["include", "exclude", "review_required"]
    reason: Nonblank


CASES = (
    (
        "An issuer checklist explicitly requests the firm's audited FY2025 statements. "
        "The candidate is the firm's audited FY2025 financial report, with matching entity "
        "and printed year.",
        "include",
    ),
    (
        "The form asks the firm to describe its U.S. agency market capabilities. The candidate "
        "is a current corporate-agency business overview describing the firm's services and "
        "capabilities. It is not a market snapshot or an audited performance record.",
        "include",
    ),
    (
        "The issuer requests the firm's sustainable-finance activities. The candidate is a "
        "current firm statement describing the firm's own role in those activities and covers "
        "the requested period.",
        "include",
    ),
    (
        "The form asks for agency underwriting league-table experience during FY2025. An "
        "approved packet from another municipality linked a league table to a question about "
        "the same firm-wide underwriting experience. The candidate table is for this firm, "
        "the same ranking category and FY2025.",
        "include",
    ),
    (
        "The current form asks only for settlement instructions. A prior packet from another "
        "municipality included a broad U.S. agency market snapshot, but its linked question "
        "and reason for inclusion are unavailable. The snapshot does not contain settlement "
        "instructions.",
        "exclude_or_review",
    ),
    (
        "The current form requests settlement and delivery instructions for the firm's "
        "identified legal entity and account. The candidate is the approved confidential "
        "instruction document for that same entity and account.",
        "include",
    ),
)


@pytest.mark.skipif(
    os.environ.get("BD_RUN_ATTACHMENT_EVAL") != "1",
    reason="Opt in with BD_RUN_ATTACHMENT_EVAL=1; paid synthetic attachment-reasoning evaluation",
)
@pytest.mark.parametrize(("scenario", "expected"), CASES)
def test_model_recommends_support_from_request_content_and_context(
    scenario: str, expected: str
) -> None:
    result = request_structured(
        FoundryConfig(
            endpoint=os.environ["BD_FOUNDRY_ENDPOINT"],
            deployment=os.environ["BD_FOUNDRY_DEPLOYMENT"],
            timeout_seconds=180,
        ),
        allow_paid=True,
        instructions=AGENT_INSTRUCTIONS
        + """
Evaluation only: no tools. Classify the candidate document for this current packet. Return
include only when its described contents support the current requirement; use exclude when it
does not; use review_required if the available facts cannot establish relevance. Prior inclusion
alone is never sufficient. Keep the rationale tied to the supplied scenario.
""",
        input_json=json.dumps({"scenario": scenario}),
        response_type=AttachmentDecision,
        max_output_tokens=1024,
    )
    if expected == "exclude_or_review":
        assert result.value.decision in {"exclude", "review_required"}
    else:
        assert result.value.decision == expected
