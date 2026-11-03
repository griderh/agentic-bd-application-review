"""Explicit, repeatable local demo configuration for the approved Broward reference."""

import hashlib
import json
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from bd_packet_builder.foundry import FoundryConfig, write_private_json
from bd_packet_builder.history import ArchiveEntry, ArchiveManifest
from bd_packet_builder.inventory import SourceRecord, build_inventory
from bd_packet_builder.live import run_agent_command
from bd_packet_builder.run import RunManifest

BROWARD_BLANK = Path("bd_agreements/Blank/Broward_County/BrokerDealerQuestionnaire.pdf")
BROWARD_REFERENCE = Path(
    "bd_agreements/Completed/Broward_County/Application to Broward County from InspereX.2026.pdf"
)
DEFAULT_ENDPOINT = "https://bd-application-builder-resource.openai.azure.com/openai/v1"
DEFAULT_DEPLOYMENT = "gpt-6.1-sol"
DEFAULT_REQUEST_TIMEOUT_SECONDS = 180


@dataclass(frozen=True)
class BrowardDemoPlan:
    root: Path
    blank: Path
    blank_sha256: str
    historical_source: ArchiveEntry
    historical_manifest: Path
    available_sources: tuple[SourceRecord, ...]
    evidence_set_id: str


def prepare_broward_demo(root: Path) -> BrowardDemoPlan:
    root = root.resolve(strict=True)
    blank = root / BROWARD_BLANK
    historical = root / BROWARD_REFERENCE
    for path in (blank, historical):
        if (
            path.is_symlink()
            or any(parent.is_symlink() for parent in path.parents if parent != root.parent)
            or not path.is_file()
            or not path.resolve(strict=True).is_relative_to(root)
            or path.stat().st_size > 64 * 1024 * 1024
        ):
            raise ValueError(f"Demo input is missing, unsafe, or exceeds size limit: {path.name}")
    blank_hash = hashlib.sha256(blank.read_bytes()).hexdigest()
    historical_hash = hashlib.sha256(historical.read_bytes()).hexdigest()
    entry = ArchiveEntry(
        path=BROWARD_REFERENCE.as_posix(),
        sha256=historical_hash,
        partition="reference",
        issuer="Broward County",
    )
    archive = ArchiveManifest(entries=(entry,))
    output = root / "outputs" / "demo-inputs"
    output.mkdir(mode=0o700, parents=True, exist_ok=True)
    if output.is_symlink() or output.resolve(strict=True) != output.absolute():
        raise ValueError("Demo input manifest directory must not resolve through symlinks")
    manifest_path = output / f"broward-reference-{historical_hash[:16]}.json"
    serialized = archive.model_dump(mode="json")
    if manifest_path.exists():
        if (
            manifest_path.is_symlink()
            or not manifest_path.is_file()
            or manifest_path.stat().st_size > 2 * 1024 * 1024
            or ArchiveManifest.model_validate_json(manifest_path.read_bytes()) != archive
        ):
            raise ValueError("Existing demo reference manifest does not match the approved input")
    else:
        write_private_json(manifest_path, serialized)
    sources = build_inventory(root).sources
    evidence_digest = hashlib.sha256(
        json.dumps(
            sorted(
                [
                    *((source.path, source.sha256) for source in sources),
                    (entry.path, entry.sha256),
                ]
            ),
            separators=(",", ":"),
        ).encode()
    ).hexdigest()
    return BrowardDemoPlan(
        root=root,
        blank=BROWARD_BLANK,
        blank_sha256=blank_hash,
        historical_source=entry,
        historical_manifest=manifest_path.relative_to(root),
        available_sources=sources,
        evidence_set_id=f"broward-demo-{evidence_digest[:24]}",
    )


def run_broward_demo(
    plan: BrowardDemoPlan,
    config: FoundryConfig,
    *,
    progress_sink: Callable[[str], None],
    runs_dir: Path | None = None,
    requirement_assessments: Path | None = None,
) -> RunManifest:
    return run_agent_command(
        plan.root,
        plan.blank,
        config,
        requester_id="broward-demo",
        evidence_set_id=plan.evidence_set_id,
        as_of=None,
        allow_paid=True,
        runs_dir=runs_dir,
        historical_manifest=plan.historical_manifest,
        issuer="Broward County",
        historical_policy="answer_first_review",
        progress_sink=progress_sink,
        requirement_assessments=requirement_assessments,
    )


def demo_config(
    endpoint: str = DEFAULT_ENDPOINT,
    deployment: str = DEFAULT_DEPLOYMENT,
    timeout_seconds: int = DEFAULT_REQUEST_TIMEOUT_SECONDS,
) -> FoundryConfig:
    return FoundryConfig(endpoint=endpoint, deployment=deployment, timeout_seconds=timeout_seconds)
