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
from io import BytesIO
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Literal
from uuid import uuid4

import pypdfium2 as pdfium
import pypdfium2.raw as pdfium_raw
from PIL import Image, UnidentifiedImageError
from reportlab.lib.utils import ImageReader
from reportlab.pdfgen.canvas import Canvas

from bd_packet_builder.local_inputs import LocalInputError, read_local_input
from bd_packet_builder.sources import (
    Cadence,
    VersionDateBasis,
    filename_period,
    filename_snapshot_date,
    select_document,
)

_SUPPORT = Path("bd_agreements/supporting_data")
_FAMILIES: dict[str, Cadence] = {"Focus_Reports": "monthly", "Audited_Financials": "annual"}
_EXTENSIONS = {".pdf", ".png", ".jpg", ".jpeg", ".doc", ".docx"}
_MAX_BYTES = 64 * 1024 * 1024
IMAGE_FORMATS = frozenset({"png", "jpg", "jpeg"})
_MAX_IMAGE_PIXELS = 40_000_000
# Supplied images are fitted to a US Letter box so appended pages match the packet scale.
_IMAGE_PAGE_BOX = (612.0, 792.0)
_PDF_DATE = re.compile(r"(?:D:)?(\d{8})(\d{6})?(Z|[+-]\d{2}'?\d{2}'?)?")


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
    version_date: str | None = None
    version_timestamp: str | None = None
    version_date_basis: VersionDateBasis | None = None
    filename_date: str | None = None


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


def _pdf_pages(data: bytes) -> tuple[int | None, tuple[str, ...], str | None]:
    try:
        with pdfium.PdfDocument(data) as document:
            if pdfium_raw.FPDF_GetSecurityHandlerRevision(document) >= 0:
                return None, ("encrypted_pdf",), None
            count = len(document)
            if count < 1:
                return None, ("unreadable_pdf",), None
            return count, (), document.get_metadata_value("CreationDate") or None
    except pdfium.PdfiumError:
        return None, ("unreadable_pdf",), None


def _version_time(
    moment: datetime, offset: str | None, invalid_flag: str
) -> tuple[str | None, str | None, tuple[str, ...]]:
    if offset is None:
        return moment.date().isoformat(), None, ("version_timezone_unknown",)
    zone = offset.replace("'", "")
    if zone != "Z" and re.fullmatch(r"[+-](?:[01]\d|2[0-3]):?[0-5]\d", zone) is None:
        return None, None, (invalid_flag,)
    aware = datetime.fromisoformat(moment.isoformat() + zone)
    return moment.date().isoformat(), aware.isoformat(), ()


def _pdf_creation_date(raw: str | None) -> tuple[str | None, str | None, tuple[str, ...]]:
    if raw is None:
        return None, None, ()
    match = _PDF_DATE.fullmatch(raw)
    if match is None:
        return None, None, ("pdf_creation_date_invalid",)
    day, time, zone = match.groups()
    try:
        moment = datetime.strptime(day + (time or ""), "%Y%m%d%H%M%S" if time else "%Y%m%d")
    except ValueError:
        return None, None, ("pdf_creation_date_invalid",)
    if not time:
        if zone:
            return None, None, ("pdf_creation_date_invalid",)
        return moment.date().isoformat(), None, ()
    return _version_time(moment, zone, "pdf_creation_date_invalid")


def _image_capture_date(data: bytes) -> tuple[str | None, str | None, tuple[str, ...]]:
    with Image.open(BytesIO(data)) as image:
        exif = image.getexif()
        nested = exif.get_ifd(34665) if 34665 in exif else {}
        raw = nested.get(36867, exif.get(36867))
        offset = nested.get(36881, exif.get(36881))
    if raw is None:
        return None, None, ()
    if not isinstance(raw, str) or (offset is not None and not isinstance(offset, str)):
        return None, None, ("image_capture_date_invalid",)
    try:
        moment = datetime.strptime(raw.rstrip("\x00"), "%Y:%m:%d %H:%M:%S")
    except ValueError:
        return None, None, ("image_capture_date_invalid",)
    return _version_time(moment, offset, "image_capture_date_invalid")


def _open_image(data: bytes) -> Image.Image:
    with Image.open(BytesIO(data)) as probe:
        width, height = probe.size
        if probe.format not in ("PNG", "JPEG") or not 0 < width * height <= _MAX_IMAGE_PIXELS:
            raise InventoryError("Image source is unreadable or exceeds the pixel limit")
        probe.verify()
    image = Image.open(BytesIO(data))
    image.load()
    return image


