import json

import pytest
from pydantic import ValidationError

from bd_packet_builder.representatives import RepresentativeBioRequest


@pytest.mark.parametrize(
    "changes",
    [
        {"person": "Avery Example"},
        {"role": " "},
        {"requirement_ids": ["name", "name"]},
        {"requirement_ids": ["other"]},
        {"role_requirement_id": 1},
    ],
)
def test_bio_request_rejects_malformed_or_unbound_identity(changes):
    request = {
        "role_requirement_id": "name",
        "requirement_ids": ["name"],
        "role": "Primary representative",
        **changes,
    }
    with pytest.raises(ValidationError):
        RepresentativeBioRequest.model_validate_json(json.dumps(request))


@pytest.mark.parametrize(
    "changes",
    [
        {"field_requirements": [{"requirement_id": "name", "field": "title"}]},
        {"field_requirements": [{"requirement_id": "other", "field": "title"}]},
        {
            "field_requirements": [
                {"requirement_id": "title", "field": "title"},
                {"requirement_id": "title", "field": "email_address"},
            ]
        },
        {"field_requirements": [{"requirement_id": "title", "field": "fax"}]},
    ],
)
def test_bio_field_mapping_must_name_distinct_related_requirements(changes):
    request = {
        "role_requirement_id": "name",
        "requirement_ids": ["name", "title"],
        "role": "Primary representative",
        **changes,
    }
    with pytest.raises(ValidationError):
        RepresentativeBioRequest.model_validate_json(json.dumps(request))


PERSON = "Avery Example"
CARD = (
    "Professional Experience\nDirector\nExample Securities\n"
    "AVERY EXAMPLE\nAvery Example\nDirector\nHead of Synthetic Sales\n"
    "(555) 010-0100\navery@example.test\n"
    "Avery Example is a synthetic employee used for offline tests.\n"
)


def test_bio_contact_card_is_extracted_with_exact_line_offsets():
    from bd_packet_builder.representatives import extract_contact_card

    card, status = extract_contact_card(CARD, PERSON)
    assert status == "extracted"
    assert card is not None
    assert [(line.kind, line.text) for line in card] == [
        ("title", "Director"),
        ("title", "Head of Synthetic Sales"),
        ("telephone", "(555) 010-0100"),
        ("email_address", "avery@example.test"),
    ]
    assert all(CARD[line.start : line.end] == line.text for line in card)


@pytest.mark.parametrize(
    ("text", "status"),
    [
        ("Avery Example is a Director of Synthetic Sales.\n(555) 010-0100\n", "not_found"),
        ("AVERY EXAMPLE\nDirector\nAvery Example joined in 2020.\n", "not_found"),
        ("Avery Example\nDirector\nOne\nTwo\nThree\n(555) 010-0100\n", "not_found"),
        (
            "Avery Example\nDirector\n(555) 010-0100\n\nAvery Example\nPartner\n(555) 010-0100\n",
            "ambiguous",
        ),
        (
            "Avery Example\nDirector\n(555) 010-0100\n\nAvery Example\nDirector\n(555) 010-0100\n",
            "extracted",
        ),
        ("Avery Examples\nDirector\n(555) 010-0100\n", "not_found"),
    ],
)
def test_contact_card_requires_one_structural_name_title_contact_block(text, status):
    from bd_packet_builder.representatives import extract_contact_card

    assert extract_contact_card(text, PERSON)[1] == status


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("(214) 555-0142", [("2145550142", "unspecified")]),
        ("214.555.0142", [("2145550142", "unspecified")]),
        ("+1 214-555-0142", [("2145550142", "unspecified")]),
        ("w214-555-0142,c214-555-0199", [("2145550142", "work"), ("2145550199", "mobile")]),
        ("Office: 214-555-0142 ext. 12", [("2145550142x12", "work")]),
        (
            "Mobile 214 555 0199; Fax 214-555-0100",
            [("2145550199", "mobile"), ("2145550100", "fax")],
        ),
        ("CRD #1234567", []),
    ],
)
def test_phone_comparison_normalizes_format_but_keeps_extensions_and_types(text, expected):
    from bd_packet_builder.representatives import phone_numbers

    assert [(p.key, p.kind) for p in phone_numbers(text)] == expected


SOURCE = "a" * 64


def resolution(fields, text=CARD, status="selected"):
    from bd_packet_builder.contracts import Citation
    from bd_packet_builder.representatives import (
        BioProfile,
        RepresentativeBioResolution,
        extract_contact_card,
    )

    card, card_status = extract_contact_card(text, PERSON)
    start, end = (card[0].start, card[-1].end) if card else (0, 1)
    request = {
        "role_requirement_id": "name",
        "requirement_ids": ["name", *(f for f, _ in fields)],
        "role": "Primary representative",
        "person": PERSON,
        "assignment": {"source_id": "b" * 64, "page": 1, "start": 0, "end": 1, "quote": "x"},
        "field_requirements": [{"requirement_id": r, "field": f} for r, f in fields],
    }
    profile = (
        BioProfile(
            status=card_status,
            source_id=SOURCE,
            page=1 if card else None,
            citation=Citation(source_id=SOURCE, page=1, start=start, end=end, quote=text[start:end])
            if card
            else None,
            lines=card or (),
        )
        if status == "selected"
        else None
    )
    raw = RepresentativeBioResolution.model_validate_json(
        json.dumps(
            {
                "request": request,
                "status": status,
                "assignment_status": "explicit_source_assignment",
                "selected_source_id": SOURCE if status == "selected" else None,
                "candidates": [
                    {
                        "source_id": SOURCE,
                        "source_sha256": "c" * 64,
                        "identity": {
                            "source_id": SOURCE,
                            "page": 1,
                            "start": 0,
                            "end": 1,
                            "quote": "x",
                        },
                    }
                ],
            }
        )
    )
    return raw.model_copy(update={"profile": profile})


