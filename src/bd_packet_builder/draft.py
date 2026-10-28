"""Reviewed, version-bound local drafts; not automatic answer approval or submission."""

import hashlib
import json
import math
import re
from contextlib import closing
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from io import BytesIO
from pathlib import Path
from typing import Annotated, Literal, Self

import pypdfium2 as pdfium
from PIL import Image, ImageChops, ImageDraw
from pydantic import Field, ValidationError, model_validator
from pypdf import PdfReader, PdfWriter
from pypdf.generic import RectangleObject
from reportlab.pdfbase.pdfmetrics import stringWidth
from reportlab.pdfgen.canvas import Canvas

from bd_packet_builder.contracts import (
    AnswerProposal,
    ApplicationRequirements,
    Contract,
    Identifier,
    IdentifierValue,
    MultiSelectValue,
    NarrativeValue,
    Nonblank,
    OcrCitation,
    Sha256,
    SingleSelectValue,
    TextValue,
    check_proposal,
)
from bd_packet_builder.inventory import (
    Inventory,
    SourceRecord,
    build_inventory,
    publish_json_run,
    read_source_bytes,
)
from bd_packet_builder.layout import MappedResponse, PageBox, ResponseLayout, validate_layout
from bd_packet_builder.local_inputs import LocalInputError, read_local_input
from bd_packet_builder.responses import (
    NarrativeRegion,
    PacketPagination,
    PacketReference,
    PacketSection,
    wrap_text,
)
from bd_packet_builder.retrieval import default_catalog
from bd_packet_builder.review import AnswerProposals

MAX_PACKET_PAGES = 100
BANNER_HEIGHT = 24
RENDER_SCALE = 2
MAX_RENDER_PIXELS = 12_000_000
SUPPLEMENT_LINES = 42


class DraftError(ValueError):
    """Safe failures of draft input, placement, rendering or publication."""


class DraftSource(Contract):
    path: Nonblank
    sha256: Sha256


class DraftFormField(Contract):
    requirement_id: Identifier
    region: NarrativeRegion


class DraftAdditionalForm(Contract):
    source: DraftSource
    fields: Annotated[tuple[DraftFormField, ...], Field(max_length=20)]
    protected_regions: Annotated[tuple[PageBox, ...], Field(max_length=20)] = ()

    @model_validator(mode="after")
    def unique_placements(self) -> Self:
        placements = {
            (
                field.region.page,
                field.region.left,
                field.region.bottom,
                field.region.right,
                field.region.top,
            )
            for field in self.fields
        }
        if len(placements) != len(self.fields):
            raise ValueError("Additional form placements must be unique")
        return self


class DraftRequest(Contract):
    schema_version: Literal[1] = 1
    mode: Literal["fictional", "reviewed_evidence"]
    source: Nonblank
    requirements: ApplicationRequirements
    layout: ResponseLayout
    proposals: AnswerProposals
    sources: Annotated[tuple[DraftSource, ...], Field(max_length=10)]
    attachments: Annotated[tuple[Sha256, ...], Field(max_length=10)]
    protected_regions: Annotated[tuple[PageBox, ...], Field(max_length=100)]
    additional_forms: Annotated[tuple[DraftAdditionalForm, ...], Field(max_length=10)] = ()

    @model_validator(mode="after")
    def identities(self) -> Self:
        requirements = {r.requirement_id: r for r in self.requirements.requirements}
        if len(requirements) > 100:
            raise ValueError("Draft trial supports at most 100 requirements")
        if {p.requirement_id for p in self.proposals.proposals} != requirements.keys():
            raise ValueError("Draft proposals must cover exactly the declared requirements")
        if any(
            requirements.get(m.requirement.requirement_id) != m.requirement
            for m in self.layout.responses
        ):
            raise ValueError("Mapped requirements must match the declared requirement contracts")
        if any(
            r.application_sha256 != self.layout.application_sha256
            for r in self.requirements.requirements
        ):
            raise ValueError("All draft inputs must refer to one blank application version")
        if len({s.path for s in self.sources}) != len(self.sources):
            raise ValueError("Draft source paths must be unique")
        if len(set(self.attachments)) != len(self.attachments):
            raise ValueError("Draft attachment identities must be unique")
        blank_sources = [form.source.path for form in self.additional_forms]
        if (
            len(set(blank_sources)) != len(blank_sources)
            or self.source in blank_sources
            or any(
                field.requirement_id not in requirements
                for additional_form in self.additional_forms
                for field in additional_form.fields
            )
        ):
            raise ValueError("Additional forms must be distinct and reference known requirements")
        if (
            any(r.kind in ("signature", "signature_date") for r in requirements.values())
            and not self.protected_regions
        ):
            raise ValueError("Signing requirements require explicit protected regions")
        return self


class DraftDecision(Contract):
    requirement_id: Identifier
    decision: Literal["draft_verified", "withhold"]
    evidence_support_confirmed: bool
    source_approved: bool
    placement_confirmed: bool
    source_subject_confirmed: bool = False
    ocr_visual_confirmed: bool = False
    confirmed_source_subject: Nonblank | None = None
    reason: Nonblank

    @model_validator(mode="after")
    def confirmations(self) -> Self:
        if self.decision == "draft_verified" and not (
            self.evidence_support_confirmed and self.source_approved and self.placement_confirmed
        ):
            raise ValueError("Draft writing requires source, support and placement confirmation")
        return self


class DraftReview(Contract):
    request_sha256: Sha256
    reviewer: Nonblank
    decisions: Annotated[tuple[DraftDecision, ...], Field(max_length=100)]
    attachment_source_ids: Annotated[tuple[Sha256, ...], Field(max_length=10)] = ()
    reviewer_notes: Annotated[tuple[Nonblank, ...], Field(max_length=20)] = ()

    @model_validator(mode="after")
    def unique(self) -> Self:
        if len({d.requirement_id for d in self.decisions}) != len(self.decisions):
            raise ValueError("Draft review decisions cannot repeat a requirement")
        if len(set(self.attachment_source_ids)) != len(self.attachment_source_ids):
            raise ValueError("Attachment reviews cannot repeat a source")
        return self


