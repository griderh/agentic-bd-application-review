import hashlib
import json
from io import BytesIO

import pytest
from reportlab.pdfgen.canvas import Canvas

from bd_packet_builder.contracts import Requirement
from bd_packet_builder.historical_context import (
    question_text_agrees,
    verified_question_requirements,
)
from bd_packet_builder.layout import MappedResponse

QUESTION = (
    "6. Has your firm ever been temporarily closed or prohibited from trading "
    "due to net capital inadequacy?"
)


@pytest.mark.parametrize(
    ("ocr", "accepted"),
    [
        (QUESTION, True),
        (QUESTION.replace("temporarily", "emp"), True),
        (QUESTION.replace("temporarily", "tempor arily"), True),
        (QUESTION.replace("?", "").replace("6. ", "6) "), True),
        (QUESTION.replace("ever", "never"), False),
        (QUESTION.replace("ever", "not ever"), False),
        (QUESTION.replace("or", "and"), False),
        (QUESTION.replace("temporarily", "permanently"), False),
        (QUESTION.replace("prohibited", "permitted"), False),
        (QUESTION.replace("temporarily", ""), False),
        (QUESTION.replace("temporarily", "emp").replace("inadequacy", "adequacy"), False),
        (QUESTION + " Only during the last five years.", False),
    ],
)
def test_question_alignment_is_bounded_not_a_percentage_vote(ocr, accepted):
    assert question_text_agrees(QUESTION, ocr, QUESTION) is accepted


@pytest.mark.parametrize(
    ("image", "ocr"),
    [
        ("Has the firm been closed for 10 days?", "Has the firm been closed for 1 days?"),
        ("Has the firm been closed for five years?", "Has the firm been closed for four years?"),
        ("Has capital fallen below -100 dollars?", "Has capital fallen below 100 dollars?"),
        ("Is capital > $10 million?", "Is capital < $10 million?"),
        ("Is capital 10.5 million?", "Is capital 105 million?"),
        (
            "Has the firm been closed since January 2020?",
            "Has the firm been closed since June 2020?",
        ),
        (
            QUESTION.replace("your firm", "Example Holdings"),
            QUESTION.replace("your firm", "amp Holdings"),
        ),
        (
            QUESTION.replace("temporarily", "unregistered"),
            QUESTION.replace("temporarily", "registered"),
        ),
        ("Is temporarily closed?", "Is emp closed?"),
    ],
)
def test_protected_values_entities_periods_and_short_questions_do_not_fuzz(image, ocr):
    assert not question_text_agrees(image, ocr, image)


def test_image_must_match_the_blank_question_not_merely_ocr():
    assert not question_text_agrees(
        QUESTION, QUESTION.replace("temporarily", "emp"), QUESTION + " Why?"
    )


def test_question_number_is_not_a_business_value():
    assert question_text_agrees(
        QUESTION, QUESTION.replace("temporarily", "emp"), QUESTION.replace("6.", "9.")
    )


@pytest.mark.parametrize(
    ("question", "whole", "fragment"),
    [
        (
            "Has your organization previously experienced an interruption of securities "
            "settlement services due to operational difficulties?",
            "interruption",
            "rupt",
        ),
        (
            "Does the organization provide independently maintained supporting documentation "
            "for all account opening requirements?",
            "documentation",
            "ment",
        ),
    ],
)
def test_word_fragment_alignment_is_not_specific_to_one_form(question, whole, fragment):
    assert question_text_agrees(question, question.replace(whole, fragment), question)


@pytest.mark.parametrize("change", ["none", "hash", "page", "invented", "duplicate"])
def test_blank_anchor_requires_unique_native_text_bound_to_exact_application(change):
    data = BytesIO()
    canvas = Canvas(data, pagesize=(800, 600), invariant=True)
    canvas.setFont("Helvetica", 8)
    canvas.drawString(20, 550, QUESTION)
    if change == "duplicate":
        canvas.drawString(20, 500, QUESTION)
    canvas.save()
    blank = data.getvalue()
    requirement = Requirement(
        requirement_id="q6",
        application_sha256="a" * 64 if change == "hash" else hashlib.sha256(blank).hexdigest(),
        page=2 if change == "page" else 1,
        instruction=QUESTION + " Why?" if change == "invented" else QUESTION,
        kind="boolean",
    )
    assert verified_question_requirements(blank, (requirement,)) == (
        (requirement,) if change == "none" else ()
    )


