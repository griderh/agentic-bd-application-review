import json
from pathlib import Path

from bd_packet_builder.foundry import FoundryConfig
from bd_packet_builder.live import LiveRunRequest, prepare_live_run
from tests.integration.test_agent import Setup, blank_pdf
from tests.integration.test_historical_prefill import call
from tests.integration.test_retrieval import pdf


def setup_library(tmp_path: Path):
    setup = Setup(tmp_path, blank_pdf())
    for folder in ("bios", "Bloomberg_League_Tables", "Cover_Letters", "Restricted_Financials"):
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
    tools = setup.tools()
    call(tools, "interpret_form")
    sources = call(tools, "list_sources")["sources"]
    return setup, tools, sources


def test_purpose_documents_are_accessible_but_restricted_and_cover_sources_are_not(tmp_path: Path):
    _, _, sources = setup_library(tmp_path)
    assert {s["family"] for s in sources} == {
        "FINRA_Certification",
        "bios",
        "Bloomberg_League_Tables",
    }


def test_attachment_plan_survives_publication_with_rationale_and_gaps(tmp_path: Path):
    setup, tools, sources = setup_library(tmp_path)
    source = next(s for s in sources if s["family"] == "Bloomberg_League_Tables")
    call(
        tools,
        "plan_supporting_document",
        {
            "family": source["family"],
            "source_id": source["source_id"],
            "disposition": "include",
            "requirement_ids": ["p1.name"],
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
    handoff = call(tools, "finish_evidence")
    assert handoff["attachment_plan"][0]["reason"].startswith("Relevant historical")
    call(tools, "submit_answers", {"proposals": []})
    call(tools, "assemble_packet")
    call(tools, "publish_results")
    manifest = json.loads(setup.artifact("attachment-manifest.json"))
    assert manifest["selected_source_ids"] == [source["source_id"]]
    assert any(p["disposition"] == "unavailable" for p in manifest["decisions"])
    assert source["source_id"] in setup.artifact("reviewer-summary.txt").decode()
    assert "Not a current ranking" in setup.artifact("reviewer-summary.txt").decode()


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
