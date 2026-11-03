import json

import pytest

from bd_packet_builder.historical_context import HistoricalContextCheck
from bd_packet_builder.visual import NormalizedBox
from tests.integration.test_historical_context import box, setup_page
from tests.integration.test_historical_prefill import call


@pytest.mark.parametrize("label", ["Other", "Other (please specify)", "Alternative"])
@pytest.mark.parametrize(
    "change",
    [
        "none",
        "missing",
        "invented",
        "omit_option",
        "forged",
        "unverified_peer",
        "ambiguous_peer",
        "unmapped_peer",
        "unrelated_context",
    ],
)
@pytest.mark.parametrize("include_write_in_context", [False, True])
def test_merged_option_label_retains_separate_native_write_in(
    tmp_path,
    monkeypatch,
    label,
    change,
    include_write_in_context,
):
    from bd_packet_builder import ocr
    from bd_packet_builder.contracts import (
        AnswerProposal,
        ChoiceGroup,
        ChoiceOption,
        ChoiceWriteIn,
        HistoricalBasis,
        MultiSelectValue,
        Requirement,
    )
    from bd_packet_builder.draft import verify_historical_context
    from bd_packet_builder.history import with_historical_sources
    from bd_packet_builder.inventory import build_inventory

    offset = 400 if label == "Alternative" else 0
    wrapped = label == "Other (please specify)"
    setup, tools, reader, prior, _ = setup_page(
        tmp_path,
        monkeypatch,
        primary_question="Services",
        primary_answer=label,
        scanned_answer=True,
        control_state="selected",
        primary_write_in="Alpha\nBonds" if wrapped else "Alpha Bonds",
        primary_x_offset=offset * 600 // 1000,
        historical_policy="answer_first_review",
    )
    transcript = reader.transcribe.return_value
    first = transcript.historical_fields[0]
    first = first.model_copy(
        update={
            "answer": first.answer.model_copy(
                update={
                    "box": NormalizedBox.model_validate(box(290 + offset, 95, 390 + offset, 120))
                }
            ),
        }
    )
    if label == "Alternative" or wrapped:
        from bd_packet_builder.scan import HistoricalPagePart

        first = first.model_copy(
            update={
                "write_in": HistoricalPagePart(
                    text="Alpha Bonds",
                    box=NormalizedBox.model_validate(
                        box(395 + offset, 95, 550 + offset, 140 if wrapped else 120)
                    ),
                ),
            }
        )
    reader.transcribe.return_value = transcript.model_copy(
        update={
            "historical_fields": (first, *transcript.historical_fields[1:]),
        }
    )
    execute = ocr._execute

    def merged(command, *args):
        output = execute(command, *args)
        if "--version" in command:
            return output
        rows = []
        for line in output.splitlines():
            parts = line.split("\t")
            if len(parts) == 12 and parts[7] == "330":
                if parts[-1] == "Avery":
                    parts[-1] = label + "_Alpha"
                    parts[8] = "300"
                    parts[10] = "0"
                if parts[-1] == "Example":
                    parts[-1] = "Bonds"
                    parts[6] = str(1150 + offset * 2500 // 1000)
                    if wrapped:
                        parts[7] = "380"
                line = "\t".join(parts)
            rows.append(line)
        return "\n".join(rows) + "\n"

    monkeypatch.setattr(ocr, "_execute", merged)
    result = call(tools, "read_historical_page", {"source_id": prior["source_id"], "page": 1})
    assert label in [a["candidate_answer"] for a in result["associations"]], result["issues"]
    option = next(a for a in result["associations"] if a["candidate_answer"] == label)
    write_in = next(a for a in result["associations"] if a["candidate_answer"] == "Alpha Bonds")
    assert option["discrepancies"][0]["code"] == "historical_label_write_in_separated"
    assert " ".join(write_in["answer_citation"]["quote"].split()) == "Alpha Bonds"
    assert option["write_in"]["text"] == "Alpha Bonds"
    assert option["write_in"]["answer_citation"] == write_in["answer_citation"]
    call(tools, "finish_evidence")
    checks = [
        HistoricalContextCheck.model_validate_json(json.dumps(c))
        for c in json.loads(setup.artifact("historical_context_checks.json"))["checks"]
    ]
    assert any(c.field.write_in is not None for c in checks)
    inventory = with_historical_sources(
        setup.evidence_root,
        build_inventory(setup.evidence_root),
        setup.store.load(setup.manifest.run_id).request.historical_archive,
    )
    control = next(c for c in checks if c.field.control is not None)
    if change in ("unverified_peer", "ambiguous_peer", "unmapped_peer"):
        from bd_packet_builder.scan import HistoricalPagePart

        peer = control.field.model_copy(
            update={
                "question": control.field.question.model_copy(
                    update={
                        "box": control.field.question.box.model_copy(
                            update={"right": control.field.question.box.right + 1}
                        ),
                    }
                ),
                "answer": HistoricalPagePart(
                    text="Unmapped" if change == "unmapped_peer" else "Standard",
                    box=NormalizedBox.model_validate(box(600, 95, 700, 120)),
                ),
                "control": control.field.control.model_copy(
                    update={
                        "box": NormalizedBox.model_validate(box(570, 100, 590, 115)),
                        "state": "ambiguous" if change == "ambiguous_peer" else "selected",
                    }
                ),
                "write_in": None,
            }
        )
        checks = [
            c.model_copy(
                update={
                    "transcript": c.transcript.model_copy(
                        update={
                            "historical_fields": (*c.transcript.historical_fields, peer),
                        }
                    )
                }
            )
            for c in checks
        ]
        control = next(c for c in checks if c.field.control is not None)
    if change == "forged":
        checks = [
            c.model_copy(
                update={
                    "field": c.field.model_copy(
                        update={
                            "write_in": c.field.write_in.model_copy(
                                update={"text": "Forged Notes"}
                            ),
                        }
                    ),
                }
            )
            if c.field.write_in is not None
            else c
            for c in checks
        ]
        control = next(c for c in checks if c.field.control is not None)
    requirement = Requirement(
        requirement_id="services",
        application_sha256="a" * 64,
        page=1,
        instruction="Services",
        kind="multi_select",
        choices=ChoiceGroup(
            options=(
                ChoiceOption(option_id="other", label=label, instruction=label, write_in=True),
                ChoiceOption(option_id="standard", label="Standard", instruction="Standard"),
            )
        ),
    )
    proposal = AnswerProposal(
        requirement_id="services",
        outcome="proposed",
        confidence=0.9,
        value=MultiSelectValue(
            kind="multi_select",
            selected=("standard",) if change == "omit_option" else ("other",),
            write_ins=()
            if change in ("missing", "omit_option")
            else (
                ChoiceWriteIn(
                    option_id="other",
                    text="Invented Notes" if change == "invented" else "Alpha Bonds",
                ),
            ),
        ),
        citations=(
            control.answer,
            next(
                c.answer
                for c in checks
                if c.field.control is None and c.field.answer.text == "Alpha Bonds"
            ),
        ),
        historical_basis=HistoricalBasis(
            category="firm_description",
            context="firm_wide",
            role=None,
            prior_question=control.context_citation,
            additional_contexts=(
                (
                    next(
                        c.context_citation
                        for c in checks
                        if c.field.control is None
                        and c.field.answer.text
                        == ("Blair Example" if change == "unrelated_context" else "Alpha Bonds")
                    ),
                )
                if include_write_in_context or change == "unrelated_context"
                else ()
            ),
            current_checks=(),
            reviewer_confirmation="Confirm historical continuity.",
        ),
    )
    issues, snapshots = verify_historical_context(
        setup.evidence_root,
        inventory,
        proposal,
        tuple(checks),
        {},
        requirement,
        allow_disagreements=True,
    )
    assert (not issues and bool(snapshots)) == (change == "none"), issues
    if label != "Other":
        return
    import hashlib
    from io import BytesIO
    from pathlib import Path

    from pypdf import PdfReader
    from reportlab.pdfgen.canvas import Canvas

    from bd_packet_builder.draft import DraftRequest, publish_draft
    from bd_packet_builder.gate import validate_answers

    stream = BytesIO()
    canvas = Canvas(stream, pagesize=(600, 800), invariant=True)
    canvas.drawString(40, 700, "Services")
    for y, text in ((650, "Standard"), (610, "Other")):
        canvas.rect(40, y, 10, 10)
        canvas.drawString(60, y, text)
    canvas.line(110, 607, 400, 607)
    canvas.save()
    blank = stream.getvalue()
    digest = hashlib.sha256(blank).hexdigest()
    target = setup.evidence_root / "bd_agreements/Blank/choices.pdf"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(blank)
    requirement = requirement.model_copy(update={"application_sha256": digest})

    def region(left, bottom, right, top):
        return dict(
            page=1, left=float(left), bottom=float(bottom), right=float(right), top=float(top)
        )

    request = DraftRequest.model_validate_json(
        json.dumps(
            {
                "mode": "reviewed_evidence",
                "source": "bd_agreements/Blank/choices.pdf",
                "requirements": {"requirements": [requirement.model_dump(mode="json")]},
                "layout": {
                    "application_sha256": digest,
                    "responses": [
                        {
                            "requirement": requirement.model_dump(mode="json"),
                            "options": [
                                {
                                    "option_id": "standard",
                                    "control": "checkbox",
                                    "box": region(40, 650, 50, 660),
                                    "label_box": region(60, 647, 115, 664),
                                    "label_quote": "Standard",
                                },
                                {
                                    "option_id": "other",
                                    "control": "checkbox",
                                    "box": region(40, 610, 50, 620),
                                    "label_box": region(60, 607, 100, 624),
                                    "label_quote": "Other",
                                    "write_in_region": region(110, 608, 400, 626),
                                },
                            ],
                        }
                    ],
                },
                "proposals": {"proposals": [proposal.model_dump(mode="json")]},
                "sources": [{"path": s.path, "sha256": s.sha256} for s in inventory.sources],
                "attachments": [],
                "protected_regions": [],
                "historical_archive": setup.manifest.request.historical_archive.model_dump(
                    mode="json"
                ),
                "issuer": "Broward",
                "historical_policy": "answer_first_review",
            }
        )
    )
    raw = request.model_dump_json().encode()
    review = validate_answers(
        setup.evidence_root,
        request,
        hashlib.sha256(raw).hexdigest(),
        historical_context_checks=tuple(checks),
    )
    assert (review.decisions[0].decision == "draft_verified") == (change == "none"), (
        review.decisions[0].reason
    )
    decision = review.decisions[0].model_copy(
        update={
            "decision": "draft_verified",
            "evidence_support_confirmed": True,
            "source_approved": True,
            "placement_confirmed": True,
            "source_subject_confirmed": True,
            "ocr_visual_confirmed": True,
        }
    )
    stale = review.model_copy(update={"decisions": (decision,)})
    request_path = Path("outputs/choice-request.json")
    (setup.evidence_root / request_path).write_bytes(raw)
    output = publish_draft(
        setup.evidence_root,
        request_path,
        raw,
        request,
        stale,
        stale.model_dump_json().encode(),
        None,
    )
    report = json.loads((output / "draft.json").read_bytes())
    assert report["written_requirements"] == (["services"] if change == "none" else [])
    assert ("Alpha Bonds" in PdfReader(output / "draft-packet.pdf").pages[0].extract_text()) == (
        change == "none"
    )
    assert report["render_checks"]["outside_allowed_regions_changed_pixels"] == 0
