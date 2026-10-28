"""Live Foundry wiring: the real page mapper, chat client and run driver for the agent."""

import asyncio
import json
from collections.abc import Callable, Mapping
from datetime import date
from importlib.metadata import version as package_version
from pathlib import Path

from agent_framework_openai import OpenAIChatClient
from azure.identity.aio import AzureCliCredential, get_bearer_token_provider
from openai import AsyncOpenAI, OpenAI

from bd_packet_builder.agent import (
    AGENT_VERSION,
    AgentLimits,
    PacketAgentTools,
    PageMapError,
    run_packet_agent,
)
from bd_packet_builder.contracts import Contract, Identifier
from bd_packet_builder.foundry import FoundryConfig, FoundryError, request_structured
from bd_packet_builder.inventory import build_inventory
from bd_packet_builder.local_inputs import read_local_input
from bd_packet_builder.run import (
    ComponentVersion,
    EvidenceItem,
    EvidenceSnapshot,
    FileRunStore,
    Label,
    RunLimits,
    RunManifest,
    RunRequest,
    RunStore,
)
from bd_packet_builder.visual import INSTRUCTIONS, PROMPT_VERSION, RenderedPage, VisualPage, _render

_REQUEST_TIMEOUT_SECONDS = 60.0
_PAGE_OUTPUT_TOKENS = 4096
# Authorized budget for live synthetic runs: 40 agent model turns, plus one call per blank page.
LIVE_LIMITS = AgentLimits(max_turns=40)


class LiveRunRequest(Contract):
    blank_name: Label
    requester_id: Identifier
    evidence_set_id: Identifier
    as_of: date | None = None


class FoundryPageMapper:
    """One bounded visual-mapping call per page of the run's blank; failures are technical."""

    def __init__(
        self,
        config: FoundryConfig,
        *,
        allow_paid: bool,
        client_factory: Callable[[FoundryConfig], OpenAI] | None = None,
    ) -> None:
        if not allow_paid:
            raise FoundryError("Live page mapping requires explicit paid-call authorization")
        self._config = config
        self._client_factory = client_factory

    def map_pages(self, blank: bytes) -> Mapping[int, VisualPage]:
        try:
            rendered = _render(blank, None)
            pages: dict[int, VisualPage] = {}
            for page in rendered:
                response = request_structured(
                    self._config,
                    allow_paid=True,
                    instructions=INSTRUCTIONS,
                    input_json=_page_input(page),
                    image_png=page.png,
                    response_type=VisualPage,
                    max_output_tokens=_PAGE_OUTPUT_TOKENS,
                    client_factory=self._client_factory,
                )
                pages[page.number] = response.value
        except FoundryError as error:
            raise PageMapError(f"Page mapping failed ({PROMPT_VERSION}): {error}") from None
        return pages


def _page_input(page: RenderedPage) -> str:
    return json.dumps(
        {
            "page": page.number,
            "display_width_points": page.width,
            "display_height_points": page.height,
            "image_width": page.pixels[0],
            "image_height": page.pixels[1],
            "native_text_optional": page.native,
        }
    )


def build_live_client(config: FoundryConfig) -> OpenAIChatClient:
    """Framework chat client for the Foundry deployment; tokens come from the work sign-in."""
    credential = AzureCliCredential(process_timeout=10)
    provider = get_bearer_token_provider(credential, "https://cognitiveservices.azure.com/.default")
    return OpenAIChatClient(
        model=config.deployment,
        async_client=AsyncOpenAI(
            base_url=config.endpoint,
            api_key=provider,
            max_retries=0,
            timeout=_REQUEST_TIMEOUT_SECONDS,
        ),
    )


def prepare_live_run(
    store: RunStore,
    request: LiveRunRequest,
    blank: bytes,
    evidence_root: Path,
    config: FoundryConfig,
) -> RunManifest:
    inventory = build_inventory(evidence_root)
    snapshot = EvidenceSnapshot(
        evidence_set_id=request.evidence_set_id,
        items=tuple(
            EvidenceItem(path=s.path, sha256=s.sha256, size_bytes=s.size_bytes)
            for s in inventory.sources
        ),
    )
    return store.create(
        RunRequest(
            evidence_set_id=request.evidence_set_id,
            requester_id=request.requester_id,
            blank_name=request.blank_name,
            as_of=request.as_of,
        ),
        blank,
        snapshot,
        versions=(
            ComponentVersion(name="code", version=package_version("bd-packet-builder")),
            ComponentVersion(name="agent", version=AGENT_VERSION),
            ComponentVersion(name="mapping-prompt", version=PROMPT_VERSION),
            ComponentVersion(name="model", version=config.deployment),
        ),
        limits=RunLimits(),
    )


async def run_live(
    store: RunStore,
    run_id: str,
    evidence_root: Path,
    config: FoundryConfig,
    *,
    allow_paid: bool,
    trace_sink: list[str] | None = None,
) -> RunManifest:
    mapper = FoundryPageMapper(config, allow_paid=allow_paid)
    client = build_live_client(config)
    tools = PacketAgentTools(store, run_id, evidence_root, mapper, limits=LIVE_LIMITS)
    try:
        return await run_packet_agent(client, tools)
    finally:
        if trace_sink is not None:
            trace_sink.extend(tools.trace)


def run_agent_command(
    root: Path,
    blank: Path,
    config: FoundryConfig,
    *,
    requester_id: str,
    evidence_set_id: str,
    as_of: date | None,
    allow_paid: bool,
    trace_sink: list[str] | None = None,
) -> RunManifest:
    """Workstation driver for slice 6: same agent code as the hosted runtime, local storage."""
    if not allow_paid:
        raise FoundryError("A live agent run requires --allow-paid")
    root = root.resolve(strict=True)
    runs = root / "outputs" / "agent-runs"
    runs.mkdir(parents=True, exist_ok=True)
    data = read_local_input(root, blank, Path("bd_agreements/Blank"), 64 * 1024 * 1024)
    store = FileRunStore(runs)
    request = LiveRunRequest(
        blank_name=blank.name,
        requester_id=requester_id,
        evidence_set_id=evidence_set_id,
        as_of=as_of,
    )
    manifest = prepare_live_run(store, request, data, root, config)
    return asyncio.run(
        run_live(store, manifest.run_id, root, config, allow_paid=True, trace_sink=trace_sink)
    )
