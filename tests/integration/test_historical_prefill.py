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
) -> ArchiveManifest:
    target = root / ARCHIVE_PATH
    target.parent.mkdir(parents=True, exist_ok=True)
    canvas = Canvas(str(target), invariant=True)
    canvas.drawString(30, 700, text)
    canvas.drawString(30, 660, "PRIVATE PRIOR SIGNED PACKET - NEVER APPEND")
    canvas.save()
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


def prepare(tmp_path: Path, *, scanned: bool = False):
    setup = Setup(tmp_path, blank_pdf(), FakeMapper())
    manifest = archive(setup.evidence_root, scanned=scanned)
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
    assert len(packet.pages) == 1
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
