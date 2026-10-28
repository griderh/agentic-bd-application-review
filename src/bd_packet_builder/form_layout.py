"""Deterministic conversion of visual page maps into unapproved requirements and placements.

Model page maps are untrusted proposals. This module never answers questions; it anchors
issuer wording to native PDF text, converts normalized boxes to writer coordinates and turns
every item it cannot place safely into a review exception instead of failing the whole run.
"""

import hashlib
import re
import string
from collections.abc import Mapping
from contextlib import closing
from dataclasses import dataclass
from io import BytesIO
from typing import Annotated, Literal, Self

import pypdfium2 as pdfium
from pydantic import Field, model_validator
from pypdf import PdfReader
from pypdf.errors import PyPdfError

from bd_packet_builder.contracts import (
    ApplicationRequirements,
    ChoiceGroup,
    ChoiceOption,
    Contract,
    Requirement,
    RequirementKind,
    Sha256,
)
from bd_packet_builder.layout import MappedResponse, OptionPlacement, PageBox, ResponseLayout
from bd_packet_builder.responses import NarrativeRegion
from bd_packet_builder.run import ReviewException
from bd_packet_builder.visual import NormalizedBox, VisualItem, VisualPage

MAX_PAGES = 500
FONT_SIZE = 10.0
LEADING = 14.0
MIN_LEADING = 12.0
_SCALAR_KINDS = frozenset({"text", "identifier", "date"})
_SIGNING_KINDS = frozenset({"signature", "signature_date"})
_TOKEN = re.compile(r"\S+")


class FormLayoutError(ValueError):
    """Technical failure interpreting the blank; never a per-question review item."""


class FormInterpretation(Contract):
    """Unapproved requirements/placements plus explicit gaps; contains no applicant answers."""

    schema_version: Literal[1] = 1
    application_sha256: Sha256
    requirements: ApplicationRequirements | None
    layout: ResponseLayout | None
    protected_regions: Annotated[tuple[PageBox, ...], Field(max_length=500)]
    exceptions: Annotated[tuple[ReviewException, ...], Field(max_length=1_000)]
    status: Literal["automatic_mapping_unapproved_no_answers"] = (
        "automatic_mapping_unapproved_no_answers"
    )

    @model_validator(mode="after")
    def consistent(self) -> Self:
        known = (
            {}
            if self.requirements is None
            else {r.requirement_id: r for r in self.requirements.requirements}
        )
        if any(r.application_sha256 != self.application_sha256 for r in known.values()):
            raise ValueError("Requirements must refer to the interpreted application")
        if self.layout is not None:
            if self.layout.application_sha256 != self.application_sha256:
                raise ValueError("Layout must refer to the interpreted application")
            if any(
                known.get(m.requirement.requirement_id) != m.requirement
                for m in self.layout.responses
            ):
                raise ValueError("Every placed response must be an interpreted requirement")
        return self


@dataclass(frozen=True)
class _Page:
    number: int
    width: float
    height: float
    text: pdfium.PdfTextPage
    native: str
    geometry: bool
    anchorable: bool


@dataclass(frozen=True)
class _Candidate:
    mapped: MappedResponse
    writable: tuple[PageBox | NarrativeRegion, ...]


def _normalized_token(token: str) -> str:
    return token.casefold().strip(string.punctuation)


def _anchor(wanted: str, native: str) -> str | None:
    """Exact native substring whose casefolded words match ``wanted``; ignores edge punctuation."""
    target = [t for t in (_normalized_token(w) for w in wanted.split()) if t]
    spans = [
        (m.start(), m.end(), token)
        for m in _TOKEN.finditer(native)
        if (token := _normalized_token(m.group()))
    ]
    size = len(target)
    if not size:
        return None
    for index in range(len(spans) - size + 1):
        if all(spans[index + k][2] == target[k] for k in range(size)):
            return native[spans[index][0] : spans[index + size - 1][1]]
    return None


def _points(box: NormalizedBox, page: _Page) -> tuple[float, float, float, float]:
    """Displayed top-left normalized box to unrotated bottom-left (left, bottom, right, top)."""
    left, top, right, bottom = box.display_points(page.width, page.height)
    return left, max(0.0, page.height - bottom), min(right, page.width), page.height - top


def _page_box(box: NormalizedBox, page: _Page) -> PageBox:
    left, bottom, right, top = _points(box, page)
    return PageBox(page=page.number, left=left, bottom=bottom, right=right, top=top)


def _bounded(page: _Page, left: float, bottom: float, right: float, top: float) -> str:
    text: str = page.text.get_text_bounded(
        left=left, bottom=bottom, right=right, top=top, errors="strict"
    )
    return text


def _region(box: NormalizedBox, page: _Page) -> NarrativeRegion | str:
    left, bottom, right, top = _points(box, page)
    height = top - bottom
    if height >= LEADING:
        leading = LEADING
    elif height >= MIN_LEADING:
        leading = MIN_LEADING
    else:
        return "answer_region_too_small"
    if _bounded(page, left, bottom, right, top).replace("_", "").strip():
        return "answer_region_overlaps_issuer_text"
    return NarrativeRegion(
        page=page.number,
        left=left,
        bottom=bottom,
        right=right,
        top=top,
        font_size=FONT_SIZE,
        leading=leading,
    )


