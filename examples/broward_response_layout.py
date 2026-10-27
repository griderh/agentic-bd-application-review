"""Local, hash-bound Broward mapping example; no answers, model calls or packet filling."""

import argparse
import hashlib
import json
import sys
from contextlib import closing
from dataclasses import asdict
from io import BytesIO
from pathlib import Path
from tempfile import TemporaryDirectory
from uuid import uuid4

import pypdfium2 as pdfium
from PIL import ImageDraw
from pydantic import ValidationError
from pypdf import PdfReader, PdfWriter
from reportlab.pdfbase.pdfmetrics import stringWidth
from reportlab.pdfgen.canvas import Canvas

from bd_packet_builder.contracts import ChoiceGroup, ChoiceOption, Requirement
from bd_packet_builder.layout import (
    LayoutError,
    MappedResponse,
    OptionPlacement,
    PageBox,
    ResponseLayout,
    validate_layout,
)
from bd_packet_builder.local_inputs import LocalInputError, read_local_input
from bd_packet_builder.responses import (
    NarrativeRegion,
    PacketPagination,
    PacketReference,
    PacketSection,
    plan_narrative,
)

SOURCE = Path("bd_agreements/Blank/Broward_County/BrokerDealerQuestionnaire.pdf")
VERSION = "9901c61829987ac1a49fb8736b118cab0a2b389445f048a8287bc21c432d4b4d"
RENDER_SCALE = 2


def _box(page: int, left: float, bottom: float, right: float, top: float) -> PageBox:
    return PageBox(page=page, left=left, bottom=bottom, right=right, top=top)


def _narrative_preview(
    original: bytes,
    region: NarrativeRegion,
    lines: tuple[str, ...],
    output: Path,
) -> None:
    overlay = BytesIO()
    canvas = Canvas(overlay, pagesize=(612, 792), invariant=True)
    canvas.setFont("Helvetica", 12)
    canvas.drawString(28, 770, "SYNTHETIC LAYOUT PREVIEW - NOT FOR SUBMISSION")
    canvas.setFont("Helvetica", region.font_size)
    for index, line in enumerate(lines):
        canvas.drawString(
            region.left,
            region.top - region.font_size - index * region.leading,
            line,
        )
    canvas.save()
    reader = PdfReader(BytesIO(original))
    with PdfWriter() as writer:
        page = writer.add_page(reader.pages[region.page - 1])
        page.merge_page(PdfReader(overlay).pages[0])
        writer.write(output)
    with (
        pdfium.PdfDocument(output) as document,
        closing(document[0]) as rendered_page,
        closing(rendered_page.render(scale=RENDER_SCALE)) as bitmap,
    ):
        image = bitmap.to_pil()
        try:
            image.save(output.with_suffix(".png"))
        finally:
            image.close()


