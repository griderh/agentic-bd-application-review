import hashlib
import json
from pathlib import Path

import pytest
from pydantic import ValidationError
from reportlab.pdfgen.canvas import Canvas

from bd_packet_builder.layout import LayoutError, ResponseLayout, validate_layout

SOURCE = Path("bd_agreements/Blank/synthetic.pdf")


@pytest.fixture
def mapping(tmp_path: Path) -> tuple[Path, dict]:
    path = tmp_path / SOURCE
    path.parent.mkdir(parents=True)
    canvas = Canvas(str(path), invariant=True)
    canvas.drawString(60, 740, "Choose one category.")
    canvas.circle(45, 700, 4)
    canvas.drawString(60, 696, "Primary dealer")
    canvas.circle(45, 670, 4)
    canvas.drawString(60, 666, "Other")
    canvas.line(110, 665, 250, 665)
    canvas.save()
    digest = hashlib.sha256(path.read_bytes()).hexdigest()

    def box(left: float, bottom: float, right: float, top: float) -> dict:
        return {"page": 1, "left": left, "bottom": bottom, "right": right, "top": top}

    data = {
        "application_sha256": digest,
        "responses": [
            {
                "requirement": {
                    "requirement_id": "category",
                    "application_sha256": digest,
                    "page": 1,
                    "instruction": "Choose one category.",
                    "kind": "single_select",
                    "choices": {
                        "options": [
                            {
                                "option_id": "primary",
                                "label": "Primary dealer",
                                "instruction": "Primary dealer",
                            },
                            {
                                "option_id": "other",
                                "label": "Other",
                                "instruction": "Other",
                                "write_in": True,
                            },
                        ]
                    },
                },
                "options": [
                    {
                        "option_id": "primary",
                        "control": "radio",
                        "box": box(40.0, 695.0, 50.0, 705.0),
                        "label_box": box(59.0, 690.0, 220.0, 711.0),
                        "label_quote": "Primary dealer",
                    },
                    {
                        "option_id": "other",
                        "control": "radio",
                        "box": box(40.0, 665.0, 50.0, 675.0),
                        "label_box": box(59.0, 660.0, 100.0, 681.0),
                        "label_quote": "Other",
                        "write_in_region": {
                            **box(110.0, 666.0, 250.0, 680.0),
                            "font_size": 10.0,
                            "leading": 14.0,
                        },
                    },
                ],
            }
        ],
    }
    return tmp_path, data


def test_visual_mapping_checks_exact_version_labels_and_dimensions(
    mapping: tuple[Path, dict],
) -> None:
    root, data = mapping
    original = (root / SOURCE).read_bytes()
    layout = ResponseLayout.model_validate_json(json.dumps(data))
    validate_layout(root, SOURCE, layout)
    assert (root / SOURCE).read_bytes() == original
    assert layout.responses[0].options[1].write_in_region is not None


@pytest.mark.parametrize("problem", ["hash", "bounds", "label", "instruction"])
def test_mapping_mismatches_fail_explicitly(mapping: tuple[Path, dict], problem: str) -> None:
    root, data = mapping
    if problem == "hash":
        data["application_sha256"] = "a" * 64
        data["responses"][0]["requirement"]["application_sha256"] = "a" * 64
    elif problem == "bounds":
        data["responses"][0]["options"][0]["box"]["right"] = 1000.0
    elif problem == "label":
        data["responses"][0]["options"][0]["label_quote"] = "Invented"
    else:
        data["responses"][0]["requirement"]["instruction"] = "Invented question"
    with pytest.raises(LayoutError):
        validate_layout(root, SOURCE, ResponseLayout.model_validate_json(json.dumps(data)))


@pytest.mark.parametrize(
    "problem", ["missing", "duplicate", "no-write-in", "extra-write-in", "page"]
)
def test_layout_option_relationships_are_strict(mapping: tuple[Path, dict], problem: str) -> None:
    _, data = mapping
    options = data["responses"][0]["options"]
    if problem == "missing":
        options.pop()
    elif problem == "duplicate":
        options.append(options[0])
    elif problem == "no-write-in":
        options[1]["write_in_region"] = None
    elif problem == "extra-write-in":
        options[0]["write_in_region"] = options[1]["write_in_region"]
    else:
        options[0]["box"]["page"] = 2
    with pytest.raises(ValidationError):
        ResponseLayout.model_validate_json(json.dumps(data))


def test_fictional_narrative_preview_uses_measured_pdf_coordinates_without_changing_source(
    mapping: tuple[Path, dict],
) -> None:
    from contextlib import closing

    import pypdfium2 as pdfium

    from bd_packet_builder.responses import NarrativeRegion
    from examples.broward_response_layout import _narrative_preview

    root, _ = mapping
    original = (root / SOURCE).read_bytes()
    region = NarrativeRegion(page=1, left=50.0, bottom=400.0, right=500.0, top=442.0)
    output = root / "synthetic-preview.pdf"
    _narrative_preview(
        original,
        region,
        ("SYNTHETIC FIRST LINE", "Supporting evidence: packet page 7."),
        output,
    )
    assert output.exists() and output.with_suffix(".png").exists()
    assert (root / SOURCE).read_bytes() == original
    with (
        pdfium.PdfDocument(output) as document,
        closing(document[0]) as page,
        closing(page.get_textpage()) as text,
    ):
        extracted = text.get_text_bounded(
            left=region.left,
            bottom=region.bottom,
            right=region.right,
            top=region.top,
        )
        assert "SYNTHETIC FIRST LINE" in extracted
        assert "packet page 7." in extracted
        assert "NOT FOR SUBMISSION" in text.get_text_bounded()


def test_choice_conditions_must_be_present_not_only_the_short_label(
    mapping: tuple[Path, dict],
) -> None:
    root, data = mapping
    data["responses"][0]["requirement"]["choices"]["options"][0]["instruction"] = (
        "Primary dealer with invented qualifications"
    )
    with pytest.raises(LayoutError, match="conditions"):
        validate_layout(root, SOURCE, ResponseLayout.model_validate_json(json.dumps(data)))
