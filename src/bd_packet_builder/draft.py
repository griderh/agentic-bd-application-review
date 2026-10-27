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
from pydantic import Field, model_validator
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
from bd_packet_builder.local_inputs import read_local_input
from bd_packet_builder.responses import (
    NarrativeRegion,
    PacketPagination,
    PacketReference,
    PacketSection,
    wrap_text,
)
from bd_packet_builder.retrieval import default_catalog
from bd_packet_builder.review import AnswerProposals

MAX_PACKET_PAGES = 60
BANNER_HEIGHT = 24
RENDER_SCALE = 2
MAX_RENDER_PIXELS = 12_000_000
SUPPLEMENT_LINES = 42


class DraftError(ValueError):
    """Safe failures of draft input, placement, rendering or publication."""


class DraftSource(Contract):
    path: Nonblank
    sha256: Sha256


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

    @model_validator(mode="after")
    def identities(self) -> Self:
        requirements = {r.requirement_id: r for r in self.requirements.requirements}
        if len(requirements) > 20:
            raise ValueError("Draft trial supports at most 20 requirements")
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
    decisions: Annotated[tuple[DraftDecision, ...], Field(max_length=20)]
    attachment_source_ids: Annotated[tuple[Sha256, ...], Field(max_length=10)] = ()

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
) -> dict[str, object]:
    total_outside = 0
    with pdfium.PdfDocument(packet) as document:
        for placement in texts:
            b = placement.region
            with closing(document[b.page - 1]) as page, closing(page.get_textpage()) as text:
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
            _render_image(packet, number - 1) as after,
        ):
            before.save(output / f"page-{number}-before.png")
            after.save(output / f"page-{number}-after.png")
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
    form_count = len(reader.pages)
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
            page_count=form_count,
            role="form",
        )
    ]
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
            region = mappings[identity].narrative_region
            if region is None:
                raise DraftError("Narrative mapping disappeared")
            if identity in supplement_starts:
                start = pagination.resolve(
                    PacketReference(section_id="answers", page=supplement_starts[identity]),
                    role="supplemental_answers",
                )
                marker = f"See Supplemental Answers, {identity}, packet page {start}."
                texts.append(TextPlacement(region, _lines(marker, region)))
            else:
                texts.append(
                    TextPlacement(
                        region, _lines(proposal.value.value + "\n" + evidence_text, region)
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
    form = _form_pdf(original, texts, marks, request.mode == "fictional")
    with closing(PdfWriter(clone_from=PdfReader(BytesIO(form)))) as writer:
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

    payload: dict[str, object] = {
        "schema_version": 1,
        "writer_version": "reviewed-draft-overlay-v1",
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
            "no_OCR_answer_release_no_signer_copies_no_submission",
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
        for item, proposal in zip(results, request.proposals.proposals, strict=True):
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
