import hashlib
import io
import json
from contextlib import closing
from pathlib import Path

import pypdfium2 as pdfium
import pytest
from reportlab.pdfgen.canvas import Canvas

from bd_packet_builder.draft import MarkPlacement, TextPlacement, run_draft
from bd_packet_builder.inventory import build_inventory
from bd_packet_builder.layout import PageBox
from bd_packet_builder.responses import NarrativeRegion


def make_pdf(path: Path, lines: list[tuple[float, float, str]], *, radio: bool = False) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    canvas = Canvas(str(path), pagesize=(612, 792), invariant=True)
    canvas.setFont("Helvetica", 10)
    for x, y, text in lines:
        canvas.drawString(x, y, text)
    for y in (610, 580):
        if radio:
            canvas.circle(50, y, 5)
        else:
            canvas.rect(45, y - 5, 10, 10)
    canvas.drawString(60, 608, "Treasury")
    canvas.drawString(60, 578, "Other")
    canvas.save()


def prepare(root: Path, *, long: bool = False, single: bool = False) -> tuple[Path, Path, dict]:
    source = Path("bd_agreements/Blank/form.pdf")
    make_pdf(
        root / source,
        [
            (40, 740, "Firm CRD:"),
            (40, 660, "Choose instruments."),
            (40, 510, "Describe services."),
            (40, 320, "Missing tax ID:"),
            (40, 200, "Authorized signature:"),
            (340, 200, "Signature date:"),
        ],
        radio=single,
    )
    proof = Path("bd_agreements/supporting_data/FINRA_Certification/proof.pdf")
    narrative = "Our fictional firm provides public-sector fixed-income services."
    if long:
        narrative = " ".join(
            f"Service {n}: fictional evidence-backed narrative." for n in range(150)
        )
    make_pdf(
        root / proof,
        [
            (40, 740, "CRD: 001234"),
            (40, 720, "Treasury and other: Fictional Notes."),
            (40, 700, narrative),
        ],
    )
    inventory = build_inventory(root)
    record = inventory.sources[0]
    with (
        pdfium.PdfDocument(str(root / proof)) as document,
        closing(document[0]) as page,
        closing(page.get_textpage()) as tp,
    ):
        evidence = tp.get_text_bounded().replace("\r\n", "\n")

    # Semantic support is an explicit fictional review assertion, not a quotation check.
    def citation(quote: str) -> dict:
        start = evidence.index(quote)
        return dict(
            source_id=record.source_id, page=1, start=start, end=start + len(quote), quote=quote
        )

    digest = hashlib.sha256((root / source).read_bytes()).hexdigest()
    definitions = [
        ("crd", "Firm CRD:", "identifier"),
        ("instruments", "Choose instruments.", "single_select" if single else "multi_select"),
        ("services", "Describe services.", "narrative"),
        ("missing", "Missing tax ID:", "identifier"),
        ("sign", "Authorized signature:", "signature"),
        ("date", "Signature date:", "signature_date"),
    ]
    reqs: list[dict[str, object]] = [
        dict(requirement_id=key, application_sha256=digest, page=1, instruction=label, kind=kind)
        for key, label, kind in definitions
    ]
    reqs[1]["choices"] = {
        "options": [
            dict(option_id="treasury", label="Treasury", instruction="Treasury"),
            dict(option_id="other", label="Other", instruction="Other", write_in=True),
        ]
    }

    def region(left: float, bottom: float, right: float, top: float) -> dict:
        return dict(page=1, left=left, bottom=bottom, right=right, top=top)

    placements = [
        dict(requirement=reqs[0], text_region=region(120.0, 730.0, 400.0, 748.0)),
        dict(
            requirement=reqs[1],
            options=[
                dict(
                    option_id="treasury",
                    control="radio" if single else "checkbox",
                    box=region(45.0, 605.0, 55.0, 615.0),
                    label_box=region(60.0, 602.0, 120.0, 620.0),
                    label_quote="Treasury",
                ),
                dict(
                    option_id="other",
                    control="radio" if single else "checkbox",
                    box=region(45.0, 575.0, 55.0, 585.0),
                    label_box=region(60.0, 572.0, 100.0, 590.0),
                    label_quote="Other",
                    write_in_region=region(110.0, 573.0, 400.0, 589.0),
                ),
            ],
        ),
        dict(requirement=reqs[2], narrative_region=region(40.0, 400.0, 550.0, 490.0)),
        dict(requirement=reqs[3], text_region=region(140.0, 305.0, 400.0, 323.0)),
    ]
    proposals = [
        dict(
            requirement_id="crd",
            outcome="proposed",
            value=dict(kind="identifier", value="001234"),
            confidence=0.9,
            citations=[citation("CRD: 001234")],
        ),
        dict(
            requirement_id="instruments",
            outcome="proposed",
            value=dict(
                kind="single_select" if single else "multi_select",
                selected=["treasury"] if single else ["treasury", "other"],
                write_ins=[] if single else [dict(option_id="other", text="Fictional Notes")],
            ),
            confidence=0.9,
            citations=[citation("Treasury and other: Fictional Notes.")],
        ),
        dict(
            requirement_id="services",
            outcome="proposed",
            value=dict(kind="narrative", value=narrative),
            confidence=0.9,
            citations=[citation("CRD: 001234")],
        ),
    ]
    proposals.extend(
        dict(requirement_id=key, outcome=outcome, explanation="Leave blank.")
        for key, outcome in [
            ("missing", "missing_evidence"),
            ("sign", "deferred_to_signing"),
            ("date", "deferred_to_signing"),
        ]
    )
    data = dict(
        schema_version=1,
        mode="fictional",
        source=source.as_posix(),
        requirements={"requirements": reqs},
        layout=dict(application_sha256=digest, responses=placements),
        proposals={"proposals": proposals},
        sources=[dict(path=proof.as_posix(), sha256=record.sha256)],
        attachments=[record.source_id],
        protected_regions=[region(35.0, 180.0, 575.0, 225.0)],
    )
    request = root / "outputs/request.json"
    request.parent.mkdir()
    request.write_text(json.dumps(data))
    review = root / "outputs/review.json"
    write_review(request, review)
    return request, review, data


