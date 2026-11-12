import json
from pathlib import Path
from unittest.mock import Mock

import pytest

from bd_packet_builder.agent import AGENT_INSTRUCTIONS
from bd_packet_builder.evidence_tools import EvidenceLimits
from bd_packet_builder.foundry import FoundryConfig
from bd_packet_builder.live import LiveRunRequest, prepare_live_run
from bd_packet_builder.scan import ScanTranscript
from bd_packet_builder.visual import VisualPage
from tests.integration.test_agent import FakeMapper, Setup, blank_pdf, nbox
from tests.integration.test_draft import make_pdf
from tests.integration.test_historical_prefill import call
from tests.integration.test_retrieval import pdf


def setup_library(
    tmp_path: Path,
    *,
    collect_sources: bool = True,
    support_text: str = "Synthetic support; as of December 31, 2025.",
    **tool_options,
):
    setup = Setup(tmp_path, blank_pdf())
    for folder in (
        "bios",
        "Bloomberg_League_Tables",
        "Business Continuity Statement",
        "Cover_Letters",
        "Restricted_Financials",
    ):
        pdf(
            setup.evidence_root / f"bd_agreements/supporting_data/{folder}/example.pdf",
            [support_text],
        )
    setup.manifest = prepare_live_run(
        setup.store,
        LiveRunRequest(blank_name="Form.pdf", requester_id="test", evidence_set_id="library"),
        setup.blank,
        setup.evidence_root,
        FoundryConfig(endpoint="https://synthetic.openai.azure.com/openai/v1", deployment="test"),
    )
    tools = setup.tools(require_attachment_coverage=True, **tool_options)
    call(tools, "interpret_form")
    source_tools = setup.tools()
    sources = call(source_tools, "list_sources")["sources"] if collect_sources else []
    return setup, tools, sources


def test_attachment_candidates_accept_catalog_folders_with_spaces(tmp_path: Path):
    _, tools, _ = setup_library(tmp_path, collect_sources=False)

    candidates = call(tools, "list_attachment_candidates")["sources"]

    assert any(source["family"] == "Business Continuity Statement" for source in candidates)


def test_checklist_orders_document_families_before_optional_support_after_restart(tmp_path: Path):
    blank = tmp_path / "blank.pdf"
    definitions = [
        ("name", "Firm legal name", "text", 740, nbox(40, 70, 400, 90)),
        ("bios", "Attach representative biographies", "attachment", 660, None),
        ("reports", "Attach regulatory reports", "attachment", 600, None),
    ]
    make_pdf(blank, [(40, y, instruction) for _, instruction, _, y, _ in definitions])
    page = VisualPage.model_validate_json(
        json.dumps(
            {
                "readable": True,
                "explanation": None,
                "items": [
                    {
                        "item_id": key,
                        "instruction": instruction,
                        "kind": kind,
                        "instruction_box": nbox(35, 792 - y - 20, 560, 792 - y + 5),
                        "region": region,
                        "options": [],
                        "explanation": None,
                    }
                    for key, instruction, kind, y, region in definitions
                ],
            }
        )
    )
    setup = Setup(tmp_path, blank.read_bytes(), FakeMapper({1: page}))
    for family, filenames in [
        ("bios", ("second", "first")),
        ("FINRA_Certification", ("person",)),
        ("Bloomberg_League_Tables", ("current", "annual")),
    ]:
        for filename in filenames:
            pdf(
                setup.evidence_root / f"bd_agreements/supporting_data/{family}/{filename}.pdf",
                [f"Synthetic {family} {filename}."],
            )
    setup.manifest = prepare_live_run(
        setup.store,
        LiveRunRequest(blank_name="Form.pdf", requester_id="test", evidence_set_id="library"),
        setup.blank,
        setup.evidence_root,
        FoundryConfig(endpoint="https://synthetic.openai.azure.com/openai/v1", deployment="test"),
    )
    tools = setup.tools(require_attachment_coverage=True)
    call(tools, "interpret_form")
    candidates = call(tools, "list_attachment_candidates")["sources"]
    requirement_ids = {
        "bios": "p1.bios",
        "FINRA_Certification": "p1.reports",
        "Bloomberg_League_Tables": "p1.name",
    }
    for source in candidates:
        call(tools, "read_page", {"source_id": source["source_id"], "page": 1})
        call(
            tools,
            "plan_supporting_document",
            {
                "family": source["family"],
                "source_id": source["source_id"],
                "disposition": "include",
                "requirement_ids": [requirement_ids[source["family"]]],
                "inspected_pages": [1],
                "reason": "Synthetic requirement-linked support.",
                "limitation": "Controlled presentation test, not factual approval.",
            },
        )
    call(tools, "finish_evidence")
    saved = json.loads(setup.artifact("evidence_selection.json"))
    tools = setup.tools(require_attachment_coverage=True)
    call(tools, "submit_answers", {"proposals": []})
    request = json.loads(setup.artifact("draft_request.json"))
    by_id = {source["source_id"]: source for source in candidates}
    expected = [
        identity
        for family in ("bios", "FINRA_Certification", "Bloomberg_League_Tables")
        for identity in saved["attachments"]
        if by_id[identity]["family"] == family
    ]
    assert request["attachments"] == expected
    call(tools, "assemble_packet")
    report = json.loads(setup.artifact("draft.json"))
    assert [
        section["section_id"]
        for section in report["pagination"]["sections"]
        if section["role"] == "evidence"
    ] == expected


