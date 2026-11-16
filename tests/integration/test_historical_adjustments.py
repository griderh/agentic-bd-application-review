import json
import logging
from datetime import date
from pathlib import Path

import pytest

from bd_packet_builder.contracts import AnswerProposal, Citation, Requirement
from bd_packet_builder.evidence import extract_evidence
from bd_packet_builder.history import historical_issues, with_historical_sources
from bd_packet_builder.inventory import build_inventory
from tests.integration.test_historical_prefill import archive


def historical_case(
    root: Path,
    *,
    instruction: str = "How long has the business operated?",
    prior_label: str = "Years established",
    prior_answer: str = "26",
):
    (root / "bd_agreements/supporting_data").mkdir(parents=True, exist_ok=True)
    prior_text = f"{prior_label}: {prior_answer}"
    manifest = archive(root, text=f"{prior_text}. Signature date: November 2, 2024")
    inventory = with_historical_sources(root, build_inventory(root), manifest)
    source = next(s for s in inventory.sources if s.family == "historical_reference")
    page = next(
        d
        for d in extract_evidence(root, inventory).documents
        if d.source.source_id == source.source_id
    ).pages[0]

    def cite(quote: str) -> dict:
        start = page.text.index(quote)
        return Citation(
            source_id=source.source_id, page=1, start=start, end=start + len(quote), quote=quote
        ).model_dump(mode="json")

    prior = cite(prior_text)
    signature = cite("Signature date: November 2, 2024")
    proposal = {
        "requirement_id": "years",
        "outcome": "proposed",
        "value": {"kind": "text", "value": "28"},
        "citations": [prior],
        "confidence": 0.9,
        "historical_basis": {
            "category": "tenure",
            "context": "firm_wide",
            "prior_question": prior,
            "current_checks": [],
            "reviewer_confirmation": "Confirm operating continuity.",
            "correspondence": {
                "target_question": instruction,
                "assessment": "applicable",
                "differences": (
                    "Different municipality and wording; both request firm operating tenure."
                ),
                "reason": "Same firm-wide quantity, not an issuer-specific appointment.",
            },
            "tenure": {
                "prior_value": prior_answer,
                "signed_on": "2024-11-02",
                "date_citation": signature,
                "date_context": signature,
            },
        },
    }
    requirement = Requirement(
        requirement_id="years",
        application_sha256="a" * 64,
        page=1,
        instruction=instruction,
        kind="text",
    )
    return manifest, inventory, requirement, proposal


def issues(root: Path, case, *, as_of: date | None = date(2026, 11, 2)):
    manifest, inventory, requirement, raw = case
    return historical_issues(
        root,
        inventory,
        manifest,
        "Net New City",
        requirement,
        AnswerProposal.model_validate_json(json.dumps(raw)),
        historical_policy="answer_first_review",
        calculation_date=as_of,
    )


def test_new_municipality_rephrased_tenure_uses_verified_signature_baseline(tmp_path: Path) -> None:
    case = historical_case(tmp_path)
    problems, status = issues(tmp_path, case)
    assert problems == ()
    assert status == "historical_continuity_unconfirmed"