def write_review(request: Path, review: Path, *, approve: bool = True) -> None:
    review.write_text(
        json.dumps(
            dict(
                request_sha256=hashlib.sha256(request.read_bytes()).hexdigest(),
                reviewer="Fictional test fixture; not business approval",
                attachment_source_ids=json.loads(request.read_text())["attachments"],
                decisions=[
                    dict(
                        requirement_id=key,
                        decision="draft_verified" if approve else "withhold",
                        evidence_support_confirmed=approve,
                        source_approved=approve,
                        placement_confirmed=approve,
                        source_subject_confirmed=approve,
                        ocr_visual_confirmed=approve,
                        confirmed_source_subject="Fictional test source",
                        reason="Controlled fictional test only.",
                    )
                    for key in ("crd", "instruments", "services")
                ],
            )
        )
    )


def add_ocr_citation(
    root: Path,
    request_path: Path,
    data: dict,
    requirement_id: str,
    quote: str = "CRD: 001234",
) -> Path:
    inventory = build_inventory(root, families=("FINRA_Certification",), max_sources=1)
    record = inventory.sources[0]
    source_path = root / record.path
    with (
        pdfium.PdfDocument(str(source_path)) as document,
        closing(document[0]) as page,
        closing(page.render(scale=300 / 72)) as bitmap,  # pyright: ignore[reportArgumentType]
        closing(bitmap.to_pil()) as image,
    ):
        rendered = io.BytesIO()
        image.save(rendered, format="PNG")
        width, height = image.size
    words = [
        dict(
            text=word,
            confidence=96.0,
            left=20 + index * 80,
            top=20,
            width=70,
            height=20,
            block=1,
            paragraph=1,
            line=1,
        )
        for index, word in enumerate(("CRD:", "001234"))
    ]
    artifact = dict(
        schema_version=1,
        status="ocr_feasibility_unverified_not_answers",
        source=record.__dict__,
        page=1,
        engine="tesseract",
        engine_version="5.5.0",
        language="eng",
        dpi=300,
        page_segmentation_mode=6,
        image_width=width,
        image_height=height,
        coordinate_system="rendered_pixels_top_left_not_pdf_points",
        render_sha256=hashlib.sha256(rendered.getvalue()).hexdigest(),
        limits=dict(timeout_seconds=30, max_pixels=20_000_000, max_output_bytes=4_000_000),
        words=words,
        text="CRD: 001234",
        flags=["ocr_unverified", "not_semantic_grounding"],
    )
    artifact_path = root / f"outputs/ocr-{'1' * 32}/ocr.json"
    artifact_path.parent.mkdir(parents=True, exist_ok=True)
    artifact_path.write_text(json.dumps(artifact))
    citation = dict(
        evidence_kind="ocr",
        source_id=record.source_id,
        source_sha256=record.sha256,
        page=1,
        artifact_path=f"outputs/ocr-{'1' * 32}/ocr.json",
        artifact_sha256=hashlib.sha256(artifact_path.read_bytes()).hexdigest(),
        render_sha256=artifact["render_sha256"],
        word_start=0,
        word_end=2,
        quote=quote,
    )
    proposal = next(
        p for p in data["proposals"]["proposals"] if p["requirement_id"] == requirement_id
    )
    proposal["citations"] = [citation]
    request_path.write_text(json.dumps(data))
    return artifact_path