def test_agent_treats_catalog_and_historical_attachments_as_general_evidence():
    assert "discovery cues, not exhaustive" in AGENT_INSTRUCTIONS
    assert "Do not copy an old packet's attachment set" in AGENT_INSTRUCTIONS
    assert "Use review_required when" in AGENT_INSTRUCTIONS
    assert "Do not declare every absent catalog family unavailable" in AGENT_INSTRUCTIONS
    assert "every approved supporting-document candidate" in AGENT_INSTRUCTIONS


def test_purpose_documents_are_accessible_but_restricted_and_cover_sources_are_not(tmp_path: Path):
    _, _, sources = setup_library(tmp_path)
    assert {s["family"] for s in sources} == {
        "FINRA_Certification",
        "bios",
        "Bloomberg_League_Tables",
        "Business Continuity Statement",
    }


def test_attachment_plan_survives_publication_with_rationale_and_gaps(tmp_path: Path):
    setup, tools, sources = setup_library(tmp_path)
    candidates = call(tools, "list_attachment_candidates")["sources"]
    source = next(s for s in sources if s["family"] == "Bloomberg_League_Tables")
    assert source["version_date_basis"] == "pdf_creation"
    call(tools, "read_page", {"source_id": source["source_id"], "page": 1})
    call(
        tools,
        "plan_supporting_document",
        {
            "family": source["family"],
            "source_id": source["source_id"],
            "disposition": "include",
            "requirement_ids": ["p1.name"],
            "inspected_pages": [1],
            "reason": "Relevant historical category-specific market-position exhibit.",
            "limitation": "Not a current ranking or regulatory-compliance confirmation.",
        },
    )
    call(
        tools,
        "plan_supporting_document",
        {
            "family": "Audited_Financials",
            "disposition": "unavailable",
            "requirement_ids": ["p1.name"],
            "reason": "No applicable annual financial statement is present.",
            "limitation": "FOCUS is not a substitute for an audited annual statement.",
        },
    )
    bio = next(s for s in sources if s["family"] == "bios")
    call(tools, "read_page", {"source_id": bio["source_id"], "page": 1})
    bio_review = {
        "family": bio["family"],
        "source_id": bio["source_id"],
        "disposition": "review_required",
        "requirement_ids": ["p1.name"],
        "inspected_pages": [1],
        "reason": "The available form does not establish whether this biography is relevant.",
        "limitation": "Do not infer a current representative assignment from the bio.",
    }
    call(tools, "plan_supporting_document", bio_review)
    registration = next(s for s in candidates if s["family"] == "FINRA_Certification")
    continuity = next(s for s in candidates if s["family"] == "Business Continuity Statement")
    call(
        tools,
        "plan_supporting_documents",
        {
            "decisions": [
                {
                    "family": registration["family"],
                    "source_id": registration["source_id"],
                    "disposition": "exclude",
                    "requirement_ids": [],
                    "reason": (
                        "The current form has no registration or BrokerCheck attachment need."
                    ),
                    "limitation": "This exclusion does not validate any registration answer.",
                },
                {
                    "family": continuity["family"],
                    "source_id": continuity["source_id"],
                    "disposition": "exclude",
                    "requirement_ids": [],
                    "reason": "The synthetic form requests no business-continuity materials.",
                    "limitation": "This exclusion applies only to the synthetic form in this test.",
                },
            ]
        },
    )
    first_finish = json.loads(tools.call("finish_evidence", "{}"))
    assert "reconsider" in first_finish["error"]["message"].lower()
    call(tools, "plan_supporting_document", bio_review)
    handoff = call(tools, "finish_evidence")
    assert handoff["attachment_plan"][0]["reason"].startswith("Relevant historical")
    call(tools, "submit_answers", {"proposals": []})
    call(tools, "assemble_packet")
    call(tools, "publish_results")
    manifest = json.loads(setup.artifact("attachment-manifest.json"))
    assert manifest["selected_source_ids"] == [source["source_id"]]
    selected_decision = next(
        d for d in manifest["decisions"] if d.get("source_id") == source["source_id"]
    )
    assert selected_decision["version_date"] == source["version_date"]
    assert selected_decision["version_date_basis"] == "pdf_creation"
    assert bio["source_id"] not in manifest["selected_source_ids"]
    assert manifest["version"] == "attachment-plan-v6"
    assert "unavailable_families" not in manifest
    assert manifest["unassessed_source_count"] == 0
    assert all(
        decision["family"] not in {"Cover_Letters", "Restricted_Financials"}
        for decision in manifest["decisions"]
    )
    assert any(p["disposition"] == "unavailable" for p in manifest["decisions"])
    bio_decision = next(p for p in manifest["decisions"] if p.get("source_id") == bio["source_id"])
    assert bio_decision["disposition"] == "review_required"
    registration_decision = next(
        p for p in manifest["decisions"] if p.get("source_id") == registration["source_id"]
    )
    assert registration_decision["disposition"] == "exclude"
    summary = setup.artifact("reviewer-summary.txt").decode()
    assert "not capture/publication or reporting dates" in summary
    assert "basis=pdf_creation" in summary
    assert "SUPPORTING-DOCUMENT REVIEW" in summary
    assert "available form does not establish" in summary
    assert "No applicable annual financial statement" in summary
    assert "See attachment-manifest.json" in summary
    assert '"decisions": [' not in summary
    final = setup.store.load(setup.manifest.run_id)
    assert final.outcome == "incomplete"
    assert {
        exception.code
        for exception in final.exceptions()
        if exception.code.startswith("supporting_document_")
    } == {"supporting_document_unavailable", "supporting_document_review_required"}