@pytest.mark.parametrize(
    ("change", "expected"),
    [
        ("wrong_date", "historical_signature_date_mismatch"),
        ("wrong_value", "historical_tenure_calculation_mismatch"),
        ("wrong_prior", "historical_tenure_baseline_not_supported"),
        ("partial_prior", "historical_tenure_baseline_not_supported"),
        ("future", "historical_tenure_invalid"),
        ("missing_clock", "historical_calculation_date_required"),
        ("different_source", "historical_signature_source_mismatch"),
        ("incompatible", "historical_question_incompatible"),
        ("wrong_question", "historical_target_question_mismatch"),
        ("no_correspondence", "historical_cross_issuer_correspondence_required"),
        ("financial", "historical_tenure_field_not_allowed"),
        ("normalized_wrong_source", "historical_signature_source_mismatch"),
        ("normalized_invented_date", "historical_signature_context_unresolved"),
    ],
)
def test_invalid_historical_adjustments_are_not_written(
    tmp_path: Path, change: str, expected: str
) -> None:
    case = historical_case(
        tmp_path,
        instruction="Current capital"
        if change == "financial"
        else "How long has the business operated?",
    )
    raw = case[3]
    temporal = raw["historical_basis"]["tenure"]
    clock = date(2026, 11, 2)
    if change == "wrong_date":
        temporal["signed_on"] = "2024-11-01"
    elif change == "wrong_value":
        raw["value"]["value"] = "29"
    elif change == "wrong_prior":
        temporal["prior_value"] = "25"
        raw["value"]["value"] = "27"
    elif change == "partial_prior":
        temporal["prior_value"] = "2"
        raw["value"]["value"] = "4"
    elif change == "future":
        clock = date(2024, 1, 1)
    elif change == "missing_clock":
        clock = None
    elif change == "different_source":
        temporal["date_citation"]["source_id"] = "b" * 64
    elif change.startswith("normalized_"):
        from bd_packet_builder.historical_time import adjusted_tenure

        temporal["signed_on"] = "7147-07-14"
        if change == "normalized_wrong_source":
            temporal["date_citation"]["source_id"] = "b" * 64
        else:
            temporal["date_citation"]["quote"] = "Signature date: November 2, 2023"
            temporal["date_citation"]["end"] = temporal["date_citation"]["start"] + len(
                temporal["date_citation"]["quote"]
            )
        canonical = adjusted_tenure(AnswerProposal.model_validate_json(json.dumps(raw)), clock)
        raw.update(canonical.model_dump(mode="json"))
    elif change == "incompatible":
        raw["historical_basis"]["correspondence"]["assessment"] = "incompatible"
    elif change == "wrong_question":
        raw["historical_basis"]["correspondence"]["target_question"] = "Other wording"
    elif change == "no_correspondence":
        raw["historical_basis"].pop("correspondence")
    assert expected in issues(tmp_path, case, as_of=clock)[0]


def test_headcount_remains_a_qualified_historical_value(tmp_path: Path) -> None:
    case = historical_case(
        tmp_path,
        instruction="Number of employees",
        prior_label="Total firm employees",
        prior_answer="Approximately 243",
    )
    raw = case[3]
    raw["historical_basis"].pop("tenure")
    raw["historical_basis"]["category"] = "headcount"
    # Exact supplied prior value; no headcount increment is authorized.
    raw["value"]["value"] = "Approximately 243"
    assert issues(tmp_path, case)[0] == ()
    raw["value"]["value"] = "243"
    assert "historical_headcount_qualifier_missing" in issues(tmp_path, case)[0]
    raw["value"]["value"] = "245"
    assert "historical_value_not_in_prior_answer" in issues(tmp_path, case)[0]