def proposal(rid, value=None, outcome="proposed"):
    from bd_packet_builder.contracts import AnswerProposal

    if value is None:
        return AnswerProposal(requirement_id=rid, outcome="missing_evidence", explanation="none")
    return AnswerProposal.model_validate_json(
        json.dumps(
            {
                "requirement_id": rid,
                "outcome": outcome,
                "value": {"kind": "text", "value": value},
                "citations": [
                    {
                        "source_id": "d" * 64,
                        "page": 1,
                        "start": 0,
                        "end": len(value),
                        "quote": value,
                    }
                ],
                "confidence": 0.9,
            }
        )
    )


def reconcile(proposals, resolutions):
    from bd_packet_builder.representatives import reconcile_representative_fields

    answers, records = reconcile_representative_fields(tuple(proposals), tuple(resolutions))
    return {a.requirement_id: a for a in answers}, {r.requirement_id: r for r in records}


@pytest.mark.parametrize(
    ("prior", "decision", "different"),
    [
        (None, "bio_value_used", False),
        ("Director, Head of Synthetic Sales", "answer_kept_bio_confirmed", False),
        ("Director - Head of Synthetic Sales", "bio_value_used", False),
        ("Director-Institutional Synthetic Sales", "bio_value_used", True),
    ],
)
def test_bio_title_takes_precedence_and_reports_meaningful_history_differences(
    prior, decision, different
):
    answers, records = reconcile([proposal("title", prior)], [resolution([("title", "title")])])
    answer = answers["title"]
    assert answer.outcome == "proposed"
    assert answer.value.value == "Director, Head of Synthetic Sales"
    record = records["title"]
    assert record.decision == decision
    assert record.meaningful_difference is different
    assert record.prior_value == prior
    if decision == "bio_value_used":
        assert answer.citations[0].source_id == SOURCE
        assert answer.citations[0].quote == "Director\nHead of Synthetic Sales"
        assert answer.historical_basis is None


@pytest.mark.parametrize(
    ("prior", "decision", "value", "confirmed", "historical_only", "different"),
    [
        (None, "bio_value_used", "(555) 010-0100", (), (), False),
        ("555.010.0100", "answer_kept_bio_confirmed", "555.010.0100", ("555-010-0100",), (), False),
        (
            "w555-010-0100,c555-010-0199",
            "answer_kept_bio_confirmed",
            "w555-010-0100,c555-010-0199",
            ("555-010-0100",),
            ("555-010-0199 (mobile)",),
            False,
        ),
        ("555-010-0177", "bio_value_used", "(555) 010-0100", (), (), True),
        ("555-010-0100 x12", "bio_value_used", "(555) 010-0100", (), (), True),
    ],
)
def test_telephones_are_compared_number_by_number_without_treating_absence_as_conflict(
    prior, decision, value, confirmed, historical_only, different
):
    answers, records = reconcile([proposal("phone", prior)], [resolution([("phone", "telephone")])])
    assert answers["phone"].value.value == value
    record = records["phone"]
    assert (record.decision, record.confirmed, record.historical_only) == (
        decision,
        confirmed,
        historical_only,
    )
    assert record.meaningful_difference is different


@pytest.mark.parametrize(
    ("prior", "decision", "value", "different"),
    [
        ("AVERY@Example.TEST", "answer_kept_bio_confirmed", "AVERY@Example.TEST", False),
        ("avery@example.test", "answer_kept_bio_confirmed", "avery@example.test", False),
        ("avery.example@example.test", "bio_value_used", "avery@example.test", True),
        ("avery@exmaple.test", "bio_value_used", "avery@example.test", True),
    ],
)
def test_email_is_exact_case_insensitive_never_fuzzy(prior, decision, value, different):
    answers, records = reconcile(
        [proposal("email", prior)], [resolution([("email", "email_address")])]
    )
    assert answers["email"].value.value == value
    assert records["email"].decision == decision
    assert records["email"].meaningful_difference is different


def test_unavailable_bio_values_leave_answers_unchanged_and_visible():
    text = "Avery Example\nDirector\navery@example.test\n"
    prior = proposal("phone", "555-010-0177")
    answers, records = reconcile(
        [prior, proposal("title")],
        [resolution([("phone", "telephone"), ("title", "title")], text=text)],
    )
    assert answers["phone"] == prior
    assert records["phone"].decision == "bio_value_unavailable"
    assert answers["title"].value.value == "Director"


@pytest.mark.parametrize("status", ["ambiguous_bio", "missing_bio", "bio_review_required"])
def test_unselected_bios_never_support_answers(status):
    prior = proposal("title", "Historical Title")
    answers, records = reconcile([prior], [resolution([("title", "title")], status=status)])
    assert answers["title"] == prior
    assert records["title"].decision == "bio_value_unavailable"
