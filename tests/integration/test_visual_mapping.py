import base64
import hashlib
import json
from pathlib import Path
from unittest.mock import Mock

import pytest
from PIL import Image
from pydantic import ValidationError
from reportlab.lib.utils import ImageReader
from reportlab.pdfgen.canvas import Canvas

from bd_packet_builder.foundry import FoundryConfig, FoundryError
from bd_packet_builder.visual import (
    MappingReference,
    NormalizedBox,
    VisualPage,
    evaluate_mapping,
    map_visual,
)

CONFIG = FoundryConfig(endpoint="https://synthetic.openai.azure.com/openai/v1", deployment="test")
SOURCE = Path("bd_agreements/Blank/fictional.pdf")


def box(left: int, top: int, right: int, bottom: int) -> dict:
    return dict(left=left, top=top, right=right, bottom=bottom)


def mapped() -> dict:
    return {
        "readable": True,
        "explanation": None,
        "items": [
            {
                "item_id": "products",
                "instruction": "Select services",
                "kind": "multi_select",
                "instruction_box": box(60, 50, 700, 100),
                "region": None,
                "options": [
                    {
                        "option_id": "advice",
                        "label": "Advice",
                        "instruction": "Advice",
                        "control": "checkbox",
                        "box": box(70, 120, 90, 140),
                        "label_box": box(100, 115, 400, 145),
                        "write_in_region": None,
                    },
                    {
                        "option_id": "other",
                        "label": "Other",
                        "instruction": "Other",
                        "control": "checkbox",
                        "box": box(70, 170, 90, 190),
                        "label_box": box(100, 165, 200, 195),
                        "write_in_region": box(210, 165, 600, 195),
                    },
                ],
                "explanation": None,
            }
        ],
    }


@pytest.fixture(params=["native", "image", "landscape", "rotated"])
def blank(tmp_path: Path, request: pytest.FixtureRequest) -> Path:
    path = tmp_path / SOURCE
    path.parent.mkdir(parents=True)
    size = (792, 612) if request.param == "landscape" else (612, 792)
    canvas = Canvas(str(path), pagesize=size)
    if request.param == "image":
        image = Image.new("RGB", (612, 792), "white")
        canvas.drawImage(ImageReader(image), 0, 0, width=612, height=792)
        image.close()
    else:
        canvas.drawString(40, size[1] - 65, "Select services")
        canvas.drawString(65, size[1] - 100, "Advice")
        canvas.drawString(65, size[1] - 140, "Other")
    canvas.save()
    if request.param == "rotated":
        from pypdf import PdfReader, PdfWriter

        with PdfWriter() as writer:
            writer.add_page(PdfReader(path).pages[0]).rotate(90)
            writer.write(path)
    return tmp_path


def client(payload: dict | None = None) -> Mock:
    instance = Mock()
    instance.responses.parse.return_value = Mock(
        status="completed",
        output_parsed=VisualPage.model_validate_json(json.dumps(payload or mapped())),
        model="controlled-test",
        usage=Mock(input_tokens=100, output_tokens=100, total_tokens=200),
    )
    return instance


def test_visual_workflow_sends_only_selected_blank_image_and_text(blank: Path) -> None:
    original = (blank / SOURCE).read_bytes()
    api = client()
    result = map_visual(
        blank, SOURCE, CONFIG, allow_paid=True, pages=(1,), client_factory=lambda _: api
    )
    data = json.loads((result / "visual-map.json").read_text())
    assert data["status"] == "visual_mapping_review_required_no_answers_no_packet"
    assert data["pages"][0]["proposal"]["items"][0]["kind"] == "multi_select"
    assert (result / "page-1-annotated.png").is_file()
    assert (blank / SOURCE).read_bytes() == original
    kwargs = api.responses.parse.call_args.kwargs
    assert isinstance(kwargs["input"], list)
    content = kwargs["input"][0]["content"]
    assert content[1]["type"] == "input_image"
    image = base64.b64decode(content[1]["image_url"].split(",", 1)[1])
    assert image.startswith(b"\x89PNG")
    assert "expected" not in content[0]["text"]
    assert "tools" not in kwargs and kwargs["store"] is False
    assert data["evaluation"] is None
    assert "control_appearance_and_grouping_unverified" in data["pages"][0]["issues"]
    api.close.assert_called_once()


def test_opt_in_is_required_before_io_or_authentication(tmp_path: Path) -> None:
    factory = Mock()
    with pytest.raises(FoundryError, match="allow-paid"):
        map_visual(tmp_path, SOURCE, CONFIG, allow_paid=False, client_factory=factory)
    factory.assert_not_called()
    assert not (tmp_path / "outputs").exists()


@pytest.mark.parametrize("bad", [box(10, 10, 9, 20), box(0, 0, 1001, 100), box(0, -1, 50, 60)])
def test_invalid_image_coordinates_are_rejected(bad: dict) -> None:
    with pytest.raises(ValidationError):
        NormalizedBox.model_validate(bad)


def test_single_choice_and_other_relationships_are_checked() -> None:
    data = mapped()
    data["items"][0]["kind"] = "single_select"
    data["items"][0]["options"][1]["option_id"] = "advice"
    with pytest.raises(ValidationError):
        VisualPage.model_validate_json(json.dumps(data))