def _overlap(a: PageBox | NarrativeRegion, b: PageBox | NarrativeRegion) -> bool:
    return (
        a.page == b.page
        and min(a.right, b.right) > max(a.left, b.left)
        and min(a.top, b.top) > max(a.bottom, b.bottom)
    )


def _standard_geometry(reader: PdfReader, number: int) -> bool:
    page = reader.pages[number - 1]
    return (
        page.rotation == 0
        and float(page.mediabox.left) == 0
        and float(page.mediabox.bottom) == 0
        and list(page.cropbox) == list(page.mediabox)
        and page.get("/UserUnit", 1) == 1
    )


def _reader(blank: bytes) -> PdfReader:
    try:
        reader = PdfReader(BytesIO(blank))
        if reader.is_encrypted:
            raise FormLayoutError("Encrypted applications cannot be interpreted")
        count = len(reader.pages)
    except (PyPdfError, ValueError, KeyError, TypeError) as error:
        if isinstance(error, FormLayoutError):
            raise
        raise FormLayoutError("Application PDF could not be read") from None
    if not 1 <= count <= MAX_PAGES:
        raise FormLayoutError("Application page count is empty or exceeds the limit")
    return reader


class _Builder:
    def __init__(self, digest: str) -> None:
        self.digest = digest
        self.requirements: list[Requirement] = []
        self.candidates: list[_Candidate] = []
        self.protected: list[PageBox] = []
        self.exceptions: list[ReviewException] = []

    def flag(self, code: str, message: str, requirement_id: str | None = None) -> None:
        self.exceptions.append(
            ReviewException(code=code, message=message, requirement_id=requirement_id)
        )

    def item(self, item: VisualItem, page: _Page) -> None:
        rid = f"p{page.number}.{item.item_id}"
        if len(rid) > 128:
            self.flag(
                "item_identity_unsupported",
                f"An item on blank page {page.number} has an identity that is too long.",
            )
            return
        if item.kind == "money":
            self.flag(
                "financial_units_unresolved",
                f"Requirement {rid} asks for an amount without a resolved unit; "
                "it was not mapped and needs reviewer interpretation.",
                rid,
            )
            return
        native = page.native if page.anchorable else ""
        quote = _anchor(item.instruction, native)
        kind: RequirementKind = item.kind
        if kind == "boolean" and len(item.options) >= 2:
            kind = "single_select"
        choices: ChoiceGroup | None = None
        anchored = quote is not None
        placements: list[OptionPlacement] = []
        if kind in ("single_select", "multi_select"):
            declared: list[ChoiceOption] = []
            for option in item.options:
                instruction = _anchor(option.instruction, native)
                label_box = _page_box(option.label_box, page)
                label = (
                    _anchor(
                        option.label,
                        _bounded(
                            page, label_box.left, label_box.bottom, label_box.right, label_box.top
                        ),
                    )
                    if page.anchorable
                    else None
                )
                declared.append(
                    ChoiceOption(
                        option_id=option.option_id,
                        label=label or option.label,
                        instruction=instruction or option.instruction,
                        write_in=option.write_in_region is not None,
                    )
                )
                if instruction is None or label is None:
                    anchored = False
                    continue
                write_in: NarrativeRegion | None = None
                if option.write_in_region is not None and page.anchorable:
                    region = _region(option.write_in_region, page)
                    if isinstance(region, str):
                        self.flag(region, self._message(region, rid), rid)
                        anchored = False
                        continue
                    write_in = region
                placements.append(
                    OptionPlacement(
                        option_id=option.option_id,
                        control="checkbox" if option.control == "checkbox" else "radio",
                        box=_page_box(option.box, page),
                        label_box=label_box,
                        label_quote=label,
                        write_in_region=write_in,
                    )
                )
            choices = ChoiceGroup(options=tuple(declared))
        requirement = Requirement(
            requirement_id=rid,
            application_sha256=self.digest,
            page=page.number,
            instruction=quote or item.instruction,
            kind=kind,
            choices=choices,
        )
        self.requirements.append(requirement)
        if kind in _SIGNING_KINDS:
            if item.region is not None and page.geometry:
                self.protected.append(_page_box(item.region, page))
            else:
                self.flag(
                    "signing_location_unmapped",
                    f"Signing item {rid} has no verified location to protect; "
                    "the reviewer must locate it before signing.",
                    rid,
                )
            return
        if kind == "attachment":
            return
        if kind == "boolean":
            self.flag(
                "boolean_placement_unsupported",
                f"Requirement {rid} is a standalone yes/no or attestation control "
                "that cannot be placed automatically yet.",
                rid,
            )
            return
        if not page.anchorable:
            return
        if not anchored:
            if not any(e.requirement_id == rid for e in self.exceptions):
                self.flag(
                    "placement_not_native_anchored",
                    f"Requirement {rid} wording or option labels could not be matched to "
                    "the application's native text, so it was not placed.",
                    rid,
                )
            return
        if kind in ("single_select", "multi_select"):
            mapped = MappedResponse(requirement=requirement, options=tuple(placements))
        else:
            if item.region is None:
                self.flag(
                    "no_writable_region",
                    f"Requirement {rid} has no identified writable answer area.",
                    rid,
                )
                return
            region = _region(item.region, page)
            if isinstance(region, str):
                self.flag(region, self._message(region, rid), rid)
                return
            mapped = (
                MappedResponse(requirement=requirement, narrative_region=region)
                if kind == "narrative"
                else MappedResponse(requirement=requirement, text_region=region)
            )
        writable: list[PageBox | NarrativeRegion] = [o.box for o in mapped.options]
        writable.extend(o.write_in_region for o in mapped.options if o.write_in_region)
        for answer in (mapped.narrative_region, mapped.text_region):
            if answer is not None:
                writable.append(answer)
        self.candidates.append(_Candidate(mapped, tuple(writable)))

    @staticmethod
    def _message(code: str, rid: str) -> str:
        if code == "answer_region_too_small":
            return f"Requirement {rid} answer area is too small for readable text."
        return f"Requirement {rid} answer area overlaps printed issuer text."

    def placed(self) -> tuple[MappedResponse, ...]:
        conflicted: set[int] = set()
        for index, candidate in enumerate(self.candidates):
            regions = candidate.writable
            if any(_overlap(a, b) for i, a in enumerate(regions) for b in regions[i + 1 :]) or any(
                _overlap(a, p) for a in regions for p in self.protected
            ):
                conflicted.add(index)
            for other in range(index + 1, len(self.candidates)):
                if any(_overlap(a, b) for a in regions for b in self.candidates[other].writable):
                    conflicted.update((index, other))
        for index in sorted(conflicted):
            rid = self.candidates[index].mapped.requirement.requirement_id
            self.flag(
                "placement_conflict",
                f"Requirement {rid} answer area overlaps another answer or a signing area, "
                "so it was not placed.",
                rid,
            )
        return tuple(c.mapped for i, c in enumerate(self.candidates) if i not in conflicted)