def test_finish_evidence_rejects_unassessed_available_candidates(tmp_path: Path):
    _, tools, sources = setup_library(tmp_path)
    candidates = call(tools, "list_attachment_candidates")["sources"]
    source = next(s for s in sources if s["family"] == "Bloomberg_League_Tables")
    decision = {
        "family": source["family"],
        "source_id": source["source_id"],
        "disposition": "include",
        "requirement_ids": ["p1.name"],
        "inspected_pages": [1],
        "reason": "Relevant category-specific market-position evidence.",
        "limitation": "The source's period must match the request.",
    }

    uninspected = json.loads(tools.call("plan_supporting_document", json.dumps(decision)))
    assert not uninspected["ok"]
    assert "inspect" in uninspected["error"]["message"].lower()

    call(tools, "read_page", {"source_id": source["source_id"], "page": 1})
    call(tools, "plan_supporting_document", decision)

    response = json.loads(tools.call("finish_evidence", "{}"))

    assert not response["ok"]
    assert response["error"]["code"] == "invalid_input"
    assert "unassessed" in response["error"]["message"].lower()
    assert any(
        candidate["source_id"] in response["error"]["message"]
        for candidate in candidates
        if candidate["source_id"] != source["source_id"]
    )


def test_finish_evidence_requires_all_candidate_pages_to_be_listed(tmp_path: Path):
    _, tools, _ = setup_library(tmp_path)
    first_page = call(tools, "list_attachment_candidates", {"limit": 1})
    candidate = first_page["sources"][0]
    call(
        tools,
        "plan_supporting_documents",
        {
            "decisions": [
                {
                    "family": candidate["family"],
                    "source_id": candidate["source_id"],
                    "disposition": "exclude",
                    "requirement_ids": [],
                    "reason": "No current packet requirement calls for this support.",
                    "limitation": "This does not validate any answer.",
                }
            ]
        },
    )

    response = json.loads(tools.call("finish_evidence", "{}"))

    assert not response["ok"]
    assert "offset=1" in response["error"]["message"]


