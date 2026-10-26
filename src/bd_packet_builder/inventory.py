"""Read-only local metadata snapshots, not extracted facts or proof of grounding."""

import hashlib
import json
import os
import re
import stat
from collections import Counter
from collections.abc import Callable
from dataclasses import asdict, dataclass, replace
from datetime import UTC, date, datetime
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Literal
from uuid import uuid4

import pypdfium2 as pdfium
import pypdfium2.raw as pdfium_raw

from bd_packet_builder.sources import Cadence, filename_period, select_document

_SUPPORT = Path("bd_agreements/supporting_data")
_FAMILIES: dict[str, Cadence] = {"Focus_Reports": "monthly", "Audited_Financials": "annual"}
_EXTENSIONS = {".pdf", ".png", ".jpg", ".jpeg", ".doc", ".docx"}
_MAX_BYTES = 64 * 1024 * 1024


class InventoryError(ValueError):
    """Safe validation/freshness errors, without document text or absolute source paths."""


@dataclass(frozen=True)
class SourceRecord:
    source_id: str
    path: str
    sha256: str
    size_bytes: int
    format: str
    family: str
    page_count: int | None
    period: str | None
    period_precision: Cadence | None
    period_basis: str | None
    flags: tuple[str, ...]


@dataclass(frozen=True)
class InventoryIssue:
    path: str
    code: str


@dataclass(frozen=True)
class Inventory:
    created_at: datetime
    sources: tuple[SourceRecord, ...]
    issues: tuple[InventoryIssue, ...]


@dataclass(frozen=True)
class EvidenceSelection:
    family: str
    source: SourceRecord | None
    period: str | None
    requested_period: str | None
    flags: tuple[str, ...]


@dataclass(frozen=True)
class EvidenceReference:
    """Internal page reference; external/model payload schemas are a later increment."""

    source_id: str
    page: int

    def __post_init__(self) -> None:
        if not isinstance(self.source_id, str) or not re.fullmatch("[0-9a-f]{64}", self.source_id):
            raise InventoryError("Invalid source identity")
        if type(self.page) is not int or self.page < 1:
            raise InventoryError("Reference page must be a positive integer")


def _support_root(root: Path) -> Path:
    support = root / _SUPPORT
    if support.resolve() != support or not support.is_dir():
        raise InventoryError("A real local supporting-data directory is required; no symlinks")
    return support


def _source_path(root: Path, relative: str) -> Path:
    path = Path(relative)
    if path.is_absolute() or ".." in path.parts or not path.is_relative_to(_SUPPORT):
        raise InventoryError("Source must be inside the supporting-data directory")
    _support_root(root)
    target = root / path
    for parent in (target, *target.parents):
        if parent == root:
            break
        if parent.is_symlink():
            raise InventoryError("Source symlink is not permitted")
    if target.resolve() != target:
        raise InventoryError("Source path must not resolve through a symlink")
    return target


def _fingerprint(info: os.stat_result) -> tuple[int, ...]:
    return info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns, info.st_ctime_ns


def _snapshot(root: Path, relative: str) -> bytes:
    path = _source_path(root, relative)
    with path.open("rb") as stream:
        before = os.fstat(stream.fileno())
        if not stat.S_ISREG(before.st_mode):
            raise InventoryError("Source must be a regular file")
        if before.st_size > _MAX_BYTES:
            raise InventoryError("Source exceeds the 64 MiB local inventory limit")
        data = stream.read(_MAX_BYTES + 1)
        after = os.fstat(stream.fileno())
    current = _source_path(root, relative).stat()
    if (
        len(data) > _MAX_BYTES
        or len(data) != before.st_size
        or _fingerprint(before) != _fingerprint(after)
        or _fingerprint(after) != _fingerprint(current)
    ):
        raise InventoryError("Source changed during reading; no inventory was published")
    return data


def _period_label(period: date, cadence: Cadence) -> str:
    return str(period.year) if cadence == "annual" else period.strftime("%Y-%m")


def _pdf_pages(data: bytes) -> tuple[int | None, tuple[str, ...]]:
    try:
        with pdfium.PdfDocument(data) as document:
            if pdfium_raw.FPDF_GetSecurityHandlerRevision(document) >= 0:
                return None, ("encrypted_pdf",)
            count = len(document)
            if count < 1:
                return None, ("unreadable_pdf",)
            return count, ()
    except pdfium.PdfiumError:
        return None, ("unreadable_pdf",)