def test_evaluation_measures_geometry_and_does_not_receive_model_ids() -> None:
    proposal = VisualPage.model_validate_json(json.dumps(mapped()))
    reference = MappingReference.model_validate_json(
        json.dumps(
            {
                "application_sha256": "a" * 64,
                "pages": [{"page": 1, "expected": mapped()}],
            }
        )
    )
    result = evaluate_mapping({1: proposal}, reference, {1: (612.0, 792.0)})
    assert result["passed"] is True
    assert result["controls"]["matched"] == result["controls"]["expected"] == 2
    wrong = mapped()
    wrong["items"][0]["options"][0]["box"] = box(800, 800, 820, 820)
    result = evaluate_mapping(
        {1: VisualPage.model_validate_json(json.dumps(wrong))}, reference, {1: (612.0, 792.0)}
    )
    assert result["passed"] is False
    assert result["controls"]["matched"] == 1


def test_reference_is_withheld_and_source_mutation_prevents_publication(blank: Path) -> None:
    reference = {
        "application_sha256": hashlib.sha256((blank / SOURCE).read_bytes()).hexdigest(),
        "pages": [{"page": 1, "expected": mapped()}],
    }
    (blank / "outputs").mkdir()
    (blank / "outputs/reference.json").write_text(json.dumps(reference))
    api = client()
    reply = api.responses.parse.return_value

    def mutate(**kwargs: object) -> Mock:
        assert "expected" not in json.dumps(kwargs["input"])
        (blank / SOURCE).write_bytes(b"changed")
        return reply

    api.responses.parse.side_effect = mutate
    with pytest.raises(ValueError, match="changed"):
        map_visual(
            blank,
            SOURCE,
            CONFIG,
            allow_paid=True,
            pages=(1,),
            reference_path=Path("outputs/reference.json"),
            client_factory=lambda _: api,
        )
    assert list((blank / "outputs").iterdir()) == [blank / "outputs/reference.json"]


@pytest.mark.parametrize("pages", [(0,), (2,), (1, 1), (), (1, 2, 3, 4, 5, 6)])
def test_invalid_page_selection_fails_before_any_call(blank: Path, pages: tuple[int, ...]) -> None:
    factory = Mock()
    with pytest.raises(FoundryError, match="page"):
        map_visual(blank, SOURCE, CONFIG, allow_paid=True, pages=pages, client_factory=factory)
    factory.assert_not_called()


def test_reference_version_is_checked_before_any_call(blank: Path) -> None:
    (blank / "outputs").mkdir()
    (blank / "outputs/reference.json").write_text(
        json.dumps({"application_sha256": "a" * 64, "pages": [{"page": 1, "expected": mapped()}]})
    )
    factory = Mock()
    with pytest.raises(FoundryError, match="version"):
        map_visual(
            blank,
            SOURCE,
            CONFIG,
            allow_paid=True,
            pages=(1,),
            reference_path=Path("outputs/reference.json"),
            client_factory=factory,
        )
    factory.assert_not_called()


def test_unreadable_page_is_explicit_and_keeps_original(blank: Path) -> None:
    api = client({"readable": False, "explanation": "Unreadable fictional scan", "items": []})
    result = map_visual(
        blank, SOURCE, CONFIG, allow_paid=True, pages=(1,), client_factory=lambda _: api
    )
    data = json.loads((result / "visual-map.json").read_text())
    assert "unreadable_page_original_preserved" in data["pages"][0]["issues"]
    assert data["pages"][0]["proposal"]["items"] == []
    assert data["evaluation"] is None


def test_incomplete_model_output_never_publishes_a_successful_map(blank: Path) -> None:
    api = client()
    api.responses.parse.return_value.status = "incomplete"
    with pytest.raises(FoundryError, match="incomplete"):
        map_visual(blank, SOURCE, CONFIG, allow_paid=True, pages=(1,), client_factory=lambda _: api)
    assert not (blank / "outputs").exists()
    api.close.assert_called_once()


def test_duplicate_item_and_invalid_multi_control_are_rejected() -> None:
    data = mapped()
    data["items"].append(data["items"][0])
    with pytest.raises(ValidationError):
        VisualPage.model_validate_json(json.dumps(data))
    data = mapped()
    data["items"][0]["options"][0]["control"] = "radio"
    with pytest.raises(ValidationError):
        VisualPage.model_validate_json(json.dumps(data))


def test_display_point_conversion_uses_actual_page_dimensions() -> None:
    rectangle = NormalizedBox(left=100, top=200, right=300, bottom=400)
    assert rectangle.display_points(792, 612) == pytest.approx((79.2, 122.4, 237.6, 244.8))


