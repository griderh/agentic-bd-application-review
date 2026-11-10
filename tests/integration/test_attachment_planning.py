import json
from pathlib import Path

from bd_packet_builder.agent import AGENT_INSTRUCTIONS
from bd_packet_builder.foundry import FoundryConfig
from bd_packet_builder.live import LiveRunRequest, prepare_live_run
from tests.integration.test_agent import Setup, blank_pdf
from tests.integration.test_historical_prefill import call
from tests.integration.test_retrieval import pdf


def setup_library(tmp_path: Path, *, collect_sources: bool = True):
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
            ["Synthetic support; as of December 31, 2025."],
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
    source_tools = setup.tools()
    sources = call(source_tools, "list_sources")["sources"] if collect_sources else []
    return setup, tools, sources


def test_attachment_candidates_accept_catalog_folders_with_spaces(tmp_path: Path):
    _, tools, _ = setup_library(tmp_path, collect_sources=False)

    candidates = call(tools, "list_attachment_candidates")["sources"]

    assert any(source["family"] == "Business Continuity Statement" for source in candidates)


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
    call(
        tools,
        "plan_supporting_document",
        {
            "family": bio["family"],
            "source_id": bio["source_id"],
            "disposition": "review_required",
            "requirement_ids": ["p1.name"],
            "inspected_pages": [1],
            "reason": "The available form does not establish whether this biography is relevant.",
            "limitation": "Do not infer a current representative assignment from the bio.",
        },
    )
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
    handoff = call(tools, "finish_evidence")
    assert handoff["attachment_plan"][0]["reason"].startswith("Relevant historical")
    call(tools, "submit_answers", {"proposals": []})
    call(tools, "assemble_packet")
    call(tools, "publish_results")
    manifest = json.loads(setup.artifact("attachment-manifest.json"))
    assert manifest["selected_source_ids"] == [source["source_id"]]
    assert bio["source_id"] not in manifest["selected_source_ids"]
    assert manifest["version"] == "attachment-plan-v3"
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