def _image_pages(data: bytes) -> tuple[int | None, tuple[str, ...]]:
    try:
        _open_image(data).close()
    except (InventoryError, UnidentifiedImageError, OSError, SyntaxError, ValueError):
        return None, ("unreadable_image",)
    return 1, ("image_presented_as_pdf_page",)


def _image_pdf(data: bytes) -> bytes:
    """Deterministically present a supplied image as one PDF page; no content is altered."""
    try:
        with _open_image(data) as image, image.convert("RGB") as rgb:
            scale = min(_IMAGE_PAGE_BOX[0] / rgb.width, _IMAGE_PAGE_BOX[1] / rgb.height)
            size = (rgb.width * scale, rgb.height * scale)
            output = BytesIO()
            canvas = Canvas(output, pagesize=size, invariant=1, pageCompression=1)
            canvas.drawImage(ImageReader(rgb), 0, 0, width=size[0], height=size[1])
            canvas.showPage()
            canvas.save()
    except (UnidentifiedImageError, OSError, SyntaxError, ValueError):
        raise InventoryError("Image source could not be presented as a page") from None
    return output.getvalue()


def _record(root: Path, relative: str) -> SourceRecord:
    path = Path(relative)
    data = _snapshot(root, relative)
    digest = hashlib.sha256(data).hexdigest()
    identity = hashlib.sha256(relative.encode("utf-8") + b"\0" + digest.encode("ascii")).hexdigest()
    family = path.relative_to(_SUPPORT).parts[0] if path.parent != _SUPPORT else "unassigned"
    cadence = _FAMILIES.get(family)
    period = filename_period(path, cadence=cadence) if cadence else None
    flags = ["content_date_unverified"]
    filename_day, filename_flags = filename_snapshot_date(path)
    filename_date = filename_day.isoformat() if filename_day is not None else None
    flags.extend(filename_flags)
    version_date = None
    version_timestamp = None
    version_basis: VersionDateBasis | None = None
    if cadence is None:
        flags.append("period_not_configured")
    elif period is None:
        flags.append("unparseable_period")
    if path.suffix.lower() == ".pdf":
        pages, pdf_flags, creation = _pdf_pages(data)
        flags.extend(pdf_flags)
        version_date, version_timestamp, date_flags = _pdf_creation_date(creation)
        flags.extend(date_flags)
        if version_date is not None:
            version_basis = "pdf_creation"
            if filename_date is not None and version_date < filename_date:
                flags.append("pdf_creation_precedes_filename_date")
    elif path.suffix.lower()[1:] in IMAGE_FORMATS:
        pages, image_flags = _image_pages(data)
        flags.extend(image_flags)
        if pages is not None:
            version_date, version_timestamp, date_flags = _image_capture_date(data)
            flags.extend(date_flags)
            if version_date is not None:
                version_basis = "image_capture"
                if filename_date is not None and version_date != filename_date:
                    flags.append("capture_filename_date_mismatch")
    else:
        pages = None
        flags.append("page_reference_unavailable")
    if version_date is None and filename_date is not None:
        version_date = filename_date
        version_basis = "filename"
    if version_date is None:
        flags.append("version_date_unavailable")
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
        version_date=version_date,
        version_timestamp=version_timestamp,
        version_date_basis=version_basis,
        filename_date=filename_date,
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
    """Read a known source version through the same path and freshness boundary.

    Verified PNG/JPEG sources are returned as their deterministic one-page PDF presentation,
    so every page reader, OCR check and packet attachment sees the same page.
    """
    source = next((s for s in inventory.sources if s.source_id == source_id), None)
    if source is None:
        raise InventoryError("Reference has an unknown source identity")
    if source.family == "historical_reference":
        try:
            data = read_local_input(
                root.resolve(strict=True),
                Path(source.path),
                Path("bd_agreements/Completed"),
                _MAX_BYTES,
            )
        except LocalInputError as error:
            raise InventoryError(str(error)) from None
    else:
        data = _snapshot(root.resolve(strict=True), source.path)
    if hashlib.sha256(data).hexdigest() != source.sha256:
        raise InventoryError("Referenced source changed after inventory")
    if source.format in IMAGE_FORMATS and source.page_count is not None:
        return _image_pdf(data)
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
        "draft",
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
        "draft",
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