def _mapping(pages: dict[int, str]) -> ResponseLayout:
    text = pages[2]
    eligibility = text[text.index("1. In order") : text.index("2. Which")].rstrip()
    instruments = text[text.index("2. Which") : text.index("3. Does")].rstrip()
    labels = (
        ("primary", "Primary dealer", 636.0, "Primary dealer as defined"),
        ("bank", "Top 10 Bank", 608.0, "Top 10 Bank by Total Capital"),
        ("regional", "Regional dealer", 581.0, "Regional dealer that meets all"),
    )
    options = tuple(
        ChoiceOption(
            option_id=key,
            label=label,
            instruction=(
                eligibility[eligibility.index("Regional dealer") :]
                if key == "regional"
                else next(line for line in eligibility.splitlines() if quote in line).strip()
            ),
        )
        for key, label, _, quote in labels
    )
    radio = MappedResponse(
        requirement=Requirement(
            requirement_id="broward-q1",
            application_sha256=VERSION,
            page=2,
            instruction=eligibility,
            kind="single_select",
            choices=ChoiceGroup(options=options),
        ),
        options=tuple(
            OptionPlacement(
                option_id=key,
                control="radio",
                box=_box(2, 55.0, y - 5, 65.0, y + 5),
                label_box=_box(2, 67.0, y - 9, 580.0, y + 9),
                label_quote=quote,
            )
            for key, _, y, quote in labels
        ),
    )
    entries = (
        ("treasury-bills", "Treasury Bills", 55.0, 425.0, False),
        ("treasury-notes", "Treasury Notes/Bonds", 55.0, 409.0, False),
        ("commercial-paper", "Commercial Paper (A1/P1 Minimum)", 55.0, 390.0, False),
        ("world-bank-bonds", "World Bank/IBRD Notes/Bonds", 55.0, 371.0, False),
        ("world-bank-discount", "World Bank/IBRD Discount Notes", 55.0, 352.0, False),
        ("other-instrument", "Other", 55.0, 333.0, True),
        ("ffcb", "FFCB", 342.0, 409.0, False),
        ("fnma", "FNMA", 342.0, 390.0, False),
        ("fhlb", "FHLB", 342.0, 371.0, False),
        ("fhlmc", "FHLMC", 342.0, 352.0, False),
        ("farmer-mac", "Farmer Mac", 342.0, 333.0, False),
        ("other-agency", "Other", 342.0, 314.0, True),
    )
    checkbox = MappedResponse(
        requirement=Requirement(
            requirement_id="broward-q2",
            application_sha256=VERSION,
            page=2,
            instruction=instruments,
            kind="multi_select",
            choices=ChoiceGroup(
                options=tuple(
                    ChoiceOption(
                        option_id=key,
                        label=label,
                        instruction=label,
                        write_in=write_in,
                    )
                    for key, label, _, _, write_in in entries
                )
            ),
        ),
        options=tuple(
            OptionPlacement(
                option_id=key,
                control="checkbox",
                box=_box(2, x, y - 4, x + 9, y + 5),
                label_box=_box(2, x + 18, y - 7, 320.0 if x < 100 else 560.0, y + 8),
                label_quote=label,
                write_in_region=(
                    NarrativeRegion(
                        page=2,
                        left=x + 60,
                        bottom=y - 5,
                        right=265.0 if x < 100 else 519.0,
                        top=y + 9,
                        font_size=10.0,
                        leading=14.0,
                    )
                    if write_in
                    else None
                ),
            )
            for key, label, x, y, write_in in entries
        ),
    )
    narrative_start = pages[4].index("11.")
    narrative_text = pages[4][narrative_start : pages[4].index("\n___", narrative_start)]
    narrative = MappedResponse(
        requirement=Requirement(
            requirement_id="broward-q11",
            application_sha256=VERSION,
            page=4,
            instruction=narrative_text,
            kind="narrative",
        ),
        narrative_region=NarrativeRegion(
            page=4,
            left=28.0,
            bottom=328.0,
            right=580.0,
            top=454.0,
            font_size=10.0,
            leading=14.0,
        ),
    )
    return ResponseLayout(application_sha256=VERSION, responses=(radio, checkbox, narrative))


