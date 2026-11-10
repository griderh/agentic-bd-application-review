"""Opt-in synthetic role-selection evaluation, separate from deterministic identity checks."""

import json
import os

import pytest

from bd_packet_builder.agent import AGENT_INSTRUCTIONS
from bd_packet_builder.foundry import FoundryConfig, request_structured
from bd_packet_builder.representatives import RepresentativeBioRequest


@pytest.mark.skipif(
    os.environ.get("BD_RUN_REPRESENTATIVE_EVAL") != "1",
    reason="Opt in with BD_RUN_REPRESENTATIVE_EVAL=1; paid synthetic representative evaluation",
)
@pytest.mark.parametrize("basis", ["current", "historical", "bio_only"])
def test_model_separates_application_assignment_from_bio_identity(basis):
    quote = "Avery Example" if basis == "historical" else "Primary representative: Avery Example"
    assignment = {
        "source_id": "a" * 64,
        "page": 1,
        "start": 0,
        "end": len(quote),
        "quote": quote,
    }
    context = {
        "evidence_kind": "historical_context",
        "source_id": "a" * 64,
        "page": 1,
        "check_sha256": "b" * 64,
        "quote": "Primary representative\nName",
    }
    result = request_structured(
        FoundryConfig(
            endpoint=os.environ["BD_FOUNDRY_ENDPOINT"],
            deployment=os.environ["BD_FOUNDRY_DEPLOYMENT"],
            timeout_seconds=180,
        ),
        allow_paid=True,
        instructions=AGENT_INSTRUCTIONS
        + """
Evaluation phase: no tools. Return the arguments for resolve_representative_bio for
the requested PRIMARY name field. Available source observations below are synthetic,
already-checked evidence. Reuse their exact citation objects; do not generate offsets.
Historical assignment may be used for identity resolution without claiming continuity.
If only a bio is available, leave person, assignment and historical_context null.
""",
        input_json=json.dumps(
            {
                "role_requirement_id": "primary_name",
                "related_requirement_ids": ["primary_name", "primary_title"],
                "role": "Primary representative",
                "assignment_evidence": None
                if basis == "bio_only"
                else {
                    "person": "Avery Example",
                    "assignment": assignment,
                    "source_family": "historical_reference"
                    if basis == "historical"
                    else "FINRA_Certification",
                    "historical_context": context if basis == "historical" else None,
                    "continuity": "unconfirmed" if basis == "historical" else "not_assessed",
                },
                "bio_candidates": [
                    {"subject": "Blair Example", "filename": "Primary representative.pdf"},
                    {"subject": "Avery Example", "filename": "Unrelated filename.pdf"},
                ],
            }
        ),
        response_type=RepresentativeBioRequest,
        max_output_tokens=2048,
    )
    assert result.role_requirement_id == "primary_name"
    assert set(result.requirement_ids) == {"primary_name", "primary_title"}
    assert result.role == "Primary representative"
    assert result.person == (None if basis == "bio_only" else "Avery Example")
    assert (result.assignment.model_dump(mode="json") if result.assignment else None) == (
        None if basis == "bio_only" else assignment
    )
    assert (
        result.historical_context.model_dump(mode="json") if result.historical_context else None
    ) == (context if basis == "historical" else None)