def test_candidate_relisting_is_idempotent_and_directs_model_to_decide(tmp_path: Path):
    _, tools, _ = setup_library(tmp_path)
    first_page = call(tools, "list_attachment_candidates")
    repeated_page = json.loads(tools.call("list_attachment_candidates", "{}"))

    assert first_page["sources"]
    assert repeated_page["ok"] is False
    assert "already listed" in repeated_page["error"]["message"]
    assert "plan_supporting_documents" in repeated_page["error"]["message"]


def test_coverage_gate_progress_includes_safe_recovery_detail(tmp_path: Path):
    setup = Setup(tmp_path, blank_pdf())
    for folder in ("Bloomberg_League_Tables",):
        pdf(
            setup.evidence_root / f"bd_agreements/supporting_data/{folder}/example.pdf",
            ["Synthetic support."],
        )
    setup.manifest = prepare_live_run(
        setup.store,
        LiveRunRequest(blank_name="Form.pdf", requester_id="test", evidence_set_id="library"),
        setup.blank,
        setup.evidence_root,
        FoundryConfig(endpoint="https://synthetic.openai.azure.com/openai/v1", deployment="test"),
    )
    events: list[str] = []
    tools = setup.tools(require_attachment_coverage=True, progress_sink=events.append)
    call(tools, "interpret_form")
    call(tools, "list_attachment_candidates")
    tools.call("list_attachment_candidates", "{}")

    assert any("plan_supporting_documents" in event for event in events)


def test_source_retrieval_waits_for_attachment_candidate_decisions(tmp_path: Path):
    _, tools, _ = setup_library(tmp_path)
    candidates = call(tools, "list_attachment_candidates")["sources"]

    response = json.loads(tools.call("list_sources", "{}"))

    assert response["ok"] is False
    assert "plan_supporting_documents" in response["error"]["message"]
    decisions = [
        {
            "family": candidate["family"],
            "source_id": candidate["source_id"],
            "disposition": "exclude",
            "requirement_ids": [],
            "reason": "No current request link is indicated by the candidate metadata.",
            "limitation": "This exclusion does not validate any application answer.",
        }
        for candidate in candidates
    ]
    call(tools, "plan_supporting_documents", {"decisions": decisions})
    assert call(tools, "list_sources")["sources"]


def test_candidate_decision_batch_is_complete_and_idempotent(tmp_path: Path):
    _, tools, _ = setup_library(tmp_path)
    candidates = call(tools, "list_attachment_candidates")["sources"]
    decisions = [
        {
            "family": candidate["family"],
            "source_id": candidate["source_id"],
            "disposition": "exclude",
            "requirement_ids": [],
            "reason": "No current packet requirement calls for this support.",
            "limitation": "This is an attachment decision, not an answer-evidence finding.",
        }
        for candidate in candidates
    ]

    first = call(tools, "plan_supporting_documents", {"decisions": decisions})
    retry = call(tools, "plan_supporting_documents", {"decisions": decisions})
    handoff = call(tools, "finish_evidence")

    assert len(first["recorded_decisions"]) == len(candidates)
    assert retry == first
    assert handoff["attachment_plan"] == first["recorded_decisions"]


def test_attachment_plan_cannot_add_unknown_or_mismatched_sources(tmp_path: Path):
    _, tools, sources = setup_library(tmp_path)
    source = next(s for s in sources if s["family"] == "bios")
    result = json.loads(
        tools.call(
            "plan_supporting_document",
            json.dumps(
                {
                    "family": "Audited_Financials",
                    "source_id": source["source_id"],
                    "disposition": "include",
                    "requirement_ids": ["p1.name"],
                    "reason": "Wrong family",
                    "limitation": "Invalid",
                }
            ),
        )
    )
    assert not result["ok"]


