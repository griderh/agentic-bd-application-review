from io import BytesIO

import pytest
from PIL import Image, ImageDraw

from bd_packet_builder.historical_controls import inspect_control
from bd_packet_builder.visual import NormalizedBox


def image(state: str) -> bytes:
    canvas = Image.new("RGB", (1000, 1000), "white")
    draw = ImageDraw.Draw(canvas)
    draw.rectangle((200, 200, 239, 239), outline="black", width=2)
    if state == "selected":
        draw.line((206, 206, 233, 233), fill="black", width=3)
        draw.line((206, 233, 233, 206), fill="black", width=3)
    if state == "ambiguous":
        draw.point((217, 217), fill="black")
        draw.line((217, 217, 221, 217), fill="black", width=2)
    if state == "overhanging":
        draw.line((201, 219, 213, 237, 252, 182), fill="black", width=3)
    if state == "large_check":
        draw.line((201, 202, 219, 237, 259, 177), fill="black", width=5)
    stream = BytesIO()
    canvas.save(stream, format="PNG")
    return stream.getvalue()


@pytest.mark.parametrize("state", ["selected", "unselected"])
@pytest.mark.parametrize("shift", [-5, 0, 5])
def test_control_state_comes_from_pixels_not_ocr_or_model(state, shift):
    result = inspect_control(
        image(state),
        NormalizedBox(left=200 + shift, top=200 + shift, right=240 + shift, bottom=240 + shift),
    )
    assert result.state == state
    assert result.pixel_box == (200, 200, 240, 240)


@pytest.mark.parametrize("state", ["selected", "unselected"])
@pytest.mark.parametrize("scale", [1.5, 1.8])
def test_model_box_can_include_whitespace_above_and_beside_control(state, scale):
    canvas = Image.new("RGB", (1000, 1000), "white")
    draw = ImageDraw.Draw(canvas)
    draw.rectangle((200, 200, 223, 223), outline="black", width=2)
    if state == "selected":
        draw.line((204, 204, 219, 219), fill="black", width=3)
        draw.line((204, 219, 219, 204), fill="black", width=3)
    stream = BytesIO()
    canvas.save(stream, format="PNG")
    size = 24 * scale
    result = inspect_control(
        stream.getvalue(),
        NormalizedBox(left=195, top=int(224 - size), right=int(195 + size), bottom=224),
    )
    assert result.state == state
    assert result.pixel_box == (200, 200, 224, 224)


def test_broad_hint_with_two_nearby_controls_is_not_resolved_by_picking_one():
    canvas = Image.new("RGB", (1000, 1000), "white")
    draw = ImageDraw.Draw(canvas)
    for x in (200, 230):
        draw.rectangle((x, 200, x + 23, 223), outline="black", width=2)
    stream = BytesIO()
    canvas.save(stream, format="PNG")
    with pytest.raises(ValueError, match="control_outline_not_resolved"):
        inspect_control(stream.getvalue(), NormalizedBox(left=190, top=185, right=250, bottom=240))


def test_unboxed_check_arms_are_measured_against_mark_not_whitespace_in_hint():
    canvas = Image.new("RGB", (1000, 1000), "white")
    ImageDraw.Draw(canvas).line([(200, 218), (222, 226), (260, 183)], fill="black", width=3)
    stream = BytesIO()
    canvas.save(stream, format="PNG")
    assert (
        inspect_control(
            stream.getvalue(), NormalizedBox(left=200, top=190, right=260, bottom=250)
        ).state
        == "selected"
    )


def test_faint_or_partial_mark_is_ambiguous_not_unselected():
    result = inspect_control(
        image("ambiguous"), NormalizedBox(left=200, top=200, right=240, bottom=240)
    )
    assert result.state == "ambiguous"


def test_missing_outline_is_an_extraction_failure_not_missing_business_evidence():
    with pytest.raises(ValueError, match="control_outline_not_resolved"):
        inspect_control(image("selected"), NormalizedBox(left=500, top=500, right=540, bottom=540))


def test_oversized_region_cannot_convert_text_into_a_checkbox():
    with pytest.raises(ValueError, match="control_geometry_invalid"):
        inspect_control(image("selected"), NormalizedBox(left=0, top=0, right=900, bottom=900))


@pytest.mark.parametrize("state", ["overhanging", "large_check"])
def test_checkmark_can_extend_outside_its_printed_outline(state):
    result = inspect_control(image(state), NormalizedBox(left=200, top=200, right=240, bottom=240))
    assert result.state == "selected"
    assert result.pixel_box == (200, 200, 240, 240)


def test_tiny_resolved_outline_is_an_explicit_extraction_failure():
    canvas = Image.new("RGB", (1000, 1000), "white")
    ImageDraw.Draw(canvas).rectangle((200, 200, 203, 203), outline="black", width=1)
    stream = BytesIO()
    canvas.save(stream, format="PNG")
    with pytest.raises(ValueError, match="control_outline_not_resolved"):
        inspect_control(stream.getvalue(), NormalizedBox(left=200, top=200, right=206, bottom=206))


@pytest.mark.parametrize("selected", [False, True])
def test_circular_selection_outlines_are_supported(selected):
    canvas = Image.new("RGB", (1000, 1000), "white")
    draw = ImageDraw.Draw(canvas)
    draw.ellipse((200, 200, 239, 239), outline="black", width=2)
    if selected:
        draw.line((205, 215, 217, 234, 248, 190), fill="black", width=3)
    stream = BytesIO()
    canvas.save(stream, format="PNG")
    result = inspect_control(
        stream.getvalue(), NormalizedBox(left=200, top=200, right=240, bottom=240)
    )
    assert result.state == ("selected" if selected else "unselected")


@pytest.mark.parametrize("scale", [1, 2])
@pytest.mark.parametrize("shape", ["check", "slash", "cross", "dash", "dot", "empty"])
def test_outline_free_marks_require_a_resolved_check_shape(scale, shape):
    canvas = Image.new("RGB", (1000 * scale, 1000 * scale), "white")
    draw = ImageDraw.Draw(canvas)
    points = {
        "check": [(198, 210), (216, 236), (260, 165)],
        "slash": [(200, 237), (260, 165)],
        "cross": [(200, 200), (238, 238), (238, 200), (200, 238)],
        "dash": [(200, 218), (238, 218)],
        "dot": [(218, 218), (220, 218)],
        "empty": [],
    }[shape]
    if points:
        draw.line([(x * scale, y * scale) for x, y in points], fill="black", width=4 * scale)
    stream = BytesIO()
    canvas.save(stream, format="PNG")
    box = NormalizedBox(left=200, top=200, right=240, bottom=240)
    if shape == "check":
        assert inspect_control(stream.getvalue(), box).state == "selected"
    else:
        with pytest.raises(ValueError, match="control_outline_not_resolved"):
            inspect_control(stream.getvalue(), box)