@dataclass(frozen=True)
class TextPlacement:
    region: NarrativeRegion
    lines: tuple[str, ...]


@dataclass(frozen=True)
class MarkPlacement:
    box: PageBox
    control: Literal["radio", "checkbox"]


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


def _measure(text: str, size: float) -> float:
    return float(stringWidth(text, "Helvetica", size))


def _lines(text: str, region: NarrativeRegion) -> tuple[str, ...]:
    if any(not (32 <= ord(c) <= 126 or c == "\n") for c in text):
        raise DraftError("Unsupported font characters; answer needs a reviewed font/layout")
    lines = wrap_text(text, region.right - region.left, region.font_size, _measure)
    if lines is None or len(lines) > math.floor((region.top - region.bottom) / region.leading):
        raise DraftError("Answer cannot fit at the configured readable font size")
    return lines


def _overlap(a: PageBox | NarrativeRegion, b: PageBox | NarrativeRegion) -> bool:
    return (
        a.page == b.page
        and min(a.right, b.right) > max(a.left, b.left)
        and (min(a.top, b.top) > max(a.bottom, b.bottom))
    )


def _ocr_text(words: list[OcrWordEvidence]) -> str:
    lines: list[list[str]] = []
    previous: tuple[int, int, int] | None = None
    for word in words:
        key = (word.block, word.paragraph, word.line)
        if key != previous:
            lines.append([])
        lines[-1].append(word.text)
        previous = key
    return "\n".join(" ".join(line) for line in lines)


def _verify_ocr_citation(
    root: Path,
    inventory: Inventory,
    citation: OcrCitation,
    render_hashes: dict[tuple[str, int], str],
) -> tuple[str | None, bytes | None, dict[str, object] | None]:
    try:
        artifact_path = Path(citation.artifact_path)
        artifact = read_local_input(root, artifact_path, Path("outputs"), 2 * 1024 * 1024)
    except (LocalInputError, FileNotFoundError, IsADirectoryError):
        return "ocr_artifact_unavailable", None, None
    if hashlib.sha256(artifact).hexdigest() != citation.artifact_sha256:
        return "ocr_artifact_hash_mismatch", None, None
    try:
        data: object = json.loads(artifact)
    except (json.JSONDecodeError, UnicodeDecodeError):
        return "ocr_artifact_malformed", None, None
    if not isinstance(data, dict) or data.get("status") != "ocr_feasibility_unverified_not_answers":
        return "ocr_artifact_status_invalid", None, None
    source = next((s for s in inventory.sources if s.source_id == citation.source_id), None)
    artifact_source = data.get("source")
    if (
        source is None
        or not isinstance(artifact_source, dict)
        or source.sha256 != citation.source_sha256
        or artifact_source.get("source_id") != citation.source_id
        or artifact_source.get("sha256") != citation.source_sha256
        or artifact_source.get("path") != source.path
        or data.get("page") != citation.page
        or source.page_count is None
        or citation.page > source.page_count
    ):
        return "ocr_source_version_mismatch", None, None
    if (
        type(data.get("dpi")) is not int
        or data["dpi"] != 300
        or data.get("engine") != "tesseract"
        or not isinstance(data.get("engine_version"), str)
        or re.fullmatch(r"5\.\d+\.\d+", data["engine_version"]) is None
        or data.get("language") != "eng"
        or type(data.get("page_segmentation_mode")) is not int
        or data["page_segmentation_mode"] != 6
        or data.get("coordinate_system") != "rendered_pixels_top_left_not_pdf_points"
        or type(data.get("image_width")) is not int
        or type(data.get("image_height")) is not int
        or min(data["image_width"], data["image_height"]) < 1
        or data["image_width"] * data["image_height"] > 20_000_000
    ):
        return "ocr_render_or_configuration_mismatch", None, None
    if data.get("render_sha256") != citation.render_sha256:
        return "ocr_render_mismatch", None, None
    flags = data.get("flags")
    if (
        not isinstance(flags, list)
        or not all(isinstance(flag, str) for flag in flags)
        or not {"ocr_unverified", "not_semantic_grounding"} <= set(flags)
    ):
        return "ocr_artifact_status_invalid", None, None
    raw_words = data.get("words")
    if not isinstance(raw_words, list) or not 1 <= len(raw_words) <= 50_000:
        return "ocr_words_invalid", None, None
    try:
        words = [OcrWordEvidence.model_validate(word) for word in raw_words]
    except ValidationError:
        return "ocr_words_invalid", None, None
    if any(
        word.left + word.width > data["image_width"]
        or word.top + word.height > data["image_height"]
        for word in words
    ):
        return "ocr_words_invalid", None, None
    if data.get("text") != _ocr_text(words):
        return "ocr_text_mismatch", None, None
    selected = words[citation.word_start : citation.word_end]
    if citation.word_end > len(words) or not selected or _ocr_text(selected) != citation.quote:
        return "ocr_quote_mismatch", None, None
    key = citation.source_id, citation.page
    rendered = render_hashes.get(key)
    if rendered is None:
        try:
            source_data = read_source_bytes(root, inventory, citation.source_id)
            with (
                pdfium.PdfDocument(source_data) as document,
                closing(document[citation.page - 1]) as page,
            ):
                bitmap = page.render(scale=300 / 72)  # pyright: ignore[reportArgumentType]
                with closing(bitmap), closing(bitmap.to_pil()) as image:
                    if image.size != (data["image_width"], data["image_height"]):
                        return "ocr_render_mismatch", None, None
                    stream = BytesIO()
                    image.save(stream, format="PNG")
                    rendered = hashlib.sha256(stream.getvalue()).hexdigest()
        except pdfium.PdfiumError:
            return "ocr_render_unavailable", None, None
        render_hashes[key] = rendered
    if rendered != citation.render_sha256:
        return "ocr_render_mismatch", None, None
    selected_words = words[citation.word_start : citation.word_end]
    left = min(word.left for word in selected_words)
    top = min(word.top for word in selected_words)
    right = max(word.left + word.width for word in selected_words)
    bottom = max(word.top + word.height for word in selected_words)
    return (
        None,
        artifact,
        {
            "artifact_path": citation.artifact_path,
            "artifact_sha256": citation.artifact_sha256,
            "render_sha256": citation.render_sha256,
            "word_start": citation.word_start,
            "word_end": citation.word_end,
            "quote": citation.quote,
            "pixel_bounds_top_left": [left, top, right, bottom],
            "engine": data.get("engine"),
            "engine_version": data.get("engine_version"),
            "dpi": data["dpi"],
        },
    )


