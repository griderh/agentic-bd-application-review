"""Generate fictional blank forms and withheld geometry before opt-in model evaluation."""

import argparse
import hashlib
import json
from contextlib import closing
from io import BytesIO
from pathlib import Path
from uuid import uuid4

import pypdfium2 as pdfium
from pypdf import PdfReader, PdfWriter
from reportlab.lib.utils import ImageReader
from reportlab.pdfbase.pdfmetrics import stringWidth
from reportlab.pdfgen.canvas import Canvas

from bd_packet_builder.foundry import FoundryConfig
from bd_packet_builder.visual import MappingReference, NormalizedBox, VisualPage, map_visual


def _box(left: int, top: int, right: int, bottom: int) -> dict[str, int]:
    return dict(left=left, top=top, right=right, bottom=bottom)


def _page(width: int, height: int) -> tuple[bytes, dict[str, object]]:
    stream = BytesIO()
    canvas = Canvas(stream, pagesize=(width, height), invariant=True)
    canvas.setFont("Helvetica", 11)

    def text(x: int, y: int, value: str) -> dict[str, int]:
        canvas.drawString(x * width / 1000, height - y * height / 1000, value)
        return _box(
            x,
            round(y - 11 * 1000 / height),
            round(x + stringWidth(value, "Helvetica", 11) * 1000 / width),
            round(y + 3 * 1000 / height),
        )

    def rectangle(bounds: dict[str, int]) -> None:
        canvas.rect(
            bounds["left"] * width / 1000,
            height - bounds["bottom"] * height / 1000,
            (bounds["right"] - bounds["left"]) * width / 1000,
            (bounds["bottom"] - bounds["top"]) * height / 1000,
        )

    def option(
        identity: str, label: str, x: int, y: int, radio: bool = False, write: bool = False
    ) -> dict[str, object]:
        bounds = _box(x, y - 14, x + 16, y + 2)
        if radio:
            canvas.circle(
                (x + 8) * width / 1000, height - (y - 6) * height / 1000, 8 * width / 1000
            )
        else:
            rectangle(bounds)
        label_box = text(x + 28, y, label)
        region = _box(x + 110, y - 18, x + 310, y + 4) if write else None
        if region:
            rectangle(region)
        return {
            "option_id": identity,
            "label": label,
            "instruction": label,
            "control": "radio" if radio else "checkbox",
            "box": bounds,
            "label_box": label_box,
            "write_in_region": region,
        }

    text(70, 45, "SYNTHETIC BLANK FORM - NO COMPANY ANSWERS")
    items: list[dict[str, object]] = []
    heading = text(70, 110, "1. Choose one service category:")
    items.append(
        {
            "item_id": "category",
            "instruction": "Choose one service category:",
            "kind": "single_select",
            "instruction_box": heading,
            "region": None,
            "options": [
                option("dealer", "Dealer", 90, 160, True),
                option("bank", "Bank", 90, 210, True),
                option("adviser", "Adviser", 90, 260, True),
            ],
            "explanation": None,
        }
    )
    heading = text(70, 350, "2. Select all offered instruments (Other requires description):")
    items.append(
        {
            "item_id": "instruments",
            "instruction": "Select all offered instruments",
            "kind": "multi_select",
            "instruction_box": heading,
            "region": None,
            "options": [
                option("bills", "Treasury Bills", 90, 410),
                option("other-instrument", "Other", 90, 470, write=True),
                option("agencies", "Agency Bonds", 540, 410),
                option("other-agency", "Other", 540, 470, write=True),
            ],
            "explanation": None,
        }
    )
    heading = text(70, 610, "3. Describe the firm's services:")
    region = _box(70, 650, 930, 830)
    rectangle(region)
    items.append(
        {
            "item_id": "description",
            "instruction": "Describe the firm's services:",
            "kind": "narrative",
            "instruction_box": heading,
            "region": region,
            "options": [],
            "explanation": None,
        }
    )
    canvas.save()
    return stream.getvalue(), {"readable": True, "explanation": None, "items": items}