@pytest.mark.parametrize(
    ("signed_on", "recover_assembly", "forged_source"),
    [
        ("2024-11-02", False, False),
        ("7147-07-14", False, False),
        ("7202-07-14", True, False),
        ("7147-07-14", False, True),
    ],
)
def test_fresh_grouped_workflow_calculates_and_writes_cross_municipality_tenure(
    tmp_path: Path,
    caplog: pytest.LogCaptureFixture,
    monkeypatch: pytest.MonkeyPatch,
    signed_on: str,
    recover_assembly: bool,
    forged_source: bool,
):
    import asyncio
    from io import BytesIO

    from reportlab.pdfgen.canvas import Canvas

    from bd_packet_builder import draft
    from bd_packet_builder.foundry import FoundryConfig
    from bd_packet_builder.grouped import run_answer_groups
    from bd_packet_builder.live import LiveRunRequest, prepare_live_run
    from bd_packet_builder.visual import VisualPage
    from tests.integration.test_agent import HEIGHT, WIDTH, FakeMapper, Setup, nbox, visual_item
    from tests.integration.test_historical_prefill import call

    blank = BytesIO()
    canvas = Canvas(blank, pagesize=(WIDTH, HEIGHT))
    canvas.drawString(40, HEIGHT - 60, "Years established")
    canvas.save()
    mapper = FakeMapper(
        {
            1: VisualPage.model_validate_json(
                json.dumps(
                    {
                        "readable": True,
                        "explanation": None,
                        "items": [
                            visual_item("years", "Years established", "text", nbox(40, 70, 400, 90))
                        ],
                    }
                )
            )
        }
    )
    setup = Setup(tmp_path, blank.getvalue(), mapper)
    archive_manifest, _, _, raw = historical_case(setup.evidence_root)
    raw["requirement_id"] = "p1.years"
    raw["historical_basis"]["correspondence"]["target_question"] = "Years established"
    raw["value"]["value"] = "26"  # The model supplies the baseline, not its own arithmetic.
    raw["historical_basis"]["tenure"]["signed_on"] = signed_on
    if forged_source:
        raw["historical_basis"]["tenure"]["date_citation"]["source_id"] = "b" * 64
    setup.manifest = prepare_live_run(
        setup.store,
        LiveRunRequest(
            blank_name="New municipality.pdf",
            requester_id="offline",
            evidence_set_id="temporal",
            as_of=date(2026, 11, 2),
            issuer="Net New City",
            historical_archive=archive_manifest,
            historical_policy="answer_first_review",
        ),
        setup.blank,
        setup.evidence_root,
        FoundryConfig(endpoint="https://synthetic.openai.azure.com/openai/v1", deployment="test"),
    )
    events: list[str] = []
    tools = setup.tools(progress_sink=events.append)
    call(tools, "interpret_form")
    handoff = call(tools, "finish_evidence")
    assert handoff["calculation_date"] == "2026-11-02"
    caplog.set_level(logging.INFO, logger="bd_packet_builder.agent")
    for _ in range(2):
        call(tools, "stage_answers", {"proposals": [raw]})
    tools = setup.tools(progress_sink=events.append)

    async def propose(payload):
        assert payload["issuer"] == "Net New City"
        return json.dumps({"proposals": [raw]})

    if recover_assembly:
        with monkeypatch.context() as limited:
            limited.setattr(draft, "MAX_PACKET_PAGES", 0)
            failed = asyncio.run(run_answer_groups(tools, propose))
        assert failed.failure.code == "packet_assembly_failed"
        saved = setup.artifact("draft_request.json")

        async def unexpected_proposal(payload):
            pytest.fail("Assembly recovery must reuse the canonical validated proposal")

        final = asyncio.run(run_answer_groups(setup.tools(), unexpected_proposal, resume=True))
        assert setup.artifact("draft_request.json") == saved
    else:
        final = asyncio.run(run_answer_groups(tools, propose))
    assert final.status == "published" and final.outcome == "incomplete"
    request = json.loads(setup.artifact("draft_request.json"))
    assert request["proposals"]["proposals"][0]["value"]["value"] == "28"
    canonical = request["proposals"]["proposals"][0]["historical_basis"]["tenure"]
    assert canonical["signed_on"] == "2024-11-02"
    original = json.loads(setup.artifact("answer-group-000-attempt-1.json"))["response"]
    assert json.loads(original)["proposals"][0]["historical_basis"]["tenure"]["signed_on"] == (
        signed_on
    )
    assert ("Historical tenure date normalized" in caplog.text) == (signed_on != "2024-11-02")
    assert any("Historical tenure date normalized" in event for event in events) == (
        signed_on != "2024-11-02"
    )
    assert signed_on not in caplog.text
    assert "Signature date: November 2, 2024" not in caplog.text
    review = json.loads(setup.artifact("answer_review.json"))
    report = json.loads(setup.artifact("draft.json"))
    if forged_source:
        from pypdf import PdfReader

        assert review["decisions"][0]["decision"] != "draft_verified"
        assert report["completion"]["populated"] == 0
        assert "p1.years" not in report["written_requirements"]
        assert "28" not in PdfReader(BytesIO(setup.artifact("packet.pdf"))).pages[0].extract_text()
        return
    assert review["decisions"][0]["decision"] == "draft_verified"
    assert report["completion"]["populated"] == 1
    summary = setup.artifact("reviewer-summary.txt").decode()
    assert "prior=26; signed=2024-11-02; calculated as of=2026-11-02" in summary
    assert "QUESTION CORRESPONDENCE" in summary
