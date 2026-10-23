import json
from datetime import UTC, datetime
from pathlib import Path

import pytest
from pydantic import ValidationError

from bd_packet_builder.contracts import (
    AnswerProposal,
    Requirement,
    check_proposal,
)
from bd_packet_builder.inventory import Inventory
from bd_packet_builder.responses import (
    NarrativeRegion,
    PacketPagination,
    PacketReference,
    plan_narrative,
)


def requirement(kind: str = "single_select") -> Requirement:
    return Requirement.model_validate_json(
        json.dumps(
            {
                "requirement_id": "eligibility",
                "application_sha256": "a" * 64,
                "page": 2,
                "instruction": "Choose one eligibility category.",
                "kind": kind,
                "choices": {
                    "options": [
                        {
                            "option_id": "primary",
                            "label": "Primary dealer",
                            "instruction": "Primary dealer",
                        },
                        {
                            "option_id": "regional",
                            "label": "Regional dealer",
                            "instruction": "Regional dealer meeting all conditions",
                        },
                        {
                            "option_id": "other",
                            "label": "Other",
                            "instruction": "Other ___",
                            "write_in": True,
                        },
                    ],
                },
            }
        )
    )


def proposal(
    ids: list[str], write_ins: list[dict[str, str]] | None = None, kind: str = "single_select"
) -> AnswerProposal:
    return AnswerProposal.model_validate_json(
        json.dumps(
            {
                "requirement_id": "eligibility",
                "outcome": "proposed",
                "value": {"kind": kind, "selected": ids, "write_ins": write_ins or []},
                "confidence": 0.9,
                "citations": [
                    {"source_id": "b" * 64, "page": 1, "start": 0, "end": 4, "quote": "test"}
                ],
            }
        )
    )


def check(tmp_path: Path, req: Requirement, answer: AnswerProposal) -> tuple[str, ...]:
    return check_proposal(tmp_path, Inventory(datetime.now(UTC), (), ()), req, answer).issues


def test_choice_metadata_and_values_roundtrip_without_losing_conditions() -> None:
    req = requirement()
    assert req.choices is not None
    assert req.choices.options[1].instruction == "Regional dealer meeting all conditions"
    assert Requirement.model_validate_json(req.model_dump_json()) == req
    assert proposal(["primary"]).value is not None


@pytest.mark.parametrize(
    "kind,ids",
    [
        ("single_select", []),
        ("single_select", ["primary", "regional"]),
        ("multi_select", ["primary", "primary"]),
    ],
)
def test_selection_cardinality_and_duplicates_rejected(kind: str, ids: list[str]) -> None:
    with pytest.raises(ValidationError):
        proposal(ids, kind=kind)


@pytest.mark.parametrize(
    "ids,write_ins,issue",
    [
        (["unknown"], [], "unknown_choice_option"),
        (["other"], [], "choice_write_in_missing"),
        (
            ["primary"],
            [{"option_id": "other", "text": "unselected"}],
            "choice_write_in_not_selected",
        ),
        (
            ["primary"],
            [{"option_id": "primary", "text": "not allowed"}],
            "choice_write_in_not_allowed",
        ),
    ],
)
def test_choice_relations_are_checked_against_requirement(
    tmp_path: Path,
    ids: list[str],
    write_ins: list[dict[str, str]],
    issue: str,
) -> None:
    assert issue in check(tmp_path, requirement(), proposal(ids, write_ins))


def test_multiple_choices_and_linked_other_have_no_structural_choice_issues(tmp_path: Path) -> None:
    issues = check(
        tmp_path,
        requirement("multi_select"),
        proposal(
            ["primary", "other"],
            [{"option_id": "other", "text": "Synthetic product"}],
            kind="multi_select",
        ),
    )
    assert not any(i.startswith("choice_") or i == "unknown_choice_option" for i in issues)
    # Literal/source checks still reject this artificial citation.
    assert "citation_unresolved" in issues


def test_choice_metadata_is_mandatory_and_unique() -> None:
    data = requirement().model_dump(mode="json")
    for change in ("missing", "duplicate", "wrong-kind"):
        changed = json.loads(json.dumps(data))
        if change == "missing":
            changed["choices"] = None
        elif change == "duplicate":
            changed["choices"]["options"].append(changed["choices"]["options"][0])
        else:
            changed["kind"] = "text"
        with pytest.raises(ValidationError):
            Requirement.model_validate_json(json.dumps(changed))


def pagination() -> PacketPagination:
    return PacketPagination.model_validate_json(
        json.dumps(
            {
                "sections": [
                    {
                        "section_id": "form",
                        "source_sha256": "a" * 64,
                        "page_count": 5,
                        "role": "form",
                    },
                    {
                        "section_id": "supplement",
                        "source_sha256": "c" * 64,
                        "page_count": 2,
                        "role": "supplemental_answers",
                    },
                    {
                        "section_id": "evidence",
                        "source_sha256": "b" * 64,
                        "page_count": 3,
                        "role": "evidence",
                    },
                ],
            }
        )
    )


def region(lines: int = 3, width: float = 200.0) -> NarrativeRegion:
    return NarrativeRegion(
        page=4,
        left=40.0,
        bottom=200.0,
        right=40.0 + width,
        top=200.0 + lines * 14,
        font_size=10.0,
        leading=14.0,
    )


