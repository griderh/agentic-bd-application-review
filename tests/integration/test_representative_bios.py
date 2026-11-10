import json
from contextlib import closing
from io import BytesIO
from pathlib import Path
from unittest.mock import Mock

import pypdfium2 as pdfium
import pytest
from reportlab.lib.utils import ImageReader
from reportlab.pdfgen.canvas import Canvas

from bd_packet_builder.evidence_tools import EvidenceLimits
from bd_packet_builder.foundry import FoundryConfig
from bd_packet_builder.live import LiveRunRequest, prepare_live_run
from bd_packet_builder.scan import ScanTranscript
from bd_packet_builder.visual import VisualPage
from tests.integration.test_agent import FakeMapper, Setup, nbox, visual_item
from tests.integration.test_historical_prefill import call

PERSON = "Avery Example"
ROLE = "Primary representative"


FIELDS = ("title", "telephone", "email_address")


def setup_bios(
    tmp_path: Path,
    bios: dict[str, list[str]],
    *,
    scanned: bool = False,
    fields: tuple[str, ...] = (),
):
    buffer = BytesIO()
    canvas = Canvas(buffer, pagesize=(612, 792), invariant=True)
    canvas.drawString(40, 732, "Primary representative name")
    canvas.drawString(40, 682, "Backup representative name")
    for index, field in enumerate(fields):
        canvas.drawString(40, 632 - 50 * index, f"Primary representative {field}")
    canvas.save()
    mapping = VisualPage.model_validate_json(
        json.dumps(
            {
                "readable": True,
                "explanation": None,
                "items": [
                    visual_item(
                        "name", "Primary representative name", "text", nbox(40, 70, 400, 90)
                    ),
                    {
                        **visual_item(
                            "backup", "Backup representative name", "text", nbox(40, 120, 400, 140)
                        ),
                        "instruction_box": nbox(35, 95, 560, 115),
                    },
                    *(
                        visual_item(
                            field,
                            f"Primary representative {field}",
                            "text",
                            nbox(40, 170 + 50 * index, 400, 190 + 50 * index),
                        )
                        for index, field in enumerate(fields)
                    ),
                    visual_item("signature", "Signature", "signature", nbox(40, 350, 300, 380)),
                ],
            }
        )
    )
    setup = Setup(
        tmp_path,
        buffer.getvalue(),
        mapper=FakeMapper({1: mapping}),
        evidence_text=f"{ROLE}: {PERSON}. Synthetic assignment for offline verification only.",
    )
    assignment_path = (
        setup.evidence_root / "bd_agreements/supporting_data/FINRA_Certification/registration.pdf"
    )
    canvas = Canvas(str(assignment_path), invariant=True)
    canvas.drawString(40, 740, f"{ROLE}: {PERSON}")
    canvas.drawString(40, 720, f"Backup representative: {PERSON}")
    canvas.drawString(
        40, 700, "Synthetic employee assignment record for offline verification only."
    )
    canvas.save()
    for name, pages in bios.items():
        path = setup.evidence_root / f"bd_agreements/supporting_data/bios/{name}.pdf"
        path.parent.mkdir(parents=True, exist_ok=True)
        canvas = Canvas(str(path), invariant=True)
        for text in pages:
            if text:
                for i, line in enumerate(
                    text.splitlines()
                    + [
                        "Synthetic employee biography for offline verification only.",
                        "This fixture is not a real employee or an approved business record.",
                    ]
                ):
                    canvas.drawString(40, 740 - i * 18, line)
            canvas.showPage()
        canvas.save()
        if scanned:
            with (
                pdfium.PdfDocument(path.read_bytes()) as document,
                closing(document[0]) as page,
                closing(page.render(scale=2)) as bitmap,
                closing(bitmap.to_pil()) as image,
            ):
                canvas = Canvas(str(path), invariant=True)
                canvas.drawImage(ImageReader(image), 0, 0, width=595.28, height=841.89)
                canvas.save()
    setup.manifest = prepare_live_run(
        setup.store,
        LiveRunRequest(blank_name="Form.pdf", requester_id="test", evidence_set_id="bios"),
        setup.blank,
        setup.evidence_root,
        FoundryConfig(endpoint="https://synthetic.openai.azure.com/openai/v1", deployment="test"),
    )
    tools = setup.tools(allow_ocr=False)
    call(tools, "interpret_form")
    sources = call(tools, "list_sources")["sources"]
    assignment_source = next(s for s in sources if s["family"] == "FINRA_Certification")
    citation = call(
        tools,
        "locate_quote",
        {
            "source_id": assignment_source["source_id"],
            "page": 1,
            "quote": f"{ROLE}: {PERSON}",
        },
    )
    citation.pop("occurrences")
    request = {
        "role_requirement_id": "p1.name",
        "requirement_ids": ["p1.name"],
        "role": ROLE,
        "person": PERSON,
        "assignment": citation,
    }
    return setup, tools, sources, request


