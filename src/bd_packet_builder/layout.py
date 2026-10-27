"""Version-bound visual mappings, separate from response values and answer approval."""

import hashlib
from contextlib import closing
from pathlib import Path
from typing import Annotated, Literal, Self

import pypdfium2 as pdfium
from pydantic import Field, model_validator

from bd_packet_builder.contracts import Contract, Identifier, Nonblank, Requirement, Sha256
from bd_packet_builder.local_inputs import read_local_input
from bd_packet_builder.responses import NarrativeRegion


class LayoutError(ValueError):
    """Safe layout or source-validation failure."""


class PageBox(Contract):
    """Unrotated PDF points with bottom-left origin, never image pixels."""

    page: Annotated[int, Field(ge=1)]
    left: Annotated[float, Field(ge=0, allow_inf_nan=False)]
    bottom: Annotated[float, Field(ge=0, allow_inf_nan=False)]
    right: Annotated[float, Field(gt=0, allow_inf_nan=False)]
    top: Annotated[float, Field(gt=0, allow_inf_nan=False)]

    @model_validator(mode="after")
    def ordered(self) -> Self:
        if self.right <= self.left or self.top <= self.bottom:
            raise ValueError("Layout box must have positive area")
        return self


class OptionPlacement(Contract):
    option_id: Identifier
    control: Literal["radio", "checkbox"]
    box: PageBox
    label_box: PageBox
    label_quote: Nonblank
    write_in_region: NarrativeRegion | None = None


class MappedResponse(Contract):
    requirement: Requirement
    options: Annotated[tuple[OptionPlacement, ...], Field(max_length=100)] = ()
    narrative_region: NarrativeRegion | None = None
    text_region: NarrativeRegion | None = None

    @model_validator(mode="after")
    def relationships(self) -> Self:
        req = self.requirement
        if req.choices is not None:
            if self.narrative_region is not None or self.text_region is not None:
                raise ValueError("Choice groups cannot use a narrative answer region")
            if {o.option_id for o in self.options} != {o.option_id for o in req.choices.options}:
                raise ValueError("Every choice option requires exactly one placement")
            if len({o.option_id for o in self.options}) != len(self.options):
                raise ValueError("Option placements must be unique")
            for option in req.choices.options:
                placement = next(p for p in self.options if p.option_id == option.option_id)
                if option.write_in != (placement.write_in_region is not None):
                    raise ValueError("Write-in region must match its linked option")
                if req.kind == "multi_select" and placement.control != "checkbox":
                    raise ValueError("Multi-select options must use checkboxes")
        elif self.options:
            raise ValueError("Only choice groups may have option placements")
        elif req.kind == "narrative":
            if self.narrative_region is None or self.text_region is not None:
                raise ValueError("Mapped narrative requires only a narrative writable region")
        elif req.kind in ("text", "identifier", "money", "date"):
            if self.text_region is None or self.narrative_region is not None:
                raise ValueError("Mapped scalar requires only a text writable region")
        else:
            raise ValueError("This response kind cannot have a writable mapping")
        boxes = [b for o in self.options for b in (o.box, o.label_box)]
        regions = [o.write_in_region for o in self.options if o.write_in_region is not None]
        if self.narrative_region is not None:
            regions.append(self.narrative_region)
        if self.text_region is not None:
            regions.append(self.text_region)
        all_regions: list[PageBox | NarrativeRegion] = [*boxes, *regions]
        if any(b.page != req.page for b in all_regions):
            raise ValueError("Response placements must remain on the requirement page")
        return self


class ResponseLayout(Contract):
    schema_version: Literal[1] = 1
    application_sha256: Sha256
    responses: Annotated[tuple[MappedResponse, ...], Field(min_length=1, max_length=500)]
    scope: Literal["developer_mapped_subset_not_automatic_discovery"] = (
        "developer_mapped_subset_not_automatic_discovery"
    )

    @model_validator(mode="after")
    def consistent(self) -> Self:
        if len({r.requirement.requirement_id for r in self.responses}) != len(self.responses):
            raise ValueError("Mapped requirement identities must be unique")
        if any(r.requirement.application_sha256 != self.application_sha256 for r in self.responses):
            raise ValueError("Every mapping must refer to the same application version")
        return self


def validate_layout(root: Path, source: Path, layout: ResponseLayout) -> None:
    """Check version, page bounds and label text; control appearance still needs rendered review."""
    root = root.resolve(strict=True)
    original = read_local_input(root, source, Path("bd_agreements/Blank"), 64 * 1024 * 1024)
    if hashlib.sha256(original).hexdigest() != layout.application_sha256:
        raise LayoutError("Visual mapping does not match this blank application version")
    try:
        with pdfium.PdfDocument(original) as document:
            for response in layout.responses:
                number = response.requirement.page
                if number > len(document):
                    raise LayoutError("Mapped requirement page is outside the application")
                with closing(document[number - 1]) as page, closing(page.get_textpage()) as text:
                    if page.get_rotation() != 0:
                        raise LayoutError("Rotated-page mappings need explicit coordinate handling")
                    width, height = page.get_size()
                    native = text.get_text_bounded(errors="strict").replace("\r\n", "\n")
                    if response.requirement.instruction not in native:
                        raise LayoutError(
                            "Mapped instruction is not an exact native-text quotation"
                        )
                    boxes = [b for o in response.options for b in (o.box, o.label_box)]
                    regions = [o.write_in_region for o in response.options if o.write_in_region]
                    if response.narrative_region:
                        regions.append(response.narrative_region)
                    if response.text_region:
                        regions.append(response.text_region)
                    all_regions: list[PageBox | NarrativeRegion] = [*boxes, *regions]
                    if any(b.right > width or b.top > height for b in all_regions):
                        raise LayoutError("Mapped response region is outside the page")
                    for option in response.options:
                        if response.requirement.choices is None:
                            raise LayoutError("Choice metadata is missing")
                        declaration = next(
                            o
                            for o in response.requirement.choices.options
                            if o.option_id == option.option_id
                        )
                        if declaration.instruction not in native:
                            raise LayoutError(
                                "Choice conditions are not anchored in the application"
                            )
                        b = option.label_box
                        label = text.get_text_bounded(
                            left=b.left, bottom=b.bottom, right=b.right, top=b.top, errors="strict"
                        )
                        if " ".join(option.label_quote.split()) not in " ".join(label.split()):
                            raise LayoutError(
                                "Option label does not match its mapped visual region"
                            )
    except (pdfium.PdfiumError, UnicodeError):
        raise LayoutError("Application could not be validated for visual mapping") from None
    if read_local_input(root, source, Path("bd_agreements/Blank"), len(original)) != original:
        raise LayoutError("Application changed during visual mapping")