def _record(root: Path, relative: str) -> SourceRecord:
    path = Path(relative)
    data = _snapshot(root, relative)
    digest = hashlib.sha256(data).hexdigest()
    identity = hashlib.sha256(relative.encode("utf-8") + b"\0" + digest.encode("ascii")).hexdigest()
    family = path.relative_to(_SUPPORT).parts[0] if path.parent != _SUPPORT else "unassigned"
    cadence = _FAMILIES.get(family)
    period = filename_period(path, cadence=cadence) if cadence else None
    flags = ["content_date_unverified"]
    if cadence is None:
        flags.append("period_not_configured")
    elif period is None:
        flags.append("unparseable_period")
    if path.suffix.lower() == ".pdf":
        pages, pdf_flags = _pdf_pages(data)
        flags.extend(pdf_flags)
    else:
        pages = None
        flags.append("page_reference_unavailable")
    return SourceRecord(
        source_id=identity,
        path=relative,
        sha256=digest,
        size_bytes=len(data),
        format=path.suffix.lower()[1:],
        family=family,
        page_count=pages,
        period=_period_label(period, cadence) if period is not None and cadence else None,
        period_precision=cadence,
        period_basis="filename_only" if period is not None else None,
        flags=tuple(flags),
    )


def build_inventory(
    root: Path, *, families: tuple[str, ...] | None = None, max_sources: int | None = None
) -> Inventory:
    """Scan only the designated supporting-data tree; never follow source symlinks.

    Unsupported inputs are visible issues. Access failures abort the snapshot instead
    of silently omitting evidence. No text extraction, copies, or network calls occur.
    """
    root = root.resolve(strict=True)
    support = _support_root(root)
    if families is not None and (
        not families
        or len(set(families)) != len(families)
        or any(not name or Path(name).name != name or name in (".", "..") for name in families)
    ):
        raise InventoryError("Targeted families must be distinct single directory names")
    if max_sources is not None and (type(max_sources) is not int or max_sources < 1):
        raise InventoryError("Inventory source limit must be a positive integer")
    sources: list[SourceRecord] = []
    issues: list[InventoryIssue] = []

    def visit(folder: Path) -> None:
        if folder.resolve() != folder:
            raise InventoryError("Supporting directory changed to a symlink during inventory")
        with os.scandir(folder) as entries:
            ordered = sorted(entries, key=lambda entry: entry.name)
        for entry in ordered:
            path = Path(entry.path)
            relative = path.relative_to(root).as_posix()
            if entry.is_symlink():
                issues.append(InventoryIssue(relative, "symlink_rejected"))
            elif entry.is_dir(follow_symlinks=False):
                visit(path)
            elif entry.name == ".DS_Store":
                continue
            elif not entry.is_file(follow_symlinks=False):
                issues.append(InventoryIssue(relative, "nonregular_file"))
            elif path.suffix.lower() not in _EXTENSIONS:
                issues.append(InventoryIssue(relative, "unsupported_format"))
            else:
                if max_sources is not None and len(sources) >= max_sources:
                    raise InventoryError("Targeted inventory exceeds its source limit")
                sources.append(_record(root, relative))

    if families is None:
        visit(support)
    else:
        for family in families:
            folder = support / family
            if folder.is_symlink():
                raise InventoryError("Targeted source family must not be a symlink")
            if folder.exists():
                if not folder.is_dir():
                    raise InventoryError("Targeted source family must be a directory")
                visit(folder)
    counts = Counter(source.sha256 for source in sources)
    records = tuple(
        replace(source, flags=(*source.flags, "duplicate_content"))
        if counts[source.sha256] > 1
        else source
        for source in sorted(sources, key=lambda source: source.path)
    )
    return Inventory(datetime.now(UTC), records, tuple(issues))