@pytest.mark.parametrize(
    ("bios", "status", "count"),
    [
        ({"unrelated-filename": [PERSON]}, "selected", 1),
        ({"Avery Example": ["Blair Example"]}, "missing_bio", 0),
        ({"reference": [f"Blair Example works with {PERSON}."]}, "bio_review_required", 0),
        ({"similar": ["Avery Examples"]}, "missing_bio", 0),
        ({"heading": ["MEET AVERY EXAMPLE"]}, "selected", 1),
        ({"heading": ["Name: Avery Example"]}, "selected", 1),
        ({"heading": ["Avery\nExample\nDirector"]}, "selected", 1),
        ({"heading": ["Biography of Avery Example\nDirector"]}, "selected", 1),
        ({"heading": ["Meet Avery Example of Example Securities"]}, "selected", 1),
        ({"similar": ["Avery Example-Smith"]}, "missing_bio", 0),
        ({"ambiguous": ["Avery Example and Blair Example"]}, "bio_review_required", 0),
        ({}, "missing_bio", 0),
        ({"old": [PERSON], "new": [PERSON + "\nAs of 2026-10-01"]}, "ambiguous_bio", 2),
    ],
)
def test_identity_and_version_selection_are_not_filename_guesses(tmp_path, bios, status, count):
    _, tools, _, request = setup_bios(tmp_path, bios)
    result = call(tools, "resolve_representative_bio", request)
    assert result["status"] == status
    assert len(result["candidates"]) == count
    assert (result["selected_source_id"] is not None) == (status == "selected")
    assert result["assignment_status"] == "explicit_source_assignment"
    assert result["currency"] == "not_confirmed"


def test_selection_is_hash_bound_and_survives_handoff_and_publication(tmp_path):
    setup, tools, sources, request = setup_bios(tmp_path, {"bio": [PERSON]})
    result = call(tools, "resolve_representative_bio", request)
    assert call(tools, "resolve_representative_bio", request) == result
    source = next(s for s in sources if s["family"] == "bios")
    assert result["selected_source_id"] == source["source_id"]
    snapshot = next(i for i in setup.manifest.evidence.items if i.path == source["path"])
    assert result["candidates"][0]["source_sha256"] == snapshot.sha256
    handoff = call(tools, "finish_evidence")
    assert handoff["representative_bios"] == [result]
    assert handoff["attachments"] == [source["source_id"]]  # Selected bios are mandatory.
    saved = json.loads(setup.artifact("representative_bios.json"))
    assert saved["resolutions"] == [result]
    tools = setup.tools()  # Assembly must use the persisted link, not discovery's memory.
    call(tools, "submit_answers", {"proposals": []})
    call(tools, "assemble_packet")
    assert source["source_id"] in setup.artifact("reviewer-summary.txt").decode()


