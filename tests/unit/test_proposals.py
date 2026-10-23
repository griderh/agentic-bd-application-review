import json
from pathlib import Path
from unittest.mock import Mock

import pytest
from pydantic import ValidationError

from bd_packet_builder.foundry import (
    FoundryConfig,
    FoundryError,
    SmokeAnswers,
    request_structured,
)
from bd_packet_builder.proposals import ModelProposals, generate_proposals

CONFIG = FoundryConfig(
    endpoint="https://synthetic-resource.openai.azure.com/openai/v1", deployment="synthetic-model"
)


def test_model_wire_schema_uses_anyof_but_preserves_strict_application_types() -> None:
    schema = json.dumps(ModelProposals.model_json_schema())
    assert '"oneOf"' not in schema
    assert '"discriminator"' not in schema
    assert '"anyOf"' in schema
    with pytest.raises(ValidationError):
        ModelProposals.model_validate_json(
            json.dumps(
                {
                    "proposals": [
                        {
                            "requirement_id": "test",
                            "outcome": "proposed",
                            "confidence": 1.0,
                            "value": {"kind": "identifier", "value": 1234},
                            "citations": [],
                        }
                    ]
                }
            )
        )


@pytest.mark.parametrize("tokens,input_json", [(0, "{}"), (4097, "{}"), (1024, "x" * 65537)])
def test_request_bounds_fail_before_creating_client(tokens: int, input_json: str) -> None:
    factory = Mock()
    with pytest.raises(FoundryError, match="limit"):
        request_structured(
            CONFIG,
            allow_paid=True,
            instructions="synthetic",
            input_json=input_json,
            response_type=SmokeAnswers,
            max_output_tokens=tokens,
            client_factory=factory,
        )
    factory.assert_not_called()


def test_generation_opt_in_precedes_evidence_access(tmp_path: Path) -> None:
    from datetime import UTC, datetime

    from bd_packet_builder.contracts import ApplicationRequirements, Requirement
    from bd_packet_builder.inventory import Inventory

    request = ApplicationRequirements(
        requirements=(
            Requirement(
                requirement_id="test",
                application_sha256="0" * 64,
                page=1,
                instruction="Synthetic question",
                kind="text",
            ),
        )
    )
    factory = Mock()
    with pytest.raises(FoundryError, match="allow-paid"):
        generate_proposals(
            tmp_path,
            Inventory(datetime.now(UTC), (), ()),
            request,
            CONFIG,
            allow_paid=False,
            client_factory=factory,
        )
    factory.assert_not_called()
