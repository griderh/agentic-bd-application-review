import json
from pathlib import Path

import pytest

from bd_packet_builder.draft import run_draft
from tests.integration.test_draft import add_ocr_citation, prepare, write_review


@pytest.mark.parametrize("invalid", [None, "hash", "wording"])
def test_fresh_workflow_preserves_trusted_form_bound_applicability_review(tmp_path, invalid):
    from bd_packet_builder.foundry import FoundryConfig
    from bd_packet_builder.live import LiveRunRequest, prepare_live_run
    from bd_packet_builder.reconciliation import RequirementAssessment
    from tests.integration.test_agent import Setup, blank_pdf
    from tests.integration.test_historical_prefill import call

    setup = Setup(tmp_path, blank_pdf())
    assessment = RequirementAssessment(
        requirement_id="p1.name",
        application_sha256="b" * 64 if invalid == "hash" else setup.manifest.blank_sha256,
        requirement_quote="Other question" if invalid == "wording" else "Firm legal name:",
        reviewer="Synthetic sponsor review",
        reason="Controlled test of explicit optional applicability, not inferred from a blank.",
        applicability="optional",
    )
    setup.manifest = prepare_live_run(
        setup.store,
        LiveRunRequest(
            blank_name="Synthetic.pdf",
            requester_id="offline",
            evidence_set_id="review",
            requirement_assessments=(assessment,),
        ),
        setup.blank,
        setup.evidence_root,
        FoundryConfig(endpoint="https://synthetic.openai.azure.com/openai/v1", deployment="test"),
    )
    tools = setup.tools()
    call(tools, "interpret_form")
    handoff = call(tools, "finish_evidence")
    assert handoff["reviewed_requirement_assessments"] == [assessment.model_dump(mode="json")]
    call(tools, "submit_answers", {"proposals": []})
    if invalid is not None:
        result = json.loads(tools.call("assemble_packet", "{}"))
        assert not result["ok"]
        assert setup.store.load(setup.manifest.run_id).failure.code == "packet_assembly_failed"
        return
    call(tools, "assemble_packet")
    call(tools, "publish_results")
    report = json.loads(setup.artifact("draft.json"))
    assert report["completion"]["optional_not_supplied"] == 1
    result = next(a for a in report["answers"] if a["requirement_id"] == "p1.name")
    assert result["status"] == "optional_not_supplied"
    assert json.loads(setup.artifact("answer_review.json"))["requirement_assessments"] == [
        assessment.model_dump(mode="json")
    ]


def reviewed_assessment(data, **updates):
    source = data["proposals"]["proposals"][0]["citations"][0]
    assessment = dict(
        requirement_id="missing",
        application_sha256=data["layout"]["application_sha256"],
        requirement_quote="Missing tax ID:",
        reviewer="Synthetic local reviewer",
        reason="Controlled test coverage; not production approval.",
        criteria=[
            dict(
                issuer_quote="Missing tax ID:",
                status="supported",
                evidence=[source],
                explanation="Synthetic reviewed sufficiency.",
                action="No action required.",
            )
        ],
    )
    assessment.update(updates)
    return assessment


def save(request, review, data, assessments):
    request.write_text(json.dumps(data))
    write_review(request, review)
    reviewed = json.loads(review.read_bytes())
    reviewed["requirement_assessments"] = assessments
    review.write_text(json.dumps(reviewed))


@pytest.mark.parametrize("mapped", [True, False])
def test_satisfied_attachment_is_not_merely_an_included_document(tmp_path, mapped):
    request, review, data = prepare(tmp_path)
    requirement = data["requirements"]["requirements"][3]
    requirement["kind"] = "attachment"
    if mapped:
        data["layout"]["responses"][3] = dict(
            requirement=requirement,
            checklist_box=dict(page=1, left=20.0, right=30.0, bottom=317.0, top=327.0),
            checklist_label_box=dict(page=1, left=40.0, right=120.0, bottom=315.0, top=332.0),
        )
    else:
        data["layout"]["responses"].pop()
    save(request, review, data, [reviewed_assessment(data)])
    output = run_draft(tmp_path, Path("outputs/request.json"), Path("outputs/review.json"))
    report = json.loads((output / "draft.json").read_bytes())
    result = next(a for a in report["answers"] if a["requirement_id"] == "missing")
    assert result["status"] == "requirement_satisfied"
    assert result["checklist_state"] == ("marked" if mapped else "satisfied_placement_unavailable")
    assert report["completion"]["evidence_satisfied"] == 1
    assert report["completion"]["populated"] == 3
    assert report["render_checks"]["outside_allowed_regions_changed_pixels"] == 0
    assert sum(report["completion"].values()) == 6
    summary = (output / "reviewer-summary.txt").read_text()
    assert "packet page" in summary
    assert "inclusion alone is not requirement satisfaction" in summary