def execute(root: Path, request: Path, review: Path) -> Path:
    return run_draft(root, request.relative_to(root), review.relative_to(root))


def test_reviewed_ocr_citation_can_support_exact_identifier(tmp_path: Path) -> None:
    request, review, data = prepare(tmp_path)
    artifact = add_ocr_citation(tmp_path, request, data, "crd")
    write_review(request, review)
    output = execute(tmp_path, request, review)
    manifest = json.loads((output / "draft.json").read_text())
    assert "crd" in manifest["written_requirements"]
    answer = next(item for item in manifest["answers"] if item["requirement_id"] == "crd")
    assert answer["ocr_evidence"][0]["quote"] == "CRD: 001234"
    assert "ocr_citation_requires_local_review" in answer["citation_check"]["issues"]
    assert (
        answer["ocr_evidence"][0]["artifact_sha256"]
        == hashlib.sha256(artifact.read_bytes()).hexdigest()
    )


@pytest.mark.parametrize(
    ("tamper", "expected_issue"),
    [
        ("artifact_sha256", "ocr_artifact_hash_mismatch"),
        ("source_sha256", "ocr_source_version_mismatch"),
        ("render_sha256", "ocr_render_mismatch"),
        ("quote", "ocr_quote_mismatch"),
    ],
)
def test_invalid_ocr_evidence_is_withheld_while_native_work_continues(
    tmp_path: Path, tamper: str, expected_issue: str
) -> None:
    request, review, data = prepare(tmp_path)
    artifact = add_ocr_citation(tmp_path, request, data, "crd")
    request_data = json.loads(request.read_text())
    citation = request_data["proposals"]["proposals"][0]["citations"][0]
    if tamper == "artifact_sha256":
        citation["artifact_sha256"] = "0" * 64
    elif tamper == "source_sha256":
        citation["source_sha256"] = "0" * 64
    elif tamper == "render_sha256":
        citation["render_sha256"] = "0" * 64
    else:
        citation["quote"] = "CRD: 999999"
    request.write_text(json.dumps(request_data))
    write_review(request, review)
    output = execute(tmp_path, request, review)
    manifest = json.loads((output / "draft.json").read_text())
    assert "crd" not in manifest["written_requirements"]
    assert "instruments" in manifest["written_requirements"]
    answer = next(item for item in manifest["answers"] if item["requirement_id"] == "crd")
    assert expected_issue in answer["issues"]
    assert artifact.is_file()