@pytest.mark.parametrize("change", ["person", "role", "offset", "requirement", "signing"])
def test_assignment_must_be_supported_and_requirement_bound(tmp_path, change):
    _, tools, _, request = setup_bios(tmp_path, {"bio": [PERSON]})
    if change == "person":
        request["person"] = "Blair Example"
    elif change == "role":
        request["role"] = "Backup representative"
    elif change == "offset":
        request["assignment"]["start"] += 1
        request["assignment"]["end"] += 1
    elif change == "requirement":
        request["requirement_ids"] = ["unknown"]
        request["role_requirement_id"] = "unknown"
    else:
        request["role_requirement_id"] = "p1.signature"
        request["requirement_ids"] = ["p1.signature"]
    response = json.loads(tools.call("resolve_representative_bio", json.dumps(request)))
    assert not response["ok"]
    assert response["error"]["code"] == "invalid_input"


def test_unresolved_assignment_is_explicit_and_does_not_invent_a_person(tmp_path):
    setup, tools, _, request = setup_bios(tmp_path, {"bio": [PERSON]})
    request.update(person=None, assignment=None)
    result = call(tools, "resolve_representative_bio", request)
    assert result["status"] == "assignment_unresolved"
    assert result["candidates"] == []
    assert result["selected_source_id"] is None
    call(tools, "finish_evidence")
    assert any(
        e.code == "representative_assignment_unresolved" for e in tools.manifest().exceptions()
    )
    assert setup.artifact("representative_bios.json")


def test_unresolved_assignment_can_be_resolved_before_finishing_evidence(tmp_path):
    _, tools, _, request = setup_bios(tmp_path, {"bio": [PERSON]})
    unresolved = {**request, "person": None, "assignment": None}
    assert (
        call(tools, "resolve_representative_bio", unresolved)["status"] == "assignment_unresolved"
    )
    assert call(tools, "resolve_representative_bio", request)["status"] == "selected"
    changed = {**request, "person": "Blair Example"}
    response = json.loads(tools.call("resolve_representative_bio", json.dumps(changed)))
    assert not response["ok"]


def test_unreadable_candidate_does_not_turn_partial_search_into_unique_selection(tmp_path):
    _, tools, _, request = setup_bios(tmp_path, {"known": [PERSON], "scan": [""]})
    result = call(tools, "resolve_representative_bio", request)
    assert result["status"] == "bio_review_required"
    assert len(result["candidates"]) == 1
    assert result["selected_source_id"] is None
    assert result["issues"] == ["bio_identity_reading_unverified"]


def test_search_budget_exhaustion_is_an_explicit_partial_result(tmp_path):
    setup, _, _, request = setup_bios(tmp_path, {"bio": [PERSON]})
    tools = setup.tools(evidence_limits=EvidenceLimits(max_calls=1))
    result = call(tools, "resolve_representative_bio", request)
    assert result["status"] == "bio_review_required"
    assert result["issues"] == ["bio_search_incomplete"]
    assert result["selected_source_id"] is None


def test_cached_selection_cannot_hide_a_changed_source(tmp_path):
    setup, tools, sources, request = setup_bios(tmp_path, {"bio": [PERSON]})
    call(tools, "resolve_representative_bio", request)
    source = next(s for s in sources if s["family"] == "bios")
    path = setup.evidence_root / source["path"]
    path.write_bytes(path.read_bytes() + b"\n")
    result = json.loads(tools.call("resolve_representative_bio", json.dumps(request)))
    assert not result["ok"]
    assert tools.manifest().status == "failed"


def test_a_bio_cannot_assign_its_employee_to_an_application_role(tmp_path):
    _, tools, sources, request = setup_bios(tmp_path, {"bio": [f"{ROLE}: {PERSON}"]})
    source = next(s for s in sources if s["family"] == "bios")
    citation = call(
        tools,
        "locate_quote",
        {"source_id": source["source_id"], "page": 1, "quote": f"{ROLE}: {PERSON}"},
    )
    citation.pop("occurrences")
    request["assignment"] = citation
    result = json.loads(tools.call("resolve_representative_bio", json.dumps(request)))
    assert not result["ok"]
    assert "cannot establish" in result["error"]["message"]


