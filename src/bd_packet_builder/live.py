"""Live Foundry wiring: the real page mapper, chat client and run driver for the agent."""

import asyncio
import hashlib
import json
from collections.abc import Callable, Mapping
from datetime import date
from importlib.metadata import version as package_version
from pathlib import Path
from uuid import uuid4

from agent_framework_openai import OpenAIChatClient
from azure.identity.aio import AzureCliCredential, get_bearer_token_provider
from openai import AsyncOpenAI, OpenAI
from pydantic import ValidationError

from bd_packet_builder.agent import (
    AGENT_VERSION,
    AgentLimits,
    PacketAgentTools,
    PageMapError,
    run_packet_agent,
)
from bd_packet_builder.contracts import Contract, Identifier
from bd_packet_builder.foundry import (
    FoundryConfig,
    FoundryError,
    request_structured,
    write_private_json,
)
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

_PAGE_OUTPUT_TOKENS = 16_384
# Reserve five page-mapping calls within the authorized 40-call total.
LIVE_LIMITS = AgentLimits(max_turns=35)


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
        diagnostics_dir: Path | None = None,
        selected_pages: tuple[int, ...] | None = None,
    ) -> None:
        if not allow_paid:
            raise FoundryError("Live page mapping requires explicit paid-call authorization")
        self._config = config
        self._client_factory = client_factory
        self._diagnostics_dir = diagnostics_dir
        self._selected_pages = selected_pages
        if diagnostics_dir is not None:
            diagnostics_dir.mkdir(mode=0o700, parents=True, exist_ok=True)
            if diagnostics_dir.resolve() != diagnostics_dir.absolute():
                raise FoundryError("Mapping diagnostics must not resolve through symlinks")

    def _cache_key(self, blank: bytes, page: RenderedPage) -> str:
        identity = {
            "blank_sha256": hashlib.sha256(blank).hexdigest(),
            "page_input": _page_input(page),
            "image_sha256": hashlib.sha256(page.png).hexdigest(),
            "instructions": INSTRUCTIONS,
            "prompt_version": PROMPT_VERSION,
            "schema": VisualPage.model_json_schema(),
            "endpoint": self._config.endpoint,
            "deployment": self._config.deployment,
            "max_output_tokens": _PAGE_OUTPUT_TOKENS,
        }
        return hashlib.sha256(json.dumps(identity, sort_keys=True).encode()).hexdigest()

    def map_pages(self, blank: bytes) -> Mapping[int, VisualPage]:
        pages: dict[int, VisualPage] = {}
        current_page = 1
        try:
            rendered = _render(blank, self._selected_pages)
            for page in rendered:
                current_page = page.number
                cache = (
                    self._diagnostics_dir / f"{self._cache_key(blank, page)}.json"
                    if self._diagnostics_dir is not None
                    else None
                )
                if cache is not None and cache.exists():
                    if cache.is_symlink() or cache.stat().st_size > 64 * 1024:
                        raise FoundryError("Invalid mapping cache artifact")
                    try:
                        pages[page.number] = VisualPage.model_validate_json(cache.read_bytes())
                    except ValidationError:
                        raise FoundryError("Cached page map failed schema validation") from None
                    continue
                response = request_structured(
                    self._config,
                    allow_paid=True,
                    instructions=INSTRUCTIONS,
                    input_json=_page_input(page),
                    image_png=page.png,
                    response_type=VisualPage,
                    max_output_tokens=_PAGE_OUTPUT_TOKENS,
                    output_token_limit=16_384,
                    client_factory=self._client_factory,
                    diagnostic_path=(
                        self._diagnostics_dir / f"page-{page.number}-{uuid4().hex}.json"
                        if self._diagnostics_dir is not None
                        else None
                    ),
                )
                pages[page.number] = response.value
                if cache is not None:
                    write_private_json(cache, response.value.model_dump(mode="json"))
        except FoundryError as error:
            raise PageMapError(
                f"Page {current_page} mapping failed ({PROMPT_VERSION}): {error}"
            ) from None
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
            timeout=config.timeout_seconds,
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


def export_run(store: RunStore, run_id: str, runs_dir: Path) -> Path:
    """Copy a run's blank, manifest and artifacts to readable names for human review."""
    manifest = store.load(run_id)
    folder = runs_dir / run_id / "readable"
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "manifest.json").write_text(manifest.model_dump_json(indent=2), encoding="utf-8")
    (folder / "blank.pdf").write_bytes(store.read_blank(run_id))
    for artifact in manifest.artifacts:
        (folder / artifact.name).write_bytes(store.read_artifact(run_id, artifact.name))
    return folder


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
    runs_dir: Path | None = None,
) -> RunManifest:
    """Workstation driver for slice 6: same agent code as the hosted runtime, local storage."""
    if not allow_paid:
        raise FoundryError("A live agent run requires --allow-paid")
    root = root.resolve(strict=True)
    runs = runs_dir or root / "outputs" / "agent-runs"
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
    try:
        return asyncio.run(
            run_live(store, manifest.run_id, root, config, allow_paid=True, trace_sink=trace_sink)
        )
    finally:
        export_run(store, manifest.run_id, runs)