def _writable(mapped: MappedResponse) -> list[PageBox | NarrativeRegion]:
    regions: list[PageBox | NarrativeRegion] = [o.box for o in mapped.options]
    regions.extend(o.write_in_region for o in mapped.options if o.write_in_region is not None)
    if mapped.narrative_region is not None:
        regions.append(mapped.narrative_region)
    if mapped.text_region is not None:
        regions.append(mapped.text_region)
    return regions


def _validate_pdf(data: bytes, *, blank: bool) -> PdfReader:
    reader = PdfReader(BytesIO(data))
    if reader.is_encrypted or not reader.pages or len(reader.pages) > MAX_PACKET_PAGES:
        raise DraftError("Draft input is encrypted, empty or exceeds the page limit")
    if blank and any(
        field.get("/V") not in (None, "", "/Off") for field in (reader.get_fields() or {}).values()
    ):
        raise DraftError("Draft input must not contain prefilled or signed fields")
    for page in reader.pages:
        if blank and (
            page.rotation != 0
            or float(page.mediabox.left) != 0
            or float(page.mediabox.bottom) != 0
            or list(page.cropbox) != list(page.mediabox)
            or page.get("/UserUnit", 1) != 1
        ):
            raise DraftError(
                "This draft writer requires unrotated, uncropped standard-point blanks"
            )
        width, height = float(page.mediabox.width), float(page.mediabox.height)
        if (
            width <= 0
            or height <= 0
            or width * (height + BANNER_HEIGHT) * RENDER_SCALE**2 > MAX_RENDER_PIXELS
        ):
            raise DraftError("Draft page exceeds the render size limit")
    return reader


def _inventory(root: Path, request: DraftRequest) -> Inventory:
    allowed = {f.folder for f in default_catalog().families}
    families = set()
    for selection in request.sources:
        path = Path(selection.path)
        base = Path("bd_agreements/supporting_data")
        if path.is_absolute() or ".." in path.parts or not path.is_relative_to(base):
            raise DraftError("Draft sources must be within designated supporting folders")
        parts = path.relative_to(base).parts
        if len(parts) < 2 or parts[0] not in allowed:
            raise DraftError("Draft source family is outside the designated catalog")
        families.add(parts[0])
    inventory = (
        build_inventory(root, families=tuple(sorted(families)), max_sources=30)
        if families
        else Inventory(datetime.now(UTC), (), ())
    )
    selected: list[SourceRecord] = []
    for expected in request.sources:
        source = next((s for s in inventory.sources if s.path == expected.path), None)
        if source is None or source.sha256 != expected.sha256 or source.format != "pdf":
            raise DraftError("Draft supporting source is missing, changed or not a PDF")
        selected.append(source)
    return Inventory(inventory.created_at, tuple(selected), ())


def _draw_text(canvas: Canvas, placement: TextPlacement) -> None:
    region = placement.region
    canvas.setFont("Helvetica", region.font_size)
    for index, line in enumerate(placement.lines):
        canvas.drawString(region.left, region.top - region.font_size - index * region.leading, line)


def _form_pdf(
    original: bytes, texts: list[TextPlacement], marks: list[MarkPlacement], fictional: bool
) -> bytes:
    reader = _validate_pdf(original, blank=True)
    with closing(PdfWriter(clone_from=reader)) as writer:
        for number, page in enumerate(writer.pages, start=1):
            width, height = float(page.mediabox.width), float(page.mediabox.height)
            overlay = BytesIO()
            canvas = Canvas(overlay, pagesize=(width, height + BANNER_HEIGHT), invariant=True)
            canvas.setFont("Helvetica-Bold", 9)
            label = "FICTIONAL DATA - " if fictional else ""
            canvas.drawString(12, height + 8, label + "INCOMPLETE DRAFT - NOT FOR SUBMISSION")
            for text in texts:
                if text.region.page == number:
                    _draw_text(canvas, text)
            canvas.setLineWidth(1)
            for mark in marks:
                b = mark.box
                if b.page != number:
                    continue
                if mark.control == "radio":
                    canvas.circle(
                        (b.left + b.right) / 2,
                        (b.bottom + b.top) / 2,
                        min(b.right - b.left, b.top - b.bottom) / 3,
                        stroke=0,
                        fill=1,
                    )
                else:
                    inset = min(b.right - b.left, b.top - b.bottom) / 5
                    canvas.line(b.left + inset, b.bottom + inset, b.right - inset, b.top - inset)
                    canvas.line(b.left + inset, b.top - inset, b.right - inset, b.bottom + inset)
            canvas.save()
            page.mediabox = RectangleObject((0, 0, width, height + BANNER_HEIGHT))
            page.cropbox = page.mediabox
            page.merge_page(PdfReader(overlay).pages[0])
        output = BytesIO()
        writer.write(output)
    return output.getvalue()


def _render_image(data: bytes, index: int) -> Image.Image:
    with pdfium.PdfDocument(data) as document:
        document.init_forms()
        with closing(document[index]) as page, closing(page.render(scale=RENDER_SCALE)) as bitmap:
            image: Image.Image = bitmap.to_pil()
            try:
                return image.convert("RGB")
            finally:
                image.close()