def test_historical_assignment_remains_unconfirmed_and_requires_exact_role(tmp_path, monkeypatch):
    from tests.integration.test_historical_context import setup_page

    setup, tools, _, prior, _ = setup_page(tmp_path, monkeypatch)
    associations = call(
        tools, "read_historical_page", {"source_id": prior["source_id"], "page": 1}
    )["associations"]
    request = {
        "role_requirement_id": "p1.name",
        "requirement_ids": ["p1.name"],
        "role": ROLE,
        "person": PERSON,
        "assignment": associations[0]["answer_citation"],
        "historical_context": associations[0]["context_citation"],
    }
    result = call(tools, "resolve_representative_bio", request)
    assert result["assignment_status"] == "historical_assignment_unconfirmed"
    assert result["currency"] == "not_confirmed"
    assert result["status"] == "missing_bio"
    request["role_requirement_id"] = "p1.date"
    request["requirement_ids"] = ["p1.date"]
    response = json.loads(tools.call("resolve_representative_bio", json.dumps(request)))
    assert not response["ok"]
    request["role_requirement_id"] = "p1.name"
    request["requirement_ids"] = ["p1.name"]
    request["historical_context"] = associations[1]["context_citation"]
    response = json.loads(tools.call("resolve_representative_bio", json.dumps(request)))
    assert not response["ok"]


def test_two_roles_can_share_one_hash_bound_bio(tmp_path):
    setup, tools, _, request = setup_bios(tmp_path, {"bio": [PERSON], "copy": [PERSON]})
    first = call(tools, "resolve_representative_bio", request)
    assert first["status"] == "selected"
    assert len(first["candidates"]) == 1
    assert len(first["candidates"][0]["equivalent_source_ids"]) == 1
    citation = call(
        tools,
        "locate_quote",
        {
            "source_id": request["assignment"]["source_id"],
            "page": 1,
            "quote": f"Backup representative: {PERSON}",
        },
    )
    citation.pop("occurrences")
    request.update(
        role_requirement_id="p1.backup",
        requirement_ids=["p1.backup"],
        role="Backup representative",
        assignment=citation,
    )
    second = call(tools, "resolve_representative_bio", request)
    assert first["selected_source_id"] == second["selected_source_id"]
    handoff = call(tools, "finish_evidence")
    assert len(handoff["representative_bios"]) == 2


def test_omitting_bio_resolution_is_visible_not_silently_complete(tmp_path):
    setup, tools, _, _ = setup_bios(tmp_path, {"bio": [PERSON]})
    handoff = call(tools, "finish_evidence")
    assert handoff["unreviewed_representative_requirements"] == ["p1.name", "p1.backup"]
    assert {
        e.requirement_id
        for e in tools.manifest().exceptions()
        if e.code == "representative_bio_not_reviewed"
    } == {"p1.name", "p1.backup"}
    assert json.loads(setup.artifact("representative_bios.json"))["unreviewed_requirement_ids"] == [
        "p1.name",
        "p1.backup",
    ]


