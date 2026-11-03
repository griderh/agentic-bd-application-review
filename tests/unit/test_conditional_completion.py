import pytest

from bd_packet_builder.contracts import AnswerProposal, BooleanValue, Citation, Requirement
from bd_packet_builder.draft import conditional_applicability


@pytest.mark.parametrize(
    "answer,accepted,expected",
    [
        (False, True, False),
        (True, True, True),
        (False, False, None),
    ],
)
def test_conditional_explanation_uses_written_parent_not_raw_candidate(answer, accepted, expected):
    parent = Requirement(
        requirement_id="parent",
        application_sha256="a" * 64,
        page=1,
        instruction="Any reportable events?",
        kind="boolean",
    )
    child = Requirement(
        requirement_id="child",
        application_sha256="a" * 64,
        page=1,
        instruction="If yes, please explain:",
        kind="narrative",
    )
    proposal = AnswerProposal(
        requirement_id="parent",
        outcome="proposed",
        value=BooleanValue(kind="boolean", value=answer),
        confidence=1.0,
        citations=(Citation(source_id="b" * 64, page=1, start=0, end=2, quote="No"),),
    )
    disposition = conditional_applicability(
        (parent, child), child, {"parent": proposal} if accepted else {}
    )
    assert disposition is not None
    assert disposition.parent_id == "parent"
    assert disposition.applicable is expected


def test_repeated_followups_do_not_inherit_the_wrong_question_or_page():
    parent = Requirement(
        requirement_id="parent",
        application_sha256="a" * 64,
        page=1,
        instruction="Any reportable events?",
        kind="boolean",
    )
    child = Requirement(
        requirement_id="child",
        application_sha256="a" * 64,
        page=2,
        instruction="If yes, please explain:",
        kind="narrative",
    )
    assert conditional_applicability((parent, child), child, {}) is None
    same = child.model_copy(update={"page": 1})
    sibling = same.model_copy(update={"requirement_id": "sibling"})
    assert conditional_applicability((parent, same, sibling), sibling, {}) is None