def repeated_choice_blank():
    data = BytesIO()
    canvas = Canvas(data, pagesize=(612, 792), invariant=True)
    instruction = "May this representative trade securities?"
    for role, y in (("Primary representative", 600), ("Backup representative", 300)):
        canvas.drawString(40, y + 50, role)
        canvas.drawString(40, y, instruction)
        for label, x in (("Yes", 450), ("No", 500)):
            canvas.drawString(x, y, label)
            canvas.rect(x + 25, y - 2, 10, 10)
    canvas.save()
    blank = data.getvalue()
    mappings = []
    for index, y in enumerate((600, 300)):

        def region(left, bottom, right, top):
            return dict(
                page=1, left=float(left), bottom=float(bottom), right=float(right), top=float(top)
            )

        mappings.append(
            MappedResponse.model_validate_json(
                json.dumps(
                    {
                        "requirement": {
                            "requirement_id": f"field-{index}",
                            "application_sha256": hashlib.sha256(blank).hexdigest(),
                            "page": 1,
                            "instruction": instruction,
                            "kind": "single_select",
                            "choices": {
                                "options": [
                                    {
                                        "option_id": label.lower(),
                                        "label": label,
                                        "instruction": label,
                                    }
                                    for label in ("Yes", "No")
                                ]
                            },
                        },
                        "options": [
                            {
                                "option_id": label.lower(),
                                "control": "checkbox",
                                "label_quote": label,
                                "label_box": region(x, y - 4, x + 23, y + 12),
                                "box": region(x + 25, y - 2, x + 35, y + 8),
                            }
                            for label, x in (("Yes", 450), ("No", 500))
                        ],
                    }
                )
            )
        )
    return blank, tuple(m.requirement for m in mappings), tuple(mappings)


@pytest.mark.parametrize(
    "change",
    [
        "none",
        "reverse_order",
        "missing",
        "duplicate",
        "same_row",
        "overlap",
        "labels",
        "hash",
        "page",
        "wording",
        "outside",
    ],
)
def test_repeated_questions_require_complete_distinct_native_mapped_instances(change):
    blank, requirements, mappings = repeated_choice_blank()
    if change == "reverse_order":
        mappings = tuple(reversed(mappings))
    elif change == "missing":
        mappings = mappings[:1]
    elif change == "duplicate":
        mappings = (*mappings, mappings[0])
    elif change == "same_row":
        mappings = (mappings[0], mappings[1].model_copy(update={"options": mappings[0].options}))
    elif change == "overlap":
        mappings = (
            mappings[0].model_copy(
                update={
                    "options": tuple(
                        p.model_copy(
                            update={"label_box": p.label_box.model_copy(update={"bottom": 290.0})}
                        )
                        for p in mappings[0].options
                    )
                }
            ),
            mappings[1],
        )
    elif change == "labels":
        mappings = (
            mappings[0].model_copy(
                update={
                    "options": tuple(
                        p.model_copy(update={"label_quote": "Unprinted"})
                        for p in mappings[0].options
                    )
                }
            ),
            mappings[1],
        )
    elif change in ("hash", "page", "wording"):
        update = {
            "hash": {"application_sha256": "0" * 64},
            "page": {"page": 2},
            "wording": {"instruction": "May this representative never trade securities?"},
        }[change]
        requirements = tuple(r.model_copy(update=update) for r in requirements)
    elif change == "outside":
        mappings = (
            mappings[0].model_copy(
                update={
                    "options": tuple(
                        p.model_copy(update={"box": p.box.model_copy(update={"right": 700.0})})
                        for p in mappings[0].options
                    )
                }
            ),
            mappings[1],
        )
    assert verified_question_requirements(blank, requirements, mappings=mappings) == (
        requirements if change in ("none", "reverse_order") else ()
    )