@pytest.mark.parametrize("tamper", [False, True])
def test_scanned_bio_needs_checked_person_identity(tmp_path, monkeypatch, tamper):
    setup, _, sources, request = setup_bios(tmp_path, {"bio": [PERSON]}, scanned=True)
    text = f"{PERSON} Synthetic employee biography for offline verification only."
    reader = Mock()
    reader.transcribe.return_value = ScanTranscript(
        readable=True, subject=PERSON, text=text, reporting_period=None
    )
    header = (
        "level\tpage_num\tblock_num\tpar_num\tline_num\tword_num\t"
        "left\ttop\twidth\theight\tconf\ttext\n"
    )
    tsv = header + "".join(
        f"5\t1\t1\t1\t1\t{i + 1}\t{40 + i * 120}\t100\t110\t40\t96\t{word}\n"
        for i, word in enumerate(text.split())
    )
    monkeypatch.setattr("bd_packet_builder.ocr.shutil.which", lambda _: "/local/tesseract")
    monkeypatch.setattr(
        "bd_packet_builder.ocr._execute",
        lambda command, *_: "tesseract 5.5.0\n" if "--version" in command else tsv,
    )
    tools = setup.tools(scan_reader=reader)
    source = next(s for s in sources if s["family"] == "bios")
    pending = call(tools, "resolve_representative_bio", request)
    assert pending["status"] == "bio_review_required"
    checked = call(
        tools,
        "verify_scan_quote",
        {
            "source_id": source["source_id"],
            "page": 1,
            "quote": PERSON,
            "expected_subject": PERSON,
        },
    )
    if tamper:
        artifact = setup.evidence_root / checked["citation"]["artifact_path"]
        artifact.write_bytes(artifact.read_bytes() + b"\n")
        result = json.loads(tools.call("resolve_representative_bio", json.dumps(request)))
        assert not result["ok"]
    else:
        result = call(tools, "resolve_representative_bio", request)
        assert result["status"] == "selected"
        assert result["candidates"][0]["identity"] == checked["citation"]
        call(tools, "finish_evidence")
        digest = checked["citation"]["artifact_sha256"]
        assert setup.artifact(f"ocr-{digest}.json")
    assert reader.transcribe.call_count == 1


CARD = f"{PERSON}\nDirector\nHead of Synthetic Sales\n(555) 010-0100\navery@example.test"


def profile_request(request):
    request["requirement_ids"] = ["p1.name", *(f"p1.{f}" for f in FIELDS)]
    request["field_requirements"] = [{"requirement_id": f"p1.{f}", "field": f} for f in FIELDS]
    return request


def test_selected_bio_card_grounds_mapped_fields_and_is_attached_once(tmp_path):
    setup, tools, _, request = setup_bios(tmp_path, {"bio": [CARD], "copy": [CARD]}, fields=FIELDS)
    result = call(tools, "resolve_representative_bio", profile_request(request))
    assert result["profile"]["status"] == "extracted"
    assert [line["kind"] for line in result["profile"]["lines"]] == [
        "title",
        "title",
        "telephone",
        "email_address",
    ]
    bio = result["selected_source_id"]
    copies = set(result["candidates"][0]["equivalent_source_ids"])
    assert copies
    handoff = call(tools, "finish_evidence")
    assert handoff["attachments"] == [bio]
    tools = setup.tools()  # Submission uses the persisted, hash-bound resolution.
    call(tools, "submit_answers", {"proposals": []})
    review = json.loads(setup.artifact("answer_review.json"))
    decisions = {d["requirement_id"]: d["decision"] for d in review["decisions"]}
    assert {decisions[f"p1.{f}"] for f in FIELDS} == {"draft_verified"}
    assert review["attachment_source_ids"] == [bio]
    proposals = {
        p["requirement_id"]: p
        for p in json.loads(setup.artifact("draft_request.json"))["proposals"]["proposals"]
    }
    assert proposals["p1.title"]["value"]["value"] == "Director, Head of Synthetic Sales"
    assert proposals["p1.telephone"]["value"]["value"] == "(555) 010-0100"
    assert proposals["p1.email_address"]["value"]["value"] == "avery@example.test"
    assert {c["source_id"] for f in FIELDS for c in proposals[f"p1.{f}"]["citations"]} == {bio}
    contacts = json.loads(setup.artifact("representative_contacts.json"))
    assert {r["requirement_id"]: r["decision"] for r in contacts["fields"]} == {
        f"p1.{f}": "bio_value_used" for f in FIELDS
    }
    call(tools, "assemble_packet")
    summary = setup.artifact("reviewer-summary.txt").decode()
    assert "REPRESENTATIVE TITLE AND CONTACT RECONCILIATION" in summary
    attachment_manifest = json.loads(setup.artifact("attachment-manifest.json"))
    assert attachment_manifest["selected_source_ids"] == [bio]
    decision = next(d for d in attachment_manifest["decisions"] if d["source_id"] == bio)
    assert decision["disposition"] == "include"
    assert "representative" in decision["reason"].lower()
    assert not copies & {
        d["source_id"] for d in attachment_manifest["decisions"] if d["disposition"] == "include"
    }