def _render_checks(
    original: bytes,
    packet: bytes,
    output: Path,
    allowed: list[PageBox | NarrativeRegion],
    marks: list[MarkPlacement],
    texts: list[TextPlacement],
    packet_page_offset: int = 0,
    filename_prefix: str = "",
) -> dict[str, object]:
    total_outside = 0
    with pdfium.PdfDocument(packet) as document:
        for placement in texts:
            b = placement.region
            with (
                closing(document[packet_page_offset + b.page - 1]) as page,
                closing(page.get_textpage()) as text,
            ):
                actual = " ".join(
                    text.get_text_bounded(
                        left=b.left, bottom=b.bottom, right=b.right, top=b.top, errors="strict"
                    ).split()
                )
                if any(" ".join(line.split()) not in actual for line in placement.lines):
                    raise DraftError("Written text is missing or clipped in its reviewed region")
    for number in range(1, len(PdfReader(BytesIO(original)).pages) + 1):
        with (
            _render_image(original, number - 1) as before,
            _render_image(packet, packet_page_offset + number - 1) as after,
        ):
            before.save(output / f"{filename_prefix}page-{number}-before.png")
            after.save(output / f"{filename_prefix}page-{number}-after.png")
            with after.crop((0, BANNER_HEIGHT * RENDER_SCALE, before.width, after.height)) as body:
                with ImageChops.difference(before, body) as diff, diff.convert("L") as gray:
                    changed = gray.point([255 if value > 16 else 0 for value in range(256)])
                try:
                    mask = Image.new("L", before.size, 255)
                    with mask:
                        draw = ImageDraw.Draw(mask)
                        for box in allowed:
                            if box.page == number:
                                draw.rectangle(
                                    (
                                        box.left * RENDER_SCALE - 2,
                                        before.height - box.top * RENDER_SCALE - 2,
                                        box.right * RENDER_SCALE + 2,
                                        before.height - box.bottom * RENDER_SCALE + 2,
                                    ),
                                    fill=0,
                                )
                        with ImageChops.multiply(changed, mask) as outside:
                            total_outside += outside.histogram()[255]
                    for mark in marks:
                        control_box = mark.box
                        if control_box.page == number:
                            with changed.crop(
                                (
                                    int(control_box.left * RENDER_SCALE),
                                    int(before.height - control_box.top * RENDER_SCALE),
                                    int(control_box.right * RENDER_SCALE),
                                    int(before.height - control_box.bottom * RENDER_SCALE),
                                )
                            ) as region:
                                if region.histogram()[255] < 4:
                                    raise DraftError(
                                        "Rendered selected control is not visibly marked"
                                    )
                finally:
                    changed.close()
    if total_outside:
        raise DraftError("Rendered draft changed content outside reviewed writable regions")
    return {
        "scale": RENDER_SCALE,
        "luminance_difference_threshold": 16,
        "region_padding_pixels": 2,
        "outside_allowed_regions_changed_pixels": total_outside,
        "scope": "form_pages_only_not_semantic_or_human_visual_approval",
    }


