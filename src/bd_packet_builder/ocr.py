"""Opt-in single-page local OCR experiment; never promotes text to approved evidence."""

import csv
import hashlib
import io
import math
import re
import shutil
import subprocess
from collections.abc import Sequence
from contextlib import closing
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Annotated

import pypdfium2 as pdfium
from pydantic import Field

from bd_packet_builder.contracts import Contract, Nonblank
from bd_packet_builder.inventory import (
    EvidenceReference,
    Inventory,
    InventoryError,
    build_inventory,
    publish_json_run,
    read_source_bytes,
    resolve_reference,
)

_DPI = 300
_PSM = 6
_COLUMNS = (
    "level",
    "page_num",
    "block_num",
    "par_num",
    "line_num",
    "word_num",
    "left",
    "top",
    "width",
    "height",
    "conf",
    "text",
)


class OcrError(ValueError):
    """Safe local OCR failures; never include raw engine output or page content."""


@dataclass(frozen=True)
class OcrLimits:
    timeout_seconds: int = 30
    max_pixels: int = 20_000_000
    max_output_bytes: int = 4_000_000

    def __post_init__(self) -> None:
        for value in (self.timeout_seconds, self.max_pixels, self.max_output_bytes):
            if type(value) is not int or value < 1:
                raise OcrError("Every OCR limit must be a positive integer")


_DEFAULT_LIMITS = OcrLimits()


@dataclass(frozen=True)
class OcrWord:
    text: str
    confidence: float
    left: int
    top: int
    width: int
    height: int
    block: int
    paragraph: int
    line: int


class OcrWordEvidence(Contract):
    text: Nonblank
    confidence: Annotated[float, Field(ge=0, le=100, allow_inf_nan=False)]
    left: Annotated[int, Field(ge=0)]
    top: Annotated[int, Field(ge=0)]
    width: Annotated[int, Field(ge=1)]
    height: Annotated[int, Field(ge=1)]
    block: Annotated[int, Field(ge=1)]
    paragraph: Annotated[int, Field(ge=1)]
    line: Annotated[int, Field(ge=1)]


def _execute(command: list[str], temporary: Path, limits: OcrLimits) -> str:
    with (temporary / "engine-output").open("w+b") as output:
        try:
            result = subprocess.run(
                command,
                stdin=subprocess.DEVNULL,
                stdout=output,
                stderr=subprocess.DEVNULL,
                timeout=limits.timeout_seconds,
                check=False,
            )
        except subprocess.TimeoutExpired:
            raise OcrError("Tesseract exceeded its timeout; no OCR result was published") from None
        except OSError:
            raise OcrError(
                "Cannot execute local Tesseract; check installation and permissions"
            ) from None
        if result.returncode != 0:
            raise OcrError(
                "Tesseract failed; check the local engine and English language data installation"
            )
        if output.tell() > limits.max_output_bytes:
            raise OcrError("Tesseract output exceeds its byte limit")
        output.seek(0)
        data = output.read(limits.max_output_bytes + 1)
    try:
        return data.decode("utf-8", errors="strict")
    except UnicodeError:
        raise OcrError("Tesseract returned invalid UTF-8 output") from None


def _words(tsv: str, width: int, height: int) -> tuple[OcrWord, ...]:
    reader = csv.DictReader(io.StringIO(tsv), delimiter="\t", quoting=csv.QUOTE_NONE)
    if tuple(reader.fieldnames or ()) != _COLUMNS:
        raise OcrError("Tesseract returned an invalid TSV header")
    words: list[OcrWord] = []
    try:
        for row in reader:
            if None in row or any(value is None for value in row.values()):
                raise OcrError("Tesseract returned an invalid TSV row")
            level = int(row["level"])
            if not 1 <= level <= 5 or int(row["page_num"]) != 1:
                raise OcrError("Tesseract returned an invalid page hierarchy")
            if level != 5:
                continue
            left, top, w, h = (int(row[key]) for key in ("left", "top", "width", "height"))
            confidence = float(row["conf"])
            block, paragraph, line, word = (
                int(row[key]) for key in ("block_num", "par_num", "line_num", "word_num")
            )
            if (
                not math.isfinite(confidence)
                or not 0 <= confidence <= 100
                or min(left, top) < 0
                or min(w, h, block, paragraph, line, word) < 1
                or left + w > width
                or top + h > height
                or not row["text"].strip()
            ):
                raise OcrError("Tesseract returned invalid word geometry or confidence")
            words.append(OcrWord(row["text"], confidence, left, top, w, h, block, paragraph, line))
    except (ValueError, csv.Error) as error:
        if isinstance(error, OcrError):
            raise
        raise OcrError("Tesseract returned malformed word data") from None
    return tuple(words)