def select_evidence(
    inventory: Inventory, family: str, *, requested_period: str | None = None
) -> EvidenceSelection:
    """Propose a filename-selected version, without approving its factual adequacy."""
    cadence = _FAMILIES.get(family)
    if cadence is None:
        raise InventoryError("Selection is not configured for this document family")
    requested = None
    if requested_period is not None:
        pattern = r"20\d{2}" if cadence == "annual" else r"20\d{2}-(0[1-9]|1[0-2])"
        if not re.fullmatch(pattern, requested_period):
            raise InventoryError("Requested period must match the family's year/month precision")
        requested = date.fromisoformat(
            requested_period + ("-01-01" if cadence == "annual" else "-01")
        )
    candidates = [s for s in inventory.sources if s.family == family]
    selection = select_document(
        (Path(s.path) for s in candidates), requested_period=requested, cadence=cadence
    )
    flags: list[str] = list(selection.flags)
    family_prefix = (_SUPPORT / family).as_posix() + "/"
    if any(i.path.startswith(family_prefix) for i in inventory.issues):
        flags.append("incomplete_family_inventory")
    source = next((s for s in candidates if Path(s.path) == selection.path), None)
    if source is not None:
        flags.extend(source.flags)
        if source.page_count is None:
            flags.append("unusable_document")
            source = None
    if "incomplete_family_inventory" in flags:
        source = None
    return EvidenceSelection(
        family,
        source,
        _period_label(selection.period, cadence) if selection.period is not None else None,
        requested_period,
        tuple(flags),
    )


def resolve_reference(
    root: Path, inventory: Inventory, reference: EvidenceReference
) -> SourceRecord:
    """Check source/version and a one-based PDF page, not semantic answer support."""
    source = next((s for s in inventory.sources if s.source_id == reference.source_id), None)
    if source is None:
        raise InventoryError("Reference has an unknown source identity")
    if source.page_count is None or reference.page > source.page_count:
        raise InventoryError("Reference page is unavailable or outside the PDF")
    read_source_bytes(root, inventory, reference.source_id)
    return source


def read_source_bytes(root: Path, inventory: Inventory, source_id: str) -> bytes:
    """Read a known source version through the same path and freshness boundary."""
    source = next((s for s in inventory.sources if s.source_id == source_id), None)
    if source is None:
        raise InventoryError("Reference has an unknown source identity")
    data = _snapshot(root.resolve(strict=True), source.path)
    if hashlib.sha256(data).hexdigest() != source.sha256:
        raise InventoryError("Referenced source changed after inventory")
    return data


def publish_inventory(root: Path, inventory: Inventory) -> Path:
    """Atomically publish local metadata only, rechecking every version before writing."""
    root = root.resolve(strict=True)
    payload: dict[str, object] = {
        "schema_version": 1,
        "status": "metadata_only_not_answer_grounding",
        "created_at": inventory.created_at.isoformat(),
        "source_root": _SUPPORT.as_posix(),
        "sources": [asdict(s) for s in inventory.sources],
        "issues": [asdict(i) for i in inventory.issues],
        "selections": [asdict(select_evidence(inventory, family)) for family in _FAMILIES],
    }
    return publish_json_run(root, "inventory", payload, inventory)


def publish_json_run(
    root: Path,
    kind: Literal[
        "inventory",
        "evidence",
        "ocr",
        "review",
        "fact-sheet-check",
        "history-check",
        "foundry-smoke",
        "discovery",
        "visual-map",
        "retrieval",
    ],
    payload: dict[str, object],
    inventory: Inventory,
    *,
    verify_inputs: Callable[[], None] | None = None,
    write_artifacts: Callable[[Path], None] | None = None,
) -> Path:
    """Publish JSON and optional companion artifacts atomically in one local run."""
    if kind not in (
        "inventory",
        "evidence",
        "ocr",
        "review",
        "fact-sheet-check",
        "history-check",
        "foundry-smoke",
        "discovery",
        "visual-map",
        "retrieval",
    ):
        raise InventoryError("Unsupported local output kind")
    root = root.resolve(strict=True)
    output = root / "outputs"
    if output.resolve() != output:
        raise InventoryError("Local output folder must not resolve through a symlink")
    if verify_inputs is not None:
        verify_inputs()
    for source in inventory.sources:
        read_source_bytes(root, inventory, source.source_id)
    output.mkdir(exist_ok=True)
    final = output / f"{kind}-{uuid4().hex}"
    with TemporaryDirectory(prefix=".staging-", dir=output) as temporary:
        staging = Path(temporary)
        (staging / f"{kind}.json").write_text(
            json.dumps(payload, indent=2) + "\n", encoding="utf-8"
        )
        if write_artifacts is not None:
            write_artifacts(staging)
        for source in inventory.sources:
            read_source_bytes(root, inventory, source.source_id)
        if verify_inputs is not None:
            verify_inputs()
        staging.rename(final)
    return final