def run_draft(root: Path, request_path: Path, review_path: Path) -> Path:
    """Publish one incomplete draft from an explicitly reviewed local snapshot.

    Review JSON is a trusted local development input, not an authentication mechanism.
    No model calls, signing, external actions or automatic source approval occur.
    """
    root = root.resolve(strict=True)
    raw = read_local_input(root, request_path, Path("outputs"), 2 * 1024 * 1024)
    reviewed = read_local_input(root, review_path, Path("outputs"), 2 * 1024 * 1024)
    request = DraftRequest.model_validate_json(raw)
    review = DraftReview.model_validate_json(reviewed)
    request_hash = hashlib.sha256(raw).hexdigest()
    if review.request_sha256 != request_hash:
        raise DraftError("Draft review does not match this exact request snapshot")
    requirements = {r.requirement_id: r for r in request.requirements.requirements}
    if any(d.requirement_id not in requirements for d in review.decisions):
        raise DraftError("Draft review contains an unknown requirement")
    if not set(review.attachment_source_ids) <= set(request.attachments):
        raise DraftError("Attachment review contains an unknown attachment")
    if any(
        requirements[d.requirement_id].kind in ("signature", "signature_date")
        and d.decision == "draft_verified"
        for d in review.decisions
    ):
        raise DraftError("Signatures and signature dates cannot be approved for draft writing")
    original = read_local_input(
        root, Path(request.source), Path("bd_agreements/Blank"), 64 * 1024 * 1024
    )
    validate_layout(root, Path(request.source), request.layout)
    reader = _validate_pdf(original, blank=True)
    additional_forms_data: list[tuple[DraftAdditionalForm, bytes, PdfReader]] = []
    additional_form_snapshots: dict[Path, bytes] = {}
    for form in request.additional_forms:
        form_path = Path(form.source.path)
        form_bytes = read_local_input(
            root, form_path, Path("bd_agreements/Blank"), 64 * 1024 * 1024
        )
        if hashlib.sha256(form_bytes).hexdigest() != form.source.sha256:
            raise DraftError("Additional issuer form changed after request preparation")
        form_reader = _validate_pdf(form_bytes, blank=True)
        field_regions: list[PageBox | NarrativeRegion] = []
        with pdfium.PdfDocument(form_bytes) as document:
            for field in form.fields:
                region = field.region
                if region.page > len(form_reader.pages):
                    raise DraftError("Additional-form field is outside the form")
                page_width = float(form_reader.pages[region.page - 1].mediabox.width)
                page_height = float(form_reader.pages[region.page - 1].mediabox.height)
                if region.right > page_width or region.top > page_height:
                    raise DraftError("Additional-form field is outside the form")
                with (
                    closing(document[region.page - 1]) as page,
                    closing(page.get_textpage()) as text,
                ):
                    native = text.get_text_bounded(
                        left=region.left,
                        bottom=region.bottom,
                        right=region.right,
                        top=region.top,
                        errors="strict",
                    )
                    if native.replace("_", "").strip():
                        raise DraftError("Additional-form field overlaps existing issuer text")
                field_regions.append(region)
            for protected in form.protected_regions:
                if (
                    protected.page > len(form_reader.pages)
                    or protected.right > float(form_reader.pages[protected.page - 1].mediabox.width)
                    or protected.top > float(form_reader.pages[protected.page - 1].mediabox.height)
                ):
                    raise DraftError("Additional-form protected region is outside the form")
        if any(
            _overlap(region, protected)
            for region in field_regions
            for protected in form.protected_regions
        ):
            raise DraftError("Additional-form field overlaps protected content")
        if any(
            _overlap(first, second)
            for index, first in enumerate(field_regions)
            for second in field_regions[index + 1 :]
        ):
            raise DraftError("Additional-form fields overlap")
        additional_forms_data.append((form, form_bytes, form_reader))
        additional_form_snapshots[form_path] = form_bytes
    all_regions = [b for m in request.layout.responses for b in _writable(m)]
    with pdfium.PdfDocument(original) as document:
        for response in request.layout.responses:
            for writable_region in _writable(response):
                if not isinstance(writable_region, NarrativeRegion):
                    continue
                with (
                    closing(document[writable_region.page - 1]) as page,
                    closing(page.get_textpage()) as text,
                ):
                    native = text.get_text_bounded(
                        left=writable_region.left,
                        bottom=writable_region.bottom,
                        right=writable_region.right,
                        top=writable_region.top,
                        errors="strict",
                    )
                    if native.replace("_", "").strip():
                        raise DraftError("Writable text region overlaps existing issuer text")
    for protected in request.protected_regions:
        if (
            protected.page > len(reader.pages)
            or protected.right > float(reader.pages[protected.page - 1].mediabox.width)
            or protected.top > float(reader.pages[protected.page - 1].mediabox.height)
        ):
            raise DraftError("Protected region is outside the form")
    if any(_overlap(a, b) for i, a in enumerate(all_regions) for b in all_regions[i + 1 :]):
        raise DraftError("Writable regions overlap; placement needs review")
    if any(_overlap(a, b) for a in all_regions for b in request.protected_regions):
        raise DraftError("Writable region overlaps protected signing or other content")
    inventory = _inventory(root, request)
    sources = {s.source_id: s for s in inventory.sources}
    if not set(request.attachments) <= sources.keys():
        raise DraftError("Attachment is not a version-bound selected source")
    attachment_ids = [
        identity for identity in request.attachments if identity in review.attachment_source_ids
    ]
    attachments = [
        (sources[identity], read_source_bytes(root, inventory, identity))
        for identity in attachment_ids
    ]
    attachment_readers = [
        (source, _validate_pdf(data, blank=False)) for source, data in attachments
    ]
    form_count = len(reader.pages) + sum(len(form.pages) for _, _, form in additional_forms_data)
    if form_count + sum(len(r.pages) for _, r in attachment_readers) > MAX_PACKET_PAGES:
        raise DraftError("Draft packet exceeds its total page budget")
    decisions = {d.requirement_id: d for d in review.decisions}
    mappings = {m.requirement.requirement_id: m for m in request.layout.responses}
    texts: list[TextPlacement] = []
    marks: list[MarkPlacement] = []
    results: list[dict[str, object]] = []
    placements: dict[str, dict[str, object]] = {}
    accepted: list[AnswerProposal] = []
    supplements: list[tuple[str, tuple[str, ...]]] = []
    supplement_starts: dict[str, int] = {}
    supplement_page_count = 0
    ocr_render_hashes: dict[tuple[str, int], str] = {}
    ocr_artifact_snapshots: dict[Path, bytes] = {}
    for proposal in request.proposals.proposals:
        identity = proposal.requirement_id
        req = requirements[identity]
        decision = decisions.get(identity)
        mapped = mappings.get(identity)
        check = check_proposal(root, inventory, req, proposal)
        issues: list[str] = []
        result: dict[str, object] = {
            "requirement_id": identity,
            "status": "blank",
            "issues": issues,
            "proposal": proposal.model_dump(mode="json"),
            "citation_check": asdict(check),
            "review_reason": decision.reason if decision else None,
        }
        ocr_citations = tuple(c for c in proposal.citations if isinstance(c, OcrCitation))
        ocr_evidence: list[dict[str, object]] = []
        ocr_valid = True
        for citation in ocr_citations:
            ocr_issue, snapshot, details = _verify_ocr_citation(
                root, inventory, citation, ocr_render_hashes
            )
            if ocr_issue:
                issues.append(ocr_issue)
                ocr_valid = False
            if snapshot is not None:
                ocr_artifact_snapshots[Path(citation.artifact_path)] = snapshot
            if details is not None:
                ocr_evidence.append(details)
        if ocr_citations:
            result["ocr_evidence"] = ocr_evidence
        results.append(result)
        if req.kind in ("signature", "signature_date"):
            issues.append("human_signing_required")
            continue
        if proposal.outcome != "proposed":
            issues.append(proposal.outcome)
            continue
        if decision is None or decision.decision != "draft_verified":
            issues.append("withheld" if decision else "not_reviewed")
            continue
        if ocr_citations:
            if not decision.source_subject_confirmed or not decision.confirmed_source_subject:
                issues.append("ocr_source_subject_not_confirmed")
            if not decision.ocr_visual_confirmed:
                issues.append("ocr_visual_review_not_confirmed")
            if not ocr_valid:
                issues.append("ocr_evidence_not_verified")
            if any(
                issue in issues
                for issue in (
                    "ocr_source_subject_not_confirmed",
                    "ocr_visual_review_not_confirmed",
                    "ocr_evidence_not_verified",
                )
            ):
                continue
        if mapped is None:
            issues.append("placement_not_available")
            continue
        if check.status == "rejected":
            issues.extend(check.issues)
            continue
        if req.requested_period is not None and proposal.claimed_period != req.requested_period:
            issues.append("requested_period_not_confirmed")
            continue
        if any(c.source_id not in attachment_ids for c in proposal.citations):
            issues.append("supporting_evidence_not_attached")
            continue
        candidate_texts: list[TextPlacement] = []
        candidate_marks: list[MarkPlacement] = []
        try:
            value = proposal.value
            if isinstance(value, (IdentifierValue, TextValue)):
                if mapped.text_region is None:
                    raise DraftError("Scalar answer has no reviewed writable region")
                if isinstance(value, IdentifierValue) and not any(
                    re.search(r"(?<!\w)" + re.escape(value.value) + r"(?!\w)", c.quote)
                    for c in proposal.citations
                ):
                    raise DraftError("Exact identifier is not present in the cited evidence")
                candidate_texts.append(
                    TextPlacement(mapped.text_region, _lines(value.value, mapped.text_region))
                )
                placements[identity] = {"mode": "inline"}
            elif isinstance(value, (SingleSelectValue, MultiSelectValue)):
                for option in mapped.options:
                    if option.option_id in value.selected:
                        candidate_marks.append(MarkPlacement(option.box, option.control))
                for write_in in value.write_ins:
                    option = next(o for o in mapped.options if o.option_id == write_in.option_id)
                    if option.write_in_region is None:
                        raise DraftError("Selected write-in lacks a reviewed writable region")
                    candidate_texts.append(
                        TextPlacement(
                            option.write_in_region, _lines(write_in.text, option.write_in_region)
                        )
                    )
                placements[identity] = {"mode": "choice", "selected": list(value.selected)}
            elif isinstance(value, NarrativeValue):
                if mapped.narrative_region is None:
                    raise DraftError("Narrative answer has no reviewed writable region")
                # Use the largest allowed page number during allocation to avoid under-reserving.
                provisional_refs = "; ".join(
                    f"packet page {MAX_PACKET_PAGES}"
                    for _ in {(c.source_id, c.page) for c in proposal.citations}
                )
                complete = value.value + "\nSupporting evidence: " + provisional_refs + "."
                narrative_region = mapped.narrative_region
                if any(not (32 <= ord(c) <= 126 or c == "\n") for c in complete):
                    raise DraftError("Unsupported font characters; narrative needs font review")
                lines = wrap_text(
                    complete,
                    narrative_region.right - narrative_region.left,
                    narrative_region.font_size,
                    _measure,
                )
                overflow = lines is None or len(lines) > math.floor(
                    (narrative_region.top - narrative_region.bottom) / narrative_region.leading
                )
                if overflow:
                    _lines(
                        f"See Supplemental Answers, {identity}, packet page {MAX_PACKET_PAGES}.",
                        narrative_region,
                    )
                    full = wrap_text(value.value, 520.0, 10.0, _measure)
                    if full is None:
                        raise DraftError("Narrative has an unbreakable word that cannot fit")
                    count = max(1, math.ceil(len(full) / SUPPLEMENT_LINES))
                    if (
                        supplement_page_count
                        + count
                        + form_count
                        + sum(len(r.pages) for _, r in attachment_readers)
                        > MAX_PACKET_PAGES
                    ):
                        raise DraftError("Narrative exceeds the bounded supplemental page budget")
                    supplement_starts[identity] = supplement_page_count + 1
                    supplement_page_count += count
                    supplements.append((identity, full))
                placements[identity] = {"mode": "supplement" if overflow else "inline"}
            else:
                raise DraftError("This draft slice does not write this answer type")
        except DraftError as error:
            issues.append(str(error))
            continue
        texts.extend(candidate_texts)
        marks.extend(candidate_marks)
        result["status"] = "written_to_draft"
        issues.append("draft_only_requires_final_human_review")
        accepted.append(proposal)

    section_data = [
        PacketSection(
            section_id="form",
            source_sha256=request.layout.application_sha256,
            page_count=len(reader.pages),
            role="form",
        )
    ]
    section_data.extend(
        PacketSection(
            section_id=f"additional-form-{form.source.sha256[:16]}",
            source_sha256=form.source.sha256,
            page_count=len(form_reader.pages),
            role="form",
        )
        for form, _, form_reader in additional_forms_data
    )
    if supplement_page_count:
        section_data.append(
            PacketSection(
                section_id="answers",
                source_sha256="0" * 64,
                page_count=supplement_page_count,
                role="supplemental_answers",
            )
        )
    section_data.extend(
        PacketSection(
            section_id=source.source_id,
            source_sha256=source.sha256,
            page_count=len(attachment_reader.pages),
            role="evidence",
        )
        for source, attachment_reader in attachment_readers
    )
    pagination = PacketPagination(sections=tuple(section_data))
    accepted_by_id = {proposal.requirement_id: proposal for proposal in accepted}
    additional_form_texts: list[list[TextPlacement]] = []
    additional_form_manifest: list[dict[str, object]] = []
    for form, _, _ in additional_forms_data:
        form_texts: list[TextPlacement] = []
        written_requirements: list[str] = []
        for field in form.fields:
            approved_proposal = accepted_by_id.get(field.requirement_id)
            if approved_proposal is None or approved_proposal.value is None:
                continue
            if not isinstance(approved_proposal.value, (TextValue, IdentifierValue)):
                raise DraftError(
                    "Additional issuer form fields require an approved text or identifier answer"
                )
            additional_text = approved_proposal.value.value
            form_texts.append(TextPlacement(field.region, _lines(additional_text, field.region)))
            if field.requirement_id not in written_requirements:
                written_requirements.append(field.requirement_id)
        additional_form_texts.append(form_texts)
        additional_form_manifest.append(
            {
                "path": form.source.path,
                "sha256": form.source.sha256,
                "written_requirements": written_requirements,
                "fields": [
                    {
                        "requirement_id": field.requirement_id,
                        "page": field.region.page,
                        "written": field.requirement_id in written_requirements,
                    }
                    for field in form.fields
                ],
            }
        )
    supplement_evidence: dict[str, str] = {}
    for proposal in accepted:
        identity = proposal.requirement_id
        evidence_refs = tuple(
            PacketReference(section_id=c.source_id, page=c.page) for c in proposal.citations
        )
        refs = tuple(dict.fromkeys(pagination.resolve(r, role="evidence") for r in evidence_refs))
        placements[identity]["evidence_packet_pages"] = list(refs)
        evidence_text = "Supporting evidence: " + "; ".join(f"packet page {p}" for p in refs) + "."
        supplement_evidence[identity] = evidence_text
        if isinstance(proposal.value, NarrativeValue):
            answer_narrative_region = mappings[identity].narrative_region
            if answer_narrative_region is None:
                raise DraftError("Narrative mapping disappeared")
            if identity in supplement_starts:
                start = pagination.resolve(
                    PacketReference(section_id="answers", page=supplement_starts[identity]),
                    role="supplemental_answers",
                )
                marker = f"See Supplemental Answers, {identity}, packet page {start}."
                texts.append(
                    TextPlacement(
                        answer_narrative_region,
                        _lines(marker, answer_narrative_region),
                    )
                )
            else:
                texts.append(
                    TextPlacement(
                        answer_narrative_region,
                        _lines(
                            proposal.value.value + "\n" + evidence_text,
                            answer_narrative_region,
                        ),
                    )
                )

    supplemental_bytes: bytes | None = None
    if supplements:
        stream = BytesIO()
        canvas = Canvas(stream, pagesize=(612, 792), invariant=True)
        for identity, lines in supplements:
            for start in range(0, len(lines), SUPPLEMENT_LINES):
                canvas.setFont("Helvetica-Bold", 10)
                canvas.drawString(30, 770, "INCOMPLETE DRAFT - NOT FOR SUBMISSION")
                canvas.drawString(40, 735, "Supplemental Answers - " + identity)
                canvas.setFont("Helvetica", 10)
                canvas.drawString(40, 715, f"Response to form page {requirements[identity].page}.")
                for index, line in enumerate(lines[start : start + SUPPLEMENT_LINES]):
                    canvas.drawString(40, 690 - index * 14, line)
                reference_lines = wrap_text(supplement_evidence[identity], 520.0, 10.0, _measure)
                if reference_lines is None or len(reference_lines) > 4:
                    raise DraftError("Supplemental evidence references exceed reserved space")
                for index, line in enumerate(reference_lines):
                    canvas.drawString(40, 70 - index * 12, line)
                canvas.showPage()
        canvas.save()
        supplemental_bytes = stream.getvalue()
        section_data[1] = section_data[1].model_copy(
            update={"source_sha256": hashlib.sha256(supplemental_bytes).hexdigest()}
        )
        pagination = PacketPagination(sections=tuple(section_data))
    main_form_pdf = _form_pdf(original, texts, marks, request.mode == "fictional")
    additional_form_pdfs = [
        _form_pdf(form_bytes, form_texts, [], request.mode == "fictional")
        for (_, form_bytes, _), form_texts in zip(
            additional_forms_data, additional_form_texts, strict=True
        )
    ]
    with closing(PdfWriter(clone_from=PdfReader(BytesIO(main_form_pdf)))) as writer:
        for (additional_form, _, _), additional_pdf in zip(
            additional_forms_data, additional_form_pdfs, strict=True
        ):
            start = len(writer.pages)
            writer.append(PdfReader(BytesIO(additional_pdf)), import_outline=False)
            writer.add_outline_item(f"Issuer form {additional_form.source.sha256[:12]}", start)
        if supplemental_bytes:
            writer.append(PdfReader(BytesIO(supplemental_bytes)), import_outline=False)
        for source, attachment_reader in attachment_readers:
            start = len(writer.pages)
            writer.append(attachment_reader, import_outline=False)
            writer.add_outline_item(f"Evidence {source.source_id[:12]}", start)
        writer.add_metadata({"/Title": "INCOMPLETE DRAFT - NOT FOR SUBMISSION"})
        buffer = BytesIO()
        writer.write(buffer)
    packet = buffer.getvalue()
    if len(PdfReader(BytesIO(packet)).pages) != sum(s.page_count for s in pagination.sections):
        raise DraftError("Final packet pagination does not match assembled output")

    def verify() -> None:
        for path, snapshot in ((request_path, raw), (review_path, reviewed)):
            if read_local_input(root, path, Path("outputs"), 2 * 1024 * 1024) != snapshot:
                raise DraftError("Draft input or review changed; no output published")
        if (
            read_local_input(
                root, Path(request.source), Path("bd_agreements/Blank"), 64 * 1024 * 1024
            )
            != original
        ):
            raise DraftError("Blank application changed; no output published")
        for path, snapshot in additional_form_snapshots.items():
            if (
                read_local_input(root, path, Path("bd_agreements/Blank"), 64 * 1024 * 1024)
                != snapshot
            ):
                raise DraftError("Additional issuer form changed; no output published")
        for path, snapshot in ocr_artifact_snapshots.items():
            if read_local_input(root, path, Path("outputs"), 2 * 1024 * 1024) != snapshot:
                raise DraftError("OCR evidence changed; no output published")

    payload: dict[str, object] = {
        "schema_version": 1,
        "writer_version": "reviewed-draft-overlay-v2",
        "created_at": datetime.now(UTC).isoformat(),
        "status": "incomplete_draft_not_for_submission",
        "mode": request.mode,
        "request_sha256": request_hash,
        "review_sha256": hashlib.sha256(reviewed).hexdigest(),
        "reviewer": review.reviewer,
        "source": request.source,
        "application_sha256": request.layout.application_sha256,
        "requirements": request.requirements.model_dump(mode="json"),
        "layout": request.layout.model_dump(mode="json"),
        "review": review.model_dump(mode="json"),
        "additional_forms": additional_form_manifest,
        "packet_sha256": hashlib.sha256(packet).hexdigest(),
        "written_requirements": [p.requirement_id for p in accepted],
        "answers": results,
        "placements": placements,
        "pagination": pagination.model_dump(mode="json"),
        "sources": [asdict(s) for s in inventory.sources],
        "signature_policy": "signatures_and_signature_dates_left_blank",
        "unapproved_attachments_omitted": [
            s for s in request.attachments if s not in attachment_ids
        ],
        "limitations": [
            "review_JSON_is_trusted_input_not_authentication",
            "declared_subset_only_not_full_application_coverage",
            "native_unrotated_blank_mapping_only",
            "OCR_requires_source_subject_visual_support_and_placement_review",
            "no_historical_comparison_or_business_approval",
        ],
    }

    def write(output: Path) -> None:
        (output / "draft-packet.pdf").write_bytes(packet)
        render = _render_checks(
            original,
            packet,
            output,
            [t.region for t in texts] + [m.box for m in marks],
            marks,
            texts,
        )
        additional_render_checks: list[dict[str, object]] = []
        page_offset = len(reader.pages)
        for index, ((_form_request, form_bytes, form_reader), form_texts) in enumerate(
            zip(additional_forms_data, additional_form_texts, strict=True), start=1
        ):
            additional_render_checks.append(
                _render_checks(
                    form_bytes,
                    packet,
                    output,
                    [placement.region for placement in form_texts],
                    [],
                    form_texts,
                    packet_page_offset=page_offset,
                    filename_prefix=f"additional-form-{index}-",
                )
            )
            page_offset += len(form_reader.pages)
        render["additional_forms"] = additional_render_checks
        with pdfium.PdfDocument(packet) as document:
            for identity, lines in supplements:
                for offset in range(0, len(lines), SUPPLEMENT_LINES):
                    number = form_count + supplement_starts[identity] + offset // SUPPLEMENT_LINES
                    with (
                        closing(document[number - 1]) as page,
                        closing(page.get_textpage()) as text,
                    ):
                        actual = " ".join(
                            text.get_text_bounded(
                                left=40.0, bottom=105.0, right=560.0, top=705.0, errors="strict"
                            ).split()
                        )
                        expected = " ".join(
                            " ".join(lines[offset : offset + SUPPLEMENT_LINES]).split()
                        )
                        if expected not in actual:
                            raise DraftError("Supplemental answer is missing or clipped")
                    with _render_image(packet, number - 1) as image:
                        image.save(output / f"supplement-page-{number}.png")
        render["supplement_pages_rendered_and_text_checked"] = supplement_page_count
        payload["render_checks"] = render
        # The shared publisher writes its initial report before companion validation.
        (output / "draft.json").write_text(json.dumps(payload, indent=2) + "\n")
        summary = [
            "INTERNAL REVIEW - NOT PART OF THE SUBMISSION PACKET",
            "INCOMPLETE DRAFT - NOT FOR SUBMISSION",
            f"Mode: {request.mode}",
            "Coverage: declared subset only; all other form fields remain unresolved.",
            "Signatures and signature dates must be completed only by humans at signing.",
        ]
        for form in additional_form_manifest:
            summary.append(
                "Additional issuer form appended: "
                f"{form['path']}; approved mirrored fields: {form['written_requirements']}."
            )
        if review.reviewer_notes:
            summary.extend(["", "Reviewer notes:"])
            summary.extend(f"- {note}" for note in review.reviewer_notes)
        for item, proposal in zip(results, request.proposals.proposals, strict=True):
            summary_decision = decisions.get(proposal.requirement_id)
            packet_pages = placements.get(proposal.requirement_id, {}).get(
                "evidence_packet_pages", []
            )
            summary.extend(
                [
                    "",
                    f"{item['requirement_id']}: {item['status']} - {item['issues']}",
                    f"Question: {requirements[proposal.requirement_id].instruction}",
                    f"Form page: {requirements[proposal.requirement_id].page}",
                    "Proposed value: "
                    + (proposal.value.model_dump_json() if proposal.value else "(blank)"),
                    f"Review: {item['review_reason']}",
                    f"Evidence packet pages: {packet_pages}",
                ]
            )
            for citation in proposal.citations:
                source = sources.get(citation.source_id)
                summary.append(
                    f"Evidence: {source.path if source else 'UNRESOLVED SOURCE'}; "
                    f"sha256={source.sha256 if source else citation.source_id}; "
                    f"source page {citation.page}"
                )
                if isinstance(citation, OcrCitation):
                    summary.append(
                        f"OCR quote: {citation.quote}; artifact {citation.artifact_path}; "
                        f"word range [{citation.word_start}, {citation.word_end}); "
                        "see draft.json for exact pixel bounds and render hash."
                    )
            if any(isinstance(c, OcrCitation) for c in proposal.citations):
                confirmed_subject = (
                    summary_decision.confirmed_source_subject
                    if summary_decision
                    else "(not confirmed)"
                )
                visual_confirmation = (
                    summary_decision.ocr_visual_confirmed if summary_decision else False
                )
                summary.append(
                    "OCR review: "
                    f"source subject confirmed as {confirmed_subject}; "
                    f"visual confirmation={visual_confirmation}."
                )
        summary.extend(
            [
                "",
                "Detailed checks, quotations and output hashes: see draft.json.",
                "Prior-packet comparison and signer-specific copies: not performed.",
            ]
        )
        (output / "reviewer-summary.txt").write_text("\n".join(summary) + "\n")

    return publish_json_run(
        root, "draft", payload, inventory, verify_inputs=verify, write_artifacts=write
    )