def measure(text: str, size: float) -> float:
    from reportlab.pdfbase.pdfmetrics import stringWidth

    return float(stringWidth(text, "Helvetica", size))


def test_narrative_inline_contains_complete_answer_and_final_evidence_reference() -> None:
    ref = PacketReference(section_id="evidence", page=2)
    result = plan_narrative(
        "Synthetic full answer.",
        "Question 11",
        region(),
        pagination(),
        evidence=(ref,),
        supplement=PacketReference(section_id="supplement", page=1),
        measure=measure,
    )
    assert result.mode == "inline"
    assert "Synthetic full answer." in " ".join(result.inline_lines)
    assert "packet page 9" in " ".join(result.inline_lines)
    assert result.supplement_text is None
    assert result.font_size == 10.0


def test_narrative_overflow_preserves_every_word_and_redirects_to_answer_not_evidence() -> None:
    text = "Long supported fictional narrative. " * 80
    result = plan_narrative(
        text,
        "Question 11",
        region(),
        pagination(),
        evidence=(PacketReference(section_id="evidence", page=2),),
        supplement=PacketReference(section_id="supplement", page=1),
        measure=measure,
    )
    assert result.mode == "supplement"
    assert "packet page 6" in " ".join(result.inline_lines)
    assert result.supplement_text is not None and text.strip() in result.supplement_text
    assert "packet page 9" in result.supplement_text
    assert result.font_size == 10.0


def test_narrative_long_token_is_not_silently_truncated_or_shrunk() -> None:
    text = "x" * 400
    result = plan_narrative(
        text,
        "Question 11",
        region(),
        pagination(),
        evidence=(),
        supplement=PacketReference(section_id="supplement", page=1),
        measure=measure,
    )
    assert result.mode == "supplement"
    assert result.supplement_text is not None and text in result.supplement_text


def test_narrative_exact_capacity_boundary_includes_evidence_lines() -> None:
    exact = NarrativeRegion(page=1, left=0.0, bottom=0.0, right=400.0, top=28.0)
    arguments = {
        "evidence": (PacketReference(section_id="evidence", page=1),),
        "supplement": PacketReference(section_id="supplement", page=1),
        "measure": measure,
    }
    result = plan_narrative("Complete answer.", "Q11", exact, pagination(), **arguments)
    assert result.mode == "inline" and len(result.inline_lines) == 2
    smaller = exact.model_copy(update={"top": 27.99})
    redirected = plan_narrative("Complete answer.", "Q11", smaller, pagination(), **arguments)
    assert redirected.mode == "supplement"


def test_duplicate_write_in_and_boolean_option_values_are_rejected() -> None:
    with pytest.raises(ValidationError):
        proposal(
            ["other"],
            [{"option_id": "other", "text": "one"}, {"option_id": "other", "text": "two"}],
            kind="multi_select",
        )
    with pytest.raises(ValidationError):
        AnswerProposal.model_validate_json(
            json.dumps(
                {
                    **proposal(["primary"]).model_dump(mode="json"),
                    "value": {"kind": "single_select", "selected": [True], "write_ins": []},
                }
            )
        )


def test_invalid_measurement_is_not_treated_as_a_fit() -> None:
    with pytest.raises(ValueError, match="measurement"):
        plan_narrative(
            "Synthetic text",
            "Q11",
            region(),
            pagination(),
            evidence=(),
            supplement=PacketReference(section_id="supplement", page=1),
            measure=lambda text, size: float("nan"),
        )


def test_narrative_redirect_that_does_not_fit_is_explicit_failure() -> None:
    with pytest.raises(ValueError, match="reference"):
        plan_narrative(
            "word " * 300,
            "Question 11",
            region(lines=1, width=10.0),
            pagination(),
            evidence=(),
            supplement=PacketReference(section_id="supplement", page=1),
            measure=measure,
        )


def test_packet_page_references_change_with_order_and_reject_non_submission_sections() -> None:
    pages = pagination()
    assert pages.resolve(PacketReference(section_id="evidence", page=2), role="evidence") == 9
    with pytest.raises(ValueError):
        pages.resolve(PacketReference(section_id="evidence", page=4), role="evidence")
    with pytest.raises(ValueError):
        pages.resolve(PacketReference(section_id="form", page=1), role="evidence")
    data = pages.model_dump(mode="json")
    data["sections"].reverse()
    reordered = PacketPagination.model_validate_json(json.dumps(data))
    assert reordered.resolve(PacketReference(section_id="evidence", page=2), role="evidence") == 2
    data["sections"][0]["role"] = "reviewer_summary"
    with pytest.raises(ValidationError):
        PacketPagination.model_validate_json(json.dumps(data))


@pytest.mark.parametrize(
    "changes",
    [
        {"font_size": 6.0},
        {"leading": 5.0},
        {"right": 30.0},
        {"page": True},
    ],
)
def test_invalid_or_unreadable_narrative_region_rejected(changes: dict[str, object]) -> None:
    with pytest.raises(ValidationError):
        NarrativeRegion.model_validate({**region().model_dump(), **changes})
