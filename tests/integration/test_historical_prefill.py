import hashlib
import json
from contextlib import closing
from datetime import date
from io import BytesIO
from pathlib import Path
from unittest.mock import Mock

import pypdfium2 as pdfium
import pytest
from pypdf import PdfReader
from reportlab.lib.utils import ImageReader
from reportlab.pdfgen.canvas import Canvas

from bd_packet_builder.contracts import (
    AnswerProposal,
    Citation,
    CurrentEvidenceCheck,
    HistoricalBasis,
    Requirement,
    TextValue,
)
from bd_packet_builder.draft import DraftRequest
from bd_packet_builder.foundry import FoundryConfig
from bd_packet_builder.gate import validate_answers
from bd_packet_builder.history import (
    ArchiveEntry,
    ArchiveManifest,
    historical_inventory,
    historical_issues,
    with_historical_sources,
)
from bd_packet_builder.inventory import InventoryError, build_inventory, read_source_bytes
from bd_packet_builder.live import LiveRunRequest, prepare_live_run
from bd_packet_builder.scan import ScanTranscript
from tests.integration.test_agent import FakeMapper, Setup, blank_pdf

ARCHIVE_PATH = "bd_agreements/Completed/Broward/prior.pdf"
QUOTE = "Firm legal name: Insperex Fictional Securities LLC"


def archive(
    root: Path,
    *,
    evaluation: bool = False,
    scanned: bool = False,
    text: str = QUOTE,
    exhibits: bool = False,
    image_exhibit: bool = False,
) -> ArchiveManifest:
    target = root / ARCHIVE_PATH
    target.parent.mkdir(parents=True, exist_ok=True)
    canvas = Canvas(str(target), invariant=True)
    canvas.drawString(30, 700, text)
    canvas.drawString(30, 660, "PRIVATE PRIOR SIGNED PACKET - NEVER APPEND")
    if exhibits:
        canvas.showPage()
        canvas.drawString(30, 700, "Bloomberg League Table: Synthetic Agencies")
        canvas.drawString(30, 660, "Historical table as of 12/31/2025. Fictional data only.")
        canvas.showPage()
        canvas.drawString(30, 700, "Signature of authorized officer")
        canvas.drawString(30, 660, "DO NOT COPY THIS SIGNED FORM")
        canvas.drawString(
            30, 620, "This fictional form page is deliberately not a support exhibit."
        )
    canvas.save()
    if image_exhibit:
        from pypdf import PdfWriter

        original = target.read_bytes()
        with (
            pdfium.PdfDocument(original) as document,
            closing(document[1]) as page,
            closing(page.render(scale=2)) as bitmap,
            closing(bitmap.to_pil()) as image,
        ):
            stream = BytesIO()
            canvas = Canvas(stream, pagesize=(595.28, 841.89), invariant=True)
            canvas.drawImage(ImageReader(image), 0, 0, width=595.28, height=841.89)
            canvas.save()
        reader = PdfReader(BytesIO(original))
        writer = PdfWriter()
        writer.add_page(reader.pages[0])
        writer.add_page(PdfReader(BytesIO(stream.getvalue())).pages[0])
        writer.add_page(reader.pages[2])
        writer.write(target)
        writer.close()
    if scanned:
        with (
            pdfium.PdfDocument(target.read_bytes()) as document,
            closing(document[0]) as page,
            closing(page.render(scale=2)) as bitmap,
            closing(bitmap.to_pil()) as image,
        ):
            canvas = Canvas(str(target), invariant=True)
            canvas.drawImage(ImageReader(image), 0, 0, width=595.28, height=841.89)
            canvas.save()
    return ArchiveManifest(
        entries=(
            ArchiveEntry(
                path=ARCHIVE_PATH,
                sha256=hashlib.sha256(target.read_bytes()).hexdigest(),
                partition="evaluation" if evaluation else "reference",
                issuer="Broward",
                completed_on=date(2025, 10, 1),
            ),
        )
    )


def call(tools, name: str, arguments: dict | None = None) -> dict:
    response = json.loads(tools.call(name, json.dumps(arguments or {})))
    assert response["ok"], response
    return response["result"]


