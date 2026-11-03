import json
from datetime import UTC, datetime

import pytest

from bd_packet_builder.contracts import Requirement
from bd_packet_builder.inventory import Inventory
from bd_packet_builder.reconciliation import (
    RequirementAssessment,
    reconcile_requirement,
    validate_assessments,
)


def requirement(kind="attachment"):
    return Requirement(
        requirement_id="proof",
        application_sha256="a" * 64,
        page=1,
        instruction="Current registration and state proof",
        kind=kind,
    )


def assessment(**updates):
    data = dict(
        requirement_id="proof",
        application_sha256="a" * 64,
        requirement_quote="Current registration and state proof",
        reviewer="Synthetic reviewer",
        reason="Assess the actual requirement.",
        criteria=[
            dict(
                issuer_quote="Current registration",
                status="needs_review",
                explanation="Record included, current coverage unconfirmed.",
                action="Confirm current registration.",
            ),
            dict(
                issuer_quote="state proof",
                status="missing",
                explanation="Required state proof is missing.",
                action="Supply state registration proof.",
            ),
        ],
    )
    data.update(updates)
    return RequirementAssessment.model_validate_json(json.dumps(data))


def test_included_partial_evidence_is_not_satisfaction():
    result = reconcile_requirement(assessment(), {}, ())
    assert result.satisfied is False
    assert result.evidence_state == "missing"
    assert len(result.actions) == 2


def test_completed_questionnaire_depends_on_actual_completion_not_raw_proposals():
    reviewed = assessment(criteria=[], depends_on=("answer", "sign"))
    result = reconcile_requirement(reviewed, {"answer": "written_to_draft", "sign": "blank"}, ())
    assert not result.satisfied
    assert result.blocked_dependencies == ("sign",)
    assert reconcile_requirement(
        reviewed, {"answer": "written_to_draft", "sign": "not_applicable"}, ()
    ).satisfied


@pytest.mark.parametrize("kind", ["signature", "signature_date", "boolean"])
def test_optional_override_cannot_suppress_personal_acts(tmp_path, kind):
    req = requirement(kind).model_copy(update={"instruction": "Confirm I have read the policy"})
    reviewed = assessment(applicability="optional", requirement_quote=req.instruction, criteria=[])
    with pytest.raises(ValueError, match="personal"):
        validate_assessments(
            tmp_path,
            Inventory(datetime.now(UTC), (), ()),
            (req,),
            (reviewed,),
            {1: req.instruction},
        )


def test_assessment_is_bound_to_requirement_wording_and_application(tmp_path):
    reviewed = assessment(application_sha256="b" * 64)
    with pytest.raises(ValueError, match="version"):
        validate_assessments(
            tmp_path,
            Inventory(datetime.now(UTC), (), ()),
            (requirement(),),
            (reviewed,),
            {1: requirement().instruction},
        )


def test_dependency_cycles_are_rejected(tmp_path):
    first = assessment(criteria=[], depends_on=("second",))
    second = first.model_copy(update={"requirement_id": "second", "depends_on": ("proof",)})
    req = requirement()
    with pytest.raises(ValueError, match="cycle"):
        validate_assessments(
            tmp_path,
            Inventory(datetime.now(UTC), (), ()),
            (req, req.model_copy(update={"requirement_id": "second"})),
            (first, second),
            {1: req.instruction},
        )


def test_supported_criterion_needs_evidence():
    with pytest.raises(ValueError, match="evidence"):
        assessment(
            criteria=[
                dict(
                    issuer_quote="Current registration",
                    status="supported",
                    explanation="Claimed without evidence.",
                    action="No action.",
                )
            ]
        )
