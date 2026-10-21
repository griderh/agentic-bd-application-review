import json
from pathlib import Path

import pytest
from reportlab.pdfgen.canvas import Canvas

from bd_packet_builder.contracts import AnswerProposal, Requirement, check_proposal
from bd_packet_builder.evidence import extract_evidence
from bd_packet_builder.inventory import InventoryError, build_inventory


@pytest.fixture
def example(tmp_path: Path) -> tuple[Path, Requirement, AnswerProposal]:
    path = tmp_path / "bd_agreements/supporting_data/Focus_Reports/Example_July2026.pdf"
    path.parent.mkdir(parents=True)
    canvas = Canvas(str(path))
    canvas.drawString(40, 700, "Net capital USD 1234.50")
    canvas.save()
    inventory = build_inventory(tmp_path)
    page = extract_evidence(tmp_path, inventory).documents[0].pages[0]
    requirement = Requirement.model_validate_json(
        json.dumps(
            {
                "requirement_id": "capital",
                "application_sha256": "a" * 64,
                "page": 1,
                "instruction": "Provide net capital in USD",
                "kind": "money",
                "unit": "USD",
            }
        )
    )
    proposal = AnswerProposal.model_validate_json(
        json.dumps(
            {
                "requirement_id": "capital",
                "outcome": "proposed",
                "value": {"kind": "money", "amount": "1234.50", "unit": "USD"},
                "citations": [
                    {
                        "source_id": page.source_id,
                        "page": 1,
                        "start": 0,
                        "end": len(page.text),
                        "quote": page.text,
                    }
                ],
                "confidence": 0.99,
            }
        )
    )
    return tmp_path, requirement, proposal


def test_resolvable_quote_is_not_approval_or_proof_of_support(
    example: tuple[Path, Requirement, AnswerProposal],
) -> None:
    root, requirement, proposal = example
    result = check_proposal(root, build_inventory(root), requirement, proposal)
    assert result.status == "review_required"
    assert result.fill_value is None
    assert result.resolved_citations == 1
    assert "semantic_support_unverified" in result.issues
    assert "source_approval_unverified" in result.issues


@pytest.mark.parametrize("kind", ["signature", "signature_date"])
def test_signing_fields_never_have_fill_values(
    example: tuple[Path, Requirement, AnswerProposal],
    kind: str,
) -> None:
    root, req, proposal = example
    requirement = Requirement.model_validate_json(
        json.dumps(
            {
                **req.model_dump(mode="json"),
                "kind": kind,
                "unit": None,
            }
        )
    )
    result = check_proposal(root, build_inventory(root), requirement, proposal)
    assert result.status == "deferred_to_signing"
    assert result.fill_value is None


@pytest.mark.parametrize(
    ("change", "issue"),
    [
        ({"requirement_id": "other"}, "requirement_id_mismatch"),
        ({"value": {"kind": "money", "amount": "1234.50", "unit": "EUR"}}, "unit_mismatch"),
        ({"value": {"kind": "identifier", "value": "001234"}}, "answer_kind_mismatch"),
        (
            {
                "citations": [
                    {"source_id": "0" * 64, "page": 1, "start": 0, "end": 4, "quote": "fake"}
                ]
            },
            "citation_unresolved",
        ),
    ],
)
def test_inconsistent_or_fabricated_proposals_are_rejected(
    example: tuple[Path, Requirement, AnswerProposal],
    change: dict[str, object],
    issue: str,
) -> None:
    root, req, proposal = example
    modified = AnswerProposal.model_validate_json(
        json.dumps(
            {
                **proposal.model_dump(mode="json"),
                **change,
            }
        )
    )
    result = check_proposal(root, build_inventory(root), req, modified)
    assert result.status == "rejected"
    assert issue in result.issues
    assert result.fill_value is None


def test_model_period_claim_cannot_verify_reporting_period(
    example: tuple[Path, Requirement, AnswerProposal],
) -> None:
    root, req, proposal = example
    period = {"start": "2026-07-31", "end": "2026-07-31"}
    requirement = Requirement.model_validate_json(
        json.dumps(
            {
                **req.model_dump(mode="json"),
                "requested_period": period,
            }
        )
    )
    proposed = AnswerProposal.model_validate_json(
        json.dumps(
            {
                **proposal.model_dump(mode="json"),
                "claimed_period": period,
            }
        )
    )
    result = check_proposal(root, build_inventory(root), requirement, proposed)
    assert "reporting_period_unverified" in result.issues
    assert result.fill_value is None


