"""Foundry Responses hosting boundary for staged-ID packet runs.

The transport accepts JSON commands. Conversational selection and authenticated
result links belong to slice 8; it must not pretend Blob paths are download links.
"""

import asyncio
import json
import os
import threading
from collections.abc import AsyncIterator, Awaitable, Mapping, Sequence
from datetime import date
from pathlib import Path
from typing import Any, Literal, Protocol, Self, overload
from uuid import uuid4

from agent_framework import (
    AgentResponse,
    AgentResponseUpdate,
    AgentRunInputs,
    AgentSession,
    Content,
    Message,
    ResponseStream,
    ServiceSessionId,
)
from agent_framework_foundry_hosting import ResponsesHostServer
from agent_framework_openai import OpenAIChatClient
from azure.identity import DefaultAzureCredential, get_bearer_token_provider
from azure.identity.aio import DefaultAzureCredential as AsyncDefaultAzureCredential
from azure.identity.aio import get_bearer_token_provider as async_token_provider
from azure.storage.blob import BlobServiceClient
from openai import AsyncOpenAI, OpenAI
from pydantic import Field, model_validator

from bd_packet_builder.agent import PacketAgentTools, run_packet_agent
from bd_packet_builder.blob_storage import (
    REVIEWS,
    AzureBlobs,
    BlobStorageError,
    PacketBlobStorage,
    validate_account_url,
)
from bd_packet_builder.contracts import Contract
from bd_packet_builder.foundry import FoundryConfig, FoundryError
from bd_packet_builder.live import LIVE_LIMITS, FoundryPageMapper, LiveRunRequest, prepare_live_run
from bd_packet_builder.run import FileRunStore, RunManifest

# PDFium cannot run concurrently in threads, including across independent runs.
_PDF_RUN_LOCK = threading.Lock()


class HostedCommand(Contract):
    operation: Literal["build", "status"]
    request_id: str = Field(pattern=r"^[a-zA-Z0-9_-]{1,128}$")
    blank_id: str | None = Field(default=None, pattern=r"^[a-zA-Z0-9_-]{1,128}$")
    evidence_set_id: str | None = Field(default=None, pattern=r"^[a-zA-Z0-9_-]{1,128}$")
    as_of: date | None = None

    @model_validator(mode="after")
    def build_ids(self) -> Self:
        if self.operation == "build" and (self.blank_id is None or self.evidence_set_id is None):
            raise ValueError("Build requires staged blank and evidence-set IDs")
        return self


class PacketBackend(Protocol):
    def build(self, command: HostedCommand) -> dict[str, object]: ...

    def status(self, request_id: str) -> dict[str, object]: ...


class BlobPacketBackend:
    def __init__(
        self,
        storage: PacketBlobStorage,
        config: FoundryConfig,
        *,
        allow_paid: bool,
        mapping_diagnostics_dir: Path | None = None,
    ) -> None:
        self.storage = storage
        self.config = config
        self.allow_paid = allow_paid
        self.mapping_diagnostics_dir = mapping_diagnostics_dir

    def status(self, request_id: str) -> dict[str, object]:
        # A missing result is an explicit storage error, not a fictional successful status.
        value: dict[str, object] = json.loads(
            self.storage.blobs.read(REVIEWS, f"requests/{request_id}-result.json", 2 * 1024 * 1024)
        )
        return value

    def build(self, command: HostedCommand) -> dict[str, object]:
        if not self.allow_paid:
            raise FoundryError("Hosted model calls are disabled; enable BD_ALLOW_PAID explicitly")
        if command.blank_id is None or command.evidence_set_id is None:
            raise ValueError("Build requires staged IDs")
        with _PDF_RUN_LOCK:
            work = Path(os.environ.get("BD_WORK_ROOT", str(Path.home() / ".bd-packet-runs")))
            if work.is_symlink() or work.resolve() != work.absolute():
                raise BlobStorageError("Work root must not resolve through symlinks")
            root = work / uuid4().hex
            root.mkdir(parents=True)
            bundle = self.storage.stage(command.blank_id, command.evidence_set_id, root)
            self.storage.claim(command.request_id, command.blank_id, command.evidence_set_id)
            runs = root / "runs"
            runs.mkdir()
            store = FileRunStore(runs)
            manifest = prepare_live_run(
                store,
                LiveRunRequest(
                    blank_name=Path(bundle.blank.path).name,
                    requester_id="authorized-foundry-poc",
                    evidence_set_id=command.evidence_set_id,
                    as_of=command.as_of,
                ),
                (root / bundle.blank.path).read_bytes(),
                root,
                self.config,
            )
            try:
                manifest = asyncio.run(self._run(store, manifest.run_id, root))
            finally:
                # Preserve failures as well as successful drafts; publication errors propagate.
                current = store.load(manifest.run_id)
                if current.status not in ("published", "failed", "cancelled"):
                    current = store.fail(
                        manifest.run_id,
                        code="hosted_run_interrupted",
                        message="Hosted execution ended before publication; inspect run state.",
                    )
                self.storage.publish(command.request_id, store, current)
            return self.status(command.request_id)

    async def _run(self, store: FileRunStore, run_id: str, root: Path) -> RunManifest:
        with DefaultAzureCredential() as mapping_credential:
            mapping_token = get_bearer_token_provider(
                mapping_credential, "https://cognitiveservices.azure.com/.default"
            )

            def mapping_client(config: FoundryConfig) -> OpenAI:
                return OpenAI(
                    base_url=config.endpoint,
                    api_key=mapping_token,
                    timeout=config.timeout_seconds,
                    max_retries=0,
                )

            mapper = FoundryPageMapper(
                self.config,
                allow_paid=True,
                client_factory=mapping_client,
                diagnostics_dir=self.mapping_diagnostics_dir,
            )
            async with (
                AsyncDefaultAzureCredential() as credential,
                AsyncOpenAI(
                    base_url=self.config.endpoint,
                    api_key=async_token_provider(
                        credential, "https://cognitiveservices.azure.com/.default"
                    ),
                    timeout=self.config.timeout_seconds,
                    max_retries=0,
                ) as api,
            ):
                client = OpenAIChatClient(model=self.config.deployment, async_client=api)
                tools = PacketAgentTools(store, run_id, root, mapper, limits=LIVE_LIMITS)
                return await run_packet_agent(client, tools)


