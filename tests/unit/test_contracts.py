import json

import pytest
from pydantic import ValidationError

from bd_packet_builder.contracts import AnswerProposal, ApplicationRequirements, Requirement


def requirement(**changes: object) -> dict[str, object]:
    return {
        "requirement_id": "net-capital",
        "application_sha256": "a" * 64,
        "page": 1,
        "instruction": "Provide net capital as of July 31, 2026 in USD.",
        "kind": "money",
        "unit": "USD",
        "requested_period": {"start": "2026-07-31", "end": "2026-07-31"},
        **changes,
    }


def proposal(**changes: object) -> dict[str, object]:
    return {
        "requirement_id": "net-capital",
        "outcome": "proposed",
        "value": {"kind": "money", "amount": "1234.50", "unit": "USD"},
        "citations": [{"source_id": "b" * 64, "page": 1, "start": 0, "end": 7, "quote": "1234.50"}],
        "confidence": 0.9,
        **changes,
    }


def test_requirement_retains_exact_instruction_and_requested_period() -> None:
    result = Requirement.model_validate_json(json.dumps(requirement()))
    assert result.requested_period is not None
    assert result.requested_period.end.isoformat() == "2026-07-31"
    assert result.unit == "USD"
    assert "July 31" in result.instruction


@pytest.mark.parametrize(
    "changes",
    [
        {"page": True},
        {"page": "1"},
        {"page": 0},
        {"application_sha256": "../document"},
        {"instruction": ""},
        {"instruction": "  "},
        {"unit": None},
        {"requested_period": {"start": "2026-08-01", "end": "2026-07-31"}},
        {"requested_period": {"start": "07/31/26", "end": "2026-07-31"}},
        {"arbitrary_tool": "send_email"},
        {"kind": "identifier", "unit": "USD"},
    ],
)
def test_malformed_requirements_are_rejected(changes: dict[str, object]) -> None:
    with pytest.raises(ValidationError):
        Requirement.model_validate_json(json.dumps(requirement(**changes)))


def test_identifiers_preserve_leading_zeroes_and_booleans_are_not_coerced() -> None:
    data = proposal(value={"kind": "identifier", "value": "001234"})
    result = AnswerProposal.model_validate_json(json.dumps(data))
    assert result.value is not None
    assert result.value.kind == "identifier"
    assert result.value.value == "001234"
    for invalid in [0, "false", "no"]:
        with pytest.raises(ValidationError):
            AnswerProposal.model_validate_json(
                json.dumps(proposal(value={"kind": "boolean", "value": invalid}))
            )
    result = AnswerProposal.model_validate_json(
        json.dumps(proposal(value={"kind": "boolean", "value": False}))
    )
    assert result.value is not None and result.value.value is False


@pytest.mark.parametrize("amount", [1234.5, "1,234.50", "1e6", "NaN", "Infinity", "", " 12"])
def test_money_requires_explicit_plain_decimal_string(amount: object) -> None:
    with pytest.raises(ValidationError):
        AnswerProposal.model_validate_json(
            json.dumps(proposal(value={"kind": "money", "amount": amount, "unit": "USD"}))
        )


@pytest.mark.parametrize(
    "changes",
    [
        {"citations": []},
        {"value": None},
        {"confidence": True},
        {"confidence": 1.1},
        {"confidence": "0.9"},
        {"approved": True},
        {"citations": [{"source_id": "b" * 64, "page": 1, "start": 0, "end": 9, "quote": "abc"}]},
        {"value": {"kind": "date", "value": "07/31/26"}},
    ],
)
def test_proposals_require_typed_value_and_well_formed_evidence(
    changes: dict[str, object],
) -> None:
    with pytest.raises(ValidationError):
        AnswerProposal.model_validate_json(json.dumps(proposal(**changes)))


@pytest.mark.parametrize(
    "outcome", ["missing_evidence", "conflicting_evidence", "unresolved_signer"]
)
def test_unanswered_outcomes_require_explanation_and_no_value(outcome: str) -> None:
    data = proposal(
        outcome=outcome, value=None, citations=[], explanation="Needs reviewer evidence"
    )
    assert AnswerProposal.model_validate_json(json.dumps(data)).value is None
    with pytest.raises(ValidationError):
        AnswerProposal.model_validate_json(json.dumps({**data, "explanation": None}))
    with pytest.raises(ValidationError):
        AnswerProposal.model_validate_json(
            json.dumps({**data, "value": {"kind": "text", "value": "x"}})
        )


def test_duplicate_requirement_ids_are_rejected_and_schema_is_versioned() -> None:
    data = {"schema_version": 1, "requirements": [requirement(), requirement()]}
    with pytest.raises(ValidationError):
        ApplicationRequirements.model_validate_json(json.dumps(data))
    data["requirements"] = [requirement()]
    result = ApplicationRequirements.model_validate_json(json.dumps(data))
    assert result.schema_version == 1
    assert ApplicationRequirements.model_json_schema()["additionalProperties"] is False
    data["schema_version"] = 2
    with pytest.raises(ValidationError):
        ApplicationRequirements.model_validate_json(json.dumps(data))


def test_attachment_value_identifies_source_without_paths_or_delivery_actions() -> None:
    result = AnswerProposal.model_validate_json(
        json.dumps(proposal(value={"kind": "attachment", "source_id": "b" * 64}))
    )
    assert result.value is not None and result.value.kind == "attachment"
    with pytest.raises(ValidationError):
        AnswerProposal.model_validate_json(
            json.dumps(
                proposal(
                    value={"kind": "attachment", "source_id": "b" * 64, "destination": "/tmp/file"}
                )
            )
        )


def test_money_uses_decimal_and_preserves_zero_without_float_conversion() -> None:
    from decimal import Decimal

    from bd_packet_builder.contracts import MoneyValue

    result = MoneyValue(kind="money", amount="0.00", unit="USD")
    assert result.decimal_amount == Decimal("0.00")
    assert result.amount == "0.00"


@pytest.mark.parametrize("version", [True, "1", 1.0])
def test_schema_version_is_an_integer_not_a_coerced_literal(version: object) -> None:
    with pytest.raises(ValidationError):
        AnswerProposal.model_validate_json(json.dumps(proposal(schema_version=version)))


def test_requirement_sets_cannot_mix_application_versions() -> None:
    data = {
        "requirements": [
            requirement(),
            requirement(requirement_id="other", application_sha256="b" * 64),
        ]
    }
    with pytest.raises(ValidationError, match="one application"):
        ApplicationRequirements.model_validate_json(json.dumps(data))
