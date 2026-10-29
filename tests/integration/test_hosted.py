import asyncio
import json
from pathlib import Path
from unittest.mock import Mock

import pytest
from agent_framework import Message, SupportsAgentRun
from starlette.testclient import TestClient

from bd_packet_builder import hosted
from bd_packet_builder.blob_storage import PacketBlobStorage
from bd_packet_builder.foundry import FoundryConfig
from bd_packet_builder.hosted import HostedCommand, PacketHostedAgent
from bd_packet_builder.run import (
    ComponentVersion,
    EvidenceSnapshot,
    FileRunStore,
    RunLimits,
    RunRequest,
)
from tests.integration.test_blob_storage import MemoryBlobs, seed


@pytest.mark.parametrize(
    "value", ["not json", '{"operation":"shell"}', '{"operation":"build","request_id":"../bad"}']
)
def test_hosted_intake_rejects_non_commands(value: str) -> None:
    agent = PacketHostedAgent(Mock())
    with pytest.raises(ValueError):
        asyncio.run(agent.run(value))


def test_build_requires_both_staged_ids() -> None:
    with pytest.raises(ValueError):
        HostedCommand.model_validate_json('{"operation":"build","request_id":"request-1"}')


def test_invalid_command_error_does_not_echo_user_contents() -> None:
    agent = PacketHostedAgent(Mock())
    with pytest.raises(ValueError) as error:
        asyncio.run(agent.run("sensitive-example-command"))
    assert "sensitive-example-command" not in str(error.value)


def test_server_does_not_enable_sdk_telemetry_export(monkeypatch: pytest.MonkeyPatch) -> None:
    export = Mock()
    monkeypatch.setattr("microsoft.opentelemetry.use_microsoft_opentelemetry", export)
    hosted.create_server(Mock())
    export.assert_not_called()


def test_hosted_status_is_deterministic_and_does_not_call_a_model() -> None:
    backend = Mock()
    backend.status.return_value = {"status": "published", "outcome": "incomplete"}
    agent = PacketHostedAgent(backend)
    assert isinstance(agent, SupportsAgentRun)
    response = asyncio.run(
        agent.run(
            [
                Message("user", '{"operation":"status","request_id":"request-1"}'),
            ]
        )
    )
    assert json.loads(response.text)["status"] == "published"
    backend.status.assert_called_once_with("request-1")
    backend.build.assert_not_called()


def test_hosted_stream_and_nonstream_have_the_same_result() -> None:
    backend = Mock()
    backend.status.return_value = {"status": "published", "outcome": "incomplete"}
    agent = PacketHostedAgent(backend)

    async def consume() -> str:
        stream = agent.run('{"operation":"status","request_id":"request-1"}', stream=True)
        async for _ in stream:
            pass
        response = await stream.get_final_response()
        return response.text

    assert json.loads(asyncio.run(consume()))["outcome"] == "incomplete"


def test_responses_http_boundary_completes_an_id_only_status_request(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("OTEL_SDK_DISABLED", "true")
    backend = Mock()
    backend.status.return_value = {"status": "published", "outcome": "incomplete"}
    with TestClient(hosted.create_server(backend)) as client:
        assert client.get("/readiness").status_code == 200
        response = client.post(
            "/responses",
            json={
                "model": "bd-packet-builder",
                "input": '{"operation":"status","request_id":"request-1"}',
                "store": True,
            },
        )
    result = response.json()
    assert response.status_code == 200
    assert result["status"] == "completed", result
    text = result["output"][0]["content"][0]["text"]
    assert json.loads(text)["status"] == "published"
    backend.status.assert_called_once_with("request-1")


def test_unexpected_hosted_failure_publishes_failed_status_without_hiding_error(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("BD_WORK_ROOT", str(tmp_path))
    blobs = MemoryBlobs()
    seed(blobs)
    backend = hosted.BlobPacketBackend(
        PacketBlobStorage(blobs),
        FoundryConfig(endpoint="https://example.openai.azure.com/openai/v1", deployment="test"),
        allow_paid=True,
    )

    def prepare(store: FileRunStore, *_args: object) -> object:
        return store.create(
            RunRequest(evidence_set_id="set-1", requester_id="reviewer", blank_name="Form.pdf"),
            b"%PDF-blank",
            EvidenceSnapshot(evidence_set_id="set-1", items=()),
            versions=(ComponentVersion(name="code", version="test"),),
            limits=RunLimits(),
        )

    async def crash(*_args: object) -> None:
        raise RuntimeError("Synthetic unexpected technical failure")

    monkeypatch.setattr(hosted, "prepare_live_run", prepare)
    monkeypatch.setattr(backend, "_run", crash)
    with pytest.raises(RuntimeError, match="Synthetic unexpected"):
        backend.build(
            HostedCommand(
                operation="build",
                request_id="request-1",
                blank_id="blank-1",
                evidence_set_id="set-1",
            )
        )
    result = backend.status("request-1")
    assert result["status"] == "failed"
    assert result["outcome"] is None
    assert "packet.pdf" not in result["locations"]
