import hashlib
import json
from io import BytesIO
from pathlib import Path

import pytest
from PIL import Image
from pypdf import PdfReader, PdfWriter
from reportlab.lib.utils import ImageReader
from reportlab.pdfgen.canvas import Canvas

from bd_packet_builder.form_layout import FormLayoutError, build_form_layout
from bd_packet_builder.layout import validate_layout
from bd_packet_builder.visual import VisualPage

WIDTH, HEIGHT = 612.0, 792.0

# (x, distance of baseline from page top, text) in displayed points.
TEXT = [
    (40, 60, "Firm legal name:"),
    (40, 120, "Select services offered"),
    (60, 145, "Advice"),
    (60, 170, "Other"),
    (40, 210, "Describe the firm's business"),
    (40, 340, "Signature of authorized officer"),
    (40, 400, "Date"),
    (40, 450, "Attach the most recent audited financial statements"),
    (40, 490, "Total net capital ($)"),
    (40, 540, "Is the firm registered with FINRA?"),
    (60, 560, "Yes"),
    (120, 560, "No"),
]


def make_blank(
    pages: list[list[tuple[float, float, str]] | None],
    *,
    rotate: frozenset[int] = frozenset(),
) -> bytes:
    """None draws an image-only page; rotate holds 1-based page numbers."""
    buffer = BytesIO()
    canvas = Canvas(buffer, pagesize=(WIDTH, HEIGHT), invariant=True)
    for lines in pages:
        if lines is None:
            image = Image.new("RGB", (612, 792), "white")
            canvas.drawImage(ImageReader(image), 0, 0, width=WIDTH, height=HEIGHT)
            image.close()
        else:
            for x, baseline, text in lines:
                canvas.drawString(x, HEIGHT - baseline, text)
        canvas.showPage()
    canvas.save()
    if not rotate:
        return buffer.getvalue()
    writer = PdfWriter(clone_from=PdfReader(BytesIO(buffer.getvalue())))
    for number in rotate:
        writer.pages[number - 1].rotate(90)
    out = BytesIO()
    writer.write(out)
    return out.getvalue()


def nbox(left: float, top: float, right: float, bottom: float) -> dict[str, int]:
    """Displayed points (top-left origin) to the model's 0-1000 normalized boxes."""
    return {
        "left": round(left * 1000 / WIDTH),
        "top": round(top * 1000 / HEIGHT),
        "right": round(right * 1000 / WIDTH),
        "bottom": round(bottom * 1000 / HEIGHT),
    }


def item(item_id: str, instruction: str, kind: str, region: dict | None, **extra: object) -> dict:
    return {
        "item_id": item_id,
        "instruction": instruction,
        "kind": kind,
        "instruction_box": nbox(35, 40, 560, 64),
        "region": region,
        "options": extra.pop("options", []),
        "explanation": extra.pop("explanation", None),
    }


def option(
    option_id: str, label: str, box: dict, label_box: dict, write_in: dict | None = None
) -> dict:
    return {
        "option_id": option_id,
        "label": label,
        "instruction": label,
        "control": "checkbox",
        "box": box,
        "label_box": label_box,
        "write_in_region": write_in,
    }


def items() -> dict[str, dict]:
    return {
        "name": item("name", "Firm legal name", "text", nbox(40, 70, 400, 90)),
        "services": item(
            "services",
            "Select services offered",
            "multi_select",
            None,
            options=[
                option("advice", "Advice", nbox(40, 135, 52, 147), nbox(56, 134, 120, 150)),
                option(
                    "other",
                    "Other",
                    nbox(40, 160, 52, 172),
                    nbox(56, 159, 110, 175),
                    nbox(120, 158, 400, 176),
                ),
            ],
        ),
        "business": item(
            "business", "Describe the firm's business", "narrative", nbox(40, 220, 560, 300)
        ),
        "signature": item(
            "signature", "Signature of authorized officer", "signature", nbox(40, 350, 300, 380)
        ),
        "date": item("date", "Date", "signature_date", nbox(40, 405, 200, 425)),
        "audit": item(
            "audit", "Attach the most recent audited financial statements", "attachment", None
        ),
        "capital": item("capital", "Total net capital ($)", "money", nbox(40, 495, 300, 515)),
        "finra": item(
            "finra",
            "Is the firm registered with FINRA?",
            "boolean",
            None,
            options=[
                {
                    **option("yes", "Yes", nbox(40, 550, 52, 562), nbox(56, 549, 90, 565)),
                    "control": "radio",
                },
                {
                    **option("no", "No", nbox(100, 550, 112, 562), nbox(116, 549, 150, 565)),
                    "control": "radio",
                },
            ],
        ),
    }


def page(*selected: dict, readable: bool = True, explanation: str | None = None) -> VisualPage:
    return VisualPage.model_validate_json(
        json.dumps({"readable": readable, "explanation": explanation, "items": list(selected)})
    )


def full_page() -> VisualPage:
    return page(*items().values())