def prepare(
    tmp_path: Path, *, scanned: bool = False, exhibits: bool = False, image_exhibit: bool = False
):
    setup = Setup(tmp_path, blank_pdf(), FakeMapper())
    manifest = archive(
        setup.evidence_root, scanned=scanned, exhibits=exhibits, image_exhibit=image_exhibit
    )
    setup.manifest = prepare_live_run(
        setup.store,
        LiveRunRequest(
            blank_name="Synthetic questionnaire.pdf",
            requester_id="offline-test",
            evidence_set_id="history-test",
            issuer="Broward",
            historical_archive=manifest,
        ),
        setup.blank,
        setup.evidence_root,
        FoundryConfig(endpoint="https://example.openai.azure.com/openai/v1", deployment="test"),
    )
    tools = setup.tools()
    call(tools, "interpret_form")
    sources = call(tools, "list_sources")["sources"]
    historical = next(s for s in sources if s["family"] == "historical_reference")
    current = next(s for s in sources if s["family"] != "historical_reference")
    prior = (
        {
            "source_id": historical["source_id"],
            "page": 1,
            "quote": QUOTE,
            "start": 0,
            "end": len(QUOTE),
        }
        if scanned
        else call(
            tools, "locate_quote", {"source_id": historical["source_id"], "page": 1, "quote": QUOTE}
        )
    )
    current_quote = call(
        tools,
        "locate_quote",
        {"source_id": current["source_id"], "page": 1, "quote": QUOTE},
    )
    citation = {k: v for k, v in prior.items() if k != "occurrences"}
    check = {k: v for k, v in current_quote.items() if k != "occurrences"}
    basis = {
        "category": "firm_description",
        "context": "firm_wide",
        "prior_question": citation,
        "role": None,
        "current_checks": [
            {"citation": check, "finding": "not_corroborated", "explanation": "Review continuity"}
        ],
        "reviewer_confirmation": "Confirm the firm's name remains applicable.",
    }
    proposal = {
        "requirement_id": "p1.name",
        "outcome": "proposed",
        "value": {"kind": "text", "value": "Insperex Fictional Securities LLC"},
        "confidence": 0.9,
        "citations": [citation],
        "historical_basis": basis,
    }
    return setup, tools, manifest, current, historical, proposal


def test_current_comparison_document_is_attached_without_separate_selection(
    tmp_path: Path,
) -> None:
    setup, tools, _, current, _, proposal = prepare(tmp_path)
    call(tools, "finish_evidence")
    call(tools, "submit_answers", {"proposals": [proposal]})
    review = json.loads(setup.artifact("answer_review.json"))
    assert current["source_id"] in review["attachment_source_ids"]
    call(tools, "assemble_packet")
    call(tools, "publish_results")
    assert len(PdfReader(BytesIO(setup.artifact("packet.pdf"))).pages) == 2


def test_isolated_historical_exhibit_survives_handoff_and_recovery(tmp_path: Path) -> None:
    setup, tools, _, _, historical, proposal = prepare(tmp_path, exhibits=True)
    located = call(
        tools,
        "locate_quote",
        {
            "source_id": historical["source_id"],
            "page": 2,
            "quote": "Bloomberg League Table: Synthetic Agencies",
        },
    )
    title = {k: v for k, v in located.items() if k != "occurrences"}
    call(
        tools,
        "select_historical_exhibit",
        {
            "requirement_id": "p1.name",
            "source_id": historical["source_id"],
            "title": title["quote"],
            "pages": [2],
            "reason": "Historical supporting exhibit, not a current fact certification.",
            "limitation": "Printed as of 12/31/2025; does not establish a 2026 ranking.",
        },
    )
    call(tools, "finish_evidence")
    handoff = json.loads(setup.artifact("answer_handoff.json"))
    assert handoff["historical_exhibits"][0]["pages"] == [2]
    tools = setup.tools()
    call(tools, "submit_answers", {"proposals": [proposal]})
    call(tools, "assemble_packet")
    call(tools, "publish_results")
    packet = PdfReader(BytesIO(setup.artifact("packet.pdf")))
    text = "\n".join(p.extract_text() for p in packet.pages)
    assert len(packet.pages) == 3
    assert "Bloomberg League Table: Synthetic Agencies" in text
    assert "PRIVATE PRIOR SIGNED PACKET" not in text
    assert "DO NOT COPY THIS SIGNED FORM" not in text
    report = json.loads(setup.artifact("draft.json"))
    assert report["supporting_document_audit"][0]["historical_exhibits"]
    summary = setup.artifact("reviewer-summary.txt").decode()
    assert "does not establish a 2026 ranking" in summary
    assert "HISTORICAL EXHIBIT" in summary
    original = PdfReader(setup.evidence_root / ARCHIVE_PATH)
    assert packet.pages[-1].get_contents().get_data() == original.pages[1].get_contents().get_data()
    assert report["supporting_document_audit"][0]["missing_current_source_ids"] == []