def prepare(root: Path) -> tuple[Path, Path, Path]:
    root = root.resolve(strict=True)
    output = root / "outputs"
    if output.resolve() != output:
        raise ValueError("Output must not resolve through a symlink")
    output.mkdir(exist_ok=True)
    run = output / f"visual-fixture-{uuid4().hex}"
    data_root = run / "synthetic-root"
    source = Path("bd_agreements/Blank/fictional.pdf")
    target = data_root / source
    target.parent.mkdir(parents=True)
    expected = []
    with PdfWriter() as writer:
        for number, (width, height, scan, rotate) in enumerate(
            [
                (612, 792, False, False),
                (792, 612, False, False),
                (612, 792, True, False),
                (612, 792, True, True),
            ],
            1,
        ):
            original, reference = _page(width, height)
            if scan:
                with (
                    pdfium.PdfDocument(original) as doc,
                    closing(doc[0]) as page,
                    closing(page.render(scale=2)) as bitmap,
                    closing(bitmap.to_pil()) as image,
                ):
                    stream = BytesIO()
                    canvas = Canvas(stream, pagesize=(width, height), invariant=True)
                    canvas.drawImage(ImageReader(image), 0, 0, width=width, height=height)
                    canvas.save()
                    original = stream.getvalue()
            page = writer.add_page(PdfReader(BytesIO(original)).pages[0])
            if rotate:
                page.rotate(90)

                def turn(box: NormalizedBox) -> NormalizedBox:
                    return NormalizedBox(
                        left=1000 - box.bottom, top=box.left, right=1000 - box.top, bottom=box.right
                    )

                checked = VisualPage.model_validate_json(json.dumps(reference))
                reference = checked.model_copy(
                    update={
                        "items": tuple(
                            item.model_copy(
                                update={
                                    "instruction_box": turn(item.instruction_box),
                                    "region": turn(item.region) if item.region else None,
                                    "options": tuple(
                                        option.model_copy(
                                            update={
                                                "box": turn(option.box),
                                                "label_box": turn(option.label_box),
                                                "write_in_region": turn(option.write_in_region)
                                                if option.write_in_region
                                                else None,
                                            }
                                        )
                                        for option in item.options
                                    ),
                                }
                            )
                            for item in checked.items
                        )
                    }
                ).model_dump(mode="json")

            expected.append({"page": number, "expected": reference})
        writer.write(target)
    reference_path = Path("outputs/reference.json")
    (data_root / "outputs").mkdir()
    reference = MappingReference.model_validate_json(
        json.dumps(
            {
                "application_sha256": hashlib.sha256(target.read_bytes()).hexdigest(),
                "pages": expected,
            }
        )
    )
    (data_root / reference_path).write_text(reference.model_dump_json(indent=2) + "\n")
    return data_root, source, reference_path


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path("."))
    parser.add_argument("--prepare-only", action="store_true")
    parser.add_argument("--endpoint")
    parser.add_argument("--deployment")
    parser.add_argument("--allow-paid", action="store_true")
    args = parser.parse_args()
    if not args.prepare_only and not (args.allow_paid and args.endpoint and args.deployment):
        parser.error("Supply endpoint, deployment and --allow-paid, or --prepare-only")
    root, source, reference = prepare(args.root)
    print(f"Fictional source and withheld reference prepared: {root}")
    if args.prepare_only:
        return 0
    result = map_visual(
        root,
        source,
        FoundryConfig(endpoint=args.endpoint, deployment=args.deployment),
        allow_paid=True,
        reference_path=reference,
    )
    data = json.loads((result / "visual-map.json").read_text())
    print(
        json.dumps(
            {
                "report": str(result / "visual-map.json"),
                "evaluation": data["evaluation"],
                "usage": data["usage"],
            },
            indent=2,
        )
    )
    return 0 if data["evaluation"]["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