def test_ocr_artifact_mutation_during_render_prevents_publication(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import bd_packet_builder.draft as module

    request, review, data = prepare(tmp_path)
    artifact = add_ocr_citation(tmp_path, request, data, "crd")
    write_review(request, review)
    original = module._render_checks

    def mutate(
        original_data: bytes,
        packet: bytes,
        output: Path,
        allowed: list[PageBox | NarrativeRegion],
        marks: list[MarkPlacement],
        texts: list[TextPlacement],
    ) -> dict[str, object]:
        result = original(original_data, packet, output, allowed, marks, texts)
        artifact.write_bytes(artifact.read_bytes() + b" ")
        return result

    monkeypatch.setattr(module, "_render_checks", mutate)
    with pytest.raises(ValueError, match="OCR evidence changed"):
        execute(tmp_path, request, review)
    assert not list((tmp_path / "outputs").glob("draft-*"))
    assert not list((tmp_path / "outputs").glob(".staging-*"))


def test_ocr_draft_requires_explicit_subject_and_visual_review(tmp_path: Path) -> None:
    request, review, data = prepare(tmp_path)
    add_ocr_citation(tmp_path, request, data, "crd")
    write_review(request, review)
    review_data = json.loads(review.read_text())
    decision = next(item for item in review_data["decisions"] if item["requirement_id"] == "crd")
    decision["source_subject_confirmed"] = False
    review.write_text(json.dumps(review_data))
    output = execute(tmp_path, request, review)
    manifest = json.loads((output / "draft.json").read_text())
    assert "crd" not in manifest["written_requirements"]
    answer = next(item for item in manifest["answers"] if item["requirement_id"] == "crd")
    assert "ocr_source_subject_not_confirmed" in answer["issues"]

    write_review(request, review)
    review_data = json.loads(review.read_text())
    decision = next(item for item in review_data["decisions"] if item["requirement_id"] == "crd")
    decision["confirmed_source_subject"] = None
    review.write_text(json.dumps(review_data))
    output = execute(tmp_path, request, review)
    manifest = json.loads((output / "draft.json").read_text())
    assert "crd" not in manifest["written_requirements"]
    answer = next(item for item in manifest["answers"] if item["requirement_id"] == "crd")
    assert "ocr_source_subject_not_confirmed" in answer["issues"]

    write_review(request, review)
    review_data = json.loads(review.read_text())
    decision = next(item for item in review_data["decisions"] if item["requirement_id"] == "crd")
    decision["ocr_visual_confirmed"] = False
    review.write_text(json.dumps(review_data))
    output = execute(tmp_path, request, review)
    manifest = json.loads((output / "draft.json").read_text())
    assert "crd" not in manifest["written_requirements"]
    answer = next(item for item in manifest["answers"] if item["requirement_id"] == "crd")
    assert "ocr_visual_review_not_confirmed" in answer["issues"]


def test_draft_writes_reviewed_values_and_separates_report(tmp_path: Path) -> None:
    request, review, _ = prepare(tmp_path)
    original = (tmp_path / "bd_agreements/Blank/form.pdf").read_bytes()
    output = execute(tmp_path, request, review)
    manifest = json.loads((output / "draft.json").read_text())
    assert manifest["status"] == "incomplete_draft_not_for_submission"
    assert manifest["written_requirements"] == ["crd", "instruments", "services"]
    assert manifest["signature_policy"] == "signatures_and_signature_dates_left_blank"
    assert manifest["pagination"]["sections"][-1]["role"] == "evidence"
    assert manifest["render_checks"]["outside_allowed_regions_changed_pixels"] == 0
    assert (output / "reviewer-summary.txt").exists()
    with pdfium.PdfDocument(str(output / "draft-packet.pdf")) as doc:
        assert len(doc) == 2
        with closing(doc[0]) as page, closing(page.get_textpage()) as text:
            value = text.get_text_bounded()
            assert "001234" in value and "Fictional Notes" in value
            assert "NOT FOR SUBMISSION" in value
            assert "INTERNAL REVIEW" not in value
        with closing(doc[1]) as page, closing(page.get_textpage()) as text:
            assert "CRD: 001234" in text.get_text_bounded()
    assert (tmp_path / "bd_agreements/Blank/form.pdf").read_bytes() == original
    assert (output / "page-1-after.png").exists()
    assert (output / "page-1-before.png").exists()


def test_reviewer_notes_stay_in_internal_report_and_out_of_packet(tmp_path: Path) -> None:
    request, review, _ = prepare(tmp_path)
    review_data = json.loads(review.read_text())
    review_data["reviewer_notes"] = ["Fictional test exception; inspect before attestation."]
    review.write_text(json.dumps(review_data))
    output = execute(tmp_path, request, review)
    summary = (output / "reviewer-summary.txt").read_text()
    assert "Fictional test exception; inspect before attestation." in summary
    manifest = json.loads((output / "draft.json").read_text())
    assert manifest["review"]["reviewer_notes"] == [
        "Fictional test exception; inspect before attestation."
    ]
    with (
        pdfium.PdfDocument(str(output / "draft-packet.pdf")) as document,
        closing(document[0]) as page,
        closing(page.get_textpage()) as text,
    ):
        assert "Fictional test exception" not in text.get_text_bounded()


def test_long_narrative_has_real_supplement_and_final_attachment_reference(tmp_path: Path) -> None:
    request, review, _ = prepare(tmp_path, long=True)
    output = execute(tmp_path, request, review)
    manifest = json.loads((output / "draft.json").read_text())
    narrative = manifest["placements"]["services"]
    assert narrative["mode"] == "supplement"
    section = manifest["pagination"]["sections"][1]
    assert section["role"] == "supplemental_answers" and section["page_count"] >= 2
    with pdfium.PdfDocument(str(output / "draft-packet.pdf")) as doc:
        texts = []
        for i in range(len(doc)):
            with closing(doc[i]) as page, closing(page.get_textpage()) as text:
                texts.append(text.get_text_bounded().replace("\r\n", "\n"))
    assert "packet page 2" in texts[0]
    assert "Service 149:" in "\n".join(texts[1:-1])
    assert f"packet page {len(texts)}" in "\n".join(texts[1:-1])


@pytest.mark.parametrize(
    "problem", ["review-hash", "source-hash", "form-hash", "signature", "overlap"]
)
def test_draft_rejects_invalid_handoff_without_publishing(tmp_path: Path, problem: str) -> None:
    request, review, data = prepare(tmp_path)
    if problem == "review-hash":
        request.write_text(request.read_text() + " ")
    else:
        if problem == "source-hash":
            data["sources"][0]["sha256"] = "0" * 64
        elif problem == "form-hash":
            (tmp_path / data["source"]).write_bytes(b"changed")
        elif problem == "signature":
            data["layout"]["responses"][0]["requirement"] = data["requirements"]["requirements"][4]
        else:
            data["layout"]["responses"][0]["text_region"].update(bottom=190.0, top=210.0)
        request.write_text(json.dumps(data))
        write_review(request, review)
    with pytest.raises(ValueError):
        execute(tmp_path, request, review)
    assert not list((tmp_path / "outputs").glob("draft-*"))


def test_unreviewed_answers_stay_blank_without_stopping_packet(tmp_path: Path) -> None:
    request, review, _ = prepare(tmp_path)
    write_review(request, review, approve=False)
    output = execute(tmp_path, request, review)
    manifest = json.loads((output / "draft.json").read_text())
    assert manifest["written_requirements"] == []
    assert any("withheld" in item["issues"] for item in manifest["answers"])


def test_render_failure_leaves_no_partial_run(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import bd_packet_builder.draft as module

    request, review, _ = prepare(tmp_path)

    def fail(
        _original_data: bytes,
        _packet: bytes,
        _output: Path,
        _allowed: list[PageBox | NarrativeRegion],
        _marks: list[MarkPlacement],
        _texts: list[TextPlacement],
    ) -> None:
        _ = (_original_data, _packet, _output, _allowed, _marks, _texts)
        raise OSError("synthetic render failure")

    monkeypatch.setattr(module, "_render_checks", fail)
    with pytest.raises(OSError):
        execute(tmp_path, request, review)
    assert not list((tmp_path / "outputs").glob("draft-*"))
    assert not list((tmp_path / "outputs").glob(".staging-*"))


def test_reviewed_text_region_cannot_cover_an_issuer_label(tmp_path: Path) -> None:
    request, review, data = prepare(tmp_path)
    data["layout"]["responses"][0]["text_region"]["left"] = 40.0
    request.write_text(json.dumps(data))
    write_review(request, review)
    with pytest.raises(ValueError, match="issuer text"):
        execute(tmp_path, request, review)
    assert not list((tmp_path / "outputs").glob("draft-*"))


@pytest.mark.parametrize("problem", ["quote", "identifier", "choice", "fit", "font"])
def test_bad_answers_are_withheld_while_other_supported_work_continues(
    tmp_path: Path,
    problem: str,
) -> None:
    request, review, data = prepare(tmp_path)
    proposal = data["proposals"]["proposals"][0]
    if problem == "quote":
        proposal["citations"][0]["quote"] = "CRD: 999999"
    elif problem == "identifier":
        proposal["value"]["value"] = "999999"
    elif problem == "choice":
        data["proposals"]["proposals"][1]["value"]["selected"] = ["unknown"]
        data["proposals"]["proposals"][1]["value"]["write_ins"] = []
    elif problem == "fit":
        data["proposals"]["proposals"][1]["value"]["write_ins"][0]["text"] = "W" * 200
    else:
        data["proposals"]["proposals"][1]["value"]["write_ins"][0]["text"] = "Fictional \u2603"
    request.write_text(json.dumps(data))
    write_review(request, review)
    output = execute(tmp_path, request, review)
    manifest = json.loads((output / "draft.json").read_text())
    bad_id = "crd" if problem in ("quote", "identifier") else "instruments"
    assert bad_id not in manifest["written_requirements"]
    assert "services" in manifest["written_requirements"]
    assert any(
        item["requirement_id"] == bad_id and item["status"] == "blank" and item["issues"]
        for item in manifest["answers"]
    )


def test_unapproved_attachment_is_omitted_and_cannot_support_written_answers(
    tmp_path: Path,
) -> None:
    request, review, _ = prepare(tmp_path)
    data = json.loads(review.read_text())
    data["attachment_source_ids"] = []
    review.write_text(json.dumps(data))
    output = execute(tmp_path, request, review)
    manifest = json.loads((output / "draft.json").read_text())
    assert manifest["written_requirements"] == []
    assert len(manifest["unapproved_attachments_omitted"]) == 1
    assert manifest["pagination"]["sections"][-1]["role"] == "form"
    assert any("supporting_evidence_not_attached" in item["issues"] for item in manifest["answers"])


@pytest.mark.parametrize("target", ["request", "review", "source", "blank"])
def test_changes_during_rendering_prevent_atomic_publication(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    target: str,
) -> None:
    import bd_packet_builder.draft as module
    from bd_packet_builder.inventory import InventoryError

    request, review, data = prepare(tmp_path)
    original = module._render_checks

    def mutate(
        original_data: bytes,
        packet: bytes,
        output: Path,
        allowed: list[PageBox | NarrativeRegion],
        marks: list[MarkPlacement],
        texts: list[TextPlacement],
    ) -> dict[str, object]:
        result = original(original_data, packet, output, allowed, marks, texts)
        path = {
            "request": request,
            "review": review,
            "source": tmp_path / data["sources"][0]["path"],
            "blank": tmp_path / data["source"],
        }[target]
        path.write_bytes(path.read_bytes() + b" ")
        return result

    monkeypatch.setattr(module, "_render_checks", mutate)
    with pytest.raises((ValueError, InventoryError)):
        execute(tmp_path, request, review)
    assert not list((tmp_path / "outputs").glob("draft-*"))
    assert not list((tmp_path / "outputs").glob(".staging-*"))


def test_review_cannot_enable_signature_or_skip_evidence_confirmation(tmp_path: Path) -> None:
    from pydantic import ValidationError

    request, review, _ = prepare(tmp_path)
    data = json.loads(review.read_text())
    data["decisions"][0]["evidence_support_confirmed"] = False
    review.write_text(json.dumps(data))
    with pytest.raises(ValidationError):
        execute(tmp_path, request, review)
    write_review(request, review)
    data = json.loads(review.read_text())
    data["decisions"][0]["requirement_id"] = "sign"
    review.write_text(json.dumps(data))
    with pytest.raises(ValueError, match="Signatures"):
        execute(tmp_path, request, review)


def test_cli_publishes_only_an_incomplete_draft_and_redacts_bad_json(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    from bd_packet_builder.cli import main

    prepare(tmp_path)
    args = [
        "draft",
        "--root",
        str(tmp_path),
        "--request",
        "outputs/request.json",
        "--review",
        "outputs/review.json",
    ]
    assert main(args) == 0
    assert "NOT FOR SUBMISSION" in capsys.readouterr().out
    (tmp_path / "outputs/review.json").write_text('{"PRIVATE invalid')
    assert main(args) == 1
    result = capsys.readouterr()
    assert "Invalid input" in result.err and "PRIVATE" not in result.err


def test_selected_marks_are_visible_and_signing_pixels_are_unchanged(tmp_path: Path) -> None:
    from PIL import Image, ImageChops

    request, review, _ = prepare(tmp_path)
    output = execute(tmp_path, request, review)
    with (
        Image.open(output / "page-1-before.png") as before,
        Image.open(output / "page-1-after.png") as after,
        after.crop((0, 48, before.width, after.height)) as body,
    ):
        # The banner is added above, never over, the original page.
        with (
            before.crop((60, 1100, 1160, 1240)) as a,
            body.crop((60, 1100, 1160, 1240)) as b,
            ImageChops.difference(a, b) as diff,
        ):
            assert diff.getbbox() is None
        for bottom in (605, 575):
            bounds = (90, 2 * (792 - bottom - 10), 110, 2 * (792 - bottom))
            with (
                before.crop(bounds) as a,
                body.crop(bounds) as b,
                ImageChops.difference(a, b) as diff,
            ):
                assert diff.getbbox() is not None


def test_attachment_order_drives_actual_final_page_references(tmp_path: Path) -> None:
    request, review, data = prepare(tmp_path)
    path = Path("bd_agreements/supporting_data/SIPC_list/attachment.pdf")
    make_pdf(tmp_path / path, [(40, 740, "SECOND ATTACHMENT FIRST IN PACKET")])
    source = next(s for s in build_inventory(tmp_path).sources if s.path == path.as_posix())
    data["sources"].append(dict(path=source.path, sha256=source.sha256))
    data["attachments"].insert(0, source.source_id)
    request.write_text(json.dumps(data))
    write_review(request, review)
    output = execute(tmp_path, request, review)
    with pdfium.PdfDocument(str(output / "draft-packet.pdf")) as document:
        assert len(document) == 3
        strings = []
        for index in range(3):
            with closing(document[index]) as page, closing(page.get_textpage()) as text:
                strings.append(text.get_text_bounded())
    assert "packet page 3" in strings[0]
    assert "SECOND ATTACHMENT FIRST IN PACKET" in strings[1]
    assert "CRD: 001234" in strings[2]


@pytest.mark.parametrize("problem", ["unknown-folder", "traversal", "output-symlink"])
def test_draft_enforces_local_input_and_output_boundaries(tmp_path: Path, problem: str) -> None:
    request, review, data = prepare(tmp_path)
    if problem == "output-symlink":
        (tmp_path / "outputs").rename(tmp_path / "stored")
        (tmp_path / "outputs").symlink_to(tmp_path / "stored", target_is_directory=True)
    else:
        data["sources"][0]["path"] = (
            "bd_agreements/supporting_data/Restricted/private.pdf"
            if problem == "unknown-folder"
            else "../private.pdf"
        )
        request.write_text(json.dumps(data))
        write_review(request, review)
    with pytest.raises(ValueError):
        execute(tmp_path, request, review)
    assert not list((tmp_path / "outputs").glob("draft-*"))


def test_rotated_evidence_attachment_is_preserved_without_becoming_a_blank_mapping(
    tmp_path: Path,
) -> None:
    from io import BytesIO

    from PIL import ImageChops
    from pypdf import PdfReader, PdfWriter

    request, review, data = prepare(tmp_path)
    path = tmp_path / data["sources"][0]["path"]
    reader = PdfReader(path)
    reader.pages[0].rotate(90)
    with closing(PdfWriter()) as writer:
        writer.add_page(reader.pages[0])
        stream = BytesIO()
        writer.write(stream)
    path.write_bytes(stream.getvalue())
    original = path.read_bytes()
    source = build_inventory(tmp_path).sources[0]
    data["sources"][0]["sha256"] = source.sha256
    data["attachments"] = [source.source_id]
    for proposal in data["proposals"]["proposals"]:
        for citation in proposal.get("citations", []):
            citation["source_id"] = source.source_id
    request.write_text(json.dumps(data))
    write_review(request, review)
    output = execute(tmp_path, request, review)
    with (
        pdfium.PdfDocument(original) as source_pdf,
        pdfium.PdfDocument(str(output / "draft-packet.pdf")) as packet,
        closing(source_pdf[0]) as before,
        closing(packet[1]) as after,
        closing(before.render(scale=1)) as a,
        closing(after.render(scale=1)) as b,
        a.to_pil() as first,
        b.to_pil() as second,
        ImageChops.difference(first, second) as difference,
    ):
        assert after.get_rotation() == 90
        assert difference.getbbox() is None
    assert path.read_bytes() == original


def test_single_selection_marks_only_the_selected_radio(tmp_path: Path) -> None:
    from PIL import Image, ImageChops

    request, review, _ = prepare(tmp_path, single=True)
    output = execute(tmp_path, request, review)
    with (
        Image.open(output / "page-1-before.png") as before,
        Image.open(output / "page-1-after.png") as after,
        after.crop((0, 48, before.width, after.height)) as body,
    ):
        for bottom, selected in ((605, True), (575, False)):
            bounds = (90, 2 * (792 - bottom - 10), 110, 2 * (792 - bottom))
            with (
                before.crop(bounds) as first,
                body.crop(bounds) as second,
                ImageChops.difference(first, second) as difference,
            ):
                assert (difference.getbbox() is not None) == selected
