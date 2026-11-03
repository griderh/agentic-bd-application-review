"""Live Foundry wiring: the real page mapper, chat client and run driver for the agent."""

import asyncio
import hashlib
import json
import os
from collections.abc import Callable, Mapping
from datetime import UTC, date, datetime
from importlib.metadata import version as package_version
from pathlib import Path
from typing import Annotated
from uuid import uuid4

from agent_framework_openai import OpenAIChatClient
from azure.identity.aio import AzureCliCredential, get_bearer_token_provider
from openai import AsyncOpenAI, OpenAI
from pydantic import Field, ValidationError

from bd_packet_builder.agent import (
    AGENT_VERSION,
    AgentLimits,
    PacketAgentTools,
    PageMapError,
)
from bd_packet_builder.contracts import Contract, Identifier, Nonblank
from bd_packet_builder.evidence_tools import EvidenceLimits
from bd_packet_builder.foundry import (
    FoundryConfig,
    FoundryError,
    FoundrySchemaError,
    request_structured,
    write_private_json,
)
from bd_packet_builder.grouped import GROUP_VERSION, run_grouped_packet_agent
from bd_packet_builder.historical_context import CONTEXT_VERSION
from bd_packet_builder.history import (
    ArchiveManifest,
    HistoricalReusePolicy,
    HistoryError,
    with_historical_sources,
)
from bd_packet_builder.inventory import build_inventory
from bd_packet_builder.knowledge import KNOWLEDGE_SHA256, REFERENCE
from bd_packet_builder.local_inputs import read_local_input
from bd_packet_builder.reconciliation import RequirementAssessment, RequirementAssessments
from bd_packet_builder.retrieval import SOURCE_CONTEXT_VERSION
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
from bd_packet_builder.scan import SCAN_VERSION, FoundryScanReader
from bd_packet_builder.visual import INSTRUCTIONS, PROMPT_VERSION, RenderedPage, VisualPage, _render

_PAGE_OUTPUT_TOKENS = 16_384
_SCHEMA_ATTEMPTS = 2
# Hash-keyed page maps of blank forms; Git-ignored and reused only for identical inputs/config.
MAPPING_CACHE = Path("outputs/page-map-cache")
# Explicit bounded full-questionnaire profile, including both current and historical reading.
LIVE_LIMITS = AgentLimits(max_turns=60, max_tool_calls=240, max_seconds=3600)
LIVE_EVIDENCE_LIMITS = EvidenceLimits(
    max_calls=200,
    max_pages_read=80,
    max_ocr_pages=20,
    max_chars_returned=500_000,
)
LIVE_MAX_MODEL_CALLS = LIVE_LIMITS.max_turns + 10 + LIVE_EVIDENCE_LIMITS.max_ocr_pages


class LiveRunRequest(Contract):
    blank_name: Label
    requester_id: Identifier
    evidence_set_id: Identifier
    as_of: date | None = None
    issuer: Nonblank | None = None
    historical_archive: ArchiveManifest | None = None
    historical_policy: HistoricalReusePolicy = "conservative"
    requirement_assessments: Annotated[
        tuple[RequirementAssessment, ...], Field(max_length=100)
    ] = ()


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
                pages[page.number] = self._request_page(page)
                if cache is not None:
                    write_private_json(cache, pages[page.number].model_dump(mode="json"))
        except FoundryError as error:
            raise PageMapError(
                f"Page {current_page} mapping failed ({PROMPT_VERSION}): {error}"
            ) from None
        return pages

    def _request_page(self, page: RenderedPage) -> VisualPage:
        """Malformed output gets one fresh request; transport, auth and timeout errors do not."""
        for attempt in range(1, _SCHEMA_ATTEMPTS + 1):
            try:
                return request_structured(
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
                ).value
            except FoundrySchemaError as error:
                if attempt == _SCHEMA_ATTEMPTS:
                    raise FoundryError(
                        f"after {_SCHEMA_ATTEMPTS} schema-invalid model responses: {error}"
                    ) from None
        raise AssertionError("unreachable")


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
    inventory = with_historical_sources(
        evidence_root, build_inventory(evidence_root), request.historical_archive
    )
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
            issuer=request.issuer,
            historical_archive=request.historical_archive,
            historical_policy=request.historical_policy,
            requirement_assessments=request.requirement_assessments,
        ),
        blank,
        snapshot,
        versions=(
            ComponentVersion(name="code", version=package_version("bd-packet-builder")),
            ComponentVersion(name="agent", version=AGENT_VERSION),
            ComponentVersion(name="mapping-prompt", version=PROMPT_VERSION),
            ComponentVersion(name="scan-prompt", version=SCAN_VERSION),
            ComponentVersion(name="historical-context", version=CONTEXT_VERSION),
            ComponentVersion(name="reading-budget", version="full-questionnaire-v1"),
            ComponentVersion(name="answer-workflow", version=GROUP_VERSION),
            ComponentVersion(name="source-context", version=SOURCE_CONTEXT_VERSION),
            ComponentVersion(name="domain-knowledge", version=REFERENCE.version),
            ComponentVersion(name="domain-knowledge-sha256", version=KNOWLEDGE_SHA256),
            ComponentVersion(
                name="inference-endpoint",
                version=hashlib.sha256(config.endpoint.encode()).hexdigest(),
            ),
            ComponentVersion(name="model", version=config.deployment),
            ComponentVersion(name="http-timeout-seconds", version=str(config.timeout_seconds)),
        ),
        limits=RunLimits(max_steps=500),
    )


