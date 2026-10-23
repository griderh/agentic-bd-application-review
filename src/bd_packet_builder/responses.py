"""Response structure and deterministic placement plans, never evidence approval."""

import math
from collections.abc import Callable
from dataclasses import dataclass
from typing import Annotated, Literal, Self

from pydantic import Field, model_validator

from bd_packet_builder.contracts import Contract, Identifier, Sha256


class PacketReference(Contract):
    section_id: Identifier
    page: Annotated[int, Field(ge=1)]


class PacketSection(Contract):
    section_id: Identifier
    source_sha256: Sha256
    page_count: Annotated[int, Field(ge=1, le=1000)]
    role: Literal["form", "supplemental_answers", "evidence"]


class PacketPagination(Contract):
    """Ordered submission sections only; must be supplied from final assembly, not guessed."""

    sections: Annotated[tuple[PacketSection, ...], Field(min_length=1, max_length=100)]

    @model_validator(mode="after")
    def unique_sections(self) -> Self:
        if len({s.section_id for s in self.sections}) != len(self.sections):
            raise ValueError("Packet section identities must be unique")
        return self

    def resolve(
        self, reference: PacketReference, *, role: Literal["evidence", "supplemental_answers"]
    ) -> int:
        offset = 0
        for section in self.sections:
            if section.section_id == reference.section_id:
                if section.role != role or reference.page > section.page_count:
                    raise ValueError("Packet reference has the wrong section role or page")
                return offset + reference.page
            offset += section.page_count
        raise ValueError("Packet reference section is not included")


class NarrativeRegion(Contract):
    """Unrotated PDF points, bottom-left origin; line cells contain a complete baseline."""

    page: Annotated[int, Field(ge=1)]
    left: Annotated[float, Field(ge=0, allow_inf_nan=False)]
    bottom: Annotated[float, Field(ge=0, allow_inf_nan=False)]
    right: Annotated[float, Field(gt=0, allow_inf_nan=False)]
    top: Annotated[float, Field(gt=0, allow_inf_nan=False)]
    font_size: Annotated[float, Field(ge=10, le=16, allow_inf_nan=False)] = 10.0
    leading: Annotated[float, Field(gt=0, allow_inf_nan=False)] = 14.0

    @model_validator(mode="after")
    def dimensions(self) -> Self:
        if self.right <= self.left or self.top <= self.bottom or self.leading < self.font_size + 2:
            raise ValueError("Narrative region dimensions or line spacing are invalid")
        if self.top - self.bottom < self.leading:
            raise ValueError("Narrative region must contain at least one readable line")
        return self


@dataclass(frozen=True)
class NarrativePlan:
    mode: Literal["inline", "supplement"]
    inline_lines: tuple[str, ...]
    supplement_text: str | None
    font_size: float
    approval: Literal["placement_only_not_answer_approval"] = "placement_only_not_answer_approval"


def _wrap(
    text: str, width: float, size: float, measure: Callable[[str, float], float]
) -> tuple[str, ...] | None:
    lines: list[str] = []
    for paragraph in text.split("\n"):
        line = ""
        for word in paragraph.split():
            measured = measure(word, size)
            if not math.isfinite(measured) or measured < 0:
                raise ValueError("Font measurement must be finite and nonnegative")
            if measured > width:
                return None
            candidate = f"{line} {word}" if line else word
            measured = measure(candidate, size)
            if not math.isfinite(measured) or measured < 0:
                raise ValueError("Font measurement must be finite and nonnegative")
            if measured > width:
                lines.append(line)
                line = word
            else:
                line = candidate
        lines.append(line)
    return tuple(lines)


def plan_narrative(
    text: str,
    question_label: str,
    region: NarrativeRegion,
    pagination: PacketPagination,
    *,
    evidence: tuple[PacketReference, ...],
    supplement: PacketReference,
    measure: Callable[[str, float], float],
) -> NarrativePlan:
    """Prefer full inline answer; redirect overflow without shrinking or truncation.

    The caller must validate semantic support, issuer permission for supplementation,
    available supplemental space and final pagination before rendering a real packet.
    """
    if not text.strip() or not question_label.strip() or len(text) > 100_000:
        raise ValueError("Narrative text and question label are required and bounded")
    supplement_page = pagination.resolve(supplement, role="supplemental_answers")
    evidence_pages = tuple(pagination.resolve(ref, role="evidence") for ref in evidence)
    references = "; ".join(f"packet page {p}" for p in dict.fromkeys(evidence_pages))
    complete = text.strip() + (f"\nSupporting evidence: {references}." if references else "")
    width = region.right - region.left
    capacity = math.floor((region.top - region.bottom) / region.leading)
    inline = _wrap(complete, width, region.font_size, measure)
    if inline is not None and len(inline) <= capacity:
        return NarrativePlan("inline", inline, None, region.font_size)
    marker = f"See Supplemental Answers, {question_label}, packet page {supplement_page}."
    redirect = _wrap(marker, width, region.font_size, measure)
    if redirect is None or len(redirect) > capacity:
        raise ValueError("Supplemental reference cannot fit at the minimum readable font size")
    return NarrativePlan("supplement", redirect, f"{question_label}\n{complete}", region.font_size)