def codes(result: object) -> dict[str | None, set[str]]:
    found: dict[str | None, set[str]] = {}
    for exception in result.exceptions:  # type: ignore[attr-defined]
        found.setdefault(exception.requirement_id, set()).add(exception.code)
    return found


def test_full_page_converts_to_writer_coordinates_and_native_quotations(tmp_path: Path) -> None:
    blank = make_blank([TEXT])
    result = build_form_layout(blank, {1: full_page()})

    assert result.application_sha256 == hashlib.sha256(blank).hexdigest()
    assert result.layout is not None and result.requirements is not None
    assert result.layout.scope == "automatic_visual_mapping_unapproved"
    requirements = {r.requirement_id: r for r in result.requirements.requirements}
    assert set(requirements) == {
        "p1.name",
        "p1.services",
        "p1.business",
        "p1.signature",
        "p1.date",
        "p1.audit",
        "p1.finra",
    }
    assert requirements["p1.name"].instruction == "Firm legal name:"
    assert requirements["p1.finra"].kind == "single_select"
    assert requirements["p1.audit"].kind == "attachment"
    assert requirements["p1.signature"].kind == "signature"
    services = requirements["p1.services"].choices
    assert services is not None
    assert [(o.option_id, o.label, o.write_in) for o in services.options] == [
        ("advice", "Advice", False),
        ("other", "Other", True),
    ]
    mapped = {m.requirement.requirement_id: m for m in result.layout.responses}
    assert set(mapped) == {"p1.name", "p1.services", "p1.business", "p1.finra"}
    region = mapped["p1.name"].text_region
    assert region is not None
    assert region.page == 1
    assert region.left == pytest.approx(40, abs=1)
    assert region.right == pytest.approx(400, abs=1)
    assert region.top == pytest.approx(HEIGHT - 70, abs=1)
    assert region.bottom == pytest.approx(HEIGHT - 90, abs=1)
    assert mapped["p1.business"].narrative_region is not None
    other = next(o for o in mapped["p1.services"].options if o.option_id == "other")
    assert other.write_in_region is not None
    assert other.label_quote == "Other"
    assert len(result.protected_regions) == 2
    assert sorted(p.top for p in result.protected_regions) == [
        pytest.approx(HEIGHT - 405, abs=1),
        pytest.approx(HEIGHT - 350, abs=1),
    ]
    assert codes(result) == {"p1.capital": {"financial_units_unresolved"}}

    source = Path("bd_agreements/Blank/synthetic.pdf")
    (tmp_path / source.parent).mkdir(parents=True)
    (tmp_path / source).write_bytes(blank)
    validate_layout(tmp_path, source, result.layout)


def test_case_whitespace_and_trailing_punctuation_still_anchor_exact_native_text() -> None:
    selected = items()["name"]
    selected["instruction"] = "  firm   LEGAL name "
    result = build_form_layout(make_blank([TEXT]), {1: page(selected)})

    assert result.requirements is not None
    assert result.requirements.requirements[0].instruction == "Firm legal name:"
    assert result.layout is not None
    assert not result.exceptions


def test_paraphrased_instruction_is_kept_as_requirement_but_not_placed() -> None:
    selected = items()["name"]
    selected["instruction"] = "Legal name of the firm"
    result = build_form_layout(make_blank([TEXT]), {1: page(selected)})

    assert result.requirements is not None
    assert result.requirements.requirements[0].instruction == "Legal name of the firm"
    assert result.layout is None
    assert codes(result) == {"p1.name": {"placement_not_native_anchored"}}


def test_label_box_that_does_not_contain_its_label_is_not_placed() -> None:
    selected = items()["services"]
    selected["options"][0]["label_box"] = nbox(300, 134, 360, 150)
    result = build_form_layout(make_blank([TEXT]), {1: page(selected)})

    assert result.layout is None
    assert codes(result) == {"p1.services": {"placement_not_native_anchored"}}


def test_answer_region_covering_issuer_text_is_not_placed() -> None:
    selected = items()["name"]
    selected["region"] = nbox(40, 50, 400, 90)
    result = build_form_layout(make_blank([TEXT]), {1: page(selected)})

    assert result.layout is None
    assert codes(result) == {"p1.name": {"answer_region_overlaps_issuer_text"}}


def test_overlapping_answer_regions_exclude_both_items() -> None:
    first = items()["business"]
    second = item("notes", "Describe the firm's business", "narrative", nbox(300, 250, 560, 320))
    keep = items()["name"]
    result = build_form_layout(make_blank([TEXT]), {1: page(first, second, keep)})

    assert result.layout is not None
    assert [m.requirement.requirement_id for m in result.layout.responses] == ["p1.name"]
    assert codes(result) == {
        "p1.business": {"placement_conflict"},
        "p1.notes": {"placement_conflict"},
    }


def test_answer_region_overlapping_signing_area_is_not_placed() -> None:
    signature = items()["signature"]
    answer = item("name", "Firm legal name", "text", nbox(250, 360, 500, 380))
    result = build_form_layout(make_blank([TEXT]), {1: page(answer, signature)})

    assert result.layout is None
    assert len(result.protected_regions) == 1
    assert codes(result) == {"p1.name": {"placement_conflict"}}


