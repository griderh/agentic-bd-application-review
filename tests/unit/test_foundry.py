import json
from pathlib import Path
from unittest.mock import MagicMock, Mock

import httpx2
import pytest
from azure.identity import CredentialUnavailableError
from openai import OpenAI
from pydantic import ValidationError

from bd_packet_builder.foundry import (
    FoundryConfig,
    FoundryError,
    SmokeAnswers,
    evaluate_smoke,
    run_foundry_smoke,
)

ENDPOINT = "https://synthetic-resource.services.ai.azure.com/openai/v1"


def answers() -> SmokeAnswers:
    return SmokeAnswers.model_validate_json(
        json.dumps(
            {
                "legal_name": {
                    "value": "Example Demonstration LLC",
                    "source_id": "synthetic-identity",
                    "quote": "Legal name: Example Demonstration LLC",
                },
                "crd": {
                    "value": "001234",
                    "source_id": "synthetic-identity",
                    "quote": "CRD: 001234",
                },
                "tax_id": None,
                "phone": None,
                "signature": None,
                "signature_date": None,
            }
        )
    )


def response(parsed: SmokeAnswers | None = None) -> Mock:
    return Mock(
        status="completed",
        output_parsed=parsed or answers(),
        model="synthetic-model-version",
        usage=Mock(input_tokens=400, output_tokens=200, total_tokens=600),
    )


@pytest.mark.parametrize(
    "endpoint",
    [
        "http://synthetic-resource.services.ai.azure.com/openai/v1",
        "https://example.com/openai/v1",
        ENDPOINT + "?key=secret",
        "https://user:password@synthetic-resource.services.ai.azure.com/openai/v1",
        ENDPOINT + "/unexpected",
        "https://synthetic-resource.services.ai.azure.com:8443/openai/v1",
    ],
)
def test_config_rejects_unapproved_destinations(endpoint: str) -> None:
    with pytest.raises(ValidationError):
        FoundryConfig(endpoint=endpoint, deployment="synthetic-model")


def test_live_calls_require_explicit_opt_in_before_credentials_or_files(tmp_path: Path) -> None:
    factory = Mock()
    with pytest.raises(FoundryError, match="allow-paid"):
        run_foundry_smoke(
            tmp_path,
            FoundryConfig(endpoint=ENDPOINT, deployment="synthetic-model"),
            allow_paid=False,
            client_factory=factory,
        )
    factory.assert_not_called()
    assert not (tmp_path / "outputs").exists()


def test_smoke_is_one_bounded_synthetic_request_and_writes_json_only(tmp_path: Path) -> None:
    client = Mock()
    client.responses.parse.return_value = response()
    factory = Mock(return_value=client)
    result = run_foundry_smoke(
        tmp_path,
        FoundryConfig(endpoint=ENDPOINT, deployment="synthetic-model"),
        allow_paid=True,
        client_factory=factory,
    )
    client.responses.parse.assert_called_once()
    kwargs = client.responses.parse.call_args.kwargs
    assert kwargs["model"] == "synthetic-model"
    assert kwargs["store"] is False
    assert kwargs["max_output_tokens"] == 2048
    assert "Example Demonstration LLC" in kwargs["input"]
    assert "bd_agreements" not in kwargs["input"]
    assert "tools" not in kwargs
    client.close.assert_called_once()
    data = json.loads((result / "foundry-smoke.json").read_text())
    assert data["status"] == "synthetic_smoke_passed_not_packet"
    assert data["checks_passed"] == data["checks_total"] == 6
    assert data["observed_model"] == "synthetic-model-version"
    assert data["usage"]["total_tokens"] == 600
    assert len(data["prompt_sha256"]) == 64
    assert list(result.iterdir()) == [result / "foundry-smoke.json"]