@pytest.mark.parametrize("status", ["needs_review", "period_mismatch", "missing"])
def test_inclusion_does_not_clear_partial_or_period_mismatched_requirements(tmp_path, status):
    request, review, data = prepare(tmp_path)
    data["requirements"]["requirements"][3]["kind"] = "attachment"
    data["layout"]["responses"].pop()
    reviewed = reviewed_assessment(data)
    reviewed["criteria"][0]["status"] = status
    reviewed["criteria"][0]["action"] = "Resolve this exact outstanding criterion."
    save(request, review, data, [reviewed])
    output = run_draft(tmp_path, Path("outputs/request.json"), Path("outputs/review.json"))
    report = json.loads((output / "draft.json").read_bytes())
    result = next(a for a in report["answers"] if a["requirement_id"] == "missing")
    assert result["status"] == "blank"
    assert result["coverage"]["included_source_ids"] == data["attachments"]
    assert result["issues"] == ["requirement_coverage_" + status]
    assert (
        "Resolve this exact outstanding criterion." in (output / "reviewer-summary.txt").read_text()
    )


@pytest.mark.parametrize("applicability", ["optional", "not_applicable"])
def test_reviewed_applicability_leaves_field_blank_without_a_missing_answer(
    tmp_path, applicability
):
    request, review, data = prepare(tmp_path)
    reviewed = reviewed_assessment(data, applicability=applicability, criteria=[])
    save(request, review, data, [reviewed])
    output = run_draft(tmp_path, Path("outputs/request.json"), Path("outputs/review.json"))
    report = json.loads((output / "draft.json").read_bytes())
    expected = "optional_not_supplied" if applicability == "optional" else "not_applicable"
    assert report["completion"][expected] == 1
    assert report["completion"]["unresolved"] == 0
    assert report["completion"]["populated"] == 3
    assert "missing" not in report["written_requirements"]


def test_reconciliation_checks_actual_packet_inclusion(tmp_path):
    request, review, data = prepare(tmp_path)
    data["requirements"]["requirements"][3]["kind"] = "attachment"
    data["layout"]["responses"].pop()
    save(request, review, data, [reviewed_assessment(data)])
    reviewed = json.loads(review.read_bytes())
    reviewed["attachment_source_ids"] = []
    review.write_text(json.dumps(reviewed))
    output = run_draft(tmp_path, Path("outputs/request.json"), Path("outputs/review.json"))
    result = next(
        a
        for a in json.loads((output / "draft.json").read_bytes())["answers"]
        if a["requirement_id"] == "missing"
    )
    assert result["coverage"]["missing_packet_source_ids"] == data["attachments"]
    assert result["issues"] == ["requirement_coverage_not_in_packet"]


def test_reconciliation_rejects_changed_citation_and_unknown_criterion(tmp_path):
    request, review, data = prepare(tmp_path)
    reviewed = reviewed_assessment(data)
    reviewed["criteria"][0]["issuer_quote"] = "Invented issuer condition"
    save(request, review, data, [reviewed])
    with pytest.raises(ValueError, match="exact quotation"):
        run_draft(tmp_path, Path("outputs/request.json"), Path("outputs/review.json"))
    reviewed["criteria"][0]["issuer_quote"] = "Missing tax ID:"
    reviewed["criteria"][0]["evidence"][0]["quote"] = "Altered source quote"
    save(request, review, data, [reviewed])
    with pytest.raises(ValueError):
        run_draft(tmp_path, Path("outputs/request.json"), Path("outputs/review.json"))


def test_completed_questionnaire_does_not_ignore_signing_or_withheld_answers(tmp_path):
    request, review, data = prepare(tmp_path)
    data["requirements"]["requirements"][3]["kind"] = "attachment"
    data["layout"]["responses"].pop()
    reviewed = reviewed_assessment(data, criteria=[], depends_on=["crd", "sign"])
    save(request, review, data, [reviewed])
    output = run_draft(tmp_path, Path("outputs/request.json"), Path("outputs/review.json"))
    result = next(
        a
        for a in json.loads((output / "draft.json").read_bytes())["answers"]
        if a["requirement_id"] == "missing"
    )
    assert result["status"] == "blank"
    assert result["coverage"]["blocked_dependencies"] == ["sign"]
    assert "Resolve required item sign." in (output / "reviewer-summary.txt").read_text()


def test_applicability_cannot_erase_an_existing_proposal(tmp_path):
    request, review, data = prepare(tmp_path)
    reviewed = reviewed_assessment(
        data,
        requirement_id="services",
        requirement_quote="Describe services.",
        applicability="optional",
        criteria=[],
    )
    save(request, review, data, [reviewed])
    with pytest.raises(ValueError, match="discard"):
        run_draft(tmp_path, Path("outputs/request.json"), Path("outputs/review.json"))