def _exclusions(candidates, *, skip: str) -> list[dict]:
    return [
        {
            "family": c["family"],
            "source_id": c["source_id"],
            "disposition": "exclude",
            "requirement_ids": [],
            "reason": "No current packet requirement calls for this support.",
            "limitation": "This exclusion does not validate any application answer.",
        }
        for c in candidates
        if c["source_id"] != skip
    ]


def _review(candidate: dict) -> dict:
    return {
        "family": candidate["family"],
        "source_id": candidate["source_id"],
        "disposition": "review_required",
        "requirement_ids": ["p1.name"],
        "inspected_pages": [1],
        "reason": "Relevance depends on a role link not yet established.",
        "limitation": "Pending the representative resolution.",
    }


def test_review_required_decision_can_be_revised_once_with_logged_rationale(tmp_path: Path):
    setup, tools, _ = setup_library(tmp_path)
    events: list[str] = []
    tools._progress_sink = events.append
    candidates = call(tools, "list_attachment_candidates")["sources"]
    bio = next(c for c in candidates if c["family"] == "bios")
    call(tools, "read_page", {"source_id": bio["source_id"], "page": 1})
    call(
        tools,
        "plan_supporting_documents",
        {"decisions": [_review(bio), *_exclusions(candidates, skip=bio["source_id"])]},
    )
    include = {
        **_review(bio),
        "disposition": "include",
        "reason": "The resolved representative is the subject of this support.",
        "limitation": "Identity link only; not current-assignment approval.",
    }

    revised = call(tools, "plan_supporting_documents", {"decisions": [include]})
    exclude_again = json.loads(
        tools.call(
            "plan_supporting_document",
            json.dumps({**include, "disposition": "exclude", "inspected_pages": []}),
        )
    )
    excluded = next(c for c in candidates if c["source_id"] != bio["source_id"])
    final_change = json.loads(
        tools.call(
            "plan_supporting_document",
            json.dumps({**_review(excluded), "disposition": "include"}),
        )
    )
    handoff = call(tools, "finish_evidence")

    assert bio["source_id"] in revised["attachments"]
    assert exclude_again["ok"] is False
    assert "already has a different" in exclude_again["error"]["message"]
    assert final_change["ok"] is False
    assert [
        p["disposition"] for p in handoff["attachment_plan"] if p["source_id"] == bio["source_id"]
    ] == ["include"]
    assert handoff["attachment_revisions"] == [
        {
            "source_id": bio["source_id"],
            "family": "bios",
            "from_disposition": "review_required",
            "to_disposition": "include",
            "previous_reason": "Relevance depends on a role link not yet established.",
        }
    ]
    assert any(
        "attachment decision revised" in e and "review_required -> include" in e for e in events
    )
    assert not any("Relevance depends" in e for e in events)
    call(tools, "submit_answers", {"proposals": []})
    call(tools, "assemble_packet")
    manifest = json.loads(setup.artifact("attachment-manifest.json"))
    assert bio["source_id"] in manifest["selected_source_ids"]
    assert manifest["revisions"] == handoff["attachment_revisions"]


def test_finish_evidence_requires_one_reconsideration_of_pending_reviews(tmp_path: Path):
    _, tools, _ = setup_library(tmp_path)
    candidates = call(tools, "list_attachment_candidates")["sources"]
    bio = next(c for c in candidates if c["family"] == "bios")
    call(tools, "read_page", {"source_id": bio["source_id"], "page": 1})
    call(
        tools,
        "plan_supporting_documents",
        {"decisions": [_review(bio), *_exclusions(candidates, skip=bio["source_id"])]},
    )

    first = json.loads(tools.call("finish_evidence", "{}"))
    call(tools, "plan_supporting_documents", {"decisions": [_review(bio)]})
    handoff = call(tools, "finish_evidence")

    assert first["ok"] is False
    assert "reconsider" in first["error"]["message"].lower()
    assert bio["source_id"] in first["error"]["message"]
    assert "Relevance depends" not in first["error"]["message"]
    assert [
        p["disposition"] for p in handoff["attachment_plan"] if p["source_id"] == bio["source_id"]
    ] == ["review_required"]
    assert handoff["attachment_revisions"] == []