def build_form_layout(blank: bytes, pages: Mapping[int, VisualPage]) -> FormInterpretation:
    """Convert visual maps for ``blank`` into requirements, placements and review exceptions."""
    reader = _reader(blank)
    count = len(reader.pages)
    if any(type(n) is not int or not 1 <= n <= count for n in pages):
        raise FormLayoutError("Visual map page is outside the application")
    builder = _Builder(hashlib.sha256(blank).hexdigest())
    try:
        with pdfium.PdfDocument(blank) as document:
            if len(document) != count:
                raise FormLayoutError("Application page structure is inconsistent")
            for number in range(1, count + 1):
                visual = pages.get(number)
                if visual is None:
                    builder.flag(
                        "page_not_interpreted",
                        f"Blank page {number} was not interpreted; nothing on it was mapped.",
                    )
                    continue
                if not visual.readable:
                    builder.flag(
                        "unreadable_page",
                        f"Blank page {number} could not be read and was left unchanged.",
                    )
                    continue
                with (
                    closing(document[number - 1]) as pdf_page,
                    closing(pdf_page.get_textpage()) as text,
                ):
                    width, height = pdf_page.get_size()
                    native = text.get_text_bounded(errors="strict").replace("\r\n", "\n")
                    geometry = _standard_geometry(reader, number)
                    if not geometry:
                        builder.flag(
                            "page_geometry_unsupported",
                            f"Blank page {number} is rotated, cropped or nonstandard; "
                            "its items were interpreted but not placed.",
                        )
                    elif not native.strip():
                        builder.flag(
                            "image_only_placement_unverified",
                            f"Blank page {number} has no native text, so placements cannot be "
                            "verified; its items were interpreted but not placed.",
                        )
                    page = _Page(
                        number=number,
                        width=width,
                        height=height,
                        text=text,
                        native=native,
                        geometry=geometry,
                        anchorable=geometry and bool(native.strip()),
                    )
                    for item in visual.items:
                        builder.item(item, page)
    except (pdfium.PdfiumError, UnicodeError):
        raise FormLayoutError("Application PDF could not be interpreted") from None
    placed = builder.placed()
    digest = builder.digest
    return FormInterpretation(
        application_sha256=digest,
        requirements=(
            ApplicationRequirements(requirements=tuple(builder.requirements))
            if builder.requirements
            else None
        ),
        layout=(
            ResponseLayout(
                application_sha256=digest,
                responses=placed,
                scope="automatic_visual_mapping_unapproved",
            )
            if placed
            else None
        ),
        protected_regions=tuple(builder.protected),
        exceptions=tuple(builder.exceptions),
    )