def test_declared_reference_without_exhibit_is_visible_to_reviewer(tmp_path: Path) -> None:
    setup, tools, _, _, _, proposal = prepare(tmp_path)
    proposal["supporting_references"] = ["Fictional Securities"]
    call(tools, "finish_evidence")
    call(tools, "submit_answers", {"proposals": [proposal]})
    call(tools, "assemble_packet")
    report = json.loads(setup.artifact("draft.json"))
    assert report["written_requirements"] == ["p1.name"]
    audit = report["supporting_document_audit"][0]
    assert audit["referenced_support"] == ["Fictional Securities"]
    assert "referenced_exhibit_not_linked" in audit["issues"]
    assert "referenced_exhibit_not_linked" in setup.artifact("reviewer-summary.txt").decode()


def test_cross_municipality_index_survives_answering_handoff(tmp_path: Path) -> None:
    setup, tools, _, _, historical, _ = prepare(tmp_path)
    indexed = call(tools, "index_source", {"source_id": historical["source_id"]})
    assert indexed["historical_issuer"] == "Broward"
    assert (
        indexed["source_sha256"]
        == hashlib.sha256((setup.evidence_root / ARCHIVE_PATH).read_bytes()).hexdigest()
    )
    assert indexed["scope"] == "navigation_only_not_answer_evidence"
    call(tools, "finish_evidence")
    handoff = json.loads(setup.artifact("answer_handoff.json"))
    assert handoff["source_indexes"] == [indexed]
    assert setup.tools().answer_handoff()["source_indexes"] == [indexed]