def export_run(store: RunStore, run_id: str, runs_dir: Path) -> Path:
    """Copy a run's blank, manifest and artifacts to readable names for human review."""
    manifest = store.load(run_id)
    folder = runs_dir / run_id / "readable"
    folder.mkdir(parents=True, exist_ok=True, mode=0o700)
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
    progress_sink: Callable[[str], None] | None = None,
    resume: bool = False,
    mapping_cache_dir: Path | None = None,
) -> RunManifest:
    if not allow_paid:
        raise FoundryError("A live agent run requires --allow-paid")
    manifest = store.load(run_id)
    if resume:
        validate_resume_configuration(manifest, config)
    mapper = FoundryPageMapper(config, allow_paid=allow_paid, diagnostics_dir=mapping_cache_dir)
    client = build_live_client(config)
    tools = PacketAgentTools(
        store,
        run_id,
        evidence_root,
        mapper,
        limits=LIVE_LIMITS,
        evidence_limits=LIVE_EVIDENCE_LIMITS,
        scan_reader=FoundryScanReader(config, allow_paid=allow_paid),
        scan_endpoint=config.endpoint,
        scan_deployment=config.deployment,
        progress_sink=progress_sink,
    )
    try:
        return await run_grouped_packet_agent(client, tools, resume=resume)
    finally:
        if trace_sink is not None:
            trace_sink.extend(tools.trace)


def validate_resume_configuration(manifest: RunManifest, config: FoundryConfig) -> None:
    versions = {v.name: v.version for v in manifest.versions}
    if (
        versions.get("agent") != AGENT_VERSION
        or versions.get("model") != config.deployment
        or versions.get("inference-endpoint")
        != hashlib.sha256(config.endpoint.encode()).hexdigest()
        or versions.get("answer-workflow") != GROUP_VERSION
        or versions.get("domain-knowledge") != REFERENCE.version
        or versions.get("domain-knowledge-sha256") != KNOWLEDGE_SHA256
    ):
        raise FoundryError(
            "Recovery requires the original model, workflow configuration and domain knowledge"
        )


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
    progress_sink: Callable[[str], None] | None = None,
    runs_dir: Path | None = None,
    historical_manifest: Path | None = None,
    issuer: str | None = None,
    historical_policy: HistoricalReusePolicy = "conservative",
    requirement_assessments: Path | None = None,
) -> RunManifest:
    """Workstation driver for slice 6: same agent code as the hosted runtime, local storage."""
    if not allow_paid:
        raise FoundryError("A live agent run requires --allow-paid")
    root = root.resolve(strict=True)
    assessments: tuple[RequirementAssessment, ...] = ()
    if requirement_assessments is not None:
        try:
            assessments = RequirementAssessments.model_validate_json(
                read_local_input(root, requirement_assessments, Path("outputs"), 2 * 1024 * 1024)
            ).assessments
        except ValidationError:
            raise FoundryError("Requirement review input failed schema validation") from None
    historical_archive = None
    if historical_manifest is not None:
        if issuer is None:
            raise HistoryError("Historical discovery requires an explicit target issuer")
        try:
            historical_archive = ArchiveManifest.model_validate_json(
                read_local_input(root, historical_manifest, Path("outputs"), 2 * 1024 * 1024)
            )
        except ValidationError:
            raise HistoryError("Historical partition manifest failed schema validation") from None
    runs = runs_dir or root / "outputs" / "agent-runs"
    runs.mkdir(parents=True, exist_ok=True)
    data = read_local_input(root, blank, Path("bd_agreements/Blank"), 64 * 1024 * 1024)
    store = FileRunStore(runs)
    request = LiveRunRequest(
        blank_name=blank.name,
        requester_id=requester_id,
        evidence_set_id=evidence_set_id,
        as_of=as_of,
        historical_archive=historical_archive,
        historical_policy=historical_policy,
        requirement_assessments=assessments,
        issuer=issuer,
    )
    manifest = prepare_live_run(store, request, data, root, config)
    progress_path = runs / manifest.run_id / "progress.jsonl"
    with os.fdopen(
        os.open(progress_path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600),
        "w",
        encoding="utf-8",
    ) as log:

        def emit(event: str) -> None:
            log.write(
                json.dumps({"timestamp": datetime.now(UTC).isoformat(), "event": event}) + "\n"
            )
            log.flush()
            if progress_sink is not None:
                progress_sink(event)

        emit(
            f"Fresh paid agent execution started; run ID {manifest.run_id}; "
            f"HTTP request timeout {config.timeout_seconds}s; "
            f"private run directory {runs / manifest.run_id}"
        )
        try:
            return asyncio.run(
                run_live(
                    store,
                    manifest.run_id,
                    root,
                    config,
                    allow_paid=True,
                    trace_sink=trace_sink,
                    progress_sink=emit,
                    mapping_cache_dir=root / MAPPING_CACHE,
                )
            )
        finally:
            readable = export_run(store, manifest.run_id, runs)
            final = store.load(manifest.run_id)
            failure = (
                f"; failure_code={final.failure.code}; reason={final.failure.message}"
                if final.failure
                else ""
            )
            emit(
                f"Run ended: status={final.status}, outcome={final.outcome}{failure}; "
                f"human-readable artifacts {readable}"
            )


def resume_agent_command(
    root: Path,
    runs_dir: Path,
    run_id: str,
    config: FoundryConfig,
    *,
    allow_paid: bool,
) -> RunManifest:
    if not allow_paid:
        raise FoundryError("Answer recovery requires --allow-paid")
    store = FileRunStore(runs_dir)
    try:
        return asyncio.run(
            run_live(
                store,
                run_id,
                root,
                config,
                allow_paid=True,
                resume=True,
                mapping_cache_dir=root.resolve(strict=True) / MAPPING_CACHE,
            )
        )
    finally:
        export_run(store, run_id, runs_dir)