class PacketHostedAgent:
    id = "bd-packet-builder"
    name = "Broker-dealer packet builder"
    description = "Build packets from staged blank and evidence IDs, or read a prior run result."

    def __init__(self, backend: PacketBackend) -> None:
        self.backend = backend

    def create_session(self, *, session_id: str | None = None) -> AgentSession:
        return AgentSession(session_id=session_id)

    def get_session(
        self, service_session_id: str | ServiceSessionId, *, session_id: str | None = None
    ) -> AgentSession:
        return AgentSession(service_session_id=service_session_id, session_id=session_id)

    @overload
    def run(
        self,
        messages: AgentRunInputs | None = None,
        *,
        stream: Literal[False] = False,
        session: AgentSession | None = None,
        function_invocation_kwargs: Mapping[str, Any] | None = None,
        client_kwargs: Mapping[str, Any] | None = None,
    ) -> Awaitable[AgentResponse[None]]: ...

    @overload
    def run(
        self,
        messages: AgentRunInputs | None = None,
        *,
        stream: Literal[True],
        session: AgentSession | None = None,
        function_invocation_kwargs: Mapping[str, Any] | None = None,
        client_kwargs: Mapping[str, Any] | None = None,
    ) -> ResponseStream[AgentResponseUpdate, AgentResponse[None]]: ...

    def run(
        self,
        messages: AgentRunInputs | None = None,
        *,
        stream: bool = False,
        session: AgentSession | None = None,
        function_invocation_kwargs: Mapping[str, Any] | None = None,
        client_kwargs: Mapping[str, Any] | None = None,
    ) -> Awaitable[AgentResponse[None]] | ResponseStream[AgentResponseUpdate, AgentResponse[None]]:
        async def respond() -> AgentResponse[None]:
            command = HostedCommand.model_validate_json(_command_text(messages))
            if command.operation == "status":
                result = await asyncio.to_thread(self.backend.status, command.request_id)
            else:
                result = await asyncio.to_thread(self.backend.build, command)
            return AgentResponse(messages=[Message("assistant", json.dumps(result))])

        if not stream:
            return respond()
        response: AgentResponse[None] | None = None

        async def updates() -> AsyncIterator[AgentResponseUpdate]:
            nonlocal response
            response = await respond()
            yield AgentResponseUpdate(role="assistant", contents=[Content.from_text(response.text)])

        def finish(_updates: Sequence[AgentResponseUpdate]) -> AgentResponse[None]:
            if response is None:
                raise RuntimeError("Run stream did not produce a response")
            return response

        return ResponseStream(updates(), finalizer=finish)


def _command_text(messages: AgentRunInputs | None) -> str:
    if isinstance(messages, str):
        return messages
    if isinstance(messages, Message):
        if messages.role == "user":
            return messages.text
    elif messages is not None and not isinstance(messages, Content):
        users = [m for m in messages if isinstance(m, Message) and m.role == "user"]
        if users:
            return users[-1].text
    raise ValueError("Provide one JSON command as a user message")


def create_server(backend: PacketBackend) -> ResponsesHostServer:
    # The custom protocol agent owns its history; only IDs/results cross this boundary.
    return ResponsesHostServer(
        PacketHostedAgent(backend), history_source="agent", configure_observability=None
    )


def main() -> None:
    account = validate_account_url(os.environ["BD_BLOB_ACCOUNT_URL"])
    config = FoundryConfig(
        endpoint=os.environ["BD_MODEL_ENDPOINT"],
        deployment=os.environ["AZURE_AI_MODEL_DEPLOYMENT_NAME"],
    )
    with (
        DefaultAzureCredential() as credential,
        BlobServiceClient(
            account,
            credential=credential,
            retry_total=0,
            connection_timeout=10,
            read_timeout=60,
        ) as client,
    ):
        backend = BlobPacketBackend(
            PacketBlobStorage(AzureBlobs(client)),
            config,
            allow_paid=os.environ.get("BD_ALLOW_PAID") == "1",
        )
        create_server(backend).run()