@pytest.mark.parametrize(
    "change", ["kind", "missing-option", "missing-other", "extra-option", "extra-item"]
)
def test_reference_evaluation_catches_relationship_and_coverage_errors(change: str) -> None:
    expected = mapped()
    actual = mapped()
    item = actual["items"][0]
    if change == "kind":
        item["kind"] = "single_select"
    elif change == "missing-option":
        item["kind"] = "boolean"
        item["options"].pop()
    elif change == "missing-other":
        item["options"][1]["write_in_region"] = None
    elif change == "extra-option":
        extra = dict(item["options"][0])
        extra["option_id"] = "fabricated"
        item["options"].append(extra)
    else:
        extra = dict(item)
        extra["item_id"] = "fabricated"
        extra["instruction"] = "Invented"
        actual["items"].append(extra)
    reference = MappingReference.model_validate_json(
        json.dumps({"application_sha256": "a" * 64, "pages": [{"page": 1, "expected": expected}]})
    )
    result = evaluate_mapping(
        {1: VisualPage.model_validate_json(json.dumps(actual))}, reference, {1: (612.0, 792.0)}
    )
    assert result["passed"] is False


def test_generated_reference_has_known_scan_and_rotation_geometry(tmp_path: Path) -> None:
    from contextlib import closing

    import pypdfium2 as pdfium

    from examples.visual_mapping_demo import prepare

    root, source, reference_path = prepare(tmp_path)
    reference = MappingReference.model_validate_json((root / reference_path).read_bytes())
    with pdfium.PdfDocument(root / source) as document:
        assert len(document) == 4
        for index in (2, 3):
            with closing(document[index]) as page, closing(page.get_textpage()) as text:
                assert text.count_chars() == 0
        with closing(document[3]) as page:
            assert page.get_rotation() == 90
            assert page.get_size() == (792.0, 612.0)
    first = reference.pages[0].expected.items[0].options[0].box
    rotated = reference.pages[3].expected.items[0].options[0].box
    assert rotated.left == 1000 - first.bottom and rotated.top == first.left


def test_evaluation_does_not_accept_oversized_label_or_narrative_regions() -> None:
    expected = mapped()
    expected["items"].append(
        {
            "item_id": "description",
            "instruction": "Describe services",
            "kind": "narrative",
            "instruction_box": box(50, 400, 700, 450),
            "region": box(50, 480, 900, 700),
            "options": [],
            "explanation": None,
        }
    )
    reference = MappingReference.model_validate_json(
        json.dumps({"application_sha256": "a" * 64, "pages": [{"page": 1, "expected": expected}]})
    )
    actual = json.loads(json.dumps(expected))
    actual["items"][0]["options"][0]["label_box"]["bottom"] = 300
    actual["items"][1]["region"]["top"] = 460
    result = evaluate_mapping(
        {1: VisualPage.model_validate_json(json.dumps(actual))}, reference, {1: (612.0, 792.0)}
    )
    assert result["labels"]["matched"] == 1
    assert result["regions"]["matched"] == 0
    assert result["passed"] is False


def test_thin_answer_regions_are_visible_review_exceptions(blank: Path) -> None:
    data = mapped()
    data["items"].append(
        {
            "item_id": "name",
            "instruction": "Name",
            "kind": "text",
            "instruction_box": box(100, 300, 200, 350),
            "region": box(210, 340, 800, 341),
            "options": [],
            "explanation": None,
        }
    )
    api = client(data)
    result = map_visual(
        blank, SOURCE, CONFIG, allow_paid=True, pages=(1,), client_factory=lambda _: api
    )
    report = json.loads((result / "visual-map.json").read_text())
    assert "some_answer_regions_below_readable_line_height" in report["pages"][0]["issues"]


@pytest.mark.parametrize(
    "evaluated,exit_code", [(None, 1), ({"passed": False}, 1), ({"passed": True}, 0)]
)
def test_cli_distinguishes_unmeasured_failed_and_passed_evaluations(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    evaluated: dict | None,
    exit_code: int,
) -> None:
    from bd_packet_builder import cli

    output = tmp_path / "visual-output"
    output.mkdir()
    (output / "visual-map.json").write_text(json.dumps({"evaluation": evaluated}))
    call = Mock(return_value=output)
    monkeypatch.setattr(cli, "map_visual", call)
    assert (
        cli.main(
            [
                "map-visual",
                "--root",
                str(tmp_path),
                "--source",
                str(SOURCE),
                "--endpoint",
                CONFIG.endpoint,
                "--deployment",
                CONFIG.deployment,
                "--pages",
                "2",
                "4",
                "--allow-paid",
            ]
        )
        == exit_code
    )
    assert call.call_args.kwargs["pages"] == (2, 4)


def test_subset_evaluation_does_not_claim_unscored_questions_are_correct() -> None:
    reference = MappingReference.model_validate_json(
        json.dumps(
            {
                "application_sha256": "a" * 64,
                "pages": [{"page": 1, "exhaustive": False, "expected": mapped()}],
            }
        )
    )
    actual = mapped()
    extra = dict(actual["items"][0])
    extra["item_id"] = "extra"
    extra["instruction"] = "Unscored question"
    actual["items"].append(extra)
    result = evaluate_mapping(
        {1: VisualPage.model_validate_json(json.dumps(actual))}, reference, {1: (612.0, 792.0)}
    )
    assert result["subset_reference_pages"] == [1]
    assert result["unscored_questions"] == 1
    assert result["passed"] is True