@pytest.mark.parametrize("partial", [False, True])
def test_visual_inspection_can_resolve_attachment_relevance_without_granting_answer_evidence(
    tmp_path: Path,
    caplog,
    partial: bool,
):
    caplog.set_level("INFO", logger="bd_packet_builder.agent")
    reader = Mock()
    reader.transcribe.return_value = ScanTranscript.model_validate(
        {
            "readable": not partial,
            "subject": None if partial else "Example LLC",
            "text": "Callable league table\nAgency market positioning",
            "reporting_period": None,
            "identification": {
                "description": "Callable league-table market supplement",
                "visible_cues": ("Callable league table", "Agency market positioning"),
            }
            if partial
            else None,
        }
    )
    setup, tools, _ = setup_library(tmp_path, scan_reader=reader)
    events = []
    tools._progress_sink = events.append
    candidates = call(tools, "list_attachment_candidates")["sources"]
    source = next(c for c in candidates if c["family"] == "Bloomberg_League_Tables")
    args = {"source_id": source["source_id"], "page": 1}

    inspected = call(tools, "inspect_attachment_page", args)
    call(tools, "inspect_attachment_page", args)
    call(
        tools,
        "plan_supporting_documents",
        {
            "decisions": [
                {**_review(source), "disposition": "include"},
                *_exclusions(candidates, skip=source["source_id"]),
            ]
        },
    )
    handoff = call(tools, "finish_evidence")
    call(tools, "submit_answers", {"proposals": []})
    # Assembly after a process restart must retain the private inspection record.
    call(setup.tools(), "assemble_packet")

    reader.transcribe.assert_called_once()
    assert handoff["attachment_inspections"] == [inspected]
    assert handoff["scan_quotes"] == []
    manifest = json.loads(setup.artifact("attachment-manifest.json"))
    assert manifest["inspections"] == [inspected]
    assert source["source_id"] in manifest["selected_source_ids"]
    assert next(p for p in manifest["decisions"] if p["source_id"] == source["source_id"])[
        "inspected_pages"
    ] == [1]
    status = "identified" if partial else "readable"
    assert inspected["status"] == status
    assert any(f"status={status}" in event for event in events)
    assert f"status={status}" in caplog.text
    assert reader.transcribe.return_value.text not in caplog.text + "\n".join(events)


def test_unresolved_visual_inspection_becomes_an_actionable_reviewer_question(tmp_path: Path):
    reader = Mock()
    setup, tools, _ = setup_library(
        tmp_path,
        scan_reader=reader,
        evidence_limits=EvidenceLimits(max_ocr_pages=0),
        support_text="",
    )
    candidates = call(tools, "list_attachment_candidates")["sources"]
    source = next(c for c in candidates if c["family"] == "Bloomberg_League_Tables")
    call(tools, "read_page", {"source_id": source["source_id"], "page": 1})
    inspected = call(
        tools,
        "inspect_attachment_page",
        {
            "source_id": source["source_id"],
            "page": 1,
        },
    )
    call(
        tools,
        "plan_supporting_documents",
        {"decisions": [_review(source), *_exclusions(candidates, skip=source["source_id"])]},
    )
    json.loads(tools.call("finish_evidence", "{}"))
    call(tools, "plan_supporting_document", _review(source))
    call(tools, "finish_evidence")
    call(tools, "submit_answers", {"proposals": []})
    call(setup.tools(), "assemble_packet")

    reader.transcribe.assert_not_called()
    assert inspected["status"] == "budget_exhausted"
    summary = setup.artifact("reviewer-summary.txt").decode()
    assert source["path"] in summary and source["source_id"] in summary
    assert "page 1: budget_exhausted" in summary
    assert "Include / Exclude / Leave unresolved" in summary
    assert "Relevance depends on a role link" in summary
    assert (
        source["source_id"]
        not in json.loads(setup.artifact("attachment-manifest.json"))["selected_source_ids"]
    )


def test_agent_guidance_pairs_official_periods_with_latest_supplement():
    from bd_packet_builder.agent import AGENT_VERSION

    assert AGENT_VERSION == "packet-agent-v50"
    assert "most recent official full-period" in AGENT_INSTRUCTIONS
    assert "latest printed date" in AGENT_INSTRUCTIONS
    assert "review_required is provisional" in AGENT_INSTRUCTIONS