def create_demo(root: Path) -> Path:
    root = root.resolve(strict=True)
    original = read_local_input(root, SOURCE, Path("bd_agreements/Blank"), 64 * 1024 * 1024)
    if hashlib.sha256(original).hexdigest() != VERSION:
        raise LayoutError(
            "This developer example supports only the visually inspected Broward version"
        )
    output = root / "outputs"
    if output.resolve() != output:
        raise LayoutError("Output must not resolve through a symlink")
    output.mkdir(exist_ok=True)
    final = output / f"broward-layout-{uuid4().hex}"
    with TemporaryDirectory(prefix=".broward-layout-", dir=output) as directory:
        staging = Path(directory)
        with pdfium.PdfDocument(original) as document:
            pages = {}
            for number in (2, 4):
                with closing(document[number - 1]) as page, closing(page.get_textpage()) as text:
                    pages[number] = text.get_text_bounded(errors="strict").replace("\r\n", "\n")
            layout = _mapping(pages)
            validate_layout(root, SOURCE, layout)
            for number in (2, 4):
                with (
                    closing(document[number - 1]) as page,
                    closing(page.render(scale=RENDER_SCALE)) as bitmap,
                ):
                    image = bitmap.to_pil().copy()
                    try:
                        image.save(staging / f"page-{number}-original.png")
                        draw = ImageDraw.Draw(image)
                        for response in layout.responses:
                            if response.requirement.page != number:
                                continue
                            boxes: list[tuple[PageBox | NarrativeRegion, str, str]] = [
                                (o.box, "red" if o.control == "radio" else "blue", o.option_id)
                                for o in response.options
                            ]
                            boxes.extend(
                                (o.write_in_region, "orange", f"{o.option_id}-text")
                                for o in response.options
                                if o.write_in_region
                            )
                            if response.narrative_region:
                                boxes.append((response.narrative_region, "green", "q11-narrative"))
                            for box, color, label in boxes:
                                coords = (
                                    box.left * RENDER_SCALE,
                                    (page.get_height() - box.top) * RENDER_SCALE,
                                    box.right * RENDER_SCALE,
                                    (page.get_height() - box.bottom) * RENDER_SCALE,
                                )
                                draw.rectangle(coords, outline=color, width=2)
                                draw.text((coords[0], coords[1] - 12), label, fill=color)
                        draw.text((30, 20), "LAYOUT REVIEW ONLY - NO APPLICANT ANSWERS", fill="red")
                        image.save(staging / f"page-{number}-annotated.png")
                    finally:
                        image.close()
        region = layout.responses[2].narrative_region
        if region is None:
            raise LayoutError("Narrative mapping is missing")
        # Hypothetical ordering illustrates references; no assembled packet exists in this demo.
        pagination = PacketPagination(
            sections=(
                PacketSection(section_id="form", source_sha256=VERSION, page_count=5, role="form"),
                PacketSection(
                    section_id="answers",
                    source_sha256=hashlib.sha256(b"fictional answers").hexdigest(),
                    page_count=1,
                    role="supplemental_answers",
                ),
                PacketSection(
                    section_id="support",
                    source_sha256=hashlib.sha256(b"fictional evidence").hexdigest(),
                    page_count=2,
                    role="evidence",
                ),
            )
        )

        def measure(text: str, size: float) -> float:
            return float(stringWidth(text, "Helvetica", size))

        plans = {}
        for name, text in (
            ("short", "SYNTHETIC EXAMPLE ONLY. This illustrates an inline narrative."),
            ("overflow", "SYNTHETIC EXAMPLE ONLY. This illustrates a supplemental answer. " * 160),
        ):
            plan = plan_narrative(
                text,
                "Question 11",
                region,
                pagination,
                evidence=(PacketReference(section_id="support", page=1),),
                supplement=PacketReference(section_id="answers", page=1),
                measure=measure,
            )
            plans[name] = asdict(plan)
            _narrative_preview(
                original,
                region,
                plan.inline_lines,
                staging / f"narrative-{name}-preview.pdf",
            )
        data = {
            "status": "developer_mapped_subset_no_packet_no_answer_approval",
            "source": SOURCE.as_posix(),
            "layout": layout.model_dump(mode="json"),
            "validation": "hash_page_bounds_native_instruction_and_visual_label_regions",
            "visual_review": "annotated_renders_require_review_not_automatic_control_detection",
            "pagination_status": "hypothetical_example_not_an_assembled_packet",
            "narrative_plans": plans,
            "limitations": [
                "only_questions_1_2_11",
                "not_automatic_mapping_or_model_accuracy",
                "no_values_selected_or_filled",
                "no_eligibility_or_evidence_approval",
                "supplement_rendering_assembly_and_final_reference_verification_not_implemented",
            ],
        }
        (staging / "response-layout.json").write_text(json.dumps(data, indent=2) + "\n")
        if read_local_input(root, SOURCE, Path("bd_agreements/Blank"), len(original)) != original:
            raise LayoutError("Original changed; mapping was not published")
        staging.rename(final)
    return final


def main() -> int:
    parser = argparse.ArgumentParser(description="Local Broward choice/narrative layout example")
    parser.add_argument("--root", type=Path, default=Path("."))
    args = parser.parse_args()
    try:
        result = create_demo(args.root)
    except (LayoutError, LocalInputError, ValidationError) as error:
        print(f"Layout example rejected: {type(error).__name__}", file=sys.stderr)
        return 1
    except (OSError, pdfium.PdfiumError):
        print("Layout example could not read, render or publish local files", file=sys.stderr)
        return 1
    print(f"Local layout example only; no packet or model calls: {result}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