@pytest.mark.parametrize(
    "field,value",
    [
        (
            "tax_id",
            {"value": "invented", "source_id": "synthetic-identity", "quote": "CRD: 001234"},
        ),
        ("crd", {"value": "1234", "source_id": "synthetic-identity", "quote": "CRD: 001234"}),
        (
            "legal_name",
            {
                "value": "Example Demonstration LLC",
                "source_id": "unknown",
                "quote": "Legal name: Example Demonstration LLC",
            },
        ),
        (
            "signature",
            {"value": "Signed", "source_id": "synthetic-identity", "quote": "CRD: 001234"},
        ),
        (
            "phone",
            {"value": "555-0101", "source_id": "synthetic-identity", "quote": "Phone: 555-0101"},
        ),
    ],
)
def test_measurable_failures_are_not_blessed_as_grounded(field: str, value: dict) -> None:
    data = answers().model_dump()
    data[field] = value
    checked = SmokeAnswers.model_validate(data)
    assert not all(evaluate_smoke(checked).values())


@pytest.mark.parametrize("kind", ["incomplete", "refusal", "missing-usage", "oversized"])
def test_incomplete_refused_or_unmeasurable_responses_do_not_publish(
    tmp_path: Path, kind: str
) -> None:
    client = Mock()
    reply = response()
    if kind == "incomplete":
        reply.status = "incomplete"
    elif kind == "refusal":
        reply.output_parsed = None
    elif kind == "missing-usage":
        reply.usage = None
    else:
        reply.usage.output_tokens = 2049
    client.responses.parse.return_value = reply
    with pytest.raises(FoundryError):
        run_foundry_smoke(
            tmp_path,
            FoundryConfig(endpoint=ENDPOINT, deployment="synthetic-model"),
            allow_paid=True,
            client_factory=Mock(return_value=client),
        )
    client.close.assert_called_once()
    assert not list((tmp_path / "outputs").glob("foundry-smoke-*"))


def test_behavior_failure_is_recorded_explicitly(tmp_path: Path) -> None:
    client = Mock()
    failed = answers().model_copy(update={"legal_name": None})
    client.responses.parse.return_value = response(failed)
    result = run_foundry_smoke(
        tmp_path,
        FoundryConfig(endpoint=ENDPOINT, deployment="synthetic-model"),
        allow_paid=True,
        client_factory=Mock(return_value=client),
    )
    data = json.loads((result / "foundry-smoke.json").read_text())
    assert data["status"] == "synthetic_smoke_failed_not_packet"
    assert data["checks_passed"] == 5