def test_a_bio_without_a_structural_card_is_attached_but_supplies_no_values(tmp_path):
    setup, tools, _, request = setup_bios(
        tmp_path, {"bio": [f"{PERSON}\n{PERSON} directs synthetic sales."]}, fields=FIELDS
    )
    result = call(tools, "resolve_representative_bio", profile_request(request))
    assert result["status"] == "selected"
    assert result["profile"]["status"] == "not_found"
    call(tools, "finish_evidence")
    call(tools, "submit_answers", {"proposals": []})
    review = json.loads(setup.artifact("answer_review.json"))
    decisions = {d["requirement_id"]: d["decision"] for d in review["decisions"]}
    assert {decisions[f"p1.{f}"] for f in FIELDS} == {"withhold"}
    assert review["attachment_source_ids"] == [result["selected_source_id"]]
    assert "representative_bio_card_not_found" in {e.code for e in tools.manifest().exceptions()}


def test_changed_bio_after_selection_is_a_technical_failure_not_a_packet(tmp_path):
    setup, tools, sources, request = setup_bios(tmp_path, {"bio": [CARD]}, fields=FIELDS)
    call(tools, "resolve_representative_bio", profile_request(request))
    call(tools, "finish_evidence")
    source = next(s for s in sources if s["family"] == "bios")
    path = setup.evidence_root / source["path"]
    path.write_bytes(path.read_bytes() + b"\n")
    tools = setup.tools()
    result = json.loads(tools.call("submit_answers", json.dumps({"proposals": []})))
    assert not result["ok"]
    assert tools.manifest().status == "failed"


@pytest.mark.parametrize("problem", ["identifier", "shared", "name"])
def test_field_mapping_must_be_text_unshared_and_not_the_name(tmp_path, problem):
    _, tools, _, request = setup_bios(tmp_path, {"bio": [CARD]}, fields=FIELDS)
    request = profile_request(request)
    if problem == "identifier":
        request["requirement_ids"].append("p1.signature")
        request["field_requirements"] = [{"requirement_id": "p1.signature", "field": "title"}]
    elif problem == "shared":
        call(tools, "resolve_representative_bio", request)
        citation = call(
            tools,
            "locate_quote",
            {
                "source_id": request["assignment"]["source_id"],
                "page": 1,
                "quote": f"Backup representative: {PERSON}",
            },
        )
        citation.pop("occurrences")
        request.update(
            role_requirement_id="p1.backup",
            requirement_ids=["p1.backup", "p1.title"],
            role="Backup representative",
            assignment=citation,
            field_requirements=[{"requirement_id": "p1.title", "field": "title"}],
        )
    else:
        request["field_requirements"] = [{"requirement_id": "p1.name", "field": "title"}]
    response = json.loads(tools.call("resolve_representative_bio", json.dumps(request)))
    assert not response["ok"]


def test_field_mappings_can_be_added_without_reassigning_the_person(tmp_path):
    _, tools, _, request = setup_bios(tmp_path, {"bio": [CARD]}, fields=FIELDS)
    first = call(tools, "resolve_representative_bio", request)
    assert first["request"]["field_requirements"] == []
    second = call(tools, "resolve_representative_bio", profile_request(request))
    assert len(second["request"]["field_requirements"]) == 3