def test_region_below_readable_line_height_is_not_placed() -> None:
    selected = items()["name"]
    selected["region"] = nbox(40, 70, 400, 79)
    result = build_form_layout(make_blank([TEXT]), {1: page(selected)})

    assert result.layout is None
    assert codes(result) == {"p1.name": {"answer_region_too_small"}}


def test_single_line_region_uses_minimum_readable_leading() -> None:
    selected = items()["name"]
    selected["region"] = nbox(40, 70, 400, 83)
    result = build_form_layout(make_blank([TEXT]), {1: page(selected)})

    assert result.layout is not None
    region = result.layout.responses[0].text_region
    assert region is not None
    assert region.font_size == 10
    assert region.leading == 12


def test_missing_writable_region_is_an_exception() -> None:
    selected = items()["name"]
    selected["region"] = None
    selected["explanation"] = "No visible answer line."
    result = build_form_layout(make_blank([TEXT]), {1: page(selected)})

    assert result.requirements is not None
    assert result.layout is None
    assert codes(result) == {"p1.name": {"no_writable_region"}}


def test_single_attestation_checkbox_is_kept_without_placement() -> None:
    selected = item(
        "attest", "Is the firm registered with FINRA?", "boolean", nbox(40, 550, 52, 562)
    )
    result = build_form_layout(make_blank([TEXT]), {1: page(selected)})

    assert result.requirements is not None
    assert result.requirements.requirements[0].kind == "boolean"
    assert result.layout is None
    assert codes(result) == {"p1.attest": {"boolean_placement_unsupported"}}


def test_signing_item_without_location_is_still_reported() -> None:
    selected = items()["signature"]
    selected["region"] = None
    selected["explanation"] = "Signature line not visible."
    result = build_form_layout(make_blank([TEXT]), {1: page(selected)})

    assert result.requirements is not None
    assert result.requirements.requirements[0].kind == "signature"
    assert result.protected_regions == ()
    assert codes(result) == {"p1.signature": {"signing_location_unmapped"}}


def test_uninterpreted_unreadable_image_only_and_rotated_pages_are_explicit() -> None:
    blank = make_blank([TEXT, TEXT, None, TEXT, TEXT], rotate=frozenset({4}))
    result = build_form_layout(
        blank,
        {
            1: full_page(),
            3: page(items()["name"]),
            4: page(items()["name"]),
            5: page(readable=False, explanation="Page is illegible."),
        },
    )

    found = codes(result)
    assert found[None] == {
        "page_not_interpreted",
        "image_only_placement_unverified",
        "page_geometry_unsupported",
        "unreadable_page",
    }
    assert result.layout is not None
    assert {m.requirement.page for m in result.layout.responses} == {1}
    assert result.requirements is not None
    assert {"p3.name", "p4.name"} <= {r.requirement_id for r in result.requirements.requirements}
    pages = sorted(
        (e.message for e in result.exceptions if e.requirement_id is None),
    )
    assert any("page 2" in m for m in pages)
    assert any("page 5" in m for m in pages)


def test_nothing_mappable_returns_no_requirements_or_layout() -> None:
    result = build_form_layout(
        make_blank([TEXT]), {1: page(readable=False, explanation="Illegible.")}
    )

    assert result.requirements is None
    assert result.layout is None
    assert codes(result) == {None: {"unreadable_page"}}


@pytest.mark.parametrize("number", [0, 2])
def test_proposal_for_page_outside_blank_is_rejected(number: int) -> None:
    with pytest.raises(FormLayoutError, match="page"):
        build_form_layout(make_blank([TEXT]), {number: full_page()})


@pytest.mark.parametrize("blank", [b"", b"not a pdf", b"%PDF-1.7\ntruncated"])
def test_unreadable_blank_is_a_technical_error(blank: bytes) -> None:
    with pytest.raises(FormLayoutError):
        build_form_layout(blank, {1: full_page()})


def test_encrypted_blank_is_rejected() -> None:
    writer = PdfWriter(clone_from=PdfReader(BytesIO(make_blank([TEXT]))))
    writer.encrypt("secret")
    out = BytesIO()
    writer.write(out)
    with pytest.raises(FormLayoutError, match="ncrypted"):
        build_form_layout(out.getvalue(), {1: full_page()})


def test_output_is_deterministic_and_serializable_as_run_artifact() -> None:
    blank = make_blank([TEXT])
    first = build_form_layout(blank, {1: full_page()})
    second = build_form_layout(blank, {1: full_page()})

    assert first.model_dump_json() == second.model_dump_json()
    restored = type(first).model_validate_json(first.model_dump_json())
    assert restored == first
    payload = json.loads(first.model_dump_json())
    assert payload["status"] == "automatic_mapping_unapproved_no_answers"
    assert all("Firm legal name" not in e["message"] for e in payload["exceptions"])