def test_image_exhibit_uses_checked_title_not_scalar_subject_inference(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    setup, _, _, _, historical, proposal = prepare(tmp_path, exhibits=True, image_exhibit=True)
    monkeypatch.setattr("bd_packet_builder.ocr.shutil.which", lambda _: "/local/tesseract")
    title = "Bloomberg League Table: Synthetic Agencies"
    header = (
        "level\tpage_num\tblock_num\tpar_num\tline_num\tword_num\t"
        "left\ttop\twidth\theight\tconf\ttext\n"
    )
    tsv = header + "".join(
        f"5\t1\t1\t1\t1\t{i + 1}\t{20 + i * 100}\t20\t90\t30\t96\t{word}\n"
        for i, word in enumerate(title.split())
    )
    monkeypatch.setattr(
        "bd_packet_builder.ocr._execute",
        lambda command, *_: "tesseract 5.5.0\n" if "--version" in command else tsv,
    )
    reader = Mock()
    reader.transcribe.return_value = ScanTranscript(
        readable=True,
        subject=None,
        text=title,
        reporting_period=None,
    )
    tools = setup.tools(scan_reader=reader)
    call(
        tools,
        "select_historical_exhibit",
        {
            "requirement_id": "p1.name",
            "source_id": historical["source_id"],
            "title": title,
            "pages": [2],
            "reason": "Historical image exhibit only.",
            "limitation": "No numeric ranking or current period verified.",
        },
    )
    call(tools, "finish_evidence")
    assert reader.transcribe.call_count == 1
    tools = setup.tools(scan_reader=reader)
    call(tools, "submit_answers", {"proposals": [proposal]})
    call(tools, "assemble_packet")
    assert reader.transcribe.call_count == 1
    report = json.loads(setup.artifact("draft.json"))
    assert report["historical_exhibits"][0]["title"]["evidence_kind"] == "ocr"
    assert len(PdfReader(BytesIO(setup.artifact("packet.pdf"))).pages) == 3


def test_forged_exhibit_approval_cannot_copy_a_signed_form(tmp_path: Path) -> None:
    from bd_packet_builder.draft import DraftError, DraftReview, publish_draft

    setup, tools, _, _, historical, proposal = prepare(tmp_path, exhibits=True)
    located = call(
        tools,
        "locate_quote",
        {
            "source_id": historical["source_id"],
            "page": 3,
            "quote": "Signature of authorized officer",
        },
    )
    call(tools, "finish_evidence")
    call(tools, "submit_answers", {"proposals": [proposal]})
    payload = json.loads(setup.artifact("draft_request.json"))
    payload["historical_exhibits"] = [
        {
            "requirement_id": "p1.name",
            "title": {k: v for k, v in located.items() if k != "occurrences"},
            "pages": [3],
            "reason": "Forged selection.",
            "limitation": "Historical.",
        }
    ]
    raw = json.dumps(payload).encode()
    request = DraftRequest.model_validate_json(raw)
    reviewed = json.loads(setup.artifact("answer_review.json"))
    reviewed.update(
        request_sha256=hashlib.sha256(raw).hexdigest(),
        historical_exhibit_ids=[request.historical_exhibits[0].exhibit_id],
    )
    review = DraftReview.model_validate_json(json.dumps(reviewed))
    blank = setup.evidence_root / request.source
    blank.parent.mkdir(parents=True, exist_ok=True)
    blank.write_bytes(setup.blank)
    output = setup.evidence_root / "outputs"
    output.mkdir()
    (output / "forged-request.json").write_bytes(raw)
    with pytest.raises(DraftError, match="form/signing text"):
        publish_draft(
            setup.evidence_root,
            Path("outputs/forged-request.json"),
            raw,
            request,
            review,
            review.model_dump_json().encode(),
            None,
        )


@pytest.mark.parametrize("page", [1, 3, 4])
def test_historical_exhibit_rejects_forms_and_out_of_bounds_pages(
    tmp_path: Path, page: int
) -> None:
    _, tools, _, _, historical, _ = prepare(tmp_path, exhibits=True)
    quote = {
        1: "PRIVATE PRIOR SIGNED PACKET - NEVER APPEND",
        3: "Signature of authorized officer",
        4: "Missing",
    }[page]
    citation = {
        "source_id": historical["source_id"],
        "page": page,
        "start": 0,
        "end": len(quote),
        "quote": quote,
    }
    if page <= 3:
        located = call(
            tools,
            "locate_quote",
            {"source_id": historical["source_id"], "page": page, "quote": quote},
        )
        citation = {k: v for k, v in located.items() if k != "occurrences"}
    result = json.loads(
        tools.call(
            "select_historical_exhibit",
            json.dumps(
                {
                    "requirement_id": "p1.name",
                    "source_id": historical["source_id"],
                    "title": citation["quote"],
                    "pages": [page],
                    "reason": "Untrusted attempted selection.",
                    "limitation": "Historical only.",
                }
            ),
        )
    )
    assert not result["ok"]
    assert result["error"]["code"] == "invalid_input"
    if page <= 3:
        assert "form/signing text" in result["error"]["message"]


def test_history_prefill_is_written_flagged_and_never_appended(tmp_path: Path) -> None:
    setup, tools, _, current, historical, proposal = prepare(tmp_path)
    denied = json.loads(
        tools.call("select_attachment", json.dumps({"source_id": historical["source_id"]}))
    )
    assert not denied["ok"]
    call(tools, "select_attachment", {"source_id": current["source_id"]})
    call(tools, "finish_evidence")
    result = call(tools, "submit_answers", {"proposals": [proposal]})
    assert result["answered"] == 1
    call(tools, "assemble_packet")
    call(tools, "publish_results")
    packet = PdfReader(BytesIO(setup.artifact("packet.pdf")))
    assert len(packet.pages) == 2
    assert "Insperex Fictional Securities LLC" in packet.pages[0].extract_text()
    assert "PRIVATE PRIOR SIGNED PACKET" not in "\n".join(p.extract_text() for p in packet.pages)
    summary = setup.artifact("reviewer-summary.txt").decode()
    assert "HISTORICAL - CONTINUITY UNCONFIRMED" in summary
    assert "2025-10-01" in summary
    assert "Broward" in summary
    assert ARCHIVE_PATH in summary
    assert "Confirm the firm's name remains applicable." in summary
    report = json.loads(setup.artifact("draft.json"))
    assert report["answers"][0]["evidence_status"] == "historical_continuity_unconfirmed"
    assert report["render_checks"]["outside_allowed_regions_changed_pixels"] == 0
    assert setup.store.load(setup.manifest.run_id).outcome == "incomplete"


@pytest.mark.parametrize("issuer", ["Broward", "Broward County", "Other County"])
@pytest.mark.parametrize("role", ["Primary Representative", "Backup Representative"])
def test_broward_primary_assignment_resolves_printed_qualified_representative(
    tmp_path: Path, issuer: str, role: str
) -> None:
    setup, tools, _, _, _, proposal = prepare(tmp_path)
    proposal["historical_basis"].update(
        category="representative_assignment",
        context="issuer_specific",
        role=role,
    )
    call(tools, "finish_evidence")
    call(tools, "submit_answers", {"proposals": [proposal]})
    raw = json.loads(setup.artifact("draft_request.json"))
    raw["issuer"] = issuer
    raw["historical_archive"]["entries"][0]["issuer"] = issuer
    raw["requirements"]["requirements"][0].update(
        instruction="Printed Name & Title", required_signer_role="Qualified Representative"
    )
    raw["layout"]["responses"][0]["requirement"] = raw["requirements"]["requirements"][0]
    raw["navigation_context"] = {"p1.name": "Qualified Representative printed name and title."}
    # Use an independently resolved prior role citation; never change source text in place.
    prior = setup.evidence_root / ARCHIVE_PATH
    canvas = Canvas(str(prior), invariant=True)
    canvas.drawString(30, 700, "Primary Representative " + QUOTE)
    canvas.save()
    from bd_packet_builder.evidence import resolve_quote

    raw["historical_archive"]["entries"][0]["sha256"] = hashlib.sha256(
        prior.read_bytes()
    ).hexdigest()
    raw["sources"] = [s for s in raw["sources"] if s["path"] != ARCHIVE_PATH]
    raw["sources"].append(
        {"path": ARCHIVE_PATH, "sha256": raw["historical_archive"]["entries"][0]["sha256"]}
    )
    inventory = with_historical_sources(
        setup.evidence_root,
        build_inventory(setup.evidence_root),
        ArchiveManifest.model_validate_json(json.dumps(raw["historical_archive"])),
    )
    source = next(s for s in inventory.sources if s.path == ARCHIVE_PATH)
    with (
        pdfium.PdfDocument(prior) as document,
        closing(document[0]) as page,
        closing(page.get_textpage()) as textpage,
    ):
        text = textpage.get_text_bounded().replace("\r\n", "\n")
    quote = "Primary Representative " + QUOTE
    start = text.index(quote)
    citation = Citation(
        source_id=source.source_id, page=1, start=start, end=start + len(quote), quote=quote
    )
    resolve_quote(setup.evidence_root, inventory, citation.text_citation())
    raw["proposals"]["proposals"][0]["citations"] = [citation.model_dump(mode="json")]
    raw["proposals"]["proposals"][0]["historical_basis"]["prior_question"] = citation.model_dump(
        mode="json"
    )
    request = DraftRequest.model_validate_json(json.dumps(raw))
    decision = validate_answers(setup.evidence_root, request, "a" * 64).decisions[0]
    assert (decision.decision == "draft_verified") == (
        issuer != "Other County" and role == "Primary Representative"
    )


def test_source_listing_and_handoff_expose_document_context_not_answers(tmp_path: Path) -> None:
    setup, tools, _, _, _, _ = prepare(tmp_path)
    listing = call(tools, "list_sources")
    guidance = listing["source_context"]
    from bd_packet_builder.knowledge import knowledge_context

    assert guidance["version"] == "source-context-v7"
    assert guidance["domain_knowledge"]["sha256"] == knowledge_context()["sha256"]
    handoff = call(tools, "finish_evidence")
    assert handoff["source_context"] == guidance
    snapshot = json.loads(setup.artifact("domain_knowledge.json"))
    assert snapshot == knowledge_context()


def test_additional_historical_context_quote_need_not_repeat_the_answer(tmp_path: Path) -> None:
    setup, tools, _, _, historical, proposal = prepare(tmp_path)
    extra = call(
        tools,
        "locate_quote",
        {
            "source_id": historical["source_id"],
            "page": 1,
            "quote": "PRIVATE PRIOR SIGNED PACKET - NEVER APPEND",
        },
    )
    extra.pop("occurrences")
    proposal["citations"].append(extra)
    call(tools, "finish_evidence")
    call(tools, "submit_answers", {"proposals": [proposal]})
    review = json.loads(setup.artifact("answer_review.json"))
    assert review["decisions"][0]["decision"] == "draft_verified"


@pytest.mark.parametrize(
    ("change", "expected"),
    [
        ("conflict", "historical_current_contradiction"),
        ("missing_basis", "historical_context_required"),
        ("wrong_issuer", "historical_issuer_context_mismatch"),
        ("disclosure", "historical_sensitive_requirement"),
        ("personal_act", "historical_sensitive_requirement"),
        ("role", "historical_role_context_mismatch"),
        ("financial", "historical_sensitive_requirement"),
        ("unknown_current", "historical_current_check_unresolved"),
    ],
)
def test_history_gate_withholds_ineligible_reuse(
    tmp_path: Path, change: str, expected: str
) -> None:
    setup, tools, _, _, _, proposal = prepare(tmp_path)
    if change == "conflict":
        proposal["historical_basis"]["current_checks"][0]["finding"] = "contradicts"
    elif change == "missing_basis":
        proposal.pop("historical_basis")
    elif change == "wrong_issuer":
        proposal["historical_basis"]["context"] = "issuer_specific"
    elif change == "role":
        proposal["historical_basis"]["category"] = "representative_assignment"
        proposal["historical_basis"]["context"] = "issuer_specific"
        proposal["historical_basis"]["role"] = "Chief Compliance Officer"
    elif change == "unknown_current":
        proposal["historical_basis"]["current_checks"][0]["citation"]["source_id"] = "0" * 64
    call(tools, "finish_evidence")
    call(tools, "submit_answers", {"proposals": [proposal]})
    raw = json.loads(setup.artifact("draft_request.json"))
    if change in ("wrong_issuer", "disclosure", "personal_act", "financial"):
        if change == "wrong_issuer":
            raw["issuer"] = "Different issuer"
        else:
            instruction = {
                "disclosure": "Have you ever been subject to disciplinary action?",
                "personal_act": "I acknowledge receipt and review of the investment policy",
                "financial": "Current excess net capital",
            }[change]
            raw["requirements"]["requirements"][0]["instruction"] = instruction
            raw["layout"]["responses"][0]["requirement"]["instruction"] = instruction
    request = DraftRequest.model_validate_json(json.dumps(raw))
    review = validate_answers(setup.evidence_root, request, hashlib.sha256(b"test").hexdigest())
    assert review.decisions[0].decision == "withhold"
    assert expected in review.decisions[0].reason


def test_archive_evaluation_and_copies_never_become_inputs(tmp_path: Path) -> None:
    setup = Setup(tmp_path, blank_pdf())
    manifest = archive(setup.evidence_root, evaluation=True)
    assert historical_inventory(setup.evidence_root, manifest).sources == ()
    copied = setup.evidence_root / "bd_agreements/supporting_data/FINRA_Certification/copy.pdf"
    copied.write_bytes((setup.evidence_root / ARCHIVE_PATH).read_bytes())
    with pytest.raises(InventoryError, match="historical|Historical|archive|Archive"):
        historical_inventory(
            setup.evidence_root, manifest, current=build_inventory(setup.evidence_root)
        )


def test_historical_source_mutation_is_technical_failure(tmp_path: Path) -> None:
    setup = Setup(tmp_path, blank_pdf())
    manifest = archive(setup.evidence_root)
    inventory = historical_inventory(setup.evidence_root, manifest)
    (setup.evidence_root / ARCHIVE_PATH).write_bytes(b"changed")
    with pytest.raises(InventoryError, match="changed"):
        read_source_bytes(setup.evidence_root, inventory, inventory.sources[0].source_id)


def test_historical_basis_is_typed_not_freeform() -> None:
    with pytest.raises(ValueError):
        HistoricalBasis.model_validate({"category": "disclosure"})
    assert "historical_basis" in AnswerProposal.model_fields
    assert "source_id" in Citation.model_fields


def test_historical_ocr_context_uses_existing_blind_receipt_path(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    setup, _, _, _, historical, proposal = prepare(tmp_path, scanned=True)
    monkeypatch.setattr("bd_packet_builder.ocr.shutil.which", lambda _: "/local/tesseract")
    header = (
        "level\tpage_num\tblock_num\tpar_num\tline_num\tword_num\t"
        "left\ttop\twidth\theight\tconf\ttext\n"
    )
    tsv = header + "".join(
        f"5\t1\t1\t1\t1\t{i + 1}\t{20 + i * 100}\t20\t90\t30\t96\t{word}\n"
        for i, word in enumerate(QUOTE.split())
    )
    monkeypatch.setattr(
        "bd_packet_builder.ocr._execute",
        lambda command, *_: "tesseract 5.5.0\n" if "--version" in command else tsv,
    )
    reader = Mock()
    reader.transcribe.return_value = ScanTranscript(
        readable=True,
        subject="Insperex Fictional Securities LLC",
        text=QUOTE,
        reporting_period=None,
    )
    tools = setup.tools(scan_reader=reader)
    call(tools, "read_page", {"source_id": historical["source_id"], "page": 1})
    checked = call(
        tools,
        "verify_scan_quote",
        {
            "source_id": historical["source_id"],
            "page": 1,
            "quote": QUOTE,
            "expected_subject": "Insperex Fictional Securities LLC",
        },
    )
    proposal["citations"] = [checked["citation"]]
    proposal["historical_basis"]["prior_question"] = checked["citation"]
    call(tools, "finish_evidence")
    assert call(tools, "submit_answers", {"proposals": [proposal]})["answered"] == 1
    call(tools, "assemble_packet")
    report = json.loads(setup.artifact("draft.json"))
    assert report["written_requirements"] == ["p1.name"]
    packet = PdfReader(BytesIO(setup.artifact("packet.pdf")))
    assert len(packet.pages) == 2
    assert "Synthetic registration record" in packet.pages[1].extract_text()
    assert "Insperex Fictional Securities LLC" in packet.pages[0].extract_text()


@pytest.mark.parametrize(
    ("finding", "expected"),
    [
        ("corroborates", "currently_corroborated"),
        ("not_corroborated", "historical_continuity_unconfirmed"),
    ],
)
def test_current_and_historical_statuses_are_not_conflated(
    tmp_path: Path, finding: str, expected: str
) -> None:
    setup, tools, _, _, _, proposal = prepare(tmp_path)
    proposal["historical_basis"]["current_checks"][0]["finding"] = finding
    call(tools, "finish_evidence")
    call(tools, "submit_answers", {"proposals": [proposal]})
    review = json.loads(setup.artifact("answer_review.json"))
    assert review["decisions"][0]["evidence_status"] == expected


def test_old_reference_does_not_meet_current_reporting_period(tmp_path: Path) -> None:
    setup, tools, _, _, _, proposal = prepare(tmp_path)
    proposal["historical_basis"]["category"] = "reference"
    call(tools, "finish_evidence")
    call(tools, "submit_answers", {"proposals": [proposal]})
    raw = json.loads(setup.artifact("draft_request.json"))
    period = {"start": "2026-01-01", "end": "2026-10-29"}
    raw["requirements"]["requirements"][0]["requested_period"] = period
    raw["layout"]["responses"][0]["requirement"]["requested_period"] = period
    request = DraftRequest.model_validate_json(json.dumps(raw))
    review = validate_answers(setup.evidence_root, request, "0" * 64)
    assert review.decisions[0].decision == "withhold"
    assert "historical_current_period_requires_current_evidence" in review.decisions[0].reason


def test_writer_rechecks_historical_contradictions_even_with_forged_decision(
    tmp_path: Path,
) -> None:
    from bd_packet_builder.draft import DraftReview, publish_draft

    setup, tools, _, _, _, proposal = prepare(tmp_path)
    call(tools, "finish_evidence")
    call(tools, "submit_answers", {"proposals": [proposal]})
    payload = json.loads(setup.artifact("draft_request.json"))
    payload["proposals"]["proposals"][0]["historical_basis"]["current_checks"][0]["finding"] = (
        "contradicts"
    )
    raw = json.dumps(payload).encode()
    request = DraftRequest.model_validate_json(raw)
    review_data = json.loads(setup.artifact("answer_review.json"))
    review_data["request_sha256"] = hashlib.sha256(raw).hexdigest()
    review = DraftReview.model_validate_json(json.dumps(review_data))
    output = setup.evidence_root / "outputs"
    output.mkdir()
    (output / "request.json").write_bytes(raw)
    blank = setup.evidence_root / request.source
    blank.parent.mkdir(parents=True, exist_ok=True)
    blank.write_bytes(setup.blank)
    published = publish_draft(
        setup.evidence_root,
        Path("outputs/request.json"),
        raw,
        request,
        review,
        review.model_dump_json().encode(),
        None,
    )
    report = json.loads((published / "draft.json").read_bytes())
    assert report["written_requirements"] == []
    assert "historical_current_contradiction" in report["answers"][0]["issues"]


@pytest.mark.parametrize(
    ("current_issuer", "navigation", "expected"),
    [
        ("Broward", "Primary representative contact details", ()),
        (
            "Other issuer",
            "Primary representative contact details",
            ("historical_issuer_context_mismatch",),
        ),
        ("Broward", "Backup representative contact details", ("historical_role_context_mismatch",)),
    ],
)
def test_prior_assignments_match_issuer_and_role_not_registration(
    tmp_path: Path,
    current_issuer: str,
    navigation: str,
    expected: tuple[str, ...],
) -> None:
    from bd_packet_builder.evidence import extract_evidence

    setup = Setup(tmp_path, blank_pdf())
    quote = "Primary representative: Avery Example. Prior assignment stated by the business."
    manifest = archive(setup.evidence_root, text=quote)
    current = build_inventory(setup.evidence_root)
    inventory = with_historical_sources(setup.evidence_root, current, manifest)
    extracted = extract_evidence(setup.evidence_root, inventory)
    prior_source = inventory.sources[-1]
    prior_page = next(
        p for d in extracted.documents for p in d.pages if p.source_id == prior_source.source_id
    )
    current_source = inventory.sources[0]
    current_page = next(
        p for d in extracted.documents for p in d.pages if p.source_id == current_source.source_id
    )
    prior_cite = Citation(
        source_id=prior_source.source_id,
        page=1,
        start=prior_page.text.index(quote),
        end=prior_page.text.index(quote) + len(quote),
        quote=quote,
    )
    start = current_page.text.index(QUOTE)
    current_cite = Citation(
        source_id=current_source.source_id,
        page=1,
        start=start,
        end=start + len(QUOTE),
        quote=QUOTE,
    )
    proposal = AnswerProposal(
        requirement_id="name",
        outcome="proposed",
        value=TextValue(kind="text", value="Avery Example"),
        confidence=0.9,
        citations=(prior_cite,),
        historical_basis=HistoricalBasis(
            category="representative_assignment",
            context="issuer_specific",
            prior_question=prior_cite,
            role="Primary representative",
            current_checks=(
                CurrentEvidenceCheck(
                    citation=current_cite,
                    finding="not_corroborated",
                    explanation=(
                        "Firm identity does not confirm the prior representative assignment."
                    ),
                ),
            ),
            reviewer_confirmation="Confirm the designated primary representative is unchanged.",
        ),
    )
    requirement = Requirement(
        requirement_id="name",
        application_sha256="0" * 64,
        page=1,
        instruction="Name",
        kind="text",
    )
    issues, status = historical_issues(
        setup.evidence_root,
        inventory,
        manifest,
        current_issuer,
        requirement,
        proposal,
        navigation_context=navigation,
    )
    assert issues == expected
    assert status == ("unsupported" if expected else "historical_continuity_unconfirmed")