def ocr_text(words: Sequence[OcrWord | OcrWordEvidence]) -> str:
    lines: list[list[str]] = []
    previous: tuple[int, int, int] | None = None
    for word in words:
        key = (word.block, word.paragraph, word.line)
        if key != previous:
            lines.append([])
        lines[-1].append(word.text)
        previous = key
    return "\n".join(" ".join(line) for line in lines)


def run_ocr(
    root: Path,
    source: Path,
    page: int,
    *,
    limits: OcrLimits = _DEFAULT_LIMITS,
    inventory: Inventory | None = None,
) -> Path:
    """Rasterize one explicitly selected supporting PDF page and publish unverified OCR."""
    root = root.resolve(strict=True)
    if source.is_absolute() or ".." in source.parts:
        raise OcrError("Choose a relative PDF path from the supporting-document inventory")
    inventory = inventory if inventory is not None else build_inventory(root)
    record = next((s for s in inventory.sources if s.path == source.as_posix()), None)
    if record is None:
        raise OcrError("Choose a PDF from the supporting-document inventory; no symlinks")
    reference = EvidenceReference(record.source_id, page)
    resolve_reference(root, inventory, reference)
    executable = shutil.which("tesseract")
    if executable is None:
        raise OcrError("Tesseract is not installed; install local Tesseract with English data")
    output = root / "outputs"
    if output.resolve() != output:
        raise InventoryError("Local output folder must not resolve through a symlink")
    data = read_source_bytes(root, inventory, record.source_id)
    output.mkdir(exist_ok=True)
    with TemporaryDirectory(prefix=".ocr-working-", dir=output) as directory:
        temporary = Path(directory)
        version_output = _execute([executable, "--version"], temporary, limits)
        match = re.match(r"tesseract (5\.\d+\.\d+)\b", version_output)
        if match is None:
            raise OcrError("Local OCR feasibility requires Tesseract 5.x")
        try:
            with pdfium.PdfDocument(data) as document, closing(document[page - 1]) as pdf_page:
                scale = _DPI / 72
                w, h = pdf_page.get_size()
                if (
                    not math.isfinite(w)
                    or not math.isfinite(h)
                    or min(w, h) <= 0
                    or math.ceil(w * scale) * math.ceil(h * scale) > limits.max_pixels
                ):
                    raise OcrError("Rendered page exceeds the OCR pixel limit or has invalid size")
                # PDFium documents float scale; its untyped integer default misleads Pylance.
                bitmap = pdf_page.render(scale=scale)  # pyright: ignore[reportArgumentType]
                with closing(bitmap), closing(bitmap.to_pil()) as image:
                    width, height = image.size
                    image.save(temporary / "page.png")
        except pdfium.PdfiumError:
            raise OcrError("Cannot render the selected PDF page for OCR") from None
        tsv = _execute(
            [
                executable,
                str(temporary / "page.png"),
                "stdout",
                "-l",
                "eng",
                "--dpi",
                str(_DPI),
                "--psm",
                str(_PSM),
                "tsv",
            ],
            temporary,
            limits,
        )
        words = _words(tsv, width, height)
        payload: dict[str, object] = {
            "schema_version": 1,
            "status": "ocr_feasibility_unverified_not_answers",
            "created_at": datetime.now(UTC).isoformat(),
            "source": asdict(record),
            "page": page,
            "engine": "tesseract",
            "engine_version": match[1],
            "language": "eng",
            "dpi": _DPI,
            "page_segmentation_mode": _PSM,
            "image_width": width,
            "image_height": height,
            "coordinate_system": "rendered_pixels_top_left_not_pdf_points",
            "render_sha256": hashlib.sha256((temporary / "page.png").read_bytes()).hexdigest(),
            "limits": asdict(limits),
            "words": [asdict(word) for word in words],
            "text": ocr_text(words),
            "flags": ["ocr_unverified", "not_semantic_grounding"]
            + ([] if words else ["no_ocr_text"]),
        }
        return publish_json_run(root, "ocr", payload, inventory)