@pytest.mark.parametrize("withheld", [True, False])
def test_dependency_uses_written_result_even_when_assessed_later(tmp_path, withheld):
    request, review, data = prepare(tmp_path)
    data["requirements"]["requirements"][3]["kind"] = "attachment"
    data["layout"]["responses"].pop()
    reviewed = reviewed_assessment(data, criteria=[], depends_on=["crd"])
    save(request, review, data, [reviewed])
    if withheld:
        decisions = json.loads(review.read_bytes())
        next(d for d in decisions["decisions"] if d["requirement_id"] == "crd")["decision"] = (
            "withhold"
        )
        review.write_text(json.dumps(decisions))
    output = run_draft(tmp_path, Path("outputs/request.json"), Path("outputs/review.json"))
    report = json.loads((output / "draft.json").read_bytes())
    result = next(a for a in report["answers"] if a["requirement_id"] == "missing")
    assert result["status"] == ("blank" if withheld else "requirement_satisfied")
    assert result["coverage"]["blocked_dependencies"] == (["crd"] if withheld else [])


@pytest.mark.parametrize("bad_box", ["wrong_label", "overlap"])
def test_checklist_cannot_write_against_unverified_label_or_existing_answer(tmp_path, bad_box):
    request, review, data = prepare(tmp_path)
    requirement = data["requirements"]["requirements"][3]
    requirement["kind"] = "attachment"
    data["layout"]["responses"][3] = dict(
        requirement=requirement,
        checklist_box=dict(page=1, left=20.0, right=30.0, bottom=317.0, top=327.0),
        checklist_label_box=dict(page=1, left=40.0, right=120.0, bottom=315.0, top=332.0),
    )
    if bad_box == "wrong_label":
        data["layout"]["responses"][3]["checklist_label_box"]["top"] = 310.0
        data["layout"]["responses"][3]["checklist_label_box"]["bottom"] = 300.0
    else:
        data["layout"]["responses"][0]["text_region"].update(
            left=20.0, right=30.0, bottom=317.0, top=327.0
        )
    save(request, review, data, [reviewed_assessment(data)])
    with pytest.raises(ValueError):
        run_draft(tmp_path, Path("outputs/request.json"), Path("outputs/review.json"))


@pytest.mark.parametrize("tamper", [False, True])
def test_assessment_ocr_requires_original_verified_artifact(tmp_path, tamper):
    request, review, data = prepare(tmp_path)
    original = json.loads(json.dumps(data))
    artifact = add_ocr_citation(tmp_path, request, data, "crd")
    citation = data["proposals"]["proposals"][0]["citations"][0]
    original["requirements"]["requirements"][3]["kind"] = "attachment"
    original["layout"]["responses"].pop()
    reviewed = reviewed_assessment(original)
    reviewed["criteria"][0]["evidence"] = [citation]
    save(request, review, original, [reviewed])
    if tamper:
        artifact.write_bytes(artifact.read_bytes() + b"\n")
        with pytest.raises(ValueError, match="ocr_artifact_hash_mismatch"):
            run_draft(tmp_path, Path("outputs/request.json"), Path("outputs/review.json"))
    else:
        output = run_draft(tmp_path, Path("outputs/request.json"), Path("outputs/review.json"))
        report = json.loads((output / "draft.json").read_bytes())
        assert report["completion"]["evidence_satisfied"] == 1


def test_historical_review_note_rejects_current_source(tmp_path):
    request, review, data = prepare(tmp_path)
    citation = data["proposals"]["proposals"][0]["citations"][0]
    reviewed = reviewed_assessment(
        data,
        historical_notes=[
            dict(citation=citation, explanation="Not initials.", action="Human must initial.")
        ],
    )
    save(request, review, data, [reviewed])
    with pytest.raises(ValueError, match="approved reference"):
        run_draft(tmp_path, Path("outputs/request.json"), Path("outputs/review.json"))


def test_satisfied_assessment_cannot_clear_unmapped_personal_act(tmp_path):
    request, review, data = prepare(tmp_path)
    data["requirements"]["requirements"][4]["kind"] = "attachment"
    reviewed = reviewed_assessment(
        data, requirement_id="sign", requirement_quote="Authorized signature:"
    )
    reviewed["criteria"][0]["issuer_quote"] = "Authorized signature:"
    save(request, review, data, [reviewed])
    with pytest.raises(ValueError, match="personal act"):
        run_draft(tmp_path, Path("outputs/request.json"), Path("outputs/review.json"))