def test_cli_does_not_call_model_by_default(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    from bd_packet_builder.cli import main

    assert (
        main(
            [
                "foundry-smoke",
                "--root",
                str(tmp_path),
                "--endpoint",
                ENDPOINT,
                "--deployment",
                "synthetic-model",
            ]
        )
        == 1
    )
    assert "allow-paid" in capsys.readouterr().err


@pytest.mark.parametrize("status", [401, 403, 404, 429, 500])
def test_http_failures_are_safe_and_never_retried(tmp_path: Path, status: int) -> None:
    calls = []

    def handler(request: httpx2.Request) -> httpx2.Response:
        calls.append(request)
        return httpx2.Response(
            status, json={"error": {"message": "PRIVATE_REMOTE_PAYLOAD", "code": "test"}}
        )

    client = OpenAI(
        api_key="synthetic-test-token",
        base_url=ENDPOINT,
        max_retries=0,
        http_client=httpx2.Client(transport=httpx2.MockTransport(handler)),
    )
    with pytest.raises(FoundryError, match=f"HTTP {status}") as caught:
        run_foundry_smoke(
            tmp_path,
            FoundryConfig(endpoint=ENDPOINT, deployment="synthetic-model"),
            allow_paid=True,
            client_factory=lambda _: client,
        )
    assert "PRIVATE_REMOTE_PAYLOAD" not in str(caught.value)
    assert len(calls) == 1
    request = json.loads(calls[0].content)
    assert request["text"]["format"]["strict"] is True
    assert request["text"]["format"]["schema"]["additionalProperties"] is False
    assert request["store"] is False
    assert request["max_output_tokens"] == 2048
    assert calls[0].url.path == "/openai/v1/responses"
    assert not (tmp_path / "outputs").exists()


@pytest.mark.parametrize("failure", ["timeout", "connection", "schema"])
def test_transport_and_schema_errors_are_explicit(tmp_path: Path, failure: str) -> None:
    def handler(request: httpx2.Request) -> httpx2.Response:
        if failure == "timeout":
            raise httpx2.ReadTimeout("PRIVATE", request=request)
        if failure == "connection":
            raise httpx2.ConnectError("PRIVATE", request=request)
        return httpx2.Response(
            200,
            json={
                "id": "resp_synthetic",
                "object": "response",
                "created_at": 0,
                "model": "synthetic-model",
                "status": "completed",
                "output": [
                    {
                        "type": "message",
                        "id": "msg_test",
                        "role": "assistant",
                        "status": "completed",
                        "content": [
                            {"type": "output_text", "text": '{"crd": 1234}', "annotations": []}
                        ],
                    }
                ],
                "parallel_tool_calls": False,
                "tool_choice": "auto",
                "tools": [],
            },
        )

    client = OpenAI(
        api_key="synthetic-test-token",
        base_url=ENDPOINT,
        max_retries=0,
        http_client=httpx2.Client(transport=httpx2.MockTransport(handler)),
    )
    with pytest.raises(FoundryError) as caught:
        run_foundry_smoke(
            tmp_path,
            FoundryConfig(endpoint=ENDPOINT, deployment="synthetic-model"),
            allow_paid=True,
            client_factory=lambda _: client,
        )
    assert "PRIVATE" not in str(caught.value)
    assert not (tmp_path / "outputs").exists()


def test_real_factory_uses_only_cli_identity_and_disables_sdk_retries(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from bd_packet_builder import foundry

    credential = MagicMock()
    cli = Mock(return_value=credential)
    provider = Mock(return_value=Mock(return_value="synthetic-token"))
    client = Mock()
    client.responses.parse.return_value = response()
    constructor = Mock(return_value=client)
    monkeypatch.setattr(foundry, "AzureCliCredential", cli)
    monkeypatch.setattr(foundry, "get_bearer_token_provider", provider)
    monkeypatch.setattr(foundry, "OpenAI", constructor)
    run_foundry_smoke(
        tmp_path,
        FoundryConfig(endpoint=ENDPOINT, deployment="synthetic-model"),
        allow_paid=True,
    )
    cli.assert_called_once_with(process_timeout=10)
    provider.assert_called_once_with(
        credential.__enter__.return_value, "https://cognitiveservices.azure.com/.default"
    )
    credential.__exit__.assert_called_once()
    assert constructor.call_args.kwargs["max_retries"] == 0
    assert constructor.call_args.kwargs["timeout"] == 60.0


def test_credential_failure_has_safe_context_and_no_report(tmp_path: Path) -> None:
    with pytest.raises(FoundryError, match="Azure CLI") as caught:
        run_foundry_smoke(
            tmp_path,
            FoundryConfig(endpoint=ENDPOINT, deployment="synthetic-model"),
            allow_paid=True,
            client_factory=Mock(side_effect=CredentialUnavailableError("PRIVATE_ACCOUNT_DETAILS")),
        )
    assert "PRIVATE_ACCOUNT_DETAILS" not in str(caught.value)
    assert not (tmp_path / "outputs").exists()


def test_output_symlink_is_rejected_before_authentication(tmp_path: Path) -> None:
    outside = tmp_path / "elsewhere"
    outside.mkdir()
    (tmp_path / "outputs").symlink_to(outside, target_is_directory=True)
    factory = Mock()
    with pytest.raises(FoundryError, match="symlink"):
        run_foundry_smoke(
            tmp_path,
            FoundryConfig(endpoint=ENDPOINT, deployment="synthetic-model"),
            allow_paid=True,
            client_factory=factory,
        )
    factory.assert_not_called()
    assert not list(outside.iterdir())