def test_period_mismatch_is_explicit_without_silently_filling(
    example: tuple[Path, Requirement, AnswerProposal],
) -> None:
    root, req, proposal = example
    requirement = Requirement.model_validate_json(
        json.dumps(
            {
                **req.model_dump(mode="json"),
                "requested_period": {"start": "2026-08-31", "end": "2026-08-31"},
            }
        )
    )
    proposed = AnswerProposal.model_validate_json(
        json.dumps(
            {
                **proposal.model_dump(mode="json"),
                "claimed_period": {"start": "2026-07-31", "end": "2026-07-31"},
            }
        )
    )
    result = check_proposal(root, build_inventory(root), requirement, proposed)
    assert "requested_period_mismatch" in result.issues
    assert result.status == "review_required"
    assert result.fill_value is None


def test_source_mutation_is_technical_failure_not_missing_evidence(
    example: tuple[Path, Requirement, AnswerProposal],
) -> None:
    root, req, proposal = example
    inventory = build_inventory(root)
    (root / inventory.sources[0].path).write_bytes(b"changed")
    with pytest.raises(InventoryError, match="changed"):
        check_proposal(root, inventory, req, proposal)


def test_unanswered_proposal_preserves_explicit_exception(
    example: tuple[Path, Requirement, AnswerProposal],
) -> None:
    root, req, _ = example
    missing = AnswerProposal.model_validate_json(
        json.dumps(
            {
                "requirement_id": req.requirement_id,
                "outcome": "missing_evidence",
                "explanation": "No approved report available",
            }
        )
    )
    result = check_proposal(root, build_inventory(root), req, missing)
    assert result.status == "unanswered"
    assert result.issues == ("missing_evidence",)
    assert result.fill_value is None


def test_attachment_must_match_a_resolved_citation(
    example: tuple[Path, Requirement, AnswerProposal],
) -> None:
    root, req, proposal = example
    requirement = Requirement.model_validate_json(
        json.dumps(
            {
                **req.model_dump(mode="json"),
                "kind": "attachment",
                "unit": None,
            }
        )
    )
    data = proposal.model_dump(mode="json")
    data["value"] = {"kind": "attachment", "source_id": "0" * 64}
    candidate = AnswerProposal.model_validate_json(json.dumps(data))
    result = check_proposal(root, build_inventory(root), requirement, candidate)
    assert result.status == "rejected"
    assert "attachment_source_not_cited" in result.issues
    data["value"]["source_id"] = proposal.citations[0].source_id
    result = check_proposal(
        root,
        build_inventory(root),
        requirement,
        AnswerProposal.model_validate_json(json.dumps(data)),
    )
    assert result.status == "review_required"


def test_real_but_unrelated_quote_cannot_pass_semantic_support(
    example: tuple[Path, Requirement, AnswerProposal],
) -> None:
    root, req, proposal = example
    data = proposal.model_dump(mode="json")
    data["value"] = {"kind": "money", "amount": "999999.00", "unit": "USD"}
    result = check_proposal(
        root, build_inventory(root), req, AnswerProposal.model_validate_json(json.dumps(data))
    )
    assert result.status == "review_required"
    assert "semantic_support_unverified" in result.issues
    assert result.fill_value is None


def test_altered_quote_rejected_without_suppressing_technical_errors(
    example: tuple[Path, Requirement, AnswerProposal],
) -> None:
    root, req, proposal = example
    data = proposal.model_dump(mode="json")
    data["citations"][0]["quote"] = "X" * len(proposal.citations[0].quote)
    result = check_proposal(
        root, build_inventory(root), req, AnswerProposal.model_validate_json(json.dumps(data))
    )
    assert result.status == "rejected"
    assert "citation_quote_mismatch" in result.issues


def test_required_signer_role_is_not_inferred_from_answer_text(
    example: tuple[Path, Requirement, AnswerProposal],
) -> None:
    root, req, proposal = example
    requirement = Requirement.model_validate_json(
        json.dumps(
            {
                **req.model_dump(mode="json"),
                "required_signer_role": "Chief Compliance Officer",
            }
        )
    )
    result = check_proposal(root, build_inventory(root), requirement, proposal)
    assert "signer_role_unverified" in result.issues
    assert result.fill_value is None
